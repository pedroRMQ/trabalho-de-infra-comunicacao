from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .segment import Segment
    from .socket import TCPSocket
    from .address import Address
    from .state import TCPState
    from .syn_manager import SynManager

def handle_listen(server: TCPSocket,client: TCPSocket,segment: Segment, payload: bytes, address: Address) -> None:
    if segment.rst:
        return

    if segment.syn:
        client = server._from_socket(address)
        client._state = TCPState.SYN_RECEIVED
        client.ack = (segment.seq + 1) % 0x100000000

        syn_ack = client._send_info(syn=True,ack=True,track=False)
        server._syn_manager.add(address,syn_ack)
        server._sessions[address] = client

def handle_syn_received(server: TCPSocket,client: TCPSocket, segment:Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        pending = server._syn_manager.pop(address)
        if not pending:
            server._sessions.pop(address, None)
            return

        client._state = TCPState.ESTABLISHED
        server._accept_queue.put((address, client))

    if segment.rst:
        client._state = TCPState.CLOSED
        server._sessions.pop(address)

def handle_established(server: TCPSocket,client: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if payload or segment.fin:
        client._send_info(ack=True,track=False)
        client._recv_buffer.push(segment,payload)
        if segment.fin:
            client._state = TCPState.CLOSE_WAIT

    if segment.rst:
        client._state = TCPState.CLOSED
        server._sessions.pop(address)


def handle_fin_wait_1(server:TCPSocket,client: TCPSocket, segment: Segment, payload: bytes,address: Address) -> None:
    if segment.ack:
        client._tracker.acknowledge(segment.ack_seq)
        client._state = TCPState.FIN_WAIT_2

    if segment.fin:
        client._send_info(ack=True,track=False)
        client._recv_buffer.push(segment,payload)

        client._state = TCPState.CLOSING
        if segment.ack:
            client._state = TCPState.TIME_WAIT

    if segment.rst:
        server._sessions.pop(address, None)
        client._state = TCPState.CLOSED

def handle_fin_wait_2(server:TCPSocket, client: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.fin:
        client._recv_buffer.push(segment, payload)
        client._send_info(ack=True,track=False)
        client._state = TCPState.TIME_WAIT

    if segment.rst:
        server._sessions.pop(address, None)
        client._state = TCPState.CLOSED

def handle_last_ack(server:TCPSocket,client: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        server._sessions.pop(address,None)
        client._tracker.acknowledge(segment.ack_seq)
        client._state = TCPState.CLOSED

    if segment.rst:
        server._sessions.pop(address,None)
        client._state = TCPState.CLOSED

def handle_closing(server:TCPSocket,client: TCPSocket, segment: Segment, payload:bytes, address: Address) -> None:
    if segment.ack:
        client._tracker.acknowledge(segment.ack_seq)
        client._state = TCPState.TIME_WAIT

    if segment.rst:
        server._sessions.pop(address,None)
        client._state = TCPState.CLOSED

STATE_HANDLERS: dict[TCPState, Callable | None] = {
    TCPState.CLOSED: None,
    TCPState.LISTEN: handle_listen,
    TCPState.SYN_RECEIVED: handle_syn_received,
    TCPState.SYN_SENT: None,
    TCPState.ESTABLISHED: handle_established,
    TCPState.FIN_WAIT_1: handle_fin_wait_1,
    TCPState.FIN_WAIT_2: handle_fin_wait_2,
    TCPState.CLOSING: handle_closing,
    TCPState.LAST_ACK: handle_last_ack,
    TCPState.CLOSE_WAIT: None,
    TCPState.TIME_WAIT: None,
}




def handle_close_wait(server:TCPSocket,client: TCPSocket, segment: Segment, payload: bytes, address: Address) -> None:
    if segment.ack:
        server._tracker.acknowledge(segment.ack_seq)

    if segment.rst:
        server._sessions.pop(address, None)
        client._state = TCPState.CLOSED


def handle_time_wait(server:TCPSocket,client: TCPSocket, segment: Segment, payload:bytes, address: Address) -> None:
    if segment.fin:
        client._send_info(ack=True)

    if segment.rst:
        server._sessions.pop(address,None)
        client._state = TCPState.CLOSED


