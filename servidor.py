# servidor.py
import zmq
import json
from datetime import datetime
import os

# --- Configuração dos Sockets ---
context = zmq.Context()

# Socket para Request-Reply
rep_socket = context.socket(zmq.REP)
rep_socket.connect("tcp://broker:5556")

# Socket para Publisher-Subscriber
pub_socket = context.socket(zmq.PUB)
pub_socket.connect("tcp://pubsub_proxy:5557") # Conecta ao XSUB do novo proxy

# --- Persistência de Dados ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")

def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Carrega os dados
users = load_data(USERS_FILE)
channels = load_data(CHANNELS_FILE)
messages = load_data(MESSAGES_FILE)

print("Servidor iniciado, aguardando requisições...")

while True:
    request = rep_socket.recv_json()
    service = request.get("service")
    data = request.get("data", {})
    reply = {}

    print(f"Requisição recebida: {request}")

    match service:
        case "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            
            reply["service"] = "login"
            reply["data"] = {"timestamp": datetime.now().isoformat()}

            if user_name not in users:
                users[user_name] = {"timestamp": timestamp}
                save_data(users, USERS_FILE)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Usuário já existe"
        
        case "users":
            reply["service"] = "users"
            reply["data"] = {
                "timestamp": datetime.now().isoformat(),
                "users": list(users.keys())
            }

        case "channel":
            channel_name = data.get("channel")
            timestamp = data.get("timestamp")
            
            reply["service"] = "channel"
            reply["data"] = {"timestamp": datetime.now().isoformat()}

            if channel_name not in channels:
                channels[channel_name] = {"timestamp": timestamp}
                save_data(channels, CHANNELS_FILE)
                reply["data"]["status"] = "sucesso"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["description"] = "Canal já existe"

        case "channels":
            reply["service"] = "channels"
            reply["data"] = {
                "timestamp": datetime.now().isoformat(),
                "channels": list(channels.keys())
            }

        case "publish": # NOVO SERVIÇO
            user = data.get("user")
            channel = data.get("channel")
            message = data.get("message")
            timestamp = data.get("timestamp")
            
            reply["service"] = "publish"
            reply["data"] = {"timestamp": datetime.now().isoformat()}

            if channel in channels:
                # Publica a mensagem no tópico do canal
                topic = f"channel:{channel}"
                full_message = f"[{channel}] {user}: {message}"
                pub_socket.send_string(f"{topic} {full_message}")
                
                # Persiste a mensagem
                if topic not in messages:
                    messages[topic] = []
                messages[topic].append({"user": user, "message": message, "timestamp": timestamp})
                save_data(messages, MESSAGES_FILE)
                
                reply["data"]["status"] = "OK"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["message"] = "Canal não existe"
        
        case "message": # NOVO SERVIÇO
            src_user = data.get("src")
            dst_user = data.get("dst")
            message = data.get("message")
            timestamp = data.get("timestamp")
            
            reply["service"] = "message"
            reply["data"] = {"timestamp": datetime.now().isoformat()}

            if dst_user in users:
                # Publica a mensagem no tópico do usuário de destino
                topic = f"user:{dst_user}"
                full_message = f"(privado) {src_user}: {message}"
                pub_socket.send_string(f"{topic} {full_message}")
                
                # Persiste a mensagem
                if topic not in messages:
                    messages[topic] = []
                messages[topic].append({"src": src_user, "message": message, "timestamp": timestamp})
                save_data(messages, MESSAGES_FILE)
                
                reply["data"]["status"] = "OK"
            else:
                reply["data"]["status"] = "erro"
                reply["data"]["message"] = "Usuário de destino não existe"

        case _:
            reply["service"] = "erro"
            reply["data"] = {
                "status": "erro",
                "timestamp": datetime.now().isoformat(),
                "description": "Serviço não encontrado"
            }

    rep_socket.send_json(reply)