from __future__ import annotations
from typing import TYPE_CHECKING

from tcp.address import Address
from tcp.socket import MAX_SYN_RETRIES, RTO_SECONDS, TCPSocket

from .segment import Segment
from threading import Lock, Thread
from time import sleep,time
from errno import EBADF, ENETDOWN

if TYPE_CHECKING:
    from .socket import TCPSocket

MAX_RETRIES = 5

class TrackedSegment:
    segment: Segment
    last_sent: float
    retries: int

    def __init__(self,segment: Segment,last_sent:float) -> None:
        self.segment = segment
        self.last_sent = last_sent
        self.retries = 0

class RetransmitTracker:
    _unacked: dict[int, tuple[TrackedSegment, bytes]]
    _lock: Lock

    def __init__(self) -> None:
        self._unacked = {}
        self._lock = Lock()

    def track(self,seq: int, segment: Segment, chunk: bytes) -> None:
        with self._lock:
            self._unacked[seq] = (TrackedSegment(segment,time()), chunk)

    def get(self,seq: int) -> tuple[Segment, bytes] | None:
        with self._lock:
            if seq in self._unacked:
                data = self._unacked[seq]
                return data[0].segment, data[1]
            return None

    def acknowledge(self, ack_seq: int) -> None:
        with self._lock:
            confirmed_seqs = [
                seq for seq, item in self._unacked.items()
                if (seq + len(item[1]) + int(item[0].segment.syn) + int(item[0].segment.fin)) % 0x100000000 <= ack_seq
            ]

            for seq in confirmed_seqs:
                del self._unacked[seq]

    def get_expired(self,now: float,rto: float) -> list[tuple[TrackedSegment, bytes]]:
        with self._lock:
            expired: list[tuple[TrackedSegment, bytes]] = []
            for seq, (tracked, chunk) in list(self._unacked.items()):
                if now - tracked.last_sent >= rto:
                    expired.append((tracked, chunk))
            return expired

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._unacked) == 0

class RetransmitWorker:
    @classmethod
    def start(cls,connections: dict[Address, TCPSocket]):
        Thread(target=cls._work,args=(connections,),daemon=True).start()

    @classmethod
    def _work(cls,connections: dict[Address, TCPSocket]):
        while True:
            sleep(0.1)
            now = time()

            for connection in list (connections.values()):
                expired_items = connection._tracker.get_expired(now,RTO_SECONDS)

                for tracked, chunk in expired_items:
                    if tracked.retries >= MAX_RETRIES:
                        connection.close()
                        break

                    tracked.retries += 1
                    tracked.last_sent = now
                    try:
                        connection.retransmit(tracked.segment.seq)
                    except OSError as error:
                        if error.errno in (EBADF,ENETDOWN):
                            return

