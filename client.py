import sys
import socket as sock

def main(args: list[str]):
    host: str = '127.0.0.1'
    port = 8080

    if len(args) > 1:
        try:
            port = int(args[1])
        except ValueError:
            print("ERRO FATAL: A porta deve ser um numero inteiro")
            sys.exit(1)

    socket: sock.socket = sock.socket(sock.AF_INET,sock.SOCK_STREAM)

    try:
        socket.connect((host, port))

        while True:
            message = input("Messagem a ser enviada: ")

            data = (message + "\n").encode('utf-8')
            socket.sendall(data)
    except ConnectionRefusedError:
        sys.exit(1)

if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print("\nEncerrando programa")
        sys.exit(1)
