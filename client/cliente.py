import zmq
from datetime import datetime
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

print("Bem-vindo ao sistema de canais!")
opcao = input("Entre com a opção: ")
while opcao != "sair":
    request = {}
    match opcao:
        case "login":
            usuario = input("Entre com o nome: ")
            request = {
                "service": "login",
                "data": {
                    "user": usuario,
                    "timestamp": datetime.now().isoformat()
                }
            }
            socket.send_json(request)
            reply = socket.recv_json()
            if reply["data"]["status"] == "sucesso":
                print(f"Login do usuário '{usuario}' realizado com sucesso!")
            else:
                print(f"ERRO: {reply['data']['description']}")

        case "listar":
            request = {
                "service": "users",
                "data": {
                    "timestamp": datetime.now().isoformat()
                }
            }
            socket.send_json(request)
            reply = socket.recv_json()
            if reply["service"] == "users":
                print("Usuários cadastrados:")
                print(reply["data"]["users"])
            else:
                print("ERRO: Resposta inválida do servidor.")

        case "canal":
            canal_nome = input("Nome do novo canal: ")
            request = {
                "service": "channel",
                "data": {
                    "channel": canal_nome,
                    "timestamp": datetime.now().isoformat()
                }
            }
            socket.send_json(request)
            reply = socket.recv_json()
            if reply["data"]["status"] == "sucesso":
                print(f"Canal '{canal_nome}' criado com sucesso!")
            else:
                print(f"ERRO: {reply['data']['description']}")

        case "canais":
            request = {
                "service": "channels",
                "data": {
                    "timestamp": datetime.now().isoformat()
                }
            }
            socket.send_json(request)
            reply = socket.recv_json()
            if reply["service"] == "channels":
                print("Canais disponíveis:")
                print(reply["data"]["channels"])
            else:
                print("ERRO: Resposta inválida do servidor.")

        case _:
            print("Opção não encontrada. As opções disponíveis são: login, listar, canal, canais ou sair.")

    opcao = input("Entre com a opção: ")

socket.close()
context.term()