import enum
import socket as sock
import copy

from core import *

HOST = '127.0.0.1'
PORT = 8080

class failure_type_t(Enum):
	CORRUPTION = 0
	DROP = 1
	REORDER = 2
	DUPLICATE = 3

class failure_t:
	message: message_t;

	def __init__(self,message: message_t) -> None:
		self.original = message
		self.message = copy.deepcopy(message)

	def add(self, type: failure_type_t) -> "failure_t":
		match type:
			case failure_type_t.CORRUPTION:
				self._apply_corruption()
			case failure_type_t.DROP:
				self._apply_drop()
			case failure_type_t.REORDER:
				self._apply_reorder()
			case failure_type_t.DUPLICATE:
				self._apply_duplicate()
			case _:
				raise ValueError(f"Tipo de falha não suportado: {type}")
		return self

	def _select_packet_index(self, action: str) -> int | None:
		packets = self.message.packets
		if not packets:
			print(f"\tNão há pacotes disponiveis para {action}.")
			return None

		print("\n\tPacotes Disponiveis")
		for i, packet in enumerate(packets):
			print(f"\t\t[{i}] {packet}")

		while True:
			value = input(f"Qual pacote {action}? ").strip()
			if value.isdigit() and int(value) >= 0 and len(packets) > int(value):
				return int(value)
			print("Indice invalido")

	def _apply_corruption(self):
		i = self._select_packet_index("corromper")
		if i is not None:
			self.message.packets[i] = self._corrupt_packet(self.message.packets[i])
			print(f"-> Pacote [{i}] corrompido!")

	def _corrupt_packet(self,packet: packet_t) -> packet_t:
		packet.data = random.randbytes(len(packet.data))
		return packet

	def _apply_drop(self):
		i = self._select_packet_index("derrubar")
		if i is not None:
			self.message.packets.pop(i)
			print(f"-> Pacote [{i}] derrubado!")

	def _apply_duplicate(self) -> None:
		i = self._select_packet_index("duplicar")
		if i is not None:
			packets = self.message.packets
			duplicate = copy.deepcopy(packets[i])
			if packets[i].flush:
				packets[i].flush = False
			packets.insert(i + 1, duplicate)
			print(f"-> Pacote [{i}] duplicado!")

	def _apply_reorder(self) -> None:
		packets = self.message.packets
		if len(packets) < 2:
			print("\tPacotes insuficientes para reordenar.")
			return

		random.shuffle(packets)
		print("-> Pacotes reordenados!")
	
	def build(self):
		return self.message

def main():
	client = sock.socket(sock.AF_INET,sock.SOCK_STREAM)
	client.connect((HOST,PORT))

	shipping = shipping_t.BATCH
	while True:
		try:
			shipping = shipping_t(input("Digite 0 para envio individual e 1 para envio em lote: "))
			break
		except ValueError:
			continue

	protocol = protocol_t.GO_BACK_N
	while True:
		try:
			protocol = protocol_t(input("Digite 0 para Go-Back-N e 1 para Repetição seletiva: "))
			break
		except ValueError:
			continue

	text_max_len = 30
	while True:
		try:
			number = input("Digite um numero para o tamanho maximo do texto ou aperte enter:")
			text_max_len = 30 if not number else int(number)
			break
		except ValueError:
			continue

	text_min_len = 30
	while True:
		try:
			number = input("Digite um numero para o tamanho minimo do texto ou aperte enter:")
			text_min_len = 30 if not number else int(number)
			break
		except ValueError:
			continue

	config = config_t(protocol,shipping,text_max_len,text_min_len)

	client.send(config.to_bytes())
	print(f'Requisição de configuração enviada: {config}')

	recv_config = config_t.recv(client)

	config.window = recv_config.window
	print(
		f'\tConfiguração:'
		f'\n\t\tModo de operação: {config.algorithm}'
		f'\n\t\tTamanho maximo do texto: {config.text_max_len}'
		f'\n\t\tTamanho da janela: {config.window}'
		f'\n\t\tNumero de sequencia: {config.seq}'
	)

	while True:
		message = message_t(input("Digite a mensagem a ser enviada: ").encode(),config.seq)
		if(len(message) < config.text_min_len):
			print(f'A mensagem deve ter {config.text_min_len} ou mais caracteres')
			continue
		if len(message) > config.text_max_len:
			print(f'A mensagem deve ter no maximo {config.text_max_len} caracteres')
			continue

		message_f = None
		if(input("Inserir erros? [S/N]: ").strip().lower() == "s"):
			failure = failure_t(message)
			while True:
				print("Selecione o tipo de erro:")
				for tpe in failure_type_t:
					print(f"\t[{tpe.value}] {tpe.name}")

				option = input("Opção: ").strip()
				if not option:
					print("Edição de erros concluida")
					message_f = failure.build()
					break

				try:
					selected = failure_type_t(int(option)) if option.isdigit() else failure_type_t(option)
					failure.add(selected)
				except ValueError:
					print("Opção inválida! Tente novamente.")

		if message_f:
			try:
				print("Enviando mensagem com erros")
				message_f.send(client,config.algorithm)
				config.seq += message.packets_cnt()
			except KeyboardInterrupt:
				print("\n[!] Envio com erros abortado!")
				print("Enviando mensagem original")
				message.send(client,config.algorithm)
				config.seq += message.packets_cnt()
		else:
			message.send(client,config.algorithm)
			config.seq += message.packets_cnt()

if __name__ == '__main__':
	main()
