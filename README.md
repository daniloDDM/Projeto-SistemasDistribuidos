# Projeto de Sistemas Distribuídos: Chat com Tolerância a Falhas

Este projeto é um sistema de chat distribuído e tolerante a falhas que implementa conceitos avançados de sistemas distribuídos. Ele utiliza uma arquitetura polyglot (Python, Go e JavaScript) e é totalmente orquestrado com Docker Compose.

O sistema é projetado para ser resiliente, com múltiplos servidores de back-end que se coordenam para eleger um líder, sincronizar relógios e replicar dados, garantindo que não haja perda de informações em caso de falha de um dos nós.

## 🚀 Conceitos Implementados

* **Arquitetura Polyglot:** Os serviços são escritos na melhor linguagem para a tarefa:
    * **Python:** Backend (Servidor, Broker, Proxy, Referência)
    * **Go:** Cliente interativo
    * **JavaScript (Node.js):** Cliente automático (bot)
* **Mensageria com ZeroMQ (ZMQ):** Utiliza os padrões REQ/REP (para comandos) e PUB/SUB (para broadcast de mensagens) para comunicação desacoplada.
* **Orquestração:** Todos os serviços são gerenciados e conectados em rede pelo Docker Compose.
* **Relógios Lógicos (Lamport):** Todos os processos (clientes e servidores) mantêm um relógio lógico para garantir a ordem causal dos eventos.
* **Serviço de Descoberta:** O serviço `referencia` atua como um coordenador centralizado, rastreando servidores ativos através de *heartbeats* e atribuindo *ranks*.
* **Eleição de Líder (Bully Algorithm):** Os servidores detectam falhas do coordenador e iniciam uma eleição (P2P) para selecionar um novo líder com base no rank.
* **Sincronização de Relógio (Christian's Algorithm):** Os servidores usam o líder eleito para sincronizar seus relógios físicos periodicamente.
* **Replicação de Dados Ativa:** Todas as operações de escrita são replicadas para todos os servidores (via PUB/SUB) para garantir consistência e tolerância a falhas.

## ⚙️ Visão Geral dos Serviços

| Serviço | Linguagem | Dockerfile | Descrição |
| :--- | :--- | :--- | :--- |
| `broker` | Python | `Dockerfile_broker` | **Broker REQ/REP.** Recebe comandos dos clientes e os balanceia (round-robin) entre os servidores. |
| `proxy` | Python | `Dockerfile_proxy` | **Broker PUB/SUB.** Recebe publicações (mensagens de chat, replicação) e as transmite para todos os inscritos. |
| `referencia` | Python | `Dockerfile_referencia` | **Serviço de Descoberta.** Atribui ranks aos servidores, recebe *heartbeats* e fornece a lista de servidores ativos. |
| `servidor` | Python | `Dockerfile_servidor` | **Servidor de Lógica (Réplicas: 3).** Processa a lógica de negócio (login, etc.), participa da eleição, sincroniza relógios e replica dados. |
| `cliente` | Go | `Dockerfile_cliente_go` | **Cliente Interativo.** Permite que um usuário humano envie comandos (REQ) e receba mensagens (SUB). |
| `cliente_automatico` | JavaScript | `Dockerfile_cliente_automatico_js` | **Bot.** Cliente automatizado que faz login e envia mensagens em loop para gerar carga e testar a replicação. |

## 🚀 Como Executar

O projeto é totalmente conteinerizado. Você só precisa do Docker e Docker Compose instalados.

1.  **Construir e Iniciar todos os serviços (em segundo plano):**
    ```bash
    docker compose up --build -d
    ```

2.  **Visualizar os logs (recomendado):**
    Para ver a eleição, replicação e sincronia acontecendo em tempo real.
    ```bash
    docker compose logs -f servidor referencia
    ```

3.  **Executar o Cliente Interativo (em Go):**
    Abra um novo terminal e use o `run` para iniciar o cliente interativo.
    ```bash
    docker compose run cliente
    ```

4.  **Escalar os Bots (Clientes Automáticos):**
    Para simular múltiplos clientes, você pode escalar o `cliente_automatico`.
    ```bash
    docker compose up -d --scale cliente_automatico=5
    ```

5.  **Parar tudo:**
    ```bash
    docker compose down -v
    ```

---

## Parte 5: Consistência e Replicação

### Problema

O `broker` (padrão REQ/REP) distribui as requisições de escrita (`login`, `channel`, `publish`, `msg`) entre as 3 réplicas do servidor usando *round-robin*. Isso resulta em cada servidor possuindo apenas uma fração do estado total (usuários, canais) e do histórico de mensagens, levando à perda de dados em caso de falha de um servidor.

### Método de Implementação: Replicação Ativa via PUB/SUB

Para resolver este problema, foi implementado um modelo de **Replicação Ativa** com **Consistência Eventual**.

A escolha se deu por este método se integrar perfeitamente à arquitetura de *proxy* PUB/SUB (XSUB/XPUB) já existente no projeto.

#### Troca de Mensagens para Replicação

O fluxo de replicação de dados funciona da seguinte maneira:

1.  **Requisição de Escrita:** Um cliente envia uma requisição de escrita (ex: `login`) ao `broker`.
2.  **Processamento Primário:** O `broker` encaminha a requisição para um servidor (ex: **Servidor 1**). A *thread principal* do Servidor 1 processa a requisição, salva a alteração em seus arquivos locais (`users.json`, `channels.json` ou `messages.jsonl`) e envia a resposta de `OK` (REP) de volta ao cliente.
3.  **Publicação (Broadcast):** Imediatamente após o salvamento local, a *thread principal* do Servidor 1 também **publica (PUB)** a requisição original completa em um tópico interno chamado `replication` no *proxy* PUB/SUB.
4.  **Processamento da Réplica (SUB):**
    * Todos os servidores (incluindo o Servidor 1) possuem uma *thread P2P* que está inscrita (SUB) no tópico `replication`.
    * O *proxy* transmite a requisição para **todos** os servidores (Servidor 1, 2 e 3).
    * Ao receberem a mensagem no tópico `replication`, as *threads P2P* de todos os servidores invocam a função `handle_replication()`.
5.  **Escrita Replicada:** A função `handle_replication()` executa a mesma lógica de escrita do passo 2 (salva em `users.json`, `channels.json`, etc.).

#### Resultado

* **Tolerância a Falhas:** Todos os servidores agora possuem uma cópia idêntica dos arquivos `users.json`, `channels.json` e `messages.jsonl`. Se um servidor falhar, nenhum dado é perdido.
* **Consistência Eventual:** O cliente recebe uma resposta rápida (baixa latência) do Servidor 1. Os Servidores 2 e 3 se tornam consistentes alguns milissegundos depois, quando recebem e processam a mensagem `replication`.
* **Idempotência:** O Servidor 1 (o originador) recebe sua própria mensagem de replicação e a processa uma segunda vez (uma vez na thread principal, outra na thread P2P). Isso é intencional e seguro, pois as operações de escrita (salvar em dicionário, adicionar em arquivo `.jsonl`) são idempotentes ou seguras para repetição.
