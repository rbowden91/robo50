# https://realpython.com/python-sockets/#multi-connection-client-and-server
import sys
import os
import json
import argparse
import socket
import selectors
import traceback
import time
import signal
import uuid

#from multiprocessing import Process, Queue
from queue import Queue
from threading import Thread
from typing import Dict

NUM_PROCESSES = 1
HOST = ''
#servers = [('korra.rbowden.com', 12347), ('appa.rbowden.com', 12347), ('aang.rbowden.com', 12347)]
servers = [('appa.rbowden.com', 12347)]

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--port', help='port number (default 12344)', type=int, default=12344)

args = parser.parse_args()

sel = selectors.DefaultSelector()

def sigint_handler(signum, frame):
    sel.close()
    sys.exit()

signal.signal(signal.SIGINT, sigint_handler)

def send_json(sock, msg):
    output = json.dumps(msg).encode('latin-1') + b'\n\n'
    sleep_error = 0
    while len(output) > 0 and sleep_error <= 10:
        try:
            sent = sock.send(output)
            output = output[sent:]
            sleep_error = 0
        except:
            sleep_error += 1
            time.sleep(1)
    return len(output) == 0

def start_worker(q):
    while True:
        sock, input_ = q.get()
        if not send_json(sock, input_):
            print(sock, input_)
            # TODO: close socket
            #if sock in reverse_client_map:
            #    del(client_map[reverse_client_map[sock]])
            #sel.unregister(sock)
            #sock.close()
            pass
        q.task_done()

def server_connect():
    # connect to external servers
    while True:
        for server in servers:
            if server in reverse_server_map: continue
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            reverse_server_map[server] = sock
            server_map[sock] = server
            sock.connect_ex(server)
            sel.register(sock, selectors.EVENT_READ, data={'input':b'', 'type':'server'})
        time.sleep(2)

server_map = {} # type:ignore
reverse_server_map = {} # type:ignore
client_map = {} # type:ignore
reverse_client_map = {} # type:ignore

opaque_map = {}

def close_socket(sock):
    if sock in client_map:
        del(client_map[sock])
    elif sock in server_map:
        del(reverse_server_map[server_map[sock]])
        del(server_map[sock])
    sel.unregister(sock)
    sock.close()

# TODO: disconnect after timeout, messages too long, etc.
# TODO: kill subprocesses?
def main():
    q = Queue()

    server_thread = Thread(target=server_connect)
    server_thread.daemon = True
    server_thread.start()

    # when you use Process instead of Thread, tensorflow gives an out_of_resources error...
    pool = [Thread(target=start_worker, args=(q,)) for p in range(NUM_PROCESSES)]
    for p in pool:
        p.daemon = True
        p.start()

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((HOST, args.port))
    lsock.listen()
    print('listening on', (HOST, args.port))
    lsock.setblocking(False)

    sel.register(lsock, selectors.EVENT_READ, data={'type': 'listener'})

    while True:
        events = sel.select(timeout=5)
        for key, mask in events:
            sock = key.fileobj
            data = key.data
            if data['type'] == 'listener':
                conn, addr = sock.accept()  # Should be ready to read
                print('accepted connection from', addr)
                conn.setblocking(False)
                sel.register(conn, selectors.EVENT_READ, data={'input':b'', 'type':'client'})
            else:
                if mask & selectors.EVENT_READ:
                    recv_data = ''
                    try:
                        recv_data = sock.recv(4096)  # Should be ready to read
                    except Exception as e:
                        # this is fine
                        pass

                    if len(recv_data) == 0:
                        close_socket(sock)
                        continue

                    data['input'] += recv_data
                    input_ = data['input'].split(b'\n\n')
                    data['input'] = input_.pop()
                    for i in range(len(input_)):
                        # TODO: prevent further reading from this socket until the current command is handled
                        json_input = json.loads(input_[i])
                        assert 'opaque' in json_input

                        if data['type'] == 'client':
                            new_opaque = uuid.uuid4().hex
                            old_opaque = json_input['opaque']
                            client_map[new_opaque] = (sock, old_opaque)
                            json_input['opaque'] = new_opaque
                            for sock in server_map:
                                q.put((sock, json_input))
                        else:
                            assert data['type'] == 'server'
                            new_opaque = json_input['opaque']
                            if new_opaque not in client_map: continue
                            client_sock, old_opaque = client_map[new_opaque]
                            json_input['opaque'] = old_opaque

                            q.put((client_sock, json_input))
