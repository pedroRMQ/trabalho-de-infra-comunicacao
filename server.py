import socket

HOST = '127.0.0.1'
PORT = 8080

# envio individual vs envio em lote (IND X GRP) 
# Go-Back-N vs Repetição Seletiva (GBN X SR)

# tamanho maximo do texto inicial
# tamanho da janela
TEXT_MAX_DEFAULT = 30
TAM_JANELA_DEFAULT = 5

def recv(connection: socket.socket) -> bytes:
    buffer = b''
    while True:
        byte = connection.recv(1)
        if not byte or byte == b'\n':
            break
        buffer += byte
    return buffer

def recvConfiguration(connection: socket.socket) -> tuple[str,int,int]:
    data = recv(connection)
    data = data if not data else data.strip().decode()

    if not data or not data.startswith("CFG:"): return 'GBN', TEXT_MAX_DEFAULT, TAM_JANELA_DEFAULT

    pieces = data[4:].split(',')
    protocol = pieces[0]
    text_max = int(pieces[1])
    window = int(pieces[2])

    return protocol, text_max, window

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST,PORT))
    server.listen()
    print(f'Servidor escutando na porta: {HOST}:{PORT}')
    while True:
        connection, address = server.accept()
        protocol, text_max, window = recvConfiguration(connection)
        print(f'Cliente Configurado para \n\tModo de operaçaõ:{protocol}\n\tTamanho maximo do texto inicial:{text_max}\n\tjanela inicial:{window}')
        connection.send((f'CFG:{protocol},{text_max},{window}\n').encode())
        connection.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Fechando servidor...')
