from __future__ import annotations
from contextlib import contextmanager
from enum import Enum
from math import exp
import struct
import socket as sock
from dataclasses import dataclass
from random import randint
from typing import Protocol

HOST = '127.0.0.1'
PORT = 8080

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

	@classmethod
	def _missing_(cls, value: object):
		if isinstance(value,str) and value.isdigit():
			return cls(int(value))
		return super()._missing_(value)

class algorithm_t(Enum):
	GBN = 0
	SR = 1

	def __str__(self) -> str:
		return self.name

	@classmethod
	def _missing_(cls, value: object):
		if isinstance(value,str) and value.isdigit():
			return cls(int(value))
		return super()._missing_(value)

@dataclass
class config_t:
	shipping: shipping_t = shipping_t.BATCH
	algorithm: algorithm_t = algorithm_t.GBN
	text_max_len: int = 30
	text_min_len: int = 30
	window_size: int = 5

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
			raise TypeError("Só é possivel diferenciar dois config_t")

		diffs = []
		if self.shipping != other.shipping:
			diffs.append('shipping')

		if self.algorithm != other.algorithm:
			diffs.append('algorithm')

		if self.text_max_len != other.text_max_len:
			diffs.append('text_max_len')

		if self.text_min_len != other.text_min_len:
			diffs.append('text_min_len')

		if self.window_size is not None and self.window_size != other.window_size:
			diffs.append('window_size')

		return diffs
@dataclass()
class packet_t:
	seq: int
	is_ack: bool = False
	flush: bool = False
	data: bytes = b''

	HEADER_FORMAT = '!HBB'
	HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

	def to_bytes(self) -> bytes:
		flags = 0
		if self.is_ack: flags |= 0x01
		if self.flush: flags |= 0x02

		header = struct.pack(self.HEADER_FORMAT, self.seq,flags,len(self.data))
		return header + self.data

	@classmethod
	def from_bytes(cls,data:bytes):
		seq, flags, size = struct.unpack_from(cls.HEADER_FORMAT, data)

		is_ack = bool(flags & 0x01)
		flush = bool(flags & 0x02)

		return cls(seq,is_ack,flush,data[cls.HEADER_SIZE:])

	@classmethod
	def recv(cls,socket: sock.socket) -> packet_t:
		header = b''
		while len(header) < cls.HEADER_SIZE:
			chunk = socket.recv(cls.HEADER_SIZE - len(header))
			if not chunk: raise RuntimeError("Conexão fechada")
			header += chunk

		_,_,size = struct.unpack_from(cls.HEADER_FORMAT, header)

		payload = b''
		while len(payload) < size:
			chunk = socket.recv(size - len(payload))
			if not chunk: raise RuntimeError("Conexão fechada")
			payload += chunk

		return cls.from_bytes(header + payload)

class ProtocolHandler:
	socket: sock.socket
	config: config_t

	def __init__(self,socket: sock.socket, config: config_t) -> None:
		self.socket = socket
		self.config = config

	def transmit(self,packets: list[packet_t]) -> None:
		raise NotImplementedError

	def recv(self) -> list[packet_t]:
		raise NotImplemented

	def _wait_for_ack(self,seq:int):
		while True:
			packet = packet_t.recv(self.socket)
			if(packet.is_ack and packet.seq == seq): return

	def _wait_for_batch_acks(self,seq: int) -> int:
		while True:
			packet = packet_t.recv(self.socket)
			if packet.is_ack and packet.seq == seq:
				return seq + 1

class GoBackN(ProtocolHandler):
	def transmit(self, packets: list[packet_t]) -> None:
		if self.config.shipping == shipping_t.INDIVIDUAL:
			for packet in packets:
				self.socket.send(packet.to_bytes())
				self._wait_for_ack(packet.seq)

		elif self.config.shipping == shipping_t.BATCH:
			window = 0
			while window < len(packets):
				limit = min(window + self.config.window_size, len(packets))

				for i in range(window,limit):
					self.socket.send(packets[i].to_bytes())

				last_seq_sent = packets[limit - 1].seq
				window = self._wait_for_batch_acks(last_seq_sent)

	def recv(self) -> list[packet_t]:
		packets = []
		expected_seq = 0
		while True:
			packet = packet_t.recv(self.socket)

			if packet.seq == expected_seq:
				packets.append(packet)
				
				ack_packet = packet_t(seq=expected_seq, is_ack=True)
				self.socket.send(ack_packet.to_bytes())
				expected_seq += 1

				if packet.flush:
					break
		return packets

class SelectiveRepeat(ProtocolHandler):
	def transmit(self, packets: list[packet_t]) -> None:
		if self.config.shipping == shipping_t.INDIVIDUAL:
			for packet in packets:
				self.socket.send(packet.to_bytes())
				self._wait_for_ack(packet.seq)

		elif self.config.shipping == shipping_t.BATCH:
			window = 0
			next_seq_to_send = 0
			acked_packets = set()
			
			while window < len(packets):
				limit = min(window + self.config.window_size,len(packets))
				while next_seq_to_send < limit:
					self.socket.send(packets[next_seq_to_send].to_bytes())
					next_seq_to_send += 1

				while window < len(packets) and window not in acked_packets:
					ack_packet = packet_t.recv(self.socket)

					if ack_packet.is_ack:
						acked_packets.add(ack_packet.seq)

					while window in acked_packets:
						window += 1

	def recv(self) -> list[packet_t]:
		packets = []
		while True:
			packet = packet_t.recv(self.socket)
			ack_packet = packet_t(seq=packet.seq,is_ack=True)
			self.socket.send(ack_packet.to_bytes())

			packets.append(packet)

			if packet.flush:
				break
		return packets

class message_t:
	packets: list[packet_t]

	def __init__(self,data:bytes = b'') -> None:
		if not data: return
		self.packets: list[packet_t] = []

		seq = 0
		while len(data) > 4:
			self.packets.append(packet_t(seq,data=data[:4]))
			seq += 1
			data = data[4:]
		self.packets.append(packet_t(seq,flush=True,data=data[:4]))
		seq += 1

	def send(self,socket: sock.socket,config: config_t) -> None:
		ALGORITHM_DISPATCHER = {
			algorithm_t.GBN: GoBackN,
			algorithm_t.SR: SelectiveRepeat
		} 

		handler_class = ALGORITHM_DISPATCHER[config.algorithm]
		protocol = handler_class(socket=socket, config=config)

		protocol.transmit(self.packets)

	def __len__(self):
		return sum(len(packet.data) for packet in self.packets)

	@classmethod
	def recv(cls,socket:sock.socket,config: config_t) -> message_t:
		ALGORITHM_DISPATCHER = {
			algorithm_t.GBN: GoBackN,
			algorithm_t.SR: SelectiveRepeat
		} 

		handler_class = ALGORITHM_DISPATCHER[config.algorithm]
		protocol = handler_class(socket=socket, config=config)

		packets = protocol.recv()
		message = cls()
		message.packets = packets

		return message

	def __str__(self) -> str:
		data = b''
		for packet in self.packets:
			data += packet.data
		return data.decode().strip()

def main():
	server = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
	server.setsockopt(sock.SOL_SOCKET, sock.SO_REUSEADDR, 1)
	server.bind((HOST,PORT))
	server.listen()
	print(f'Servidor escutando na porta: {HOST}:{PORT}')

	while True:
		client, address = server.accept()
		config = config_t.recv(client)
		config.window_size = randint(1,5)
		print(f'Cliente Configurado:\n\tModo de operaçaõ: {config.shipping} / {config.algorithm}\n\tTamanho maximo do texto:{config.text_max_len}\n\tjanela inicial:{config.window_size}')
		client.send(config.to_bytes())
		try:
			while True:
				message = message_t.recv(client,config)
				print(message)
		except RuntimeError as e:
			print("Cliente desconectado")
		client.close()

if __name__ == '__main__':
	main()
