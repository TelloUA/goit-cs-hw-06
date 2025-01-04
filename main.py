import urllib.parse
import mimetypes
import pathlib
import socket
import json
import sys
import signal
from concurrent import futures as cf
from http.server import HTTPServer, BaseHTTPRequestHandler
from pymongo import MongoClient
from datetime import datetime
from threading import Thread, Event

TCP_IP = 'localhost'
TCP_PORT = 5000

stop_event = Event()

class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pr_url = urllib.parse.urlparse(self.path)
        if pr_url.path == '/':
            self.send_html_file('index.html')
        elif pr_url.path == '/message':
            self.send_html_file('message.html')
        else:
            if pathlib.Path().joinpath(pr_url.path[1:]).exists():
                self.send_static()
            else:
                self.send_html_file('error.html', 404)
    
    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        data_parse = urllib.parse.unquote_plus(data.decode())
        data_dict = {key: value for key, value in [el.split('=') for el in data_parse.split('&')]}
        print(data_dict)
        self.send_to_socket(data_dict)
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

    def send_to_socket(self, data):
        serialized_data = json.dumps(data).encode('utf-8')
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((TCP_IP, TCP_PORT))
            sock.send(serialized_data)

    def send_html_file(self, filename, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        with open(filename, 'rb') as fd:
            self.wfile.write(fd.read())

    def send_static(self):
        self.send_response(200)
        mt = mimetypes.guess_type(self.path)
        if mt:
            self.send_header("Content-type", mt[0])
        else:
            self.send_header("Content-type", 'text/plain')
        self.end_headers()
        with open(f'.{self.path}', 'rb') as file:
            self.wfile.write(file.read())

def run_http_server(server_class=HTTPServer, handler_class=HttpHandler):
    server_address = ('', 3000)
    http = server_class(server_address, handler_class)
    try:
        while not stop_event.is_set():
            http.serve_forever()
    except KeyboardInterrupt:
        http.server_close()

def run_socket_server():
    MONGO_URI = "mongodb://root:example@mongodb:27017/"
    client = MongoClient(MONGO_URI)
    db = client['messages_db']
    collection = db['messages']

    def save_to_db(message):
        message['date'] = datetime.now().isoformat()
        collection.insert_one(message)
        print("Повідомлення збережено:", message)

    def handle_client(sock: socket.socket, address: str):
        print(f'З\'єднання встановлено: {address}')
        try:
            received = sock.recv(1024)
            if not received:
                print(f'З\'єднання завершено: {address}')
                return
            
            data = received.decode()
            print(f'Отримані дані: {data}')
            message = eval(data)
            save_to_db(message)
            
        except Exception as e:
            print(f'Помилка під час обробки даних: {e}')
        finally:
            print(f'З\'єднання закрито: {address}')
            sock.close()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((TCP_IP, TCP_PORT))
    server_socket.listen(5)
    print(f'Сервер запущено на {TCP_IP}:{TCP_PORT}')

    try:
        while True:
            while not stop_event.is_set():
                client_socket, client_address = server_socket.accept()
                handle_client(client_socket, client_address)
    except KeyboardInterrupt:
        print("Сервер зупинено.")
    finally:
        server_socket.close()

def handle_signal():
    stop_event.set()
    print("Зупинка серверів...")
    sys.exit(0)
    
if __name__ == '__main__':
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    http_server = Thread(target=run_http_server)
    http_server.start()

    socket_server = Thread(target=run_socket_server)
    socket_server.start()
