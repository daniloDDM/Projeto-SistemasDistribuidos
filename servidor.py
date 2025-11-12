# servidor.py (Atualizado para Etapa 3)
import zmq
import json
from datetime import datetime
import os
import msgpack
import threading # <-- NOVO: Importa threading
import time        # <-- NOVO: Para o sleep do heartbeat
import random      # <-- NOVO: Para o nome do servidor

# --- Constantes de Caminho ---
DATA_PATH = "/app/data"
USERS_FILE = os.path.join(DATA_PATH, "users.json")
CHANNELS_FILE = os.path.join(DATA_PATH, "channels.json")
MESSAGES_FILE = os.path.join(DATA_PATH, "messages.jsonl")

# --- NOVO: Variáveis Globais de Servidor ---
logical_clock = 0
# O nome precisa ser único para cada réplica no docker-compose
server_name = f"server_{random.randint(1000, 9999)}"
server_rank = None
# O Mutex é ESSENCIAL para proteger o logical_clock
clock_mutex = threading.Lock()
# --- FIM NOVO ---


# --- Inicialização do ZeroMQ ---
context = zmq.Context()

# --- Socket 1: REQ/REP (Para comandos de clientes) ---
rep_socket = context.socket(zmq.REP)
rep_socket.connect("tcp://broker:5558")

# --- Socket 2: PUB (Para publicar mensagens) ---
pub_socket = context.socket(zmq.PUB)
pub_socket.connect("tcp://proxy:5555") 


# --- Funções de Persistência ---
# (load_data, save_data, save_message ... sem mudanças)
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
        print(f"[ERRO AO SALVAR MENSAGEM] {e}")

# Carrega os dados
users = load_data(USERS_FILE)
channels = load_data(CHANNELS_FILE)

# --- NOVO: Thread de Heartbeat ---
def heartbeat_thread():
    """
    Esta thread cuida de se registrar no 'referencia' e
    enviar heartbeats periódicos.
    """
    global logical_clock, server_rank
    
    # Cada thread deve criar seu próprio socket
    ref_socket = context.socket(zmq.REQ)
    ref_socket.connect("tcp://referencia:5560")
    
    print(f"Servidor '{server_name}' iniciando thread de heartbeat...")
    
    # 1. Pedir Rank (ao iniciar)
    try:
        # Pede o lock para atualizar o clock
        with clock_mutex:
            logical_clock += 1
            rank_req = {
                "service": "rank",
                "data": {
                    "user": server_name, # Envia o nome único
                    "timestamp": datetime.now().isoformat(),
                    "clock": logical_clock
                }
            }
        
        ref_socket.send(msgpack.packb(rank_req, default=str))
        
        reply_packed = ref_socket.recv()
        reply = msgpack.unpackb(reply_packed, raw=False)
        
        # Atualiza o clock com a resposta
        with clock_mutex:
            received_clock = reply.get("data", {}).get("clock", 0)
            logical_clock = max(logical_clock, received_clock)
            
        server_rank = reply.get("data", {}).get("rank")
        print(f"*** SERVIDOR '{server_name}' REGISTRADO COM RANK: {server_rank} (Clock: {logical_clock}) ***")

    except Exception as e:
        print(f"[ERRO NO REGISTRO DE RANK] {e}")

    # 2. Loop de Heartbeat
    while True:
        try:
            # Espera 15 segundos entre heartbeats
            time.sleep(15)
            
            with clock_mutex:
                logical_clock += 1
                heartbeat_req = {
                    "service": "heartbeat",
                    "data": {
                        "user": server_name,
                        "timestamp": datetime.now().isoformat(),
                        "clock": logical_clock
                    }
                }
            
            ref_socket.send(msgpack.packb(heartbeat_req, default=str))
            
            reply_packed = ref_socket.recv()
            reply = msgpack.unpackb(reply_packed, raw=False)
            
            # Atualiza o clock com a resposta
            with clock_mutex:
                received_clock = reply.get("data", {}).get("clock", 0)
                logical_clock = max(logical_clock, received_clock)
            
            print(f"[{server_name}] Heartbeat enviado com sucesso. (Clock: {logical_clock})")

        except Exception as e:
            print(f"[{server_name}] Erro no heartbeat: {e}")
            # Tenta reconectar se falhar
            ref_socket.close()
            time.sleep(5)
            ref_socket = context.socket(zmq.REQ)
            ref_socket.connect("tcp://referencia:5560")

# --- FIM DA THREAD ---


# --- Inicia a Thread de Heartbeat ANTES do loop principal ---
hb_thread = threading.Thread(target=heartbeat_thread, daemon=True)
hb_thread.start()
# --- FIM NOVO ---

print(f"Servidor '{server_name}' REQ/REP e PUB iniciado, aguardando clientes...")

# --- Loop Principal (Processando comandos de clientes) ---
while True:
    try:
        frames = rep_socket.recv_multipart()
        request_packed = frames[-1]
        request = msgpack.unpackb(request_packed, raw=False)
        
        # --- NOVO: LÓGICA DO RELÓGIO (RECEBER) COM MUTEX ---
        received_clock = request.get("data", {}).get("clock", 0)
        with clock_mutex:
            logical_clock = max(logical_clock, received_clock)
        # --- FIM NOVO ---

    except Exception as e:
        print(f"ERRO GERAL no recebimento REQ/REP: {e}")
        # (código de erro sem mudança)
        continue

    service = request.get("service")
    data = request.get("data", {})
    reply = {} 

    print(f"[{server_name}] Requisição REQ/REP (Clock: {received_clock}): {request}")

    # --- NOVO: LÓGICA DO RELÓGIO (ENVIAR) COM MUTEX ---
    current_clock_for_reply = 0
    with clock_mutex:
        logical_clock += 1
        current_clock_for_reply = logical_clock
    # --- FIM NOVO ---

    match service:
        # ... (Casos "login", "users", "channel", "channels" sem mudança de lógica) ...
        case "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            reply = {"service": "login", "data": {}}
            if user_name not in users:
                users[user_name] = {"timestamp": timestamp}
                save_data(users, USERS_FILE)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Usuário já existe"
        
        case "users":
            reply = {"service": "users", "data": {"users": list(users.keys())}}

        case "channel":
            channel_name = data.get("channel")
            timestamp = data.get("timestamp")
            reply = {"service": "channel", "data": {}}
            if channel_name not in channels:
                channels[channel_name] = {"timestamp": timestamp}
                save_data(channels, CHANNELS_FILE)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Canal já existe"

        case "channels":
            reply = {"service": "channels", "data": {"channels": list(channels.keys())}}

        # --- LÓGICA DE PUBLICAÇÃO REAL ---
        case "publish":
            channel_name = data.get("channel")
            user_name = data.get("user")
            message = data.get("message")
            
            reply["service"] = "publish"
            
            if channel_name not in channels:
                reply["data"] = {"status": "erro", "message": "Canal não existe."}
            else:
                message_payload = {
                    "user": user_name,
                    "message": message,
                    "timestamp": data.get("timestamp"),
                    "clock": current_clock_for_reply # <-- NOVO: Usa o clock protegido
                }
                
                message_to_log = {
                    "type": "channel",
                    "channel": channel_name,
                    "user": user_name,
                    "message": message,
                    "timestamp": data.get("timestamp")
                }
                save_message(message_to_log, MESSAGES_FILE)
                
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
                    "src": src_user,
                    "message": message,
                    "timestamp": data.get("timestamp"),
                    "clock": current_clock_for_reply # <-- NOVO: Usa o clock protegido
                }
                
                message_to_log = {
                    "type": "private",
                    "from_user": src_user,
                    "to_user": dest_user,
                    "message": message,
                    "timestamp": data.get("timestamp")
                }
                save_message(message_to_log, MESSAGES_FILE)
                
                topic = f"user:{dest_user}"
                
                pub_socket.send_multipart([
                    topic.encode('utf-8'),
                    msgpack.packb(message_payload, default=str)
                ])
                
                reply["data"] = {"status": "OK", "message": "Mensagem privada enviada."}

        case _:
            reply = {"service": "erro", "data": {"status": "erro", "description": "Serviço não encontrado"}}

    # --- ENVIA A RESPOSTA REQ/REP ---
    if "data" not in reply:
        reply["data"] = {}
    
    reply["data"]["timestamp"] = datetime.now().isoformat()
    reply["data"]["clock"] = current_clock_for_reply # <-- NOVO: Usa o clock protegido

    reply_packed = msgpack.packb(reply, default=str) 
    rep_socket.send(reply_packed)