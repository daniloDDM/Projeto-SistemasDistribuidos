# cliente.py
import zmq
from datetime import datetime
import msgpack # Importado para serialização/desserialização
import threading

# --- Variáveis Globais ---
context = zmq.Context()
user_name = None # Armazena o nome do usuário logado
running = True # Flag para controlar a execução das threads

# --- Thread para Receber Mensagens (SUB) ---
def receive_messages():
    sub_socket = context.socket(zmq.SUB)
    # ATENÇÃO: Verifique se este endereço 'pubsub_proxy:5558' está correto na sua configuração
    sub_socket.connect("tcp://pubsub_proxy:5558")
    
    # ... Inscrição do tópico (deve ser em bytes ou string, dependendo do PUB) ...
    # Vamos manter a inscrição como string, já que o tópico é uma string:
    if user_name:
        # A inscrição deve ser feita como bytes se o broker for um proxy simples
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, f"user:{user_name}")

    print("Listener de mensagens iniciado.")
    
    while running:
        try:
            if sub_socket.poll(timeout=1000): 
                # 1. Recebe a mensagem como frames de bytes (multipart)
                frames = sub_socket.recv_multipart()
                
                # O primeiro frame é o TÓPICO, o segundo é o PAYLOAD (MessagePack)
                topic = frames[0].decode('utf-8')
                payload_packed = frames[1]

                # 2. DESSERIALIZA o payload com MessagePack
                # O MessagePack agora deve conter a mensagem de chat
                message_data = msgpack.unpackb(payload_packed, raw=False)
                
                # Monta uma string de exibição
                if topic.startswith("user:"):
                    # Mensagem privada: {src} -> {dst}: {message}
                    src = message_data.get("src", "Desconhecido")
                    msg = message_data.get("message", "N/A")
                    output = f"[{src} para VOCÊ] {msg}"
                else:
                    # Mensagem de canal: [canal] user: mensagem
                    channel = topic
                    user = message_data.get("user", "Desconhecido")
                    msg = message_data.get("message", "N/A")
                    output = f"[{channel}] {user}: {msg}"

                print(f"\n[MENSAGEM RECEBIDA] {output}\nEntre com a opção: ", end="", flush=True)

        except zmq.ContextTerminated:
            break
        except Exception as e:
            # Captura exceções, incluindo possíveis erros de decodificação se o broker enviar algo inesperado
            print(f"\n[ERRO NO LISTENER] {e}\nEntre com a opção: ", end="", flush=True)
            pass
    
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
        
        # --- Lógica de Envio e Recebimento com MessagePack ---
        
        match opcao:
            case "login":
                if user_name:
                    print("Você já está logado. Saia para trocar de usuário.")
                    continue
                
                usuario = input("Entre com o nome: ")
                request = {"service": "login", "data": {"user": usuario, "timestamp": datetime.now().isoformat()}}
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)

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
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)
                
                print("Usuários cadastrados:", reply.get("data", {}).get("users", []))

            case "canal":
                canal_nome = input("Nome do novo canal: ")
                request = {"service": "channel", "data": {"channel": canal_nome, "timestamp": datetime.now().isoformat()}}
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)
                
                if reply["data"]["status"] == "sucesso":
                    print(f"Canal '{canal_nome}' criado com sucesso!")
                else:
                    print(f"ERRO: {reply['data']['description']}")

            case "canais":
                request = {"service": "channels", "data": {"timestamp": datetime.now().isoformat()}}
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)
                
                print("Canais disponíveis:", reply.get("data", {}).get("channels", []))

            case "subscribe":
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
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)
                
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
                
                # Envia MessagePack
                req_socket.send(msgpack.packb(request, default=str))
                # Recebe MessagePack
                reply_packed = req_socket.recv()
                reply = msgpack.unpackb(reply_packed, raw=False)
                
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