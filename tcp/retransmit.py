from __future__ import annotations
from typing import TYPE_CHECKING

from .address import Address

from .segment import Segment
from threading import Lock, Thread
from time import sleep,time
from errno import EBADF, ENETDOWN
from .constant import MAX_RETRIES, RTO_SECONDS
from .tracked_segment import TrackedSegment

if TYPE_CHECKING:
    from .socket import TCPSocket

class RetransmitTracker:
    _unacked: dict[int, tuple[TrackedSegment, bytes]]
    _lock: Lock

    def __init__(self) -> None:
        self._unacked = {}
        self._lock = Lock()

    def track(self, segment: Segment,chunk: bytes = b'') -> None:
        with self._lock:
            self._unacked[segment.seq] = (TrackedSegment(segment), chunk)

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

    def get_expired(self,now: float) -> list[tuple[TrackedSegment, bytes]]:
        with self._lock:
            expired: list[tuple[TrackedSegment, bytes]] = []
            for seq, (tracked, chunk) in list(self._unacked.items()):
                if now - tracked.last_sent >= RTO_SECONDS:
                    expired.append((tracked, chunk))
            return expired

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._unacked) == 0

class RetransmitWorker:
    @classmethod
    def start(cls,server: TCPSocket):
        Thread(target=cls._work,args=(server,),daemon=True).start()

    @classmethod
    def _work(cls,server: TCPSocket):
        while True:
            sleep(0.1)
            now = time()

            for session in list (server._sessions.values()):
                expired_items = session._tracker.get_expired(now)

                for tracked, chunk in expired_items:
                    if tracked.retries >= MAX_RETRIES:
                        session._close_abrupt()
                        break
                    try:
                        session._socket.sendto(tracked.segment.to_bytes() + chunk,session._remote_address.to_tuple())
                        tracked.retries += 1
                        tracked.last_sent = now
                    except OSError as error:
                        if error.errno in (EBADF,ENETDOWN):
                            return

