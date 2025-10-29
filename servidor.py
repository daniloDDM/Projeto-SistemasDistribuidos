import zmq
import json
from datetime import datetime
import os
import msgpack

# --- Inicialização do ZeroMQ ---
context = zmq.Context()

# --- Socket 1: REQ/REP (Para comandos) ---
rep_socket = context.socket(zmq.REP)
rep_socket.connect("tcp://broker:5558")

# --- Socket 2: PUB (Para publicar mensagens) ---
pub_socket = context.socket(zmq.PUB)
pub_socket.connect("tcp://proxy:5555") 


# --- Funções de Persistência ---
def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                content = f.read()
                return json.loads(content) if content else {}
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Carrega os dados
users = load_data("users.json")
channels = load_data("channels.json")

print("Servidor REQ/REP e PUB iniciado...")

# --- Loop Principal (Processando comandos) ---
while True:
    try:
        # 1. RECEBE COMANDOS do socket REQ/REP
        frames = rep_socket.recv_multipart()
        request_packed = frames[-1]
        request = msgpack.unpackb(request_packed, raw=False)
        
    except Exception as e:
        print(f"ERRO GERAL no recebimento REQ/REP: {e}")
        error_reply = msgpack.packb({"service": "erro", "data": {"status": "erro", "description": "Erro interno no servidor."}}, default=str)
        rep_socket.send(error_reply)
        continue

    service = request.get("service")
    data = request.get("data", {})
    reply = {} # Resposta para o cliente REQ

    print(f"Requisição REQ/REP recebida: {request}")

    match service:
        # ... (Casos "login", "users", "channel", "channels" permanecem os mesmos) ...
        case "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            reply = {"service": "login", "data": {"timestamp": datetime.now().isoformat()}}
            if user_name not in users:
                users[user_name] = {"timestamp": timestamp}
                save_data(users, "users.json")
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Usuário já existe"
        
        case "users":
            reply = {"service": "users", "data": {"timestamp": datetime.now().isoformat(), "users": list(users.keys())}}

        case "channel":
            channel_name = data.get("channel")
            timestamp = data.get("timestamp")
            reply = {"service": "channel", "data": {"timestamp": datetime.now().isoformat()}}
            if channel_name not in channels:
                channels[channel_name] = {"timestamp": timestamp}
                save_data(channels, "channels.json")
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Canal já existe"

        case "channels":
            reply = {"service": "channels", "data": {"timestamp": datetime.now().isoformat(), "channels": list(channels.keys())}}
        

        # --- LÓGICA DE PUBLICAÇÃO REAL ---
        case "publish":
            channel_name = data.get("channel")
            user_name = data.get("user")
            message = data.get("message")
            
            reply["service"] = "publish"
            
            if channel_name not in channels:
                reply["data"] = {"status": "erro", "message": "Canal não existe."}
            else:
                # 1. Prepara a mensagem a ser publicada
                message_payload = {
                    "user": user_name,
                    "message": message,
                    "timestamp": data.get("timestamp")
                }
                
                # 2. PUBLICA A MENSAGEM (Tópico + Payload MessagePack)
                pub_socket.send_multipart([
                    channel_name.encode('utf-8'),               # Frame 1: Tópico (Bytes)
                    msgpack.packb(message_payload, default=str) # Frame 2: Payload (Bytes)
                ])
                
                # 3. Prepara a resposta REQ/REP de sucesso
                reply["data"] = {"status": "OK", "message": "Mensagem publicada."}

        case "message":
            dest_user = data.get("dst")
            src_user = data.get("src")
            message = data.get("message")
            
            reply["service"] = "message"
            
            if dest_user not in users:
                reply["data"] = {"status": "erro", "message": "Usuário de destino não existe."}
            else:
                # 1. Prepara a mensagem privada
                message_payload = {
                    "src": src_user,
                    "message": message,
                    "timestamp": data.get("timestamp")
                }
                
                # 2. Define o tópico privado
                topic = f"user:{dest_user}"
                
                # 3. PUBLICA A MENSAGEM (Tópico + Payload MessagePack)
                pub_socket.send_multipart([
                    topic.encode('utf-8'),                      # Frame 1: Tópico (Bytes)
                    msgpack.packb(message_payload, default=str) # Frame 2: Payload (Bytes)
                ])
                
                # 4. Prepara a resposta REQ/REP de sucesso
                reply["data"] = {"status": "OK", "message": "Mensagem privada enviada."}

        case _:
            reply = {"service": "erro", "data": {"status": "erro", "timestamp": datetime.now().isoformat(), "description": "Serviço não encontrado"}}

    # --- ENVIA A RESPOSTA REQ/REP ---
    reply_packed = msgpack.packb(reply, default=str) 
    rep_socket.send(reply_packed)