from __future__ import annotations
from typing import TYPE_CHECKING

from .base import IState
from protocol.ip_header import IpPseudoHeader
from protocol.segment import Segment

import time

if TYPE_CHECKING:
    from protocol.client import Client
    from state_machine import StateMachine

class HandshakeState(IState):
    _client: Client
    _state_machine: StateMachine
    _max_retries: int = 5

    def __init__(self,client:Client) -> None:
        self._client = client
        self._state_machine = client.state_machine 

    def enter(self, args: list | None = None) -> None:
        pass

    def exit(self) -> None:
        pass

    def update(self) -> None:
        syn_ack_sent = False
        last_send_time = 0.0
        retries = 0
        rto = 1.0
        while True:
            segment, payload = self._client.recv()

            if not syn_ack_sent:
                if not segment:
                    continue

                if not segment.syn or segment.ack or not self._client.is_segment_valid(segment):
                    self._client.send_flag(['rst'])
                    return

                self._client.ack_seq = (segment.seq + 1) % 0x100000000
                self._send_syn_ack()
                syn_ack_sent = True
                last_send_time = time.time()
                continue

            if segment and self._client.is_segment_valid(segment):
                if segment.ack:
                    self._client.state_machine.change("Established",[tuple[segment,payload]])
                    return
                elif segment.syn:
                    self._send_syn_ack()
                    last_send_time = time.time()
                    continue

            now = time.time()
            if now - last_send_time >= rto:
                if retries >= self._max_retries:
                    print(f'limite de retries para o cliente {self._client.address} atingido')
                    self._client.send_flag(['rst'])
                    self._client.is_running = False
                    return

                self._send_syn_ack()
                retries += 1
                rto *= 2.0
                last_send_time = now

    def _send_syn_ack(self):
        syn_ack = Segment(
                self._client.server.get_port(),
                self._client.get_port(),
                self._client.seq,
                self._client.ack_seq)

        syn_ack.syn = True
        syn_ack.ack = True

        ip_header = IpPseudoHeader(
                    self._client.server.get_ip(),
                    self._client.get_ip(),
                    len(syn_ack)
        )
        syn_ack.update_checksum(ip_header)

        self._client.server.socket.sendto(syn_ack.to_bytes(),self._client.address)

        self._client.seq = (self._client.seq + 1) % 0x100000000


