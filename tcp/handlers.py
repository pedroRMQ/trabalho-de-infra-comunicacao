from __future__ import annotations
from time import pthread_getcpuclockid
from typing import TYPE_CHECKING, Callable
from .state import TCPState

if TYPE_CHECKING:
    from .segment import Segment
    from .socket import TCPSocket
    from .address import Address

def handle_established(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)

    if payload or segment.fin:
        connection._recv_buffer.push(segment, payload)

        if segment.fin:
            connection._state = TCPState.CLOSE_WAIT

        connection._send_ack(connection.seq, connection.ack,address)

def handle_fin_wait_1(connection: TCPSocket, segment: Segment, payload: bytes,address: Address):
    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)
        if connection._tracker.is_empty():
            connection._state = TCPState.FIN_WAIT_2

        if segment.fin or payload:
            if segment.fin:
                if connection._state != TCPState.FIN_WAIT_2:
                    segment.fin = False
                    connection._state = TCPState.CLOSING
                else:
                    connection._state = TCPState.CLOSED

            if payload:
                connection._recv_buffer.push(segment, payload)

            connection._send_ack(connection.seq,connection.ack,address)

def handle_fin_wait_2(connection: TCPSocket, segment: Segment, payload: bytes, address: Address):
    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)

    if payload or segment.fin:
        if segment.fin: connection._state = TCPState.CLOSED
        connection._recv_buffer.push(segment,payload)
        connection._send_ack(connection.seq, connection._recv_buffer.ack, address)

def handle_closing(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)
        if connection._tracker.is_empty():
            connection._state = TCPState.CLOSED

def handle_close_wait(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.fin:
        connection._send_ack(connection.seq,connection.ack,address)
        return

    if payload:
        connection._recv_buffer.push(segment, payload)
        connection._send_ack(connection.seq,connection.ack,address)


def handle_last_ack(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)
        if connection._tracker.is_empty():
            connection._state = TCPState.CLOSED


STATE_HANDLERS: dict[TCPState, Callable[[TCPSocket, Segment, bytes, Address], None]] = {
    TCPState.ESTABLISHED: handle_established,
    TCPState.FIN_WAIT_1: handle_fin_wait_1,
    TCPState.FIN_WAIT_2: handle_fin_wait_2,
    TCPState.CLOSING: handle_closing,
    TCPState.CLOSE_WAIT: handle_close_wait,
    TCPState.LAST_ACK: handle_last_ack,
}

