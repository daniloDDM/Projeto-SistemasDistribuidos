import zmq

context = zmq.Context()

client_socket = context.socket(zmq.ROUTER)
client_socket.bind("tcp://*:5557")

server_socket = context.socket(zmq.DEALER)
server_socket.bind("tcp://*:5558")

zmq.proxy(client_socket, server_socket)

client_socket.close()
server_socket.close()
context.term()
