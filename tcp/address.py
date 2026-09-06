from ipaddress import IPv4Address

class Host:
    ip: IPv4Address

    def __init__(self,ip:str | int):
        self.ip = IPv4Address(ip)

    def __str__(self) -> str:
        return str(self.ip)

    def __int__(self) -> int:
        return int(self.ip)

    def __repr__(self) -> str:
        return f"'{self.ip}'"


class Address:
    host: Host
    port: int

    def __init__(self,host: Host, port: int):
        self.host = host
        self.port = port

    def __str__(self) -> str:
        return f'{self.host}:{self.port}'

    def to_tuple(self) -> tuple[str,int]:
        return str(self.host), self.port

    @classmethod
    def from_tuple(cls,tuple: tuple[str | int, int]):
        return cls(Host(tuple[0]),tuple[1])

