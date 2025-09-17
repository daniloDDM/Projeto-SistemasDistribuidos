# cliente_automatico.py
import zmq
from datetime import datetime
import time
import random
import string

# --- Configuração ---
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

# --- Funções Auxiliares ---
def random_string(length=8):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

# --- Lógica Principal ---

# 1. Login com usuário aleatório
user_name = f"bot_{random_string(5)}"
login_req = {
    "service": "login",
    "data": {"user": user_name, "timestamp": datetime.now().isoformat()}
}
socket.send_json(login_req)
reply = socket.recv_json()
if reply["data"]["status"] != "sucesso":
    print(f"Bot {user_name} falhou ao logar. Encerrando.")
    exit()
print(f"Bot '{user_name}' logado com sucesso.")

# Mensagens de exemplo para enviar
MENSAGENS = [
    "Olá a todos!", "Alguém aí?", "Este é um teste do sistema de mensagens.",
    "Que dia para programar!", "ZeroMQ é muito interessante.",
    "Testando, 1, 2, 3...", "Docker facilita muito a vida.",
    "Python é uma ótima linguagem.", "Quem quer café?", "Preciso de férias."
]

# 2. Loop infinito de publicação
while True:
    try:
        # Pega a lista de canais
        socket.send_json({"service": "channels", "data": {"timestamp": datetime.now().isoformat()}})
        channels_reply = socket.recv_json()
        available_channels = channels_reply.get("data", {}).get("channels", [])

        if not available_channels:
            # Se não houver canais, cria um
            new_channel = f"canal_{random_string(4)}"
            print(f"Bot '{user_name}' criando canal '{new_channel}'...")
            socket.send_json({"service": "channel", "data": {"channel": new_channel, "timestamp": datetime.now().isoformat()}})
            socket.recv_json() # Apenas consome a resposta
            available_channels.append(new_channel)
        
        # Escolhe um canal aleatório
        target_channel = random.choice(available_channels)

        # Envia 10 mensagens
        print(f"Bot '{user_name}' vai enviar 10 mensagens para o canal '{target_channel}'.")
        for _ in range(10):
            message_to_send = random.choice(MENSAGENS)
            publish_req = {
                "service": "publish",
                "data": {
                    "user": user_name,
                    "channel": target_channel,
                    "message": message_to_send,
                    "timestamp": datetime.now().isoformat()
                }
            }
            socket.send_json(publish_req)
            socket.recv_json() # Consome a resposta
            time.sleep(random.uniform(0.5, 2.0)) # Espera um pouco entre as mensagens

    except Exception as e:
        print(f"Bot '{user_name}' encontrou um erro: {e}")
        time.sleep(5) # Espera antes de tentar novamente