package main

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strings"
	"sync" // <-- IMPORTAR SYNC
	"time"

	zmq "github.com/pebbe/zmq4"
	"github.com/vmihailenco/msgpack/v5"
)

var userName string
var logicalClock int64 = 0   // <-- ADICIONAR CLOCK
var clockMutex sync.Mutex // <-- ADICIONAR MUTEX

// Função helper para pegar o max de int64
func max(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

// Struct para desserializar APENAS o clock de qualquer resposta
type ClockReply struct {
	Data struct {
		Clock int64 `msgpack:"clock"`
	} `msgpack:"data"`
}

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

	// Conecta ao proxy PUB/SUB
	subSocket.Connect("tcp://proxy:5556")

	// Inscreve-se no tópico de usuário privado
	subSocket.SetSubscribe("user:" + user)

	fmt.Println("\n[INFO] Listener de mensagens (SUB) iniciado.")

	for {
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

		var msgData map[string]interface{}
		err = msgpack.Unmarshal(payload, &msgData)
		if err != nil {
			log.Printf("Erro ao desserializar msg: %v", err)
			continue
		}

		// --- LÓGICA DO RELÓGIO (RECEBER) ---
		var receivedClock int64
		if clockVal, ok := msgData["clock"]; ok {
			// msgpack pode decodificar números como float64 ou int64
			if floatVal, ok := clockVal.(float64); ok {
				receivedClock = int64(floatVal)
			} else if intVal, ok := clockVal.(int64); ok {
				receivedClock = intVal
			} else if uintVal, ok := clockVal.(uint64); ok {
				receivedClock = int64(uintVal)
			}
		}

		clockMutex.Lock()
		logicalClock = max(logicalClock, receivedClock)
		currentClock := logicalClock // Pega o valor para logar
		clockMutex.Unlock()
		// --- FIM DA LÓGICA ---

		var output string
		if strings.HasPrefix(topic, "user:") {
			src, _ := msgData["src"].(string)
			msg, _ := msgData["message"].(string)
			output = fmt.Sprintf("[%s para VOCÊ] %s", src, msg)
		} else {
			channel := topic
			user, _ := msgData["user"].(string)
			msg, _ := msgData["message"].(string)
			output = fmt.Sprintf("[%s] %s: %s", channel, user, msg)
		}

		fmt.Printf("\n[MENSAGEM RECEBIDA (Clock: %d)] %s\nEntre com a opção: ", currentClock, output)
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

	reader := bufio.NewReader(os.Stdin)

	for {
		fmt.Print("Entre com a opção: ")
		opcao, _ := reader.ReadString('\n')
		opcao = strings.TrimSpace(opcao)

		request := make(map[string]interface{})
		data := make(map[string]interface{})
		request["data"] = data

		didSend := false

		switch opcao {
		case "sair":
			fmt.Println("Encerrando...")
			return

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
			didSend = true

		case "listar":
			request["service"] = "users"
			data["timestamp"] = time.Now().Format(time.RFC3339)
			didSend = true

		case "canal":
			fmt.Print("Nome do novo canal: ")
			canalNome, _ := reader.ReadString('\n')
			canalNome = strings.TrimSpace(canalNome)

			request["service"] = "channel"
			data["channel"] = canalNome
			data["timestamp"] = time.Now().Format(time.RFC3339)
			didSend = true

		case "canais":
			request["service"] = "channels"
			data["timestamp"] = time.Now().Format(time.RFC3339)
			didSend = true

		case "subscribe":
			fmt.Println("ERRO: Funcionalidade de subscribe dinâmico não implementada.")
			didSend = false

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
			didSend = true

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
			didSend = true

		default:
			fmt.Println("Opção não encontrada.")
			didSend = false
		}

		// --- LÓGICA DE ENVIO/RECEBIMENTO CENTRALIZADA ---
		if didSend {
			// --- LÓGICA DO RELÓGIO (ENVIAR) ---
			clockMutex.Lock()
			logicalClock++
			data["clock"] = logicalClock
			fmt.Printf("[INFO] Enviando (Clock: %d)\n", logicalClock)
			clockMutex.Unlock()
			// --- FIM DA LÓGICA ---

			// Serializa e envia
			reqBytes, err := msgpack.Marshal(request)
			if err != nil {
				log.Printf("Erro ao serializar request: %v", err)
				continue
			}
			reqSocket.SendBytes(reqBytes, 0)

			// Recebe
			replyBytes, err := reqSocket.RecvBytes(0) // <-- 'replyBytes' é definido aqui
			if err != nil {
				log.Printf("Erro ao receber resposta: %v", err)
				continue
			}

			// --- LÓGICA DO RELÓGIO (RECEBER) ---
			var clockReply ClockReply
			msgpack.Unmarshal(replyBytes, &clockReply) // Ignora erro, se falhar clockReply.Data.Clock será 0

			clockMutex.Lock()
			logicalClock = max(logicalClock, clockReply.Data.Clock)
			clockMutex.Unlock()
			
			switch request["service"] {
			case "login":
				var errReply ErrorReply
				if msgpack.Unmarshal(replyBytes, &errReply) == nil && errReply.Data.Status == "erro" {
					fmt.Printf("ERRO: %s\n", errReply.Data.Description)
				} else {
					userName = data["user"].(string)
					fmt.Printf("Login do usuário '%s' realizado com sucesso!\n", userName)
					go receiveMessages(context, userName) // Inicia o listener
				}
			case "listar":
				var list ListReply
				msgpack.Unmarshal(replyBytes, &list)
				fmt.Println("Usuários cadastrados:", list.Data.Users)
			case "canal":
				var errReply ErrorReply
				if msgpack.Unmarshal(replyBytes, &errReply) == nil && errReply.Data.Status == "erro" {
					fmt.Printf("ERRO: %s\n", errReply.Data.Description)
				} else {
					fmt.Printf("Canal '%s' criado com sucesso!\n", data["channel"])
				}
			case "canais":
				var list ListReply
				msgpack.Unmarshal(replyBytes, &list)
				fmt.Println("Canais disponíveis:", list.Data.Channels)
			case "publish", "msg":
				var statusReply ErrorReply // Reutilizando a struct
				msgpack.Unmarshal(replyBytes, &statusReply)
				if statusReply.Data.Status == "OK" {
					fmt.Println("Mensagem enviada com sucesso.")
				} else {
					fmt.Printf("ERRO: %s\n", statusReply.Data.Description)
				}
			}
		

		} 
	} 
}