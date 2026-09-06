from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segment import Segment

class PendingConnection:
    segment: Segment
    last_sent: float
    retries: int 

    def __init__(self,segment: Segment, last_sent: float):
        self.segment = segment
        self.last_sent = last_sent
        self.retries = 0
