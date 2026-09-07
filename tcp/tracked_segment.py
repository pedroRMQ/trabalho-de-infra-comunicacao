from __future__ import annotations
from typing import TYPE_CHECKING
from time import time

if TYPE_CHECKING:
    from .segment import Segment

class TrackedSegment(Segment):
    segment: Segment
    last_sent: float
    retries: int

    def __init__(self,segment: Segment,last_sent:float | None = None,retries: int = 0) -> None:
        self.segment = segment
        self.last_sent = last_sent if last_sent is not None else time()
        self.retries = retries


