from __future__ import annotations
from os import sched_getparam
from threading import Thread
from typing import TYPE_CHECKING

from queue import Queue

if TYPE_CHECKING:
    from .socket import TCPSocket
    from .address import Address

if TYPE_CHECKING:
    from .segment import Segment

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
    def start(cls,connections: dict[Address, TCPSocket]) -> None:
        Thread(target=cls._work,args=(connections,),daemon=True).start()

    @classmethod
    def _work(cls,connections: dict[Address, TCPSocket]) -> None:
        pass


