# servidor.py (Versão Final - Etapa 5: Replicação)
import zmq
import json
from datetime import datetime
import os
import msgpack
import threading
import time
import random

# --- Constantes de Caminho ---
DATA_PATH = "/app/data"
USERS_FILE = os.path.join(DATA_PATH, "users.json")
CHANNELS_FILE = os.path.join(DATA_PATH, "channels.json")
MESSAGES_FILE = os.path.join(DATA_PATH, "messages.jsonl")

# --- Constantes de Rede ---
P2P_PORT = 5570
ELECTION_TIMEOUT = 2.0 

# --- Variáveis Globais de Servidor ---
logical_clock = 0
default_name = f"server_{random.randint(1000, 9999)}"
server_name = os.environ.get("SERVER_NAME", default_name)
p2p_address = f"tcp://{server_name}:{P2P_PORT}"

server_rank = None
clock_mutex = threading.Lock()

coordinator_name = None
active_servers = [] 
message_counter = 0 
MSG_COUNT_TRIGGER = 10 
election_in_progress = threading.Lock() 


# --- Inicialização do ZeroMQ ---
context = zmq.Context()

# --- Socket 1: (Main Thread) REQ/REP para Clientes ---
rep_socket = context.socket(zmq.REP)
rep_socket.connect("tcp://broker:5558")

# --- Socket 2: (Main Thread) PUB para Clientes ---
pub_socket = context.socket(zmq.PUB)
pub_socket.connect("tcp://proxy:5555") 

# (As funções de persistência load_data, save_data, save_message não mudam)
def load_data(filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True) 
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                content = f.read()
                return json.loads(content) if content else {}
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def save_message(data_dict, filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        json_line = json.dumps(data_dict)
        with open(filename, 'a') as f:
            f.write(json_line + '\n')
    except Exception as e:
        print(f"[{server_name}] [ERRO AO SALVAR MENSAGEM] {e}")

# Carrega os dados
users = load_data(USERS_FILE)
channels = load_data(CHANNELS_FILE)

def replicate_request(request):
    """Publica a requisição original em um tópico de replicação."""
    try:
        # print(f"[{server_name}] Replicando: {request.get('service')}")
        pub_socket.send_multipart([
            b"replication", # O tópico
            msgpack.packb(request, default=str) # O payload é a requisição inteira
        ])
    except Exception as e:
        print(f"[{server_name}] Erro ao replicar request: {e}")

def handle_replication(request):
    """
    Processa uma requisição replicada recebida do tópico PUB/SUB.
    Apenas executa a lógica de *escrita*.
    """
    global users, channels # Precisa modificar o global
    service = request.get("service")
    data = request.get("data", {})

    try:
        if service == "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            if user_name and user_name not in users:
                with clock_mutex: # Protege o 'users' dict e o 'save_data'
                    users[user_name] = {"timestamp": timestamp}
                    save_data(users, USERS_FILE)
                print(f"[{server_name}] REPLICADO login: {user_name}")

        elif service == "channel":
            channel_name = data.get("channel")
            timestamp = data.get("timestamp")
            if channel_name and channel_name not in channels:
                with clock_mutex: # Protege 'channels' e 'save_data'
                    channels[channel_name] = {"timestamp": timestamp}
                    save_data(channels, CHANNELS_FILE)
                print(f"[{server_name}] REPLICADO canal: {channel_name}")
        
        elif service == "publish":
            message_to_log = {
                "type": "channel",
                "channel": data.get("channel"),
                "user": data.get("user"),
                "message": data.get("message"),
                "timestamp": data.get("timestamp")
            }
            save_message(message_to_log, MESSAGES_FILE) # save_message já é thread-safe
            print(f"[{server_name}] REPLICADO publish: {data.get('user')} -> {data.get('channel')}")

        elif service == "message":
            message_to_log = {
                "type": "private",
                "from_user": data.get("src"),
                "to_user": data.get("dst"),
                "message": data.get("message"),
                "timestamp": data.get("timestamp")
            }
            save_message(message_to_log, MESSAGES_FILE)
            print(f"[{server_name}] REPLICADO msg: {data.get('src')} -> {data.get('dst')}")

    except Exception as e:
        print(f"[{server_name}] Erro ao processar replicação {service}: {e}")


def p2p_listener_thread():
    """
    Ouve por conexões P2P de *outros servidores* (Eleição, Clock)
    e por anúncios no Proxy (Eleição, Replicação).
    """
    global logical_clock, coordinator_name, server_rank
    
    p2p_router_socket = context.socket(zmq.ROUTER)
    p2p_router_socket.bind(f"tcp://*:{P2P_PORT}")
    print(f"[{server_name}] Listener P2P (ROUTER) iniciado em tcp://*:{P2P_PORT}")
    
    p2p_sub_socket = context.socket(zmq.SUB)
    p2p_sub_socket.connect("tcp://proxy:5556")
    p2p_sub_socket.setsockopt_string(zmq.SUBSCRIBE, "servers")
    p2p_sub_socket.setsockopt_string(zmq.SUBSCRIBE, "replication") # <-- NOVO
    print(f"[{server_name}] Listener P2P (SUB) inscrito em 'servers' e 'replication'")

    poller = zmq.Poller()
    poller.register(p2p_router_socket, zmq.POLLIN)
    poller.register(p2p_sub_socket, zmq.POLLIN)

    while True:
        try:
            socks = dict(poller.poll())

            if p2p_router_socket in socks:
                frames = p2p_router_socket.recv_multipart()
                identity, empty, request_packed = frames
                request = msgpack.unpackb(request_packed, raw=False)
                
                with clock_mutex:
                    received_clock = request.get("data", {}).get("clock", 0)
                    logical_clock = max(logical_clock, received_clock)
                
                service = request.get("service")
                data = request.get("data", {})
                reply_data = {}

                with clock_mutex:
                    logical_clock += 1
                    current_clock = logical_clock
                
                print(f"[{server_name}] Recebeu P2P '{service}' (Clock: {received_clock})")
                
                if service == "election":
                    reply_data = {"election": "OK"}
                    sender_rank = data.get("rank", 0)
                    if server_rank is not None and sender_rank < server_rank:
                        threading.Thread(target=start_election, daemon=True).start()

                elif service == "clock":
                    reply_data = {"time": time.time_ns()}

                reply = {
                    "service": service, 
                    "data": {**reply_data, "timestamp": datetime.now().isoformat(), "clock": current_clock}
                }
                p2p_router_socket.send_multipart([identity, empty, msgpack.packb(reply, default=str)])

            # --- 2. Anúncio (SUB) ---
            if p2p_sub_socket in socks:
                topic_bytes, payload_packed = p2p_sub_socket.recv_multipart()
                topic = topic_bytes.decode('utf-8')
                payload = msgpack.unpackb(payload_packed, raw=False)
                
                # O payload de replicação é a *própria request*
                # O payload de eleição tem um 'data'
                received_clock = 0
                if topic == "replication":
                    received_clock = payload.get("data", {}).get("clock", 0)
                else: # topic == "servers"
                    received_clock = payload.get("data", {}).get("clock", 0)
                
                with clock_mutex:
                    logical_clock = max(logical_clock, received_clock)
                
                if topic == "servers":
                    service = payload.get("service")
                    if service == "election":
                        new_coordinator = payload.get("data", {}).get("coordinator")
                        coordinator_name = new_coordinator
                        print(f"*** [{server_name}] NOVO COORDENADOR ELEITO: {coordinator_name} (Clock: {received_clock}) ***")
                
                elif topic == "replication":
                    # --- NOVO: Lidar com replicação ---
                    handle_replication(payload)

        except Exception as e:
            print(f"[{server_name}] Erro na thread P2P: {e}")

def heartbeat_thread():
    """
    Cuida de se registrar, enviar heartbeats, e
    INICIAR a lógica de eleição e sincronia.
    """
    global logical_clock, server_rank, coordinator_name, active_servers
    
    # Socket 5: (Thread HB) REQ para o Servidor de Referência
    ref_socket = context.socket(zmq.REQ)
    ref_socket.connect("tcp://referencia:5560")
    
    print(f"Servidor '{server_name}' iniciando thread de heartbeat...")
    
    # 1. Pedir Rank
    try:
        with clock_mutex:
            logical_clock += 1
            rank_req = {
                "service": "rank",
                "data": {
                    "user": server_name,
                    "p2p_address": p2p_address,
                    "timestamp": datetime.now().isoformat(),
                    "clock": logical_clock
                }
            }
        
        ref_socket.send(msgpack.packb(rank_req, default=str))
        reply = msgpack.unpackb(ref_socket.recv(), raw=False)
        
        with clock_mutex:
            received_clock = reply.get("data", {}).get("clock", 0)
            logical_clock = max(logical_clock, received_clock)
            
        server_rank = reply.get("data", {}).get("rank")
        print(f"*** SERVIDOR '{server_name}' REGISTRADO COM RANK: {server_rank} (Endereço: {p2p_address}) ***")

    except Exception as e:
        print(f"[{server_name}] [ERRO NO REGISTRO DE RANK] {e}")

    # 2. Loop de Heartbeat e Lógica de Sincronia
    while True:
        try:
            time.sleep(15)
            
            # --- A. Enviar Heartbeat ---
            with clock_mutex:
                logical_clock += 1
                heartbeat_req = {
                    "service": "heartbeat",
                    "data": {"user": server_name, "timestamp": datetime.now().isoformat(), "clock": logical_clock}
                }
            
            ref_socket.send(msgpack.packb(heartbeat_req, default=str))
            reply = msgpack.unpackb(ref_socket.recv(), raw=False)
            
            with clock_mutex:
                received_clock = reply.get("data", {}).get("clock", 0)
                logical_clock = max(logical_clock, received_clock)
            
            # --- B. Pedir Lista de Servidores ---
            with clock_mutex:
                logical_clock += 1
                list_req = {"service": "list", "data": {"timestamp": datetime.now().isoformat(), "clock": logical_clock}}
            
            ref_socket.send(msgpack.packb(list_req, default=str))
            list_reply = msgpack.unpackb(ref_socket.recv(), raw=False)
            
            with clock_mutex:
                list_clock = list_reply.get("data", {}).get("clock", 0)
                logical_clock = max(logical_clock, list_clock)
            
            active_servers = list_reply.get("data", {}).get("list", [])
            # print(f"[{server_name}] Servidores Ativos: {[s['name'] for s in active_servers]}")

            # --- C. Lógica de Eleição (Trigger) ---
            if server_rank is None:
                continue # Não faz nada se ainda não tem rank
            
            coordinator_is_alive = False
            if coordinator_name:
                for s in active_servers:
                    if s["name"] == coordinator_name:
                        coordinator_is_alive = True
                        break
            
            # Trigger: (Não tem coordenador OU o coordenador está morto) E uma eleição não está em progresso
            if (not coordinator_name or not coordinator_is_alive) and election_in_progress.acquire(blocking=False):
                print(f"[{server_name}] Coordenador '{coordinator_name}' está offline. Iniciando eleição.")
                threading.Thread(target=start_election, daemon=True).start()

        except Exception as e:
            print(f"[{server_name}] Erro no loop de heartbeat: {e}")
            ref_socket.close()
            time.sleep(5)
            ref_socket = context.socket(zmq.REQ)
            ref_socket.connect("tcp://referencia:5560")

def announce_new_coordinator():
    """Anuncia a todos (via PUB) que este servidor é o novo coordenador."""
    global coordinator_name, logical_clock
    
    if coordinator_name == server_name:
        print(f"[{server_name}] Já sou o coordenador, não preciso anunciar.")
        return

    print(f"*** [{server_name}] ME ELEGI COMO NOVO COORDENADOR! ***")
    coordinator_name = server_name
    
    with clock_mutex:
        logical_clock += 1
        announcement = {
            "service": "election",
            "data": {
                "coordinator": server_name,
                "timestamp": datetime.now().isoformat(),
                "clock": logical_clock
            }
        }
    
    # Usa o socket PUB da thread principal para anunciar no tópico 'servers'
    try:
        pub_socket.send_multipart([
            b"servers",
            msgpack.packb(announcement, default=str)
        ])
    except Exception as e:
        print(f"[{server_name}] Erro ao anunciar coordenador: {e}")

def start_election():
    """Inicia o Bully Algorithm."""
    global server_rank, active_servers, election_in_progress
    
    try:
        higher_rank_servers = [s for s in active_servers if s["rank"] > server_rank]
        
        if not higher_rank_servers:
            # Não há ninguém com rank maior. Eu sou o líder.
            announce_new_coordinator()
            return

        print(f"[{server_name}] Enviando 'election' para {len(higher_rank_servers)} servidores com rank maior.")
        
        responses = 0
        poller = zmq.Poller()
        sockets = []
        
        for server in higher_rank_servers:
            # Conecta em cada servidor com rank maior
            p2p_socket = context.socket(zmq.REQ)
            # Define um timeout de envio e recebimento curto
            p2p_socket.setsockopt(zmq.RCVTIMEO, int(ELECTION_TIMEOUT * 1000 / 2))
            p2p_socket.setsockopt(zmq.SNDTIMEO, int(ELECTION_TIMEOUT * 1000 / 2))
            p2p_socket.connect(server["address"])
            sockets.append(p2p_socket)
            
            poller.register(p2p_socket, zmq.POLLIN)
            
            with clock_mutex:
                logical_clock += 1
                req = {
                    "service": "election",
                    "data": {"rank": server_rank, "timestamp": datetime.now().isoformat(), "clock": logical_clock}
                }
            p2p_socket.send(msgpack.packb(req, default=str))

        # Espera por respostas (com timeout)
        start_time = time.time()
        while time.time() - start_time < ELECTION_TIMEOUT:
            socks = dict(poller.poll(timeout=100)) # Poll curto
            for s in sockets:
                if s in socks:
                    # Alguém respondeu 'OK'
                    try:
                        reply = msgpack.unpackb(s.recv(), raw=False)
                        if reply.get("data", {}).get("election") == "OK":
                            responses += 1
                    except:
                        pass # Ignora erro de recv
            if responses > 0:
                break # Alguém respondeu, podemos parar
        
        for s in sockets:
            s.close() # Fecha todos os sockets

        if responses == 0:
            # Ninguém com rank maior respondeu. Eu sou o líder.
            announce_new_coordinator()
        else:
            # Alguém com rank maior respondeu. Eu perdi.
            print(f"[{server_name}] Eleição perdida. {responses} servidor(es) de rank maior responderam.")
    
    except Exception as e:
        print(f"[{server_name}] Erro durante a eleição: {e}")
    finally:
        # Libera o lock para que outra eleição possa começar se necessário
        election_in_progress.release()


def sync_clock_with_coordinator():
    """Pede o relógio ao coordenador (Christian's Algorithm)."""
    global logical_clock, message_counter
    
    if not coordinator_name or server_name == coordinator_name:
        message_counter = 0
        return
    
    print(f"[{server_name}] Contador atingiu {MSG_COUNT_TRIGGER}. Sincronizando relógio com o Coordenador ({coordinator_name})...")
    
    try:
        # Pega o endereço do coordenador
        coord_address = None
        for s in active_servers:
            if s["name"] == coordinator_name:
                coord_address = s["address"]
                break
        
        if not coord_address:
            print(f"[{server_name}] Não foi possível encontrar o endereço do coordenador. Abortando sincronia.")
            message_counter = 0 # Zera mesmo se falhar
            return

        # Conecta, envia, recebe
        sync_socket = context.socket(zmq.REQ)
        sync_socket.setsockopt(zmq.RCVTIMEO, 2000) # 2s timeout
        sync_socket.setsockopt(zmq.SNDTIMEO, 2000) # 2s timeout
        sync_socket.connect(coord_address)
        
        with clock_mutex:
            logical_clock += 1
            req = {"service": "clock", "data": {"timestamp": datetime.now().isoformat(), "clock": logical_clock}}
        
        t0 = time.time_ns()
        sync_socket.send(msgpack.packb(req, default=str))
        
        reply_packed = sync_socket.recv()
        t1 = time.time_ns()
        
        reply = msgpack.unpackb(reply_packed, raw=False)
        
        with clock_mutex:
            received_clock = reply.get("data", {}).get("clock", 0)
            logical_clock = max(logical_clock, received_clock)
        
        # Lógica de Christian's Algorithm
        rtt = t1 - t0
        coordinator_time_ns = reply.get("data", {}).get("time", 0)
        
        # Tempo estimado do coordenador = (Tempo dele) + (Metade do Round Trip Time)
        estimated_coordinator_time = coordinator_time_ns + (rtt / 2)
        my_time_ns = t1
        
        time_diff = estimated_coordinator_time - my_time_ns
        
        print(f"[{server_name}] Sincronia: Meu tempo está {time_diff / 1_000_000:,.2f} ms diferente do coordenador.")
        # Em um sistema real, você ajustaria o relógio (time.settime() ou apenas um offset)
        
        sync_socket.close()

    except Exception as e:
        print(f"[{server_name}] Erro ao sincronizar relógio: {e}")
    finally:
        message_counter = 0 # Zera o contador


# --- Inicia as Threads ---
p2p_thread = threading.Thread(target=p2p_listener_thread, daemon=True)
p2p_thread.start()

hb_thread = threading.Thread(target=heartbeat_thread, daemon=True)
hb_thread.start()
# --- FIM ---


print(f"Servidor '{server_name}' REQ/REP e PUB (Main Thread) iniciado, aguardando clientes...")

# --- Loop Principal (Processando comandos de clientes) ---
while True:
    try:
        frames = rep_socket.recv_multipart()
        request_packed = frames[-1]
        request = msgpack.unpackb(request_packed, raw=False)
        
        received_clock = request.get("data", {}).get("clock", 0)
        with clock_mutex:
            logical_clock = max(logical_clock, received_clock)

    except Exception as e:
        print(f"[{server_name}] ERRO GERAL no recebimento REQ/REP: {e}")
        continue

    service = request.get("service")
    data = request.get("data", {})
    reply = {} 

    print(f"[{server_name}] Requisição REQ/REP (Clock: {received_clock}): {request}")

    # Trigger do Berkeley/Christian's
    message_counter += 1
    if message_counter >= MSG_COUNT_TRIGGER and coordinator_name != server_name:
        threading.Thread(target=sync_clock_with_coordinator, daemon=True).start()

    current_clock_for_reply = 0
    with clock_mutex:
        logical_clock += 1
        current_clock_for_reply = logical_clock
    
    
    match service:
        # --- LÓGICA DE ESCRITA ---
        # (login, channel, publish, message)
        
        case "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            reply = {"service": "login", "data": {}}
            if user_name not in users:
                users[user_name] = {"timestamp": timestamp}
                save_data(users, USERS_FILE)
                replicate_request(request)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Usuário já existe"
        
        case "channel":
            channel_name = data.get("channel")
            timestamp = data.get("timestamp")
            reply = {"service": "channel", "data": {}}
            if channel_name not in channels:
                channels[channel_name] = {"timestamp": timestamp}
                save_data(channels, CHANNELS_FILE)
                replicate_request(request)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Canal já existe"

        case "publish":
            channel_name = data.get("channel")
            user_name = data.get("user")
            message = data.get("message")
            reply["service"] = "publish"
            
            if channel_name not in channels:
                reply["data"] = {"status": "erro", "message": "Canal não existe."}
            else:
                message_payload = {
                    "user": user_name, "message": message,
                    "timestamp": data.get("timestamp"), "clock": current_clock_for_reply 
                }
                message_to_log = {
                    "type": "channel", "channel": channel_name, "user": user_name,
                    "message": message, "timestamp": data.get("timestamp")
                }
                save_message(message_to_log, MESSAGES_FILE)
                replicate_request(request)
                
                pub_socket.send_multipart([
                    channel_name.encode('utf-8'),
                    msgpack.packb(message_payload, default=str)
                ])
                reply["data"] = {"status": "OK", "message": "Mensagem publicada."}

        case "message":
            dest_user = data.get("dst")
            src_user = data.get("src")
            message = data.get("message")
            reply["service"] = "message"
            
            if dest_user not in users:
                reply["data"] = {"status": "erro", "message": "Usuário de destino não existe."}
            else:
                message_payload = {
                    "src": src_user, "message": message,
                    "timestamp": data.get("timestamp"), "clock": current_clock_for_reply
                }
                message_to_log = {
                    "type": "private", "from_user": src_user, "to_user": dest_user,
                    "message": message, "timestamp": data.get("timestamp")
                }
                save_message(message_to_log, MESSAGES_FILE)
                replicate_request(request)
                
                topic = f"user:{dest_user}"
                pub_socket.send_multipart([
                    topic.encode('utf-8'),
                    msgpack.packb(message_payload, default=str)
                ])
                reply["data"] = {"status": "OK", "message": "Mensagem privada enviada."}

        # --- LÓGICA DE LEITURA ---
        # (users, channels)
        
        case "users":
            reply = {"service": "users", "data": {"users": list(users.keys())}}

        case "channels":
            reply = {"service": "channels", "data": {"channels": list(channels.keys())}}

        case _:
            reply = {"service": "erro", "data": {"status": "erro", "description": "Serviço não encontrado"}}

    # --- ENVIA A RESPOSTA REQ/REP ---
    if "data" not in reply:
        reply["data"] = {}
    
    reply["data"]["timestamp"] = datetime.now().isoformat()
    reply["data"]["clock"] = current_clock_for_reply

    reply_packed = msgpack.packb(reply, default=str) 
    rep_socket.send(reply_packed)