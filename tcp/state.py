from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from enum import Enum, auto

class TCPState(Enum):
    CLOSED = auto()
    LISTEN = auto()
    SYN_SENT = auto()
    SYN_RECEIVED = auto()
    ESTABLISHED = auto()
    FIN_WAIT_1 = auto()
    FIN_WAIT_2 = auto()
    CLOSE_WAIT = auto()
    LAST_ACK = auto()
    TIME_WAIT = auto()
    CLOSING = auto()
