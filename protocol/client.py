from __future__ import annotations
from typing import TYPE_CHECKING

from .ip_header import IpPseudoHeader
from .segment import Segment

from state_machine import StateMachine
from states.handshake import HandshakeState
from states.established import EstablishedState

import socket as sock
import struct
import queue
import random

if TYPE_CHECKING:
    from server import Server

class Client:
    server: Server
    address: tuple[str, int]
    state_machine: StateMachine

    is_running: bool

    seq: int
    ack_seq: int
    mss: int = 3

    _queue: queue.Queue

    def __init__(self,server:Server,address:tuple[str,int]) -> None:
        self._queue = queue.Queue()
        self.server = server
        self.address = address

        self.is_running = True

        self.seq = random.randint(0, 0xFFFFFFFF)
        self.ack_seq = 0
        self.mss = 3

        states = {"HandShake": HandshakeState(self),"Established": EstablishedState(self)}
        self.state_machine = StateMachine(states)

    def run(self):
        try:
            while self.is_running:
                self.state_machine.update()
        finally:
            self.server.clients.pop(self.address, None)

    def get_port(self) -> int:
        return self.address[1]
    def get_ip(self) -> int:
        return struct.unpack('!I',sock.inet_aton(self.address[0]))[0]

    def receive_bytes(self,data: bytes) -> None:
        self._queue.put(data)

    def recv(self) -> tuple[Segment,bytes] | tuple[None,None]:
        try:
            data = self._queue.get(timeout=0.1)
        except queue.Empty:
            return None, None

        if len(data) < 20:
            return None, None

        return Segment.from_bytes(data)

    def send(self,message: str) -> None:
        data = message.encode('utf-8')

        for i in range(0, len(data),self.mss):
            chunk = data[i : i + self.mss]
            segment = Segment(self.server.get_port(),self.get_port(),self.seq,self.ack_seq)
            segment.ack = True

            if i + len(chunk) >= len(data):
                segment.psh = True

            ip_header = IpPseudoHeader(self.server.get_ip(),self.get_ip(),len(segment) + len(chunk))
            segment.update_checksum(ip_header,chunk)

            packet = segment.to_bytes() + chunk
            self.server.socket.sendto(packet, self.address)

            self.seq = (self.seq + len(chunk)) % 0x100000000

    def send_flag(self,flags: list[str]):
        segment = Segment(self.server.get_port(),self.get_port(),self.seq,self.ack_seq)
        for i in range(0, len(flags)):
            segment.set_flag(flags[i],True)

        ip_header = IpPseudoHeader(self.server.get_ip(),self.get_ip(),len(segment))
        segment.update_checksum(ip_header)

        self.server.socket.sendto(segment.to_bytes(),self.address)

        self.seq = (self.seq + 1) % 0x100000000


    def is_segment_valid(self,segment: Segment,payload: bytes = b''):
        ip_header = IpPseudoHeader(
            self.get_ip(),
            self.server.get_ip(),
            len(segment) + len(payload)
        )

        return segment.is_checksum_valid(ip_header,payload)

