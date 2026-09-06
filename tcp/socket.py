from __future__ import annotations
from typing import Dict, final, TYPE_CHECKING

from struct import pack,unpack
from socket import AF_INET, SOCK_CLOEXEC, SOCK_DGRAM, send_fds, socket, _Address, inet_aton, timeout
from queue import Queue
from threading import  Thread
from random import randint
from time import time,sleep

from tcp import syn_manager

from .address import Address, Host
from .ip import IpPseudoHeader
from .segment import Segment
from .pending import PendingConnection
from .state import TCPState
from .retransmit import RetransmitTracker, RetransmitWorker
from .recv_buffer import ReceiveBuffer
from .syn_manager import SynManager, SynWorker


MAX_SYN_RETRIES = 3
RTO_SECONDS = 1.0

class TCPSocket:
    _socket: socket
    _state: TCPState

    _remote_address: Address

    _tracker: RetransmitTracker
    _recv_buffer: ReceiveBuffer

    _established_connections: dict[Address, TCPSocket]
    _syn_manager: SynManager

    seq: int
    mss: int


    def __init__(self) -> None:
        self._socket = socket(AF_INET,SOCK_DGRAM)
        self._state = TCPState.CLOSED

        self._tracker = RetransmitTracker()
        self._recv_buffer = ReceiveBuffer()
        self._established_connections = {}

        self.seq = randint(0,0xFFFFFFFF)
        self.mss = 3

    @classmethod
    def _from_socket(cls,socket: socket,remote_address: Address) -> TCPSocket:
        instance = cls.__new__(cls)
        instance._socket = socket
        instance._state = TCPState.ESTABLISHED

        instance._remote_address = remote_address

        instance._tracker = RetransmitTracker()
        instance._recv_buffer = ReceiveBuffer()
        instance._established_connections = {}

        instance.seq = randint(0, 0xFFFFFFFF)
        instance.mss = 3

        return instance

    @property
    def local_address(self) -> Address:
        address = self._socket.getsockname()
        return Address(address[0],address[1])

    @property 
    def ack(self) -> int:
        return self._recv_buffer.ack

    def __del__(self):
        self.close()

    def bind(self,address: tuple[str,int]) -> None:
        self._remote_address = Address.from_tuple(address)
        self._socket.bind(address)

    def listen(self) -> None:
        self._syn_manager = SynManager()
        self._accept_queue: Queue[tuple[Address, TCPSocket]] = Queue()
        self._state = TCPState.LISTEN
        Thread(target=self._dispatcher,daemon=True).start()
        RetransmitWorker.start(self._established_connections)
        SynWorker.start(self._socket,self._syn_manager)

    def close(self):
        if self._state == TCPState.CLOSED: return

        self._state = TCPState.CLOSED
        # implementar função de fechar conexão caso ela esteja ativa
        try:
            self._socket.close()
        except OSError:
            pass

    def accept(self) -> tuple[Address,TCPSocket]:
        if not self._state == TCPState.LISTEN:
            raise RuntimeError("Tentativa de aceitar cliente em socket inadequada")
        return self._accept_queue.get()

    def recv(self,buffer_size: int) -> bytes:
        return self._recv_buffer.read(buffer_size);

    def retransmit(self,seq: int):
        retransmit = self._tracker.get(seq)
        if retransmit:
            self._socket.sendto(retransmit[0].to_bytes() + retransmit[1],self._remote_address.to_tuple())

    def _dispatcher(self) -> None:
        try:
            while self._state != TCPState.CLOSED:
                data, raw_address = self._socket.recvfrom(65535)
                segment,payload = Segment.from_bytes(data)
                address = Address(raw_address[0],raw_address[1])

                pseudo = IpPseudoHeader(int(address.host),int(self.local_address.host),len(data) + len(payload))
                if not segment.is_checksum_valid(pseudo, payload):
                    continue

                if address in self._established_connections:
                    self._handle_established(address,segment,payload)
                elif segment.syn and address not in self._syn_queue:
                    self._handle_syn(segment,address)
                elif segment.ack and address in self._syn_queue:
                    self._handle_handshake_ack(segment,address)
        except OSError:
            pass

    def _handle_established(self,address: Address,segment:Segment,payload: bytes) -> None:
        connection = self._established_connections[address]

        if(segment.ack):
            if(segment.syn): connection._send_ack(connection.seq,connection.ack,address)
            confirmed_seqs = [
                seq for seq, item in connection._unacked_segments.items()
                if (seq + len(item[1]) + (int(item[0].segment.syn) + int(item[0].segment.fin))) % 0x100000000 <= segment.ack_seq
            ]
            for seq in confirmed_seqs:
                del connection._unacked_segments[seq]

        if not payload:
            return

        seq = segment.seq
        payload_len = len(payload)

        if (seq + payload_len) <= connection.ack:
            connection._send_ack(connection.seq,connection.ack,address)
            return

        if seq > connection.ack:
            connection._out_of_order[seq] = payload
            connection._send_ack(connection.seq,connection.ack,address)
            return

        if seq == connection.ack:
            connection._recv_buffer.put(payload)
            connection.ack = (connection.ack + payload_len) % 0x100000000

            while connection.ack in connection._out_of_order:
                next_payload = connection._out_of_order.pop(connection.ack)
                connection._recv_buffer.put(next_payload)
                connection.ack = (connection.ack + len(next_payload)) % 0x100000000

            if hasattr(connection, '_fin_seq') and connection.ack == connection._fin_seq:
                connection.ack = (connection.ack + 1) % 0x100000000
                connection._recv_buffer.put(b'')
                delattr(connection, 'fin_seq')

            connection._send_ack(connection.seq,connection.ack,address)

    def _handle_syn(self,segment: Segment,address: Address)-> None:
        syn_ack = Segment(
            self.local_address.port,
            address.port,
            randint(0, 0xFFFFFFFF),
            (segment.seq + 1) % 0x100000000,
            syn=True,ack=True
        )
        ip_header = IpPseudoHeader(
            int(self.local_address.host),
            int(address.host),
            len(syn_ack)
        )
        syn_ack.update_checksum(ip_header)

        self._socket.sendto(syn_ack.to_bytes(),address.to_tuple())
        self._syn_queue[address] = PendingConnection(syn_ack,time())

    def _handle_handshake_ack(self,segment: Segment,address: Address) -> None:
        pending = self._syn_queue[address]

        expected_ack = (pending.segment.seq + 1) % 0x100000000
        if expected_ack != segment.ack_seq:
            return

        del self._syn_queue[address]

        client_socket = TCPSocket._from_socket(self._socket,address)
        client_socket.ack = segment.seq
        client_socket._out_of_order = {}

        client_socket.seq = segment.ack_seq
        client_socket._remote_address = address
        self._established_connections[address] = client_socket
        self._accept_queue.put((address,client_socket))

    def _send_ack(self,seq_num: int,ack_num: int,dest_address: Address):
        segment = Segment(
            self.local_address.port,
            dest_address.port,
            seq_num,
            ack_num,
            ack=True
        )
        ip_header = IpPseudoHeader(int(self.local_address.host),int(dest_address.host),len(segment))
        segment.update_checksum(ip_header)

        self._socket.sendto(segment.to_bytes(),(str(dest_address.host),dest_address.port))

    def connect(self,address: Address):
        if hasattr(self, '_is_passive'): return

        self._socket.connect(address.to_tuple())
        self.seq = randint(0, 0xFFFFFFFF)

        syn_segment = Segment(self.local_address.port,address.port,self.seq,0,syn=True)
        ip_header = IpPseudoHeader(int(self.local_address.host),int(address.host),len(syn_segment))
        syn_segment.update_checksum(ip_header)

        _timeout = 1
        _max_retries = 5

        try:
            for retry in range(_max_retries):
                self._socket.settimeout(_timeout)
                self._socket.sendto(syn_segment.to_bytes(),address.to_tuple())

                try:
                    while True:
                        data, _ = self._socket.recvfrom(65535)
                        segment, payload = Segment.from_bytes(data)

                        pseudo = IpPseudoHeader(int(address.host),int(self.local_address.host),len(data))
                        if not segment.is_checksum_valid(pseudo,payload):
                            continue
 
                        if segment.syn and segment.ack and segment.ack_seq == (self.seq + 1) % 0x100000000:
                            self.ack = (segment.seq + 1) % 0x100000000
                            self.seq = segment.ack_seq

                            self._remote_address = address

                            self._send_ack(self.seq,self.ack,address)
                            self._established_connections[address] = self
                            Thread(target=self._dispatcher, daemon=True).start()
                            Thread(target=self._retransmit_worker,daemon=True).start()
                            return
                except timeout:
                    _timeout *= 2
                    continue

            raise TimeoutError(f"Conexão para {address} expirou")
        finally:
            self._socket.settimeout(None)

    def send(self, payload: bytes) -> int:
        if not payload: return 0

        bytes_sent = 0
        total_len = len(payload)

        while bytes_sent < total_len:
            chunk = payload[bytes_sent : bytes_sent + self.mss]
            chunk_len = len(chunk)

            segment = Segment(
                    self.local_address.port,
                    self._remote_address.port,
                    self.seq,
                    self.ack,
                    ack=True
            )

            pseudo = IpPseudoHeader(
                int(self.local_address.host),
                int(self._remote_address.host),
                len(segment) + chunk_len
            )
            segment.update_checksum(pseudo,chunk)

            self._tracker.track(segment.seq,segment,chunk)
            self._socket.sendto(segment.to_bytes() + chunk,self._remote_address.to_tuple())

            self.seq = (self.seq + chunk_len) % 0x100000000
            bytes_sent += chunk_len

        return bytes_sent


