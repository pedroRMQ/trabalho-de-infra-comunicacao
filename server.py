import sys
import socket as sock
import threading
import struct
from abc import ABC,abstractmethod
from typing import assert_never

class IState(ABC):
    @abstractmethod
    def update(self) -> None:
        pass
    @abstractmethod
    def enter(self,args: list) -> None:
        pass
    @abstractmethod
    def exit(self) -> None:
        pass

class EmptyState(IState):
    def update(self) -> None:
        return
    def enter(self, args: list) -> None:
        return
    def exit(self) -> None:
        return

class StateMachine:
    _stateDict: dict[str,IState] = dict()
    _current: IState = EmptyState()

    def add(self,id: str,state: IState) -> None:
        self._stateDict[id] = state
    def remove(self,id: str) -> None:
        self._stateDict.pop(id,None)
    def clear(self) -> None:
        self._stateDict.clear()

    def change(self,id: str,args: list):
        self._current.exit()
        next = self._stateDict[id]
        next.enter(args)
        self._current = next

    def update(self):
        self._current.update()

class IpPseudoHeader:
    source: int
    dest: int
    protocol: int
    segment_len: int

    def __init__(self,source:int,dest:int,segment_len:int) -> None:
        self.source = source
        self.dest = dest
        self.segment_len = segment_len
        self.protocol = 6 # Valor do TCP

    def to_bytes(self) -> bytes:
        return struct.pack('!IIBBH',
                           self.source,
                           self.dest,
                           0,
                           self.protocol,
                           self.segment_len)


class Segment:
    source: int
    dest: int
    seq: int
    ack_seq: int
    # header_len: int esse campo sera substituido pela função len()
    urg: bool = False
    ack: bool = False
    psh: bool = False
    rst: bool = False
    syn: bool = False
    fin: bool = False
    window: int = 8192
    check: int = 0
    urg_ptr: int = 0
    options: bytes = b''

    def __init__(self,source:int,dest:int,seq:int,ack_seq:int) -> None:
        self.source = source 
        self.dest = dest
        self.seq = seq
        self.ack_seq = ack_seq

    def __len__(self):
        return 20 + len(self.options)

    def set_flag(self,flag: str,state: bool):
        setattr(self,flag,state)

    def to_bytes(self) -> bytes:
        offset = len(self) // 4

        flags = (
            (self.urg << 5) | 
            (self.ack << 4) | 
            (self.psh << 3) | 
            (self.rst << 2) | 
            (self.syn << 1) | 
            (self.fin))

        header = struct.pack('!HHIIBBHHH',
                           self.source,
                           self.dest,
                           self.seq,
                           self.ack_seq,
                           offset << 4,
                           flags,
                           self.window,
                           self.check,
                           self.urg_ptr)

        return header + self.options

    @classmethod
    def get_checksum(cls,data: bytes) -> int:
        if len(data) % 2 != 0:
            data += b'\x00'

        total = 0

        for i in range(0, len(data), 2):
           total += (data[i] << 8) + data[i+1]

        while (total >> 16) > 0:
            total = (total & 0xFFFF) + (total >> 16)

        return ~total & 0xFFFF

    def is_checksum_valid(self,ip_header: IpPseudoHeader) -> bool:
        checksum = self.check
        self.check = 0

        is_valid = (Segment.get_checksum(ip_header.to_bytes() + self.to_bytes()) == checksum)
        self.check = checksum

        return is_valid

    @classmethod
    def from_bytes(cls,data: bytes) -> 'Segment':
        header = struct.unpack('!HHIIBBHHH',data[:20])

        segment = Segment(header[0],header[1],header[2],header[3])

        flags = header[5]
        segment.urg = bool((flags >> 5) & 1)
        segment.ack = bool((flags >> 4) & 1)
        segment.psh = bool((flags >> 3) & 1)
        segment.rst = bool((flags >> 2) & 1)
        segment.syn = bool((flags >> 1) & 1)
        segment.fin = bool(flags & 1)

        segment.window = header[6]
        segment.check = header[7]
        segment.urg_ptr = header[8]
        segment.options = data[20:(header[4] >> 4)*4]

        return segment

class Client:
    socket: sock.socket
    address: tuple[str, int]
    state_machine: StateMachine

    def __init__(self,socket:sock.socket,address:tuple[str,int]) -> None:
        self.socket = socket
        self.address = address

    def update(self):
        data:bytes = b""
        while True:
            buffer:bytes = self.socket.recv(1024)

            if not buffer:
                break;

            data += buffer;

            if b"\n" in data:
                message, data = data.split(b"\n",1)
                self.handle(message)

    def handle(self,data: bytes):
        text = data.decode('utf-8')
        print(f"{text}")

    def __del__(self):
        self.socket.close()



class Server:
    socket: sock.socket
    port: int

    def __init__(self, port: int = 8080) -> None:
        self.port = port
        self.socket = sock.socket(sock.AF_INET,sock.SOCK_STREAM)
        self.socket.setsockopt(sock.SOL_SOCKET,sock.SO_REUSEADDR, 1)
        try:
            self.socket.bind(('',self.port))
            print(f"Servidor esta escutando na porta {self.port}")
        except OSError as error:
            raise RuntimeError(f"Falha ao vincular a porta {self.port}") from error
        self.socket.listen(5)

    def update(self):
        while(True):
            client_socket, client_address = self.socket.accept()

            client = Client(client_socket,client_address)

            thread = threading.Thread(target=client.update)
            thread.start()


    def __del__(self):
        if self.socket:
            self.socket.close()


def main(args: list[str]) -> None:
    port = None
    if len(args) > 1:
        try:
            port = int(args[1])
        except ValueError:
            print("ERRO FATAL: A porta deve ser um numero inteiro")
            sys.exit(1)

    try:
        server = Server(port) if port else Server()
        server.update()
    except RuntimeError as error:
        print(f"ERRO FATAL: {error}")
        sys.exit(1)


if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print("\nEncerrando programa")
        sys.exit(1)

