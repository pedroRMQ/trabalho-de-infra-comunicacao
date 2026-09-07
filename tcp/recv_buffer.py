from __future__ import annotations
from os import sched_getparam
from threading import Thread
from typing import TYPE_CHECKING

from queue import Queue

from tcp import address, segment
from tcp.ip import IpPseudoHeader
from tcp.state import TCPState

from .handlers import STATE_HANDLERS

if TYPE_CHECKING:
    from .segment import Segment
    from .address import Address
    from .socket import TCPSocket

class ReceiveBuffer:
    ack: int
    _out_of_order: dict[int,tuple[bytes, bool]]
    _read_queue: Queue[bytes]
    _bytes_buffer: bytes

    def __init__(self,ack: int = 0) -> None:
        self.ack = ack
        self._out_of_order = {}
        self._read_queue = Queue()
        self._bytes_buffer = b''

    def push(self, segment: Segment,payload: bytes = b'') -> bool:
        if segment.seq > self.ack:
            if payload or segment.fin: self._out_of_order[segment.seq] = payload, segment.fin
            return False

        if segment.seq == self.ack:
            if payload or segment.fin:
                self._read_queue.put(payload)
                if segment.fin : self._read_queue.put(b'')
                self.ack = (self.ack + len(payload) + segment.fin) % 0x100000000

            while self.ack in self._out_of_order:
                chunk, is_fin = self._out_of_order.pop(self.ack)
                if chunk: self._read_queue.put(chunk)
                if is_fin: self._read_queue.put(b'')
                self.ack = (self.ack + len(chunk) + int(is_fin)) % 0x100000000
            return True
        return False

    def read(self, size:int) -> bytes:
        while len(self._bytes_buffer) == 0:
            chunk = self._read_queue.get()
            if chunk == b'':
                return b''
            self._bytes_buffer += chunk

        data = self._bytes_buffer[:size]
        self._bytes_buffer = self._bytes_buffer[size:]
        return data

class ReceiveWorker:
    @classmethod
    def start(cls,server: TCPSocket) -> None:
        Thread(target=cls._work,args=(server,),daemon=True).start()

    @classmethod
    def _work(cls,server: TCPSocket) -> None:
        while server._state != TCPState.CLOSED:
            try:
                data, raw_address = server._socket.recvfrom(65535)
            except OSError:
                return

            segment, payload = Segment.from_bytes(data)
            address = Address.from_tuple(raw_address)

            pseudo = IpPseudoHeader(int(address.host),int(server.local_address.host),len(segment) + len(payload))
            if not segment.is_checksum_valid(pseudo,payload):
                continue

            sessions = server._sessions.get(address, server)

            handler = STATE_HANDLERS.get(sessions._state)

            if handler:
                handler(sessions,segment,payload, address)
