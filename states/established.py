from base import IState,EmptyState
from protocol import Client
from protocol import segment
from protocol.segment import Segment
from state_machine import StateMachine

class EstablishedState(IState):
    _state_machine: StateMachine
    _client: Client

    _buffer: bytearray

    def __init__(self,client: Client) -> None:
        self._client = client
        self._state_machine = client.state_machine
        self._buffer = bytearray()

    def enter(self, args: list | None = None) -> None:
        segment, payload = args[0] if args and args[0] else tuple[None, None]

        if segment and payload:
            self._process_data(segment,payload)
            self._client.send_flag(['ack'])

    def exit(self):
        pass

    def update(self):
        segment, payload = self._client.recv()

        if not segment:
            return

        payload = payload or b''

        if not self._client.is_segment_valid(segment,payload):
            return

        if segment.rst:
            self._client.is_running = False
            return

        if segment.fin:
            self._client.ack_seq = (segment.seq + 1) % 0x100000000
            self._client.send_flag(['ack'])
            self._client.is_running = False
            return

        if payload:
            self._process_data(segment,payload)
            self._client.send_flag(['ack'])

    def _process_data(self,segment: Segment,payload: bytes) -> None:
        self._buffer.extend(payload)

        self._client.ack_seq = (self._client.ack_seq + len(payload)) % 0x100000000

        if segment.psh:
            message = self._buffer.decode('utf-8', 'ignore')
            print(f'{self._client.address} disse: {message}')
            self._buffer.clear()


