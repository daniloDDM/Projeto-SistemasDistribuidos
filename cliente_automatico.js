// cliente_automatico.js

const zmq = require("zeromq");
const msgpack = require("@msgpack/msgpack");

// --- Configuração ---
// No Node.js, sockets são assíncronos
const socket = new zmq.Request();
socket.connect("tcp://broker:5557");
console.log("Cliente automático (JS) conectando ao tcp://broker:5557...");

// --- Funções Auxiliares ---
function randomString(length = 8) {
  const letters = 'abcdefghijklmnopqrstuvwxyz';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += letters.charAt(Math.floor(Math.random() * letters.length));
  }
  return result;
}

// Equivalente ao time.sleep() do Python
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Mensagens de exemplo
const MENSAGENS = [
    "Olá do Node.js!", "Alguém aí?", "Este é um teste do sistema de mensagens.",
    "Que dia para programar!", "ZeroMQ é muito interessante.",
    "Testando, 1, 2, 3...", "Docker facilita muito a vida.",
    "JavaScript também é legal.", "Quem quer café?", "Preciso de férias."
];

// --- Lógica Principal (Async) ---
// Precisamos de uma função 'async' para usar 'await'
async function main() {
  // 1. Login com usuário aleatório
  const userName = `bot_js_${randomString(5)}`;
  const loginReq = {
    "service": "login",
    "data": {"user": userName, "timestamp": new Date().toISOString()} // ISO format é o mesmo
  };

  try {
    console.log(`Bot '${userName}' tentando logar...`);
    
    // --- CORREÇÃO: Usar msgpack ---
    // Envia msgpack (equiv. a msgpack.packb)
    await socket.send(msgpack.encode(loginReq));
    
    // Recebe msgpack (equiv. a socket.recv)
    // O .receive() do JS retorna um array de frames
    const [replyPacked] = await socket.receive(); 
    
    // (equiv. a msgpack.unpackb)
    const reply = msgpack.decode(replyPacked); 

    if (reply.data.status !== "sucesso") {
      console.error(`Bot ${userName} falhou ao logar. Encerrando.`);
      process.exit(1); // Encerra o script
    }
    console.log(`Bot '${userName}' logado com sucesso.`);

  } catch (err) {
    console.error("Erro no login:", err);
    process.exit(1);
  }

  // 2. Loop infinito de publicação
  while (true) {
    try {
      // Pega a lista de canais
      const channelsReq = {"service": "channels", "data": {"timestamp": new Date().toISOString()}};
      await socket.send(msgpack.encode(channelsReq));
      const [channelsReplyPacked] = await socket.receive();
      const channelsReply = msgpack.decode(channelsReplyPacked);
      
      // 'data' pode não existir, 'channels' pode não existir.
      let availableChannels = channelsReply.data?.channels || []; 

      if (availableChannels.length === 0) {
        // Se não houver canais, cria um
        const newChannel = `canal_js_${randomString(4)}`;
        console.log(`Bot '${userName}' criando canal '${newChannel}'...`);
        const createChannelReq = {"service": "channel", "data": {"channel": newChannel, "timestamp": new Date().toISOString()}};
        
        await socket.send(msgpack.encode(createChannelReq));
        await socket.receive(); // Apenas consome a resposta
        availableChannels.push(newChannel);
      }

      // Escolhe um canal aleatório
      const targetChannel = availableChannels[Math.floor(Math.random() * availableChannels.length)];

      // Envia 10 mensagens
      console.log(`Bot '${userName}' vai enviar 10 mensagens para o canal '${targetChannel}'.`);
      for (let i = 0; i < 10; i++) {
        const messageToSend = MENSAGENS[Math.floor(Math.random() * MENSAGENS.length)];
        const publishReq = {
          "service": "publish",
          "data": {
            "user": userName,
            "channel": targetChannel,
            "message": `(JS ${i+1}/10) ${messageToSend}`,
            "timestamp": new Date().toISOString()
          }
        };

        await socket.send(msgpack.encode(publishReq));
        await socket.receive(); // Consome a resposta
        
        // Espera entre 0.5s e 2.0s
        const waitTime = Math.random() * (2000 - 500) + 500; 
        await sleep(waitTime);
      }

    } catch (err) {
      console.error(`Bot '${userName}' encontrou um erro:`, err);
      await sleep(5000); // Espera antes de tentar novamente
    }
  }
}

// Inicia a função principal
main();