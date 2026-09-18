from enum import Enum
import socket as sock
from dataclasses import dataclass
from random import randint

HOST = '127.0.0.1'
PORT = 8080

# envio individual vs envio em lote (IND X GRP) 
# Go-Back-N vs Repetição Seletiva (GBN X SR)

# tamanho maximo do texto inicial
# tamanho da janela

def recv(socket: sock.socket) -> bytes:
    buffer = b''
    while True:
        data = socket.recv(1)
        if not data or data == b'\n':
            break
        buffer += data
    return buffer

class shipping_t(Enum):
	INDIVIDUAL = 0
	BATCH = 1

	def __str__(self) -> str:
		return self.name

class algorithm_t(Enum):
	GBN = 0
	SR = 1

	def __str__(self) -> str:
		return self.name

@dataclass
class config_t:
	shipping: shipping_t
	algorithm: algorithm_t
	text_max_len: int
	text_min_len: int
	window_size: int

	def __init__(self,shipping: shipping_t = shipping_t.BATCH, algorithm: algorithm_t = algorithm_t.GBN, text_max_len:int = 30, text_min_len:int = 30,window_size:int = randint(0,5)) -> None:
		self.shipping = shipping
		self.algorithm = algorithm
		self.text_max_len = text_max_len
		self.text_min_len = text_min_len
		self.window_size = window_size

	def __str__(self) -> str:
		return f'CFG:{self.shipping.value},{self.algorithm.value},{self.text_max_len},{self.text_min_len},{self.window_size}\n'

	@classmethod
	def from_bytes(cls,conf: bytes):
		data = conf if not conf else conf.strip().decode()
		if not data or not data.startswith('CFG:'):
			return config_t()

		pieces = data[4:].split(',')
		return config_t(shipping_t(int(pieces[0])),algorithm_t(int(pieces[1])),int(pieces[2]),int(pieces[3]),int(pieces[4]))

	@classmethod
	def recv(cls,socket: sock.socket) -> config_t:
		conf = recv(socket)
		return cls.from_bytes(conf)

	def to_bytes(self) -> bytes:
		return str(self).encode()

	def diff(self,other: object) -> list[str]:
		if not isinstance(other,config_t):
			raise TypeError("Só é possivel diferencias dois config_t")

		diffs = []
		if self.shipping != other.shipping:
			diffs.append('shipping')

		if self.algorithm != other.algorithm:
			diffs.append('algorithm')

		if self.text_max_len != other.text_max_len:
			diffs.append('text_max_len')

		if self.text_min_len != other.text_min_len:
			diffs.append('text_min_len')

		if self.window_size != other.window_size:
			diffs.append('window_size')

		return diffs

def main():
	server = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
	server.setsockopt(sock.SOL_SOCKET, sock.SO_REUSEADDR, 1)
	server.bind((HOST,PORT))
	server.listen()
	print(f'Servidor escutando na porta: {HOST}:{PORT}')
	while True:
		client, address = server.accept()
		config = config_t.recv(client)
		print(f'Cliente Configurado:\n\tModo de operaçaõ:{config.shipping} / {config.algorithm}\n\tTamanho maximo do texto inicial:{config.text_max_len}\n\tjanela inicial:{config.window_size}')
		client.send(config.to_bytes())
		client.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Fechando servidor...')
