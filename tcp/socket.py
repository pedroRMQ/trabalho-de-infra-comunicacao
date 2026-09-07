from __future__ import annotations
from ast import Add
from typing import Dict, final, TYPE_CHECKING

from struct import pack,unpack
from socket import AF_INET, SOCK_CLOEXEC, SOCK_DGRAM, send_fds, socket, _Address, inet_aton, timeout
from queue import Queue
from threading import  Thread
from random import randint
from time import time,sleep

from .syn_manager import SynManager
from .address import Address
from .ip import IpPseudoHeader
from .segment import Segment
from .state import TCPState
from .retransmit import RetransmitTracker, RetransmitWorker
from .recv_buffer import ReceiveBuffer, ReceiveWorker
from .syn_manager import SynManager, SynWorker
from .constant import MAX_RETRIES,MAX_SYN_RETRIES,RTO_SECONDS

class TCPSocket:
    _socket: socket
    _state: TCPState

    _remote_address: Address

    _tracker: RetransmitTracker
    _recv_buffer: ReceiveBuffer
    _syn_manager: SynManager

    _sessions: dict[Address, TCPSocket]

    seq: int
    mss: int

    def __init__(self) -> None:
        self._socket = socket(AF_INET,SOCK_DGRAM)
        self._state = TCPState.CLOSED

        self._sessions = {}

        self._tracker = RetransmitTracker()
        self._recv_buffer = ReceiveBuffer()

        self.seq = randint(0,0xFFFFFFFF)
        self.mss = 3

    def _from_socket(self,address: Address) -> TCPSocket:
        instance = TCPSocket.__new__(TCPSocket)
        instance._socket = self._socket
        instance._state = TCPState.CLOSED

        instance._remote_address = address
        instance._tracker = RetransmitTracker()
        instance._recv_buffer = ReceiveBuffer()

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

    @ack.setter
    def ack(self, value: int) -> None:
        self._recv_buffer.ack = value

    def __del__(self):
        self.close()

    def bind(self,address: tuple[str,int]) -> None:
        self._remote_address = Address.from_tuple(address)
        self._socket.bind(address)

    def listen(self) -> None:
        self._syn_manager = SynManager()
        self._accept_queue: Queue[tuple[Address, TCPSocket]] = Queue()
        self._state = TCPState.LISTEN
        ReceiveWorker.start(self)
        RetransmitWorker.start(self._sessions)
        SynWorker.start(self._socket,self._syn_manager)

    def accept(self) -> tuple[Address,TCPSocket]:
        if not self._state == TCPState.LISTEN:
            raise RuntimeError("Tentativa de aceitar cliente em socket inadequada")

        while True:
            address, socket = self._accept_queue.get()
            if socket._state != TCPState.CLOSED:
                return address, socket

    def recv(self,buffer_size: int) -> bytes:
        return self._recv_buffer.read(buffer_size);

    def retransmit(self,seq: int):
        retransmit = self._tracker.get(seq)
        if retransmit:
            self._socket.sendto(retransmit[0].to_bytes() + retransmit[1],self._remote_address.to_tuple())

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

        self._socket.sendto(segment.to_bytes(),dest_address.to_tuple())

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

            self._tracker.track(segment,chunk)
            self._socket.sendto(segment.to_bytes() + chunk,self._remote_address.to_tuple())

            self.seq = (self.seq + chunk_len) % 0x100000000
            bytes_sent += chunk_len

        return bytes_sent

    def connect(self,address: Address):
        if self._state != TCPState.CLOSED:
            raise RuntimeError("Socket indisponivel")

        self._state = TCPState.SYN_SENT

        segment = Segment(self.local_address.port,address.port,self.seq,0,syn=True)
        pseudo = IpPseudoHeader(int(self.local_address.host),int(address.host),len(segment))
        segment.update_checksum(pseudo)
        rto = RTO_SECONDS

        for retry in range(MAX_SYN_RETRIES):
            self._socket.sendto(segment.to_bytes(),address.to_tuple())
            self._socket.settimeout(rto)

            try:
                while True:
                    data, _ = self._socket.recvfrom(65535)
                    recv_segment, payload = Segment.from_bytes(data)

                    recv_pseudo = IpPseudoHeader(int(address.host),int(self.local_address.host),len(data))
                    if not recv_segment.is_checksum_valid(recv_pseudo,payload):
                        continue

                    if recv_segment.rst:
                        self._state = TCPState.CLOSED
                        raise ConnectionRefusedError(f"Conexão recusada por {address}")
 
                    if recv_segment.syn and recv_segment.ack and recv_segment.ack_seq == (self.seq + 1) % 0x100000000:
                        self.ack = (recv_segment.seq + 1) % 0x100000000
                        self.seq = recv_segment.ack_seq

                        self._remote_address = address

                        self._send_ack(self.seq,self.ack,address)
                        self._sessions[address] = self

                        self._state = TCPState.ESTABLISHED
                        ReceiveWorker.start(self)
                        RetransmitWorker.start(self._sessions)
                        return

            except timeout:
                rto *= 2
                continue
            finally:
                self._socket.settimeout(None)

        raise TimeoutError(f'Falha ao conectar em {address}')

    def close(self):
        if self._state == TCPState.CLOSED: return

        if self._state == TCPState.ESTABLISHED:
            self._state = TCPState.FIN_WAIT_1
            self._send_info(fin=True)
            return

        if self._state == TCPState.CLOSE_WAIT:
            self._state = TCPState.LAST_ACK
            self._send_info(fin=True)

        elif self._state == TCPState.LISTEN:
            self._state = TCPState.CLOSED
            for connection in list(self._sessions.values()):
                connection.close()

            try:
                self._socket.close()
            except OSError:
                pass

    def _send_info(self,address: Address | None = None,urg:bool = False,ack:bool = False,psh:bool = False,rst:bool = False,syn:bool = False,fin:bool = False,track:bool = True) -> Segment:
        address = address if address is not None else self._remote_address
        segment = Segment(self.local_address.port,address.port,self.seq,self.ack,urg,ack,psh,rst,syn,fin)
        pseudo = IpPseudoHeader(int(self.local_address.host),int(address.host),len(segment))
        segment.update_checksum(pseudo)
        if track and (syn or fin): self._tracker.track(segment)
        self._socket.sendto(segment.to_bytes(), address.to_tuple())
        self.seq = (self.seq + int(segment.syn) + int(segment.fin)) % 0x100000000
        return segment

    def _close_abrupt(self):
        self._send_info(rst=True,track=False)
        self._state = TCPState.CLOSED
        self._sessions.pop(self._remote_address, None)
