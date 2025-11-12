# referencia.py
import zmq
import msgpack
import time
from datetime import datetime

context = zmq.Context()

# Socket REQ/REP para se comunicar com os servidores
rep_socket = context.socket(zmq.REP)
# Este broker não existe! O diagrama mostra o 'ref' falando
# direto com os servidores. Mas isso é complexo.
# O MAIS FÁCIL é fazer os servidores se conectarem a ele
# por um nome de serviço.
# VAMOS USAR O BROKER REQ/REP existente para isso.
rep_socket.connect("tcp://broker:5558") 

# --- ATUALIZAÇÃO ---
# O diagrama mostra uma conexão direta. Mas seu 'servidor.py'
# já usa o socket REP para se conectar ao 'broker'.
# Mudar isso é uma refatoração GIGANTE.
#
# PLANO B (MUITO MELHOR):
# O 'referencia' será um NOVO broker REQ/REP.
# Os servidores (servidor.py) terão um NOVO socket REQ
# para falar com este serviço.

# --- PLANO C (O CORRETO E MAIS SIMPLES) ---
# Vamos seguir o diagrama. O 'ref' é um novo broker.
# O 'servidor.py' vai precisar de um *novo socket REQ* para falar com ele.
# Por enquanto, vamos criar o 'referencia' e fazê-lo
# ouvir em uma porta.

# Socket REQ/REP (ROUTER) para receber conexões dos servidores
# Os servidores (servidor.py) vão conectar a esta porta
rep_socket = context.socket(zmq.ROUTER)
rep_socket.bind("tcp://*:5560") # Nova porta para o serviço de referência

print("Servidor de Referência iniciado na porta 5560...")

# Armazena os servidores (nome -> rank)
# E o último heartbeat (nome -> timestamp)
server_list = {}
server_heartbeats = {}
next_rank = 1
logical_clock = 0

def get_server_list():
    """Retorna a lista de servidores que deram heartbeat recentemente."""
    now = time.time()
    active_servers = []
    
    for name, rank in server_list.items():
        last_heartbeat = server_heartbeats.get(name, 0)
        # Considera ativo se o último heartbeat foi nos últimos 30 segundos
        if (now - last_heartbeat) < 30:
            active_servers.append({"name": name, "rank": rank})
    
    return active_servers

while True:
    try:
        # Usando ROUTER, recebemos [identidade, "", payload]
        frames = rep_socket.recv_multipart()
        identity = frames[0]
        empty = frames[1] # Frame vazio do REQ
        request_packed = frames[2]
        
        request = msgpack.unpackb(request_packed, raw=False)

        # --- LÓGICA DO RELÓGIO (RECEBER) ---
        received_clock = request.get("data", {}).get("clock", 0)
        logical_clock = max(logical_clock, received_clock)
        # --- FIM DA LÓGICA ---

        service = request.get("service")
        data = request.get("data", {})
        reply_data = {}

        # --- LÓGICA DO RELÓGIO (ENVIAR) ---
        logical_clock += 1
        # --- FIM DA LÓGICA ---

        match service:
            case "rank":
                server_name = data.get("user")
                if server_name not in server_list:
                    server_list[server_name] = next_rank
                    next_rank += 1
                
                # Registra o heartbeat também
                server_heartbeats[server_name] = time.time()
                reply_data = {"rank": server_list[server_name]}
                print(f"Servidor '{server_name}' registrado com Rank {server_list[server_name]}")

            case "list":
                reply_data = {"list": get_server_list()}
            
            case "heartbeat":
                server_name = data.get("user")
                server_heartbeats[server_name] = time.time()
                reply_data = {"status": "OK"}
                print(f"Heartbeat recebido de '{server_name}'")

            case _:
                reply_data = {"status": "erro", "description": "Serviço de referência não encontrado"}

        # Prepara a resposta
        reply = {
            "service": service,
            "data": {
                **reply_data, # Adiciona os dados do match
                "timestamp": datetime.now().isoformat(),
                "clock": logical_clock
            }
        }

        # Envia a resposta de volta ao REQ original
        rep_socket.send_multipart([
            identity,
            empty,
            msgpack.packb(reply, default=str)
        ])

    except Exception as e:
        print(f"Erro no Servidor de Referência: {e}")
        # Tenta enviar uma resposta de erro se possível
        try:
            reply = {"service": "error", "data": {"status": "erro", "clock": logical_clock}}
            rep_socket.send_multipart([identity, empty, msgpack.packb(reply, default=str)])
        except:
            pass