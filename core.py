from __future__ import annotations

from ast import While
from random import betavariate, randint
import random
import socket as sock
from enum import Enum
from dataclasses import dataclass
import struct

class protocol_t(Enum):
	handler_cls: type

	GO_BACK_N = 0
	SELECTIVE_REPEAT = 1

	def __str__(self) -> str:
		return self.name.lower()

	@classmethod
	def _missing_(cls, value: object):
		if(isinstance(value,str)):
			if value.isdigit():
				return cls(int(value))
			value = value.strip().upper()
			if value in cls.__members__:
				return cls[value]

		return super()._missing_(value)

class shipping_t(Enum):
	INDIVIDUAL = 0
	BATCH = 1

	def __str__(self) -> str:
		return self.name.lower()

	@classmethod
	def _missing_(cls, value: object):
		if(isinstance(value,str)):
			if value.isdigit():
				return cls(int(value))

			value = value.strip().upper()
			if value in cls.__members__:
				return cls[value]

		return super()._missing_(value)

class protocol_handler_t:
	shipping: shipping_t
	window_size: int

	def __init__(self,shipping: shipping_t,window_size: int) -> None:
		self.shipping = shipping
		self.window_size = window_size

	def transmit(self,socket: sock.socket,packets: list[packet_t]):
		{
			shipping_t.BATCH: self.batch_transmit,
			shipping_t.INDIVIDUAL: self.individual_transmit
		}[self.shipping](socket,packets)

	def recv(self,socket: sock.socket,seq: int) -> list[packet_t]:
		buffer = {}
		while True:
			packet = packet_t.recv(socket)
			if packet.is_corrupted():
				print("Pacote corrompido descartado")
				continue

			if packet.seq < seq:
				print(f"Pacote duplicado {packet} recebido, reenviando ack")
				packet.send_ack(socket)
				continue

			if packet.seq > seq:
				print(f"Pacote fora de ordem {packet} descartado")
				continue

			print(f"Pacote {packet} recebido, enviando ack")
			packet.send_ack(socket)

			buffer[packet.seq] = packet
			seq += 1
			if packet.flush:
				print(f"Pacote final recebido")
				break

		return [buffer[seq] for seq in sorted(buffer.keys())]

	def individual_transmit(self,socket: sock.socket,packets: list[packet_t]):
		for packet in packets:
			while True:
				socket.send(packet.to_bytes())
				print(f"Enviando pacote de sequencia {packet.seq}")
				try:
					self.wait_for_ack(socket,packet.seq,timeout=0.2)
					print(f"Pacote de confirmação para {packet} recebido")
					break
				except TimeoutError:
					print(f"Timeout para pacote {packet} atingido, reenviando pacote")

	def wait_for_ack(self,socket:sock.socket,seq:int|None = None,timeout:float|None = None) -> int:
		while True:
			packet = packet_t.recv(socket,timeout)
			if packet.is_corrupted():
				print("Ack corrompido descartado")
				continue
			if packet.is_ack:
				if seq is None:
					return packet.seq
				if packet.seq == seq:
					return 0

	def batch_transmit(self,socket: sock.socket,packets: list[packet_t]):
		raise NotImplementedError

class go_back_n_t(protocol_handler_t):
	def batch_transmit(self, socket: sock.socket, packets: list[packet_t]):
		sent = 0
		while sent < len(packets):
			limit = min(self.window_size,len(packets) - sent) + sent
			for i in range(sent,limit):
				socket.send(packets[i].to_bytes())
			print(f"Enviando pacotes de sequencia {packets[sent].seq} a {packets[limit-1].seq}")

			i = sent
			while(i < limit):
				try:
					ack = self.wait_for_ack(socket,timeout=0.2)
					if ack >= packets[i].seq:
						print(f"Pacote de confirmação para o pacote {packets[i]} recebido")
						i +=  ack - packets[i].seq + 1
						continue
					print(f"Pacote de confirmação para o pacote com sequencia {ack} ja reconhecido recebido")
				except TimeoutError:
					print(f"Timeout atingido, reenviando pacotes de sequencia {packets[i].seq} a {packets[limit-1].seq}")
					for k in range(i,limit):
						socket.send(packets[k].to_bytes())
			sent = limit

class selective_repeat_t(protocol_handler_t):
	def batch_transmit(self, socket: sock.socket, packets: list[packet_t]) -> None:
		sent = 0
		while sent < len(packets):
			limit = min(self.window_size,len(packets) - sent) + sent
			for i in range(sent,limit):
				socket.send(packets[i].to_bytes())
			print(f"Enviando pacotes de sequencia {packets[sent].seq} a {packets[limit-1].seq}")

			for i in range(sent,limit):
				while True:
					try:
						ack = self.wait_for_ack(socket,timeout=0.2)
						if ack == packets[i].seq:
							print(f"Pacote de confirmação para {packets[i]} recebido")
							break
						print(f"Pacote de confirmação para {ack} ignorado, esperando confirmação para {packets[i].seq}")
					except TimeoutError:
						print(f"Timeout para confirmação do pacote {packets[i].seq}, reenviando pacote")
						socket.send(packets[i].to_bytes())
			sent = limit

class algorithm_t:
	handler: protocol_handler_t
	protocol: protocol_t
	shipping: shipping_t

	PROTOCOL_DISPATCHER = {
		protocol_t.GO_BACK_N: go_back_n_t,
		protocol_t.SELECTIVE_REPEAT: selective_repeat_t,
	}

	def __init__(self,protocol: protocol_t,shipping: shipping_t,window_size: int) -> None:
		self.handler = self.PROTOCOL_DISPATCHER[protocol](shipping,window_size)
		self.protocol = protocol
		self.shipping = shipping

	def __str__(self) -> str:
		return f"{self.protocol.name},{self.shipping.name}"

	def transmit(self,socket: sock.socket,packets: list[packet_t]):
		self.handler.transmit(socket,packets)
	
	def recv(self,socket: sock.socket, seq: int) -> list[packet_t]:
		return self.handler.recv(socket,seq)

@dataclass
class config_t:
	algorithm: algorithm_t
	text_max_len: int 
	text_min_len: int 
	window: int
	seq: int

	def __init__(self,
		protocol: protocol_t = protocol_t.GO_BACK_N,
		shipping: shipping_t = shipping_t.BATCH,
		text_max_len:int = 30,
		text_min_len:int = 30,
		window:int | None = None,
		seq: int | None = None
	) -> None:
		if window is None:
			window = randint(1,5)
		if seq is None:
			seq = randint(0,10000)

		self.algorithm = algorithm_t(protocol,shipping,window)
		self.text_max_len = text_max_len
		self.text_min_len = text_min_len
		self.window = window
		self.seq = seq

	def __str__(self) -> str:
		return f'CFG:{self.algorithm},{self.text_max_len},{self.text_min_len},{self.window},{self.seq}\n'

	@classmethod
	def from_bytes(cls,conf: bytes):
		data = conf if not conf else conf.strip().decode()
		if not data or not data.startswith('CFG:'):
			return config_t()

		pieces = data[4:].split(',')
		return config_t(protocol_t(pieces[0]),shipping_t(pieces[1]),int(pieces[2]),int(pieces[3]),int(pieces[4]),int(pieces[5]))

	@classmethod
	def recv(cls,socket: sock.socket) -> config_t:
		buffer = b''
		while True:
			data = socket.recv(1)
			if not data or data == b'\n':
				break
			buffer += data
		return cls.from_bytes(buffer)

	def to_bytes(self) -> bytes:
		return str(self).encode()

@dataclass
class packet_t:
	seq: int
	sum: int
	is_ack: bool = False
	flush: bool = False
	data: bytes = b''

	HEADER_FORMAT = '!HBBB'
	HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

	def __init__(self,seq: int,sum: int | None = None,is_ack: bool = False,flush: bool = False, data: bytes = b'') -> None:
		self.seq = seq
		self.is_ack = is_ack
		self.flush = flush
		self.data = data
		if sum is None:
			self.sum = 0
			self.sum = ~self.compute_checksum() & 0xFF
		else:
			self.sum = sum

	def to_bytes(self) -> bytes:
		flags = 0
		if self.is_ack: flags |= 0x01
		if self.flush: flags |= 0x02

		header = struct.pack(self.HEADER_FORMAT, self.seq, self.sum, flags, len(self.data))
		return header + self.data

	def compute_checksum(self) -> int:
		data = self.to_bytes()
		return sum(data) & 0xFF

	def is_corrupted(self) -> bool:
		return not (self.compute_checksum() == 0xFF)

	@classmethod
	def from_bytes(cls,data:bytes):
		seq, sum, flags, size = struct.unpack_from(cls.HEADER_FORMAT, data)

		is_ack = bool(flags & 0x01)
		flush = bool(flags & 0x02)

		return cls(seq,sum,is_ack,flush,data[cls.HEADER_SIZE:])

	@classmethod
	def recv(cls,socket: sock.socket,timeout: float | None = None) -> packet_t:
		original_timeout = socket.gettimeout()

		if timeout is not None: 
			socket.settimeout(timeout)
		try:
			header = b''
			while len(header) < cls.HEADER_SIZE:
				chunk = socket.recv(cls.HEADER_SIZE - len(header))
				if not chunk: raise RuntimeError("Conexão fechada")
				header += chunk

			_,_,_,size = struct.unpack_from(cls.HEADER_FORMAT, header)

			payload = b''
			while len(payload) < size:
				chunk = socket.recv(size - len(payload))
				if not chunk: raise RuntimeError("Conexão fechada")
				payload += chunk
			return cls.from_bytes(header + payload)

		finally:
			if timeout is not None:
				socket.settimeout(original_timeout)

	def send_ack(self,socket: sock.socket):
		packet = packet_t(seq=self.seq,is_ack=True)
		socket.send(packet.to_bytes())

class message_t:
	packets: list[packet_t]

	def __init__(self,data:bytes = b'',seq:int = 0) -> None:
		self.packets: list[packet_t] = []
		if not data: return 

		while len(data) > 4:
			self.packets.append(packet_t(seq,data=data[:4]))
			seq += 1
			data = data[4:]
		self.packets.append(packet_t(seq,flush=True,data=data[:4]))

	def send(self,socket: sock.socket,algorithm: algorithm_t) -> None:
		algorithm.transmit(socket,self.packets)

	def __len__(self):
		return sum(len(packet.data) for packet in self.packets)

	@classmethod
	def from_packets(cls,packets: list[packet_t]):
		message = cls()
		message.packets = packets
		return message

	@classmethod
	def recv(cls,socket:sock.socket,algorithm: algorithm_t,seq: int) -> message_t:
		return cls.from_packets(algorithm.recv(socket,seq))

	def __str__(self) -> str:
		data = b''
		for packet in self.packets:
			data += packet.data
		return data.decode().strip()

	def packets_cnt(self) -> int:
		return len(self.packets)

