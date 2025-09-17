# cliente.py
import zmq
from datetime import datetime
import json
import threading

# --- Variáveis Globais ---
context = zmq.Context()
user_name = None # Armazena o nome do usuário logado
running = True # Flag para controlar a execução das threads

# --- Thread para Receber Mensagens (SUB) ---
def receive_messages():
    sub_socket = context.socket(zmq.SUB)
    sub_socket.connect("tcp://pubsub_proxy:5558")
    
    # Sempre se inscreve nas mensagens para o usuário logado
    if user_name:
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, f"user:{user_name}")

    print("Listener de mensagens iniciado.")
    
    while running:
        try:
            # Espera por uma mensagem, mas com um timeout para não bloquear para sempre
            if sub_socket.poll(timeout=1000): 
                message = sub_socket.recv_string()
                print(f"\n[MENSAGEM RECEBIDA] {message.split(' ', 1)[1]}\nEntre com a opção: ", end="")
        except zmq.ContextTerminated:
            break
    
    sub_socket.close()
    print("Listener de mensagens encerrado.")

# --- Thread Principal para Comandos (REQ) ---
def send_commands():
    global user_name, running
    req_socket = context.socket(zmq.REQ)
    req_socket.connect("tcp://broker:5555")

    print("Bem-vindo ao sistema de canais!")
    print("Opções: login, listar, canal, canais, subscribe, publish, msg, sair")
    
    while running:
        opcao = input("Entre com a opção: ")
        
        if opcao == "sair":
            running = False
            break

        request = {}
        
        match opcao:
            case "login":
                if user_name:
                    print("Você já está logado. Saia para trocar de usuário.")
                    continue
                
                usuario = input("Entre com o nome: ")
                request = {"service": "login", "data": {"user": usuario, "timestamp": datetime.now().isoformat()}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()

                if reply["data"]["status"] == "sucesso":
                    user_name = usuario
                    print(f"Login do usuário '{user_name}' realizado com sucesso!")
                    # Inicia a thread de recebimento de mensagens APÓS o login
                    receiver_thread = threading.Thread(target=receive_messages, daemon=True)
                    receiver_thread.start()
                else:
                    print(f"ERRO: {reply['data']['description']}")

            case "listar":
                request = {"service": "users", "data": {"timestamp": datetime.now().isoformat()}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                print("Usuários cadastrados:", reply.get("data", {}).get("users", []))

            case "canal":
                canal_nome = input("Nome do novo canal: ")
                request = {"service": "channel", "data": {"channel": canal_nome, "timestamp": datetime.now().isoformat()}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply["data"]["status"] == "sucesso":
                    print(f"Canal '{canal_nome}' criado com sucesso!")
                else:
                    print(f"ERRO: {reply['data']['description']}")

            case "canais":
                request = {"service": "channels", "data": {"timestamp": datetime.now().isoformat()}}
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                print("Canais disponíveis:", reply.get("data", {}).get("channels", []))

            case "subscribe":
                # Esta funcionalidade é local no cliente. O servidor não precisa saber.
                # A thread receiver irá se encarregar de se inscrever.
                # Por simplicidade, vamos reiniciar o receiver para adicionar a nova inscrição.
                print("ERRO: Funcionalidade de subscribe dinâmico não implementada nesta versão.")
                print("Por enquanto, você só recebe mensagens privadas.")

            case "publish":
                if not user_name:
                    print("ERRO: Faça login antes de publicar.")
                    continue
                canal = input("Canal: ")
                mensagem = input("Mensagem: ")
                request = {
                    "service": "publish",
                    "data": {
                        "user": user_name,
                        "channel": canal,
                        "message": mensagem,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply["data"]["status"] == "OK":
                    print("Mensagem publicada com sucesso!")
                else:
                    print(f"ERRO: {reply['data']['message']}")

            case "msg":
                if not user_name:
                    print("ERRO: Faça login antes de enviar mensagens.")
                    continue
                dest = input("Destinatário: ")
                mensagem = input("Mensagem privada: ")
                request = {
                    "service": "message",
                    "data": {
                        "src": user_name,
                        "dst": dest,
                        "message": mensagem,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                req_socket.send_json(request)
                reply = req_socket.recv_json()
                if reply["data"]["status"] == "OK":
                    print("Mensagem enviada com sucesso!")
                else:
                    print(f"ERRO: {reply['data']['message']}")

            case _:
                print("Opção não encontrada.")

    req_socket.close()

# --- Execução Principal ---
if __name__ == "__main__":
    send_commands()
    print("Encerrando...")
    context.term()