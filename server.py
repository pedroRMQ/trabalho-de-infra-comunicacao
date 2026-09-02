import socket as sock
import threading
import sys
import struct
from protocol import Client

class Server:
    socket: sock.socket
    port: int
    clients: dict[tuple[str,int], Client]

    def __init__(self, port: int = 8080) -> None:
        self.port = port

        self.socket = sock.socket(sock.AF_INET,sock.SOCK_DGRAM)    # NOTE: Mudei de TCP para UDP para receber pacotes completos
        self.socket.setsockopt(sock.SOL_SOCKET,sock.SO_REUSEADDR, 1)

        try:
            self.socket.bind(('',self.port))
            print(f"Servidor esta escutando na porta {self.port}")
        except OSError as error:
            raise RuntimeError(f"Falha ao vincular a porta {self.port}") from error

        self.clients = {}

    def __del__(self):
        if self.socket:
            self.socket.close()


    def listen(self) -> None:
        while(True):
            data, address = self.socket.recvfrom(65535)

            if address not in self.clients:
                client = Client(self, address)
                self.clients[address] = client

                thread = threading.Thread(target=client.run,daemon=True)
                thread.start()

            self.clients[address].receive_bytes(data)

    def get_ip(self) -> int:
        ip_str = self.socket.getsockname()[0]
        return struct.unpack('!I',sock.inet_aton(ip_str))[0]

    def get_port(self) -> int:
        return self.socket.getsockname()[1]


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
        server.listen()
    except RuntimeError as error:
        print(f"ERRO FATAL: {error}")
        sys.exit(1)


if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print("\nEncerrando programa")
        sys.exit(1)

