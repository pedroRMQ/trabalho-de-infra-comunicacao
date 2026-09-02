import struct

from .ip_header import IpPseudoHeader

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

        header_len = (header[4] >> 4) * 4
        segment.options = data[20:header_len]

        payload = data[header_len:] 

        return segment, payload

    @classmethod
    def get_len_from_bytes(cls,data: bytes) -> int:
        header = struct.unpack('!HHIIB',data[:13])

        return (header[4] >> 4) * 4


