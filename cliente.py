import zmq
from datetime import datetime

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://broker:5555")

opcao = input("Entre com a opção: ")
while opcao != "sair":
    match opcao:
        case "login":
            usuario = input("Entre com o nome: ")

            request = {
                "opcao": "login",
                "dados": {
                    "user": usuario,
                    "timestamp": datetime.now().isoformat()
                }
            }

            socket.send_json(request)
            reply = socket.recv_string()
            if reply.split(":")[0] == "ERRO":
                print(reply, flush=True)

        case "atualizar":
            id_tarefa = int(input("ID da tarefa para atualizar: "))
            titulo = input("Novo título: ")
            descricao = input("Nova descrição: ")

            request = {
                "opcao": "atualizar",
                "dados": {"id": id_tarefa, "titulo": titulo, "desc": descricao}
            }
            socket.send_json(request)
            print(socket.recv_string(), flush=True)

        case "deletar":
            id_tarefa = int(input("ID da tarefa para deletar: "))
            request = {
                "opcao": "deletar",
                "dados": {"id": id_tarefa}
            }
            socket.send_json(request)
            print(socket.recv_string(), flush=True)

        case "listar":
            request = {"opcao": "listar", "dados": {}}
            socket.send_json(request)
            print(socket.recv_string(), flush=True)

        case "buscar":
            id_tarefa = int(input("ID da tarefa para buscar: "))
            request = {"opcao": "buscar", "dados": {"id": id_tarefa}}
            socket.send_json(request)
            print(socket.recv_string(), flush=True)
            
        case _:
            print("Opção não encontrada")

    opcao = input("Entre com a opção: ")
