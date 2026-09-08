import socket

HOST = '127.0.0.1'
PORT = 8080

def recv(connection: socket.socket) -> bytes:
    buffer = b''
    while True:
        data = connection.recv(1)
        if not data or data == b'\n':
            break
        buffer += data
    return buffer

def recvConfiguration(connection: socket.socket) -> tuple[str,int,int]:
    data = recv(connection)
    data = data if not data else data.strip().decode()
    if not data or not data.startswith('CFG:'):
        return 'GBN', 30, 5 

    pieces = data[4:].split(',')
    protocol = pieces[0]
    text_max = int(pieces[1])
    window = int(pieces[2])

    return protocol, text_max, window

def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((HOST,PORT))

    protocol = 'GBN'
    text_max = 30
    window = 5

    requisition = f'CFG:{protocol},{text_max},{window}\n'

    client.send(requisition.encode())
    print(f'Requisição de configuração enviada: {requisition}')

    recv_protocol, recv_text_max, recv_window = recvConfiguration(client)
    if recv_protocol != protocol:
        print(f'servidor discorda do protocol: {recv_protocol}')
        protocol = recv_protocol
    if text_max != recv_text_max:
        print(f'servidor discorda do tamanho do texto: {recv_text_max}')
        text_max = recv_text_max
    if window != recv_window:
        print(f'servidor discorda do tamanho da janela: {recv_window}')
        recv_window = window

    print(f'Configuração:\n\tModo de operação:{protocol},\n\tTamanho do texto inicial:{text_max},\n\tTamanho da janela:{window}')

    client.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Encerrando programa')
