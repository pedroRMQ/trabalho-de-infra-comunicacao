from struct import pack

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
