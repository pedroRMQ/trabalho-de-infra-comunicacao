# Projeto Cliente-Servidor com Sockets

## Estrutura do projeto

```
.
├── cliente.py   # Script do cliente
└── server.py    # Script do servidor
```

## Como funciona (estado atual)

1. O **servidor** (`server.py`) sobe em `127.0.0.1:8080` e fica aguardando conexões.
2. O **cliente** (`cliente.py`) se conecta ao servidor e envia uma mensagem de configuração no formato:
   ```
   CFG:<protocolo>,<tamanho_max_texto>,<tamanho_janela>\n
   ```
   Exemplo: `CFG:GBN,30,5`
3. O servidor recebe essa configuração, exibe no console e **responde ao cliente com a mesma configuração** (eco), no mesmo formato.
4. O cliente recebe a resposta e compara com o que havia enviado, avisando no console caso o servidor tenha discordado de algum parâmetro (protocolo, tamanho do texto ou tamanho da janela).
5. A conexão é encerrada após a troca de configuração.

### Parâmetros de configuração

| Parâmetro           | Descrição                                                                 | Valor padrão |
|---------------------|----------------------------------------------------------------------------|--------------|
| Protocolo           | Modo de operação: `GBN` (Go-Back-N) ou `SR` (Repetição Seletiva)           | `GBN`        |
| Tamanho do texto    | Tamanho máximo do texto inicial a ser transmitido                          | `30`         |
| Tamanho da janela   | Tamanho da janela de envio/recebimento                                     | `5`          |

## Requisitos

- Python 3.9+ (usa type hints como `tuple[str, int, int]`)
- Nenhuma biblioteca externa (usa apenas o módulo `socket` da biblioteca padrão)

## Como executar

Em dois terminais separados, na pasta do projeto:

**Terminal 1 — iniciar o servidor:**
```bash
python server.py
```

**Terminal 2 — iniciar o cliente:**
```bash
python cliente.py
```

O servidor ficará escutando continuamente (aceitando uma conexão por vez); o cliente se conecta uma vez, troca a configuração e encerra.

Para parar o servidor, use `Ctrl+C`.

## Protocolo de comunicação

- Mensagens são enviadas como texto codificado em UTF-8, terminadas por `\n` (newline), lidas byte a byte pela função `recv`.
- Formato da mensagem de configuração:
  ```
  CFG:<protocolo>,<tamanho_texto>,<tamanho_janela>
  ```
- Caso a mensagem recebida esteja vazia ou não comece com `CFG:`, os valores padrão (`GBN`, `30`, `5`) são assumidos.
