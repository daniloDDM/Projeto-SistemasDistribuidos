## Parte 5: Consistência e Replicação

### Problema

O `broker` (padrão REQ/REP) distribui as requisições de escrita (`login`, `channel`, `publish`, `msg`) entre as 3 réplicas do servidor usando *round-robin*. Isso resulta em cada servidor possuindo apenas uma fração do estado total (usuários, canais) e do histórico de mensagens, levando à perda de dados em caso de falha de um servidor.

### Método de Implementação: Replicação Ativa via PUB/SUB

Para resolver este problema, foi implementado um modelo de **Replicação Ativa** (também conhecido como *Primary-Copy* onde todos são *primary*), com **Consistência Eventual**.

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