from __future__ import annotations
from re import S
from threading import local
from typing import TYPE_CHECKING

from sys import argv,exit, pycache_prefix
from socket import SOCK_DGRAM, AF_INET, socket, inet_aton
from random import randint
from struct import pack,unpack
from time import time

from protocol import ip_header, segment


class Client:
    server_address: tuple[str,int]
    socket: socket

    seq: int
    ack_seq: int

    is_connected: bool 
    _max_retries: int = 5

    def __init__(self,server_address:tuple[str,int]) -> None:
        self.server_address = server_address
        self.socket = socket(AF_INET,SOCK_DGRAM)
        self.socket.settimeout(0.1)

        self.socket.bind(('0.0.0.0', 0))

        self.seq = randint(0, 0xFFFFFFFF)
        self.is_connected = False

    def connect(self) -> bool:
        rto = 1.0
        retries = 0

        self.send_segment(syn=True)
        last_send_time = time()

        while retries < self._max_retries:
            try:
                data, _ = self.socket.recvfrom(65535)
                segment, payload = Segment.from_bytes(data)

                if segment and self._is_valid(segment,payload):
                    if segment.syn and segment.ack:
                        self.ack_seq = (segment.seq + 1) % 0x100000000
                        self.seq = (self.seq + 1) % 0x100000000
                        

    
    def send_segment(self,urg:bool = False,syn:bool = False,ack:bool = False, psh:bool = False, fin:bool = False, rst:bool = False,payload:bytes = b'') -> None:
        local_ip, local_port = self.socket.getsockname()

        segment = Segment(local_port,self.server_address[1],self.seq,self.ack_seq,urg,ack,psh,rst,syn,fin)

        ip_header = IpPseudoHeader(self.ip_to_int(local_ip),self.ip_to_int(self.server_address[0]),len(segment) + len(payload))
        segment.update_checksum(ip_header, payload)

        self.socket.sendto(segment.to_bytes() + payload,self.server_address)

    def ip_to_int(self,ip_str: str) -> int:
        if ip_str == '0.0.0.0':
            ip_str = '127.0.0.1'
        return unpack('!I', inet_aton(ip_str))[0]

    def _is_valid(self,segment: Segment,payload: bytes = b'') -> bool:
        local_ip, local_port = self.socket.getsockname()
        ip_header = IpPseudoHeader(self.ip_to_int(local_ip),self.ip_to_int(self.server_address[0]),len(segment) + len(payload))
        return segment.is_checksum_valid(ip_header,payload)



def main(args: list[str]):
    host = '127.0.0.1'
    port = 8080

    if(len(args) > 1):
        if ':' in args[1]:
            parts = args[1].split(':',1)
            if parts[0]:
                host = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                print('Argumento da porta invalido')
                return

        address = (host,port)
        

class Segment:
    source: int # porta do remetente
    dest: int # porta do destinatario
    seq: int
    ack_seq: int
    # header_len: int  NOTE: esse campo foi substituido pela função len()
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

    def __init__(self,source:int,dest:int,seq:int,ack_seq:int,urg:bool = False,ack:bool = False,psh:bool = False,rst:bool = False,syn:bool = False,fin:bool = False) -> None:
        self.source = source 
        self.dest = dest
        self.seq = seq
        self.ack_seq = ack_seq
        self.urg = urg
        self.ack = ack
        self.psh = psh
        self.rst = rst
        self.syn = syn
        self.fin = fin

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

        header = pack('!HHIIBBHHH',
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

    def update_checksum(self,ip_header: IpPseudoHeader,payload: bytes = b'') -> None:
        self.check = 0
        self.check = Segment.get_checksum(ip_header.to_bytes() + self.to_bytes() + payload)

    def is_checksum_valid(self,ip_header: IpPseudoHeader,payload: bytes = b'') -> bool:
        checksum = self.check
        self.check = 0

        is_valid = (Segment.get_checksum(ip_header.to_bytes() + self.to_bytes() + payload) == checksum)
        self.check = checksum

        return is_valid

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

    @classmethod
    def from_bytes(cls,data: bytes) -> tuple['Segment', bytes]:
        header = unpack('!HHIIBBHHH',data[:20])

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

        header_len = (header[4] >> 4) * 4
        segment.options = data[20:header_len]

        payload = data[header_len:] 

        return segment, payload

    @classmethod
    def get_len_from_bytes(cls,data: bytes) -> int:
        header = unpack('!HHIIB',data[:13])

        return (header[4] >> 4) * 4


class IpPseudoHeader:
    source: int # ip do remetente
    dest: int # ip do destinatario
    protocol: int
    segment_len: int

    def __init__(self,source:int,dest:int,segment_len:int) -> None:
        self.source = source
        self.dest = dest
        self.segment_len = segment_len
        self.protocol = 6 # Valor do TCP

    def to_bytes(self) -> bytes:
        return pack('!IIBBH',
                           self.source,
                           self.dest,
                           0,
                           self.protocol,
                           self.segment_len)


if __name__ == '__main__':
    try:
        main(argv)
    except KeyboardInterrupt:
        print("Encerrando cliente")



