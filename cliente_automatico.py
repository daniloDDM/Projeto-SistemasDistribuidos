# cliente_automatico.py
import zmq
from datetime import datetime
import time
import random
import string
import msgpack 

# --- Configuração ---
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5557") # Conexão já estava correta

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

# --- CORREÇÃO 1: Usar msgpack ---
print(f"Bot '{user_name}' tentando logar...")
socket.send(msgpack.packb(login_req, default=str))
reply_packed = socket.recv()
reply = msgpack.unpackb(reply_packed, raw=False)
# --- Fim da Correção 1 ---

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
        # --- CORREÇÃO 2: Usar msgpack ---
        socket.send(msgpack.packb({"service": "channels", "data": {"timestamp": datetime.now().isoformat()}}, default=str))
        channels_reply_packed = socket.recv()
        channels_reply = msgpack.unpackb(channels_reply_packed, raw=False)
        # --- Fim da Correção 2 ---
        
        available_channels = channels_reply.get("data", {}).get("channels", [])

        if not available_channels:
            # Se não houver canais, cria um
            new_channel = f"canal_{random_string(4)}"
            print(f"Bot '{user_name}' criando canal '{new_channel}'...")
            
            # --- CORREÇÃO 3: Usar msgpack ---
            socket.send(msgpack.packb({"service": "channel", "data": {"channel": new_channel, "timestamp": datetime.now().isoformat()}}, default=str))
            socket.recv() # Apenas consome a resposta (não precisamos desempacotar)
            # --- Fim da Correção 3 ---
            
            available_channels.append(new_channel)
        
        # Escolhe um canal aleatório
        target_channel = random.choice(available_channels)

        # Envia 10 mensagens
        print(f"Bot '{user_name}' vai enviar 10 mensagens para o canal '{target_channel}'.")
        for i in range(10):
            message_to_send = random.choice(MENSAGENS)
            publish_req = {
                "service": "publish",
                "data": {
                    "user": user_name,
                    "channel": target_channel,
                    "message": f"({i+1}/10) {message_to_send}",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # --- CORREÇÃO 4: Usar msgpack ---
            socket.send(msgpack.packb(publish_req, default=str))
            socket.recv() # Consome a resposta
            # --- Fim da Correção 4 ---
            
            time.sleep(random.uniform(0.5, 2.0)) # Espera um pouco entre as mensagens

    except Exception as e:
        print(f"Bot '{user_name}' encontrou um erro: {e}")
        time.sleep(5) # Espera antes de tentar novamente