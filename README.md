# Transporte Confiável na Camada de Aplicação (Cliente-Servidor com Sockets)

Trabalho I – Redes de Computadores. Aplicação cliente-servidor que implementa, sobre um socket TCP, um protocolo próprio de transferência de dados com **Go-Back-N** e **Repetição Seletiva**, em modo de **envio individual** ou **em lote**, agora com **soma de verificação, temporizador, retransmissão e simulação de erros** no canal.

**Estado atual: Checkpoint 3 – Protocolo com erros** (corrupção, perda, reordenação e duplicação de pacotes).

## Estrutura do projeto

```
.
├── core.py     # Código compartilhado: enums, config_t, packet_t, protocolos, message_t
├── client.py   # Cliente: handshake, fragmentação, envio e injeção de erros
├── server.py   # Servidor: handshake, recepção, ACKs e remontagem das mensagens
└── README.md
```

> Diferente do Checkpoint 2, `client.py` e `server.py` **não duplicam mais as classes**: ambos fazem `from core import *`. Cada um contém apenas a sua função `main()` (e, no cliente, as classes de falha `failure_t` / `failure_type_t`).

## Requisitos

- Python **3.10+** (uso de `match`, `int | None` e `TimeoutError` como alias de `socket.timeout`)
- Apenas biblioteca padrão (`socket`, `struct`, `enum`, `dataclasses`, `random`, `copy`)

## Como executar

Em dois terminais, na pasta do projeto:

```bash
# Terminal 1
python server.py

# Terminal 2
python client.py
```

O cliente pergunta, nesta ordem:

1. **Modo de envio**: `0` = em lote, `1` = individual (valores de `shipping_t` em `core.py`)
2. **Algoritmo**: `0` = Go-Back-N, `1` = Repetição Seletiva
3. **Tamanho máximo do texto** (Enter = 30)
4. **Tamanho mínimo do texto** (Enter = 30)

Depois do handshake, o cliente entra em um laço:

1. Digite a mensagem e pressione Enter.
2. O cliente pergunta `Inserir erros? [S/N]`. Se `N`, a mensagem é enviada normalmente.
3. Se `S`, escolha o tipo de erro (veja abaixo). Pressione Enter com a opção vazia para concluir a edição e enviar.
4. O servidor imprime a mensagem remontada.

Para sair, use `Ctrl+C` no cliente. O servidor volta a aceitar novas conexões (uma por vez).

Exemplo de sessão (cliente):

```
Digite um numero para o tamanho maximo do texto ou aperte enter:
Digite um numero para o tamanho minimo do texto ou aperte enter:
Requisição de configuração enviada: CFG:GO_BACK_N,BATCH,30,30,4,7312
	Configuração:
		Modo de operação: GO_BACK_N,BATCH
		Tamanho maximo do texto: 30
		Tamanho da janela: 3
		Numero de sequencia: 7312
Digite a mensagem a ser enviada: <texto com 30 caracteres>
Inserir erros? [S/N]: n
Enviando pacotes de sequencia 7312 a 7314
...
```

## Protocolo

### 1. Handshake (texto, terminado em `\n`)

```
CFG:<protocolo>,<envio>,<texto_max>,<texto_min>,<janela>,<seq>\n
```

| Campo       | Valores                                  | Observação                                                          |
|-------------|------------------------------------------|---------------------------------------------------------------------|
| `protocolo` | `GO_BACK_N` ou `SELECTIVE_REPEAT`        | escolhido pelo cliente (agora enviado pelo **nome**, não por número) |
| `envio`     | `BATCH` ou `INDIVIDUAL`                  | escolhido pelo cliente                                              |
| `texto_max` | inteiro (padrão 30)                      | limite do texto do usuário por envio                                |
| `texto_min` | inteiro (padrão 30)                      | tamanho mínimo aceito                                               |
| `janela`    | `1` a `5`                                | sorteada pelo cliente na proposta; **o servidor sorteia de novo** e devolve |
| `seq`       | `0` a `10000`                            | **número de sequência inicial**, sorteado pelo cliente              |

1. O cliente envia `CFG:` com a sua proposta.
2. O servidor lê, define `janela = randint(1, 5)` e responde com a configuração completa.
3. O cliente adota a janela e o número de sequência devolvidos e imprime a configuração final.

Se a linha estiver vazia ou não começar com `CFG:`, assume-se a configuração padrão.

### 2. Pacotes de dados e ACKs (binário)

Cabeçalho de **5 bytes** (`struct` com formato `!HBBB`, ordem de rede) seguido do payload:

```
 0                   16        24        32        40
+--------------------+---------+---------+---------+------------------+
|   seq  (uint16)    |  soma   | flags   | tamanho |  payload (0–4 B) |
+--------------------+---------+---------+---------+------------------+
```

| Flag (bit)  | Máscara | Significado                                        |
|-------------|---------|----------------------------------------------------|
| `is_ack`    | `0x01`  | pacote é um reconhecimento positivo (ACK)          |
| `flush`     | `0x02`  | último pacote da mensagem (fim da mensagem)        |

- O campo `tamanho` informa quantos bytes de payload seguem, o que permite ler o pacote corretamente do fluxo TCP (leitura em duas etapas: cabeçalho e depois payload).
- O ACK é um pacote com `is_ack = 1`, mesmo `seq` do pacote reconhecido e payload vazio. Ele também carrega soma de verificação.

### 3. Soma de verificação

- **Emissor:** com o campo `soma = 0`, soma todos os bytes do pacote (cabeçalho + payload) módulo 256 e grava o **complemento de 1** do resultado.
- **Receptor:** soma todos os bytes do pacote recebido (incluindo `soma`). O pacote é válido se o resultado for `0xFF`; caso contrário é considerado **corrompido** e descartado (sem ACK).

### 4. Fragmentação e numeração

O texto digitado é dividido em fragmentos de **no máximo 4 bytes**. Os números de sequência **não reiniciam mais a cada mensagem**: começam no valor sorteado no handshake e continuam crescendo de 1 em 1 ao longo da conexão (cliente e servidor somam a quantidade de pacotes de cada mensagem ao seu contador). O último fragmento leva `flush = 1`, e o servidor usa essa flag para saber que a mensagem terminou.

### 5. Temporizador e retransmissão

O emissor aguarda cada ACK com **timeout de 0,2 s**. Ao estourar o tempo, retransmite conforme o modo (veja tabela). O receptor trata cada pacote assim:

| Situação do pacote recebido     | Ação do receptor                                  |
|---------------------------------|---------------------------------------------------|
| Corrompido (soma inválida)      | descartado, sem ACK                               |
| `seq` menor que o esperado (duplicado) | descartado, **ACK reenviado**              |
| `seq` maior que o esperado (fora de ordem) | descartado, sem ACK                    |
| `seq` igual ao esperado         | aceito, ACK enviado, esperado += 1                |

### 6. Comportamento por modo

| Modo                | Emissor                                                                                                                  |
|---------------------|--------------------------------------------------------------------------------------------------------------------------|
| **Individual**      | Envia 1 pacote e espera o ACK dele; em timeout reenvia **o mesmo pacote** (vale para GBN e SR)                           |
| **Lote + GBN**      | Envia até `janela` pacotes; aceita ACK **cumulativo** (`ack >= base`) e avança a base; em timeout reenvia **da base até o fim da janela** |
| **Lote + SR**       | Envia até `janela` pacotes; espera o ACK de cada pacote; em timeout reenvia **apenas o pacote** sem ACK                  |

> A lógica de recepção está na classe base `protocol_handler_t` e é a mesma para GBN e SR; as classes `go_back_n_t` e `selective_repeat_t` diferem na transmissão em lote.

### 7. Simulação de erros (cliente)

Após digitar a mensagem, é possível injetar falhas sobre uma **cópia** da mensagem (`copy.deepcopy`). Em cada rodada escolha o tipo e, quando aplicável, o índice do pacote:

| Opção | Tipo          | Efeito                                                                 |
|-------|---------------|------------------------------------------------------------------------|
| `0`   | `CORRUPTION`  | troca o payload do pacote escolhido por bytes aleatórios (soma passa a ser inválida) |
| `1`   | `DROP`        | remove o pacote escolhido da lista de envio                            |
| `2`   | `REORDER`     | embaralha a ordem dos pacotes                                          |
| `3`   | `DUPLICATE`   | duplica o pacote escolhido (a flag `flush` fica apenas na cópia)       |

Várias falhas podem ser combinadas na mesma mensagem. Enter com a opção vazia encerra a edição e envia. Se o envio com erros for interrompido com `Ctrl+C`, o cliente envia a **mensagem original** em seguida.

## Parâmetros padrão

| Parâmetro        | Padrão                            |
|------------------|-----------------------------------|
| Envio            | BATCH                             |
| Algoritmo        | GBN                               |
| Texto máx / mín  | 30 / 30                           |
| Janela           | sorteada (1–5)                    |
| Seq. inicial     | sorteado (0–10000)                |
| Timeout          | 0,2 s                             |

## Limitações conhecidas

- **Perda e corrupção ficam "permanentes":** como as falhas alteram a própria lista de pacotes do emissor, um pacote corrompido é retransmitido corrompido e um pacote removido (`DROP`) nunca é retransmitido. Nesses casos o emissor entra em laço de retransmissão até o `Ctrl+C` (que reenvia a mensagem original).
- Não há ACK negativo (NACK): a recuperação de erros depende apenas de timeout.
- O receptor da Repetição Seletiva **não armazena** pacotes fora de ordem (descarta, como no GBN).
- A janela é "em blocos": o emissor só envia a próxima janela depois de confirmar a anterior (não é uma janela deslizante contínua).
- A soma de verificação é de 8 bits, então não detecta todos os tipos de corrupção.
- O campo `seq` tem 16 bits (máx. 65535); em conexões muito longas pode estourar.
- Os logs mostram o número de sequência dos pacotes e ACKs, mas não todos os metadados (flags, soma, tamanho).
- Mensagem vazia (apenas Enter) não é tratada no cliente.
- Os limites de tamanho são medidos em **bytes** (UTF-8), não em caracteres.
- O servidor atende um cliente por vez.

## Relatório de IA

Foi utilizada Inteligência Artificial de forma auxiliar durante o desenvolvimento, especificamente para:

- Pesquisa sobre o modo de operação: envio individual (IND) vs. envio em lote (GRP)
- Pesquisa sobre a diferença entre Go-Back-N e Repetição Seletiva
- Entendimento do conceito de tamanho da janela
