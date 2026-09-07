from random import randint
from socket import socket
from threading import Lock, Thread

from tcp.ip import IpPseudoHeader
from tcp.socket import TCPSocket

from .segment import Segment
from .address import Address
from time import sleep,time
from .segment import Segment
from errno import EBADF, ENETDOWN, ECONNREFUSED, EHOSTUNREACH
from .constant import RTO_SECONDS, MAX_SYN_RETRIES
from tcp import segment
from .tracked_segment import TrackedSegment

class SynManager:
    _syn_queue: dict[Address, TrackedSegment]
    _lock: Lock

    def __init__(self) -> None:
        self._syn_queue = {}
        self._lock = Lock()

    def add(self,address: Address, segment: Segment) -> None:
        with self._lock:
            self._syn_queue[address] = TrackedSegment(segment)

    def pop(self, address: Address) -> Segment | None:
        with self._lock:
            pending = self._syn_queue.pop(address, None)
            if pending is not None: 
                return pending.segment 
            return None

    def contains(self, address: Address) -> bool:
        with self._lock:
            return address in self._syn_queue

    def get_expired(self,now: float | None = None) -> list[tuple[TrackedSegment, Address]]:
        expired: list[tuple[TrackedSegment, Address]] = []
        now = now if now is not None else time()
        with self._lock:
            for address, tracked in list(self._syn_queue.items()):
                if now - tracked.last_sent >= RTO_SECONDS:
                    # if pending.retries >= MAX_SYN_RETRIES:
                        # del self._syn_queue[address]
                    #else:
                        # pending.retries += 1
                        # pending.last_sent = now
                    expired.append((tracked, address))
        return expired

    @classmethod
    def send_syn_ack(cls,connection: TCPSocket,address: Address,ack: int):
        seq = randint(0,0xFFFFFFFF)
        segment = Segment(connection.local_address.port,address.port,seq,ack,syn=True,ack=True)
        pseudo = IpPseudoHeader(int(connection.local_address.host),int(address.host),len(segment))
        segment.update_checksum(pseudo)

        connection._socket.sendto(segment.to_bytes(),address.to_tuple())
        connection._syn_manager.add(address,segment)

class SynWorker:
    @classmethod
    def start(cls,server: TCPSocket):
        Thread(target=cls._work,args=(server,),daemon=True).start()

    @classmethod
    def _work(cls,server: TCPSocket) -> None:
        while True:
            sleep(0.2)
            now = time()

            expired = server._syn_manager.get_expired(now)
            for tracked, address in expired:
                if tracked.retries >= MAX_SYN_RETRIES:
                    server._syn_manager.pop(address)
                    server._sessions.pop(address)
                    continue
                try:
                    server._socket.sendto(tracked.segment.to_bytes(),address.to_tuple())
                    tracked.retries += 1
                    tracked.last_sent = now
                except OSError as error:
                    if error.errno in (EBADF,ENETDOWN):
                        return
                    if error.errno in (ECONNREFUSED, EHOSTUNREACH):
                        server._syn_manager.pop(address)
                        server._sessions.pop(address)


