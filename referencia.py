# referencia.py (Atualizado para Etapa 4)
import zmq
import msgpack
import time
from datetime import datetime

context = zmq.Context()
rep_socket = context.socket(zmq.ROUTER)
rep_socket.bind("tcp://*:5560") 

print("Servidor de Referência iniciado na porta 5560...")

# --- NOVO: Estrutura de dados alterada ---
# Agora armazena o endereço P2P junto com o rank
# server_list -> { "nome_servidor": {"rank": 1, "address": "tcp://..."} }
server_list = {}
server_heartbeats = {}
next_rank = 1
logical_clock = 0

def get_server_list():
    """Retorna a lista de servidores que deram heartbeat recentemente."""
    now = time.time()
    active_servers = []
    
    for name, info in server_list.items():
        last_heartbeat = server_heartbeats.get(name, 0)
        # Considera ativo se o último heartbeat foi nos últimos 30 segundos
        if (now - last_heartbeat) < 30:
            active_servers.append({
                "name": name, 
                "rank": info["rank"],
                "address": info["address"] # <-- NOVO: Retorna o endereço
            })
    
    # Retorna ordenado pelo rank
    return sorted(active_servers, key=lambda s: s['rank'])

while True:
    try:
        frames = rep_socket.recv_multipart()
        identity = frames[0]
        empty = frames[1] 
        request_packed = frames[2]
        
        request = msgpack.unpackb(request_packed, raw=False)
        received_clock = request.get("data", {}).get("clock", 0)
        logical_clock = max(logical_clock, received_clock)

        service = request.get("service")
        data = request.get("data", {})
        reply_data = {}
        logical_clock += 1

        match service:
            case "rank":
                server_name = data.get("user")
                # --- NOVO: Recebe o endereço P2P do servidor ---
                p2p_address = data.get("p2p_address") 
                
                if server_name not in server_list:
                    server_list[server_name] = {
                        "rank": next_rank,
                        "address": p2p_address
                    }
                    next_rank += 1
                
                # Atualiza o endereço caso tenha mudado
                server_list[server_name]["address"] = p2p_address
                server_heartbeats[server_name] = time.time()
                
                reply_data = {"rank": server_list[server_name]["rank"]}
                print(f"Servidor '{server_name}' (Rank {server_list[server_name]['rank']}) registrado em '{p2p_address}'")

            case "list":
                reply_data = {"list": get_server_list()}
            
            case "heartbeat":
                server_name = data.get("user")
                if server_name in server_list:
                    server_heartbeats[server_name] = time.time()
                    reply_data = {"status": "OK"}
                    print(f"Heartbeat recebido de '{server_name}'")
                else:
                    reply_data = {"status": "erro", "description": "Servidor não registrado. Peça um 'rank' primeiro."}

            case _:
                reply_data = {"status": "erro", "description": "Serviço de referência não encontrado"}

        reply = {
            "service": service,
            "data": {
                **reply_data, 
                "timestamp": datetime.now().isoformat(),
                "clock": logical_clock
            }
        }

        rep_socket.send_multipart([
            identity,
            empty,
            msgpack.packb(reply, default=str)
        ])

    except Exception as e:
        print(f"Erro no Servidor de Referência: {e}")