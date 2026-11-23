import socket as sock

from core import *

HOST = '127.0.0.1'
PORT = 8080

def main():
	server = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
	server.setsockopt(sock.SOL_SOCKET, sock.SO_REUSEADDR, 1)
	server.bind((HOST,PORT))
	server.listen()
	print(f'Servidor escutando na porta: {HOST}:{PORT}')

	while True:
		client, address = server.accept()
		config = config_t.recv(client)
		config.window = randint(1,5)
		print(
			f'\n\tConfiguração:'
			f'\n\t\tModo de operação: {config.algorithm}'
			f'\n\t\tTamanho maximo do texto: {config.text_max_len}'
			f'\n\t\tTamanho da janela: {config.window}'
			f'\n\t\tNumero de sequencia: {config.seq}'
		)

		client.send(config.to_bytes())
		try:
			while True:
				message = message_t.recv(client,config.algorithm,config.seq)
				config.seq += message.packets_cnt()
				print(message)
		except RuntimeError:
			print("Cliente desconectado")
		client.close()

if __name__ == '__main__':
	main()
