import zmq

context = zmq.Context()
socket = context.socket(zmq.REP)
socket.connect("tcp://broker:5556")

users = dict()
cont = 0

while True:
    request = socket.recv_json()
    opcao = request["opcao"]
    dados = request["dados"]
    reply = "ERRO: função não escolhida"

    match opcao:
        case "login":
            users[cont] = dados
            cont += 1
            reply = {
                "opcao": "login",
                "data":{
                  "status": "sucesso"/"erro",
                  "timestamp": datetime.now().isoformat(),
                  "description": "deu erro sei la"
                }
            }

        case "atualizar":
            id_tarefa = dados["id"]
            if id_tarefa in tarefas:
                tarefas[id_tarefa] = {
                    "titulo": dados["titulo"],
                    "desc": dados["desc"]
                }
                reply = "OK"
            else:
                reply = "ERRO: tarefa não encontrada"

        case "deletar":
            id_tarefa = dados["id"]
            if id_tarefa in tarefas:
                del tarefas[id_tarefa]
                reply = "OK"
            else:
                reply = "ERRO: tarefa não encontrada"
            
        case "listar":
            reply = str(tarefas)

        case "buscar":
            id_tarefa = dados["id"]
            if id_tarefa in tarefas:
                reply = str(tarefas[id_tarefa])
            else:
                reply = "ERRO: tarefa não encontrada"

        case _ :
            reply = "ERRO: função não encontrada"

    socket.send_string(reply)
