from __future__ import annotations
from ast import Add
from enum import CONTINUOUS
import re
from time import pthread_getcpuclockid
from typing import TYPE_CHECKING, Callable

from tcp import segment
from tcp.syn_manager import SynManager
from .state import TCPState

if TYPE_CHECKING:
    from .segment import Segment
    from .socket import TCPSocket
    from .address import Address

def handle_listen(server: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.rst:
        return

    if segment.syn:
        SynManager.send_syn_ack(server,address,(segment.seq + 1)% 0x100000000)
        return

    if segment.ack and server._syn_manager.validate_ack(address, segment.ack_seq):
            pending = server._syn_manager.pop(address)
            if not pending:
                return

            client_socket = server._from_socket(address)
            client_socket.seq = (pending.seq + 1) % 0x100000000
            client_socket.ack = segment.seq
            server._established_connections[address] = client_socket
            server._accept_queue.put((address,client_socket))

def handle_established(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address,None)
        return

    if segment.ack:
        connection._tracker.acknowledge(segment.ack)

    pushed = connection._recv_buffer.push(segment,payload)

    if pushed and (payload or segment.fin):
        connection._send_info(address,ack=True)

    if segment.fin:
        connection._state = TCPState.CLOSE_WAIT

def handle_fin_wait_1(connection: TCPSocket, segment: Segment, payload: bytes,address: Address):
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address, None)
        return

    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)
        connection._state = TCPState.FIN_WAIT_2

    if segment.fin:
        connection._recv_buffer.push(segment,payload)
        connection._send_info(ack=True)

        if connection._state == TCPState.FIN_WAIT_2:
            connection._state = TCPState.TIME_WAIT
        else:
            connection._state = TCPState.CLOSING


def handle_fin_wait_2(connection: TCPSocket, segment: Segment, payload: bytes, address: Address):
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address, None)
        return

    if segment.fin:
        connection._recv_buffer.push(segment, payload)
        connection._send_info(ack=True)
        connection._state = TCPState.TIME_WAIT

def handle_close_wait(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address, None)
        return

    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)

def handle_last_ack(connection: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address,None)

    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)

        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address,None)

def handle_time_wait(connection: TCPSocket, segment: Segment, payload:bytes, address: Address) -> None:
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address,None)
        return

    if segment.fin:
        connection._send_info(ack=True)

def handle_closing(connection: TCPSocket, segment: Segment, payload:bytes, address: Address) -> None:
    if segment.rst:
        connection._state = TCPState.CLOSED
        connection._established_connections.pop(address,None)

    if segment.ack:
        connection._tracker.acknowledge(segment.ack_seq)
        connection._state = TCPState.TIME_WAIT

STATE_HANDLERS: dict[TCPState, Callable | None] = {
    TCPState.CLOSED: None,
    TCPState.LISTEN: handle_listen,
    TCPState.SYN_SENT: None,      
    TCPState.ESTABLISHED: handle_established,
    TCPState.FIN_WAIT_1: handle_fin_wait_1,
    TCPState.FIN_WAIT_2: handle_fin_wait_2,
    TCPState.CLOSE_WAIT: handle_close_wait,
    TCPState.CLOSING: handle_closing,
    TCPState.LAST_ACK: handle_last_ack,
    TCPState.TIME_WAIT: handle_time_wait,
}

