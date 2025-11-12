package main

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	zmq "github.com/pebbe/zmq4"
	"github.com/vmihailenco/msgpack/v5"
)

var userName string // Armazena o nome do usuário logado

// Struct para desserializar respostas de erro (para ser robusto)
type ErrorReply struct {
	Data struct {
		Status      string `msgpack:"status"`
		Description string `msgpack:"description"`
	} `msgpack:"data"`
}

// Struct para desserializar a resposta de "listar" e "canais"
type ListReply struct {
	Data struct {
		Users    []string `msgpack:"users"`
		Channels []string `msgpack:"channels"`
	} `msgpack:"data"`
}

// Goroutine para receber mensagens (o socket SUB)
func receiveMessages(context *zmq.Context, user string) {
	subSocket, err := context.NewSocket(zmq.SUB)
	if err != nil {
		log.Fatalf("Erro ao criar socket SUB: %v", err)
	}
	defer subSocket.Close()

	// Conecta ao proxy PUB/SUB (Note: 'proxy', não 'pubsub_proxy')
	subSocket.Connect("tcp://proxy:5556")
	
	// Inscreve-se no tópico de usuário privado
	subSocket.SetSubscribe("user:" + user)
	// TODO: Adicionar lógica para se inscrever em canais (ex: "canal:geral")

	fmt.Println("\n[INFO] Listener de mensagens (SUB) iniciado.")

	for {
		// Recebe a mensagem em multipartes
		frames, err := subSocket.RecvMessageBytes(0)
		if err != nil {
			log.Printf("Erro no SUB socket: %v", err)
			break
		}

		if len(frames) < 2 {
			continue // Mensagem mal formada
		}

		topic := string(frames[0])
		payload := frames[1]

		// Desserializa o payload MessagePack
		var msgData map[string]interface{}
		err = msgpack.Unmarshal(payload, &msgData)
		if err != nil {
			log.Printf("Erro ao desserializar msg: %v", err)
			continue
		}

		var output string
		if strings.HasPrefix(topic, "user:") {
			// Mensagem privada
			src, _ := msgData["src"].(string)
			msg, _ := msgData["message"].(string)
			output = fmt.Sprintf("[%s para VOCÊ] %s", src, msg)
		} else {
			// Mensagem de canal
			channel := topic
			user, _ := msgData["user"].(string)
			msg, _ := msgData["message"].(string)
			output = fmt.Sprintf("[%s] %s: %s", channel, user, msg)
		}

		// Imprime a mensagem e redesenha o prompt
		fmt.Printf("\n[MENSAGEM RECEBIDA] %s\nEntre com a opção: ", output)
	}
}

// Função principal para enviar comandos (o socket REQ)
func main() {
	context, _ := zmq.NewContext()
	defer context.Term()

	reqSocket, _ := context.NewSocket(zmq.REQ)
	reqSocket.Connect("tcp://broker:5557")
	defer reqSocket.Close()

	fmt.Println("Bem-vindo ao sistema de canais! (Cliente em Go)")
	fmt.Println("Opções: login, listar, canal, canais, publish, msg, sair")

	// Leitor de terminal
	reader := bufio.NewReader(os.Stdin)

	for {
		// Exibe o prompt
		fmt.Print("Entre com a opção: ")
		opcao, _ := reader.ReadString('\n')
		opcao = strings.TrimSpace(opcao)

		// Prepara a request (como um mapa genérico)
		request := make(map[string]interface{})
		data := make(map[string]interface{})
		request["data"] = data

		switch opcao {
		case "sair":
			fmt.Println("Encerrando...")
			return // Encerra o programa

		case "login":
			if userName != "" {
				fmt.Println("Você já está logado. Saia para trocar de usuário.")
				continue
			}
			fmt.Print("Entre com o nome: ")
			usuario, _ := reader.ReadString('\n')
			usuario = strings.TrimSpace(usuario)

			request["service"] = "login"
			data["user"] = usuario
			data["timestamp"] = time.Now().Format(time.RFC3339)
			
			// Envia e recebe
			replyBytes := sendRecv(reqSocket, request)

			// Tenta desserializar como erro primeiro
			var errReply ErrorReply
			if msgpack.Unmarshal(replyBytes, &errReply) == nil && errReply.Data.Status == "erro" {
				fmt.Printf("ERRO: %s\n", errReply.Data.Description)
			} else {
				userName = usuario
				fmt.Printf("Login do usuário '%s' realizado com sucesso!\n", userName)
				// Inicia a goroutine para receber mensagens APÓS o login
				go receiveMessages(context, userName)
			}

		case "listar":
			request["service"] = "users"
			data["timestamp"] = time.Now().Format(time.RFC3339)
			replyBytes := sendRecv(reqSocket, request)
			
			var list ListReply
			msgpack.Unmarshal(replyBytes, &list)
			fmt.Println("Usuários cadastrados:", list.Data.Users)

		case "canal":
			fmt.Print("Nome do novo canal: ")
			canalNome, _ := reader.ReadString('\n')
			canalNome = strings.TrimSpace(canalNome)

			request["service"] = "channel"
			data["channel"] = canalNome
			data["timestamp"] = time.Now().Format(time.RFC3339)
			
			replyBytes := sendRecv(reqSocket, request)
			var errReply ErrorReply
			if msgpack.Unmarshal(replyBytes, &errReply) == nil && errReply.Data.Status == "erro" {
				fmt.Printf("ERRO: %s\n", errReply.Data.Description)
			} else {
				fmt.Printf("Canal '%s' criado com sucesso!\n", canalNome)
			}

		case "canais":
			request["service"] = "channels"
			data["timestamp"] = time.Now().Format(time.RFC3339)
			replyBytes := sendRecv(reqSocket, request)
			
			var list ListReply
			msgpack.Unmarshal(replyBytes, &list)
			fmt.Println("Canais disponíveis:", list.Data.Channels)

		case "subscribe":
			fmt.Println("ERRO: Funcionalidade de subscribe dinâmico não implementada.")
			fmt.Println("Por enquanto, você só recebe mensagens privadas.")

		case "publish":
			if userName == "" {
				fmt.Println("ERRO: Faça login antes de publicar.")
				continue
			}
			fmt.Print("Canal: ")
			canal, _ := reader.ReadString('\n')
			fmt.Print("Mensagem: ")
			mensagem, _ := reader.ReadString('\n')

			request["service"] = "publish"
			data["user"] = userName
			data["channel"] = strings.TrimSpace(canal)
			data["message"] = strings.TrimSpace(mensagem)
			data["timestamp"] = time.Now().Format(time.RFC3339)
			
			replyBytes := sendRecv(reqSocket, request)
			// O servidor responde com {"data": {"status": "OK", ...}} ou {"data": {"status": "erro", ...}}
			fmt.Println("Resposta do servidor (publish):", string(replyBytes)) // Simplesmente imprime a resposta

		case "msg":
			if userName == "" {
				fmt.Println("ERRO: Faça login antes de enviar mensagens.")
				continue
			}
			fmt.Print("Destinatário: ")
			dest, _ := reader.ReadString('\n')
			fmt.Print("Mensagem privada: ")
			mensagem, _ := reader.ReadString('\n')

			request["service"] = "message"
			data["src"] = userName
			data["dst"] = strings.TrimSpace(dest)
			data["message"] = strings.TrimSpace(mensagem)
			data["timestamp"] = time.Now().Format(time.RFC3339)
			
			replyBytes := sendRecv(reqSocket, request)
			// O servidor responde com {"data": {"status": "OK", ...}} ou {"data": {"status": "erro", ...}}
			fmt.Println("Resposta do servidor (msg):", string(replyBytes)) // Simplesmente imprime a resposta

		default:
			fmt.Println("Opção não encontrada.")
		}
	}
}

// sendRecv é uma função helper para enviar um request e receber uma resposta
func sendRecv(socket *zmq.Socket, request map[string]interface{}) []byte {
	// Serializa com MessagePack
	reqBytes, err := msgpack.Marshal(request)
	if err != nil {
		log.Printf("Erro ao serializar request: %v", err)
		return nil
	}

	// Envia
	socket.SendBytes(reqBytes, 0)

	// Recebe
	replyBytes, err := socket.RecvBytes(0)
	if err != nil {
		log.Printf("Erro ao receber resposta: %v", err)
		return nil
	}
	
	return replyBytes
}