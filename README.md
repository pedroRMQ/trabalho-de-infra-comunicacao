# Transporte Confiável na Camada de Aplicação (Cliente-Servidor com Sockets)

Trabalho I – Redes de Computadores. Aplicação cliente-servidor que implementa, sobre um socket TCP, um protocolo próprio de transferência de dados com **Go-Back-N** e **Repetição Seletiva**, em modo de **envio individual** ou **em lote**.

**Estado atual: Checkpoint 2 – Protocolo sem erros** (canal sem perdas e sem corrupção).

## Estrutura do projeto

```
.
├── client.py   # Cliente: handshake, fragmentação e envio das mensagens
├── server.py   # Servidor: handshake, recepção, ACKs e remontagem das mensagens
└── README.md
```

> `client.py` e `server.py` compartilham as mesmas classes (`config_t`, `packet_t`, `GoBackN`, `SelectiveRepeat`, `message_t`). Só diferem na função `main()` e no valor padrão de `window_size`.

## Requisitos

- Python 3.9+
- Apenas biblioteca padrão (`socket`, `struct`, `enum`, `dataclasses`, `random`)

## Como executar

Em dois terminais, na pasta do projeto:

```bash
# Terminal 1
python server.py

# Terminal 2
python client.py
```

O cliente pergunta, nesta ordem:

1. **Modo de envio**: `0` = individual, `1` = em lote
2. **Algoritmo**: `0` = Go-Back-N, `1` = Repetição Seletiva
3. **Tamanho máximo do texto** (Enter = 30)
4. **Tamanho mínimo do texto** (Enter = 30)

Depois do handshake, o cliente entra em um laço: digite a mensagem e pressione Enter. O servidor imprime a mensagem remontada. Para sair, use `Ctrl+C` no cliente. O servidor volta a aceitar novas conexões (uma por vez).

Exemplo de sessão (cliente):

```
Digite 0 para envio individual e 1 para envio em lote: 1
Digite 0 para Go-Back-N e 1 para Repetição seletiva: 0
Digite um numero para o tamanho maximo do texto ou aperte enter:
Digite um numero para o tamanho minimo do texto ou aperte enter:
Requisição de configuração enviada: CFG:1,0,30,30,0
Configuração:
	Modo de operação: BATCH / GBN
	Tamanho maximo inicial do texto:30
	Tamanho da janela:3
Digite a mensagem a ser enviada: <texto com 30 caracteres>
```

## Protocolo

### 1. Handshake (texto, terminado em `\n`)

```
CFG:<envio>,<algoritmo>,<texto_max>,<texto_min>,<janela>\n
```

| Campo       | Valores                          | Observação                                                  |
|-------------|----------------------------------|-------------------------------------------------------------|
| `envio`     | `0` = INDIVIDUAL, `1` = BATCH    | escolhido pelo cliente                                      |
| `algoritmo` | `0` = GBN, `1` = SR              | escolhido pelo cliente                                      |
| `texto_max` | inteiro (padrão 30)              | limite do texto do usuário por envio                        |
| `texto_min` | inteiro (padrão 30)              | tamanho mínimo aceito                                       |
| `janela`    | `1` a `5`                        | o cliente envia `0`; **o servidor sorteia** e devolve       |

1. O cliente envia `CFG:` com a sua proposta (janela = 0).
2. O servidor lê, define `janela = randint(1, 5)` e responde com a configuração completa.
3. O cliente adota a janela recebida e imprime os parâmetros que o servidor alterou (`diff`). Se houver divergência, a configuração do servidor prevalece.

Se a linha estiver vazia ou não começar com `CFG:`, assume-se a configuração padrão.

### 2. Pacotes de dados e ACKs (binário)

Cabeçalho de **4 bytes** (`struct` com formato `!HBB`, ordem de rede) seguido do payload:

```
 0                   16        24        32
+--------------------+---------+---------+------------------+
|   seq  (uint16)    | flags   | tamanho |  payload (0–4 B) |
+--------------------+---------+---------+------------------+
```

| Flag (bit)  | Máscara | Significado                                        |
|-------------|---------|----------------------------------------------------|
| `is_ack`    | `0x01`  | pacote é um reconhecimento positivo (ACK)          |
| `flush`     | `0x02`  | último pacote da mensagem (fim da mensagem)        |

- O campo `tamanho` informa quantos bytes de payload seguem, o que permite ler o pacote corretamente do fluxo TCP (leitura em duas etapas: cabeçalho e depois payload).
- O ACK é um pacote com `is_ack = 1`, mesmo `seq` do pacote reconhecido e payload vazio.

### 3. Fragmentação

O texto digitado é dividido em fragmentos de **no máximo 4 bytes**. Os números de sequência começam em `0` a cada mensagem e crescem de 1 em 1. O último fragmento leva `flush = 1`, e o servidor usa essa flag para saber que a mensagem terminou e pode ser exibida.

### 4. Comportamento por modo

| Modo                | Emissor                                                                                          | Receptor                                                               |
|---------------------|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| **Individual**      | Envia 1 pacote e espera o ACK correspondente antes de enviar o próximo (vale para GBN e SR)      | Envia 1 ACK por pacote                                                 |
| **Lote + GBN**      | Envia até `janela` pacotes; avança a base quando chega o ACK do último pacote enviado            | Aceita apenas o pacote com `seq == esperado`; ACK de cada pacote aceito |
| **Lote + SR**       | Envia até `janela` pacotes; registra ACKs individuais e desliza a base sobre os ACKs consecutivos | ACK individual de cada pacote recebido                                  |

## Parâmetros padrão

| Parâmetro        | Padrão |
|------------------|--------|
| Envio            | BATCH  |
| Algoritmo        | GBN    |
| Texto máx / mín  | 30 / 30 |
| Janela           | sorteada pelo servidor (1–5) |

## Limitações conhecidas (a tratar no Checkpoint 3)

- Ainda **não há** soma de verificação, temporizador, ACK negativo nem simulação de erros/perdas (canal considerado perfeito).
- O servidor ainda não imprime os **metadados de cada pacote** recebido e o cliente ainda não imprime os metadados dos ACKs (item 5 da descrição do trabalho).
- Mensagem vazia (apenas Enter) não é tratada no cliente.
- Os limites de tamanho são medidos em **bytes** (UTF-8), não em caracteres.
- O servidor atende um cliente por vez.

## Relatório de IA

Foi utilizada Inteligência Artificial de forma auxiliar durante o desenvolvimento, especificamente para:

- Pesquisa sobre o modo de operação: envio individual (IND) vs. envio em lote (GRP)
- Pesquisa sobre a diferença entre Go-Back-N e Repetição Seletiva
- Entendimento do conceito de tamanho da janela
