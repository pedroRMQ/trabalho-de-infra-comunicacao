from ast import Add
from socket import socket
from threading import Lock, Thread

from .segment import Segment

from .address import Address
from .pending import PendingConnection
from time import sleep,time
from .segment import Segment
from errno import EBADF, ENETDOWN, ECONNREFUSED, EHOSTUNREACH

RTO_SECONDS = 1.0
MAX_RETRIES = 3

class SynManager:
    _syn_queue: dict[Address, PendingConnection]
    _lock: Lock

    def __init__(self) -> None:
        self._syn_queue = {}
        self._lock = Lock()

    def add(self,address: Address, pending: PendingConnection) -> None:
        with self._lock:
            self._syn_queue[address] = pending

    def pop(self, address: Address) -> PendingConnection | None:
        with self._lock:
            return self._syn_queue.pop(address, None)

    def contains(self, address: Address) -> bool:
        with self._lock:
            return address in self._syn_queue

    def process_expired(self, now: float) -> list[tuple[Segment, Address]]:
        expired: list[tuple[Segment, Address]] = []
        with self._lock:
            for address, pending in list(self._syn_queue.items()):
                if now - pending.last_sent >= RTO_SECONDS:
                    if pending.retries >= MAX_RETRIES:
                        del self._syn_queue[address]
                    else:
                        pending.retries += 1
                        pending.last_sent = now
                        expired.append((pending.segment, address))
        return expired

class SynWorker:
    @classmethod
    def start(cls,socket: socket,syn_manager: SynManager):
        Thread(target=cls._work,args=(socket,syn_manager),daemon=True).start()

    @classmethod
    def _work(cls,socket: socket,syn_manager: SynManager) -> None:
        while True:
            sleep(0.2)
            now = time()

            if socket.fileno() == -1:
                return

            expired = syn_manager.process_expired(now)
            for segment, address in expired:
                try:
                    socket.sendto(segment.to_bytes(),address.to_tuple())
                except OSError as error:
                    if error.errno in (EBADF,ENETDOWN):
                        return
                    if error.errno in (ECONNREFUSED, EHOSTUNREACH):
                        syn_manager.pop(address)


