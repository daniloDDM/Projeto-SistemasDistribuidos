import zmq
import json
from datetime import datetime
import os

context = zmq.Context()
socket = context.socket(zmq.REP)
socket.connect("tcp://broker:5556")

# Função para carregar dados do disco
def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return {}

# Função para salvar dados no disco
def save_data(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Carrega os dados de usuários e canais
users = load_data("users.json")
channels = load_data("channels.json")

print("Servidor iniciado, aguardando requisições...")

while True:
    request = socket.recv_json()
    service = request.get("service")
    data = request.get("data", {})
    reply = {}

    print(f"Requisição recebida: {request}")

    match service:
        case "login":
            user_name = data.get("user")
            timestamp = data.get("timestamp")
            
            reply["service"] = "login"
            reply["data"] = {
                "timestamp": datetime.now().isoformat()
            }

            if user_name not in users:
                users[user_name] = {"timestamp": timestamp}
                save_data(users, "users.json")
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
            reply["data"] = {
                "timestamp": datetime.now().isoformat()
            }

            if channel_name not in channels:
                channels[channel_name] = {"timestamp": timestamp}
                save_data(channels, "channels.json")
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

        case _:
            reply["service"] = "erro"
            reply["data"] = {
                "status": "erro",
                "timestamp": datetime.now().isoformat(),
                "description": "Serviço não encontrado"
            }

    socket.send_json(reply)

socket.close()
context.term()