import argparse
import threading
import socket
import time

from sup_server import SupServer

DEFAULT_URL = "http://127.0.0.1:3000/routing_gateway/"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", nargs=1, default=8183,
        type=int, help="The port this program will listen on")
    parser.add_argument("-n", "--host", nargs=1, default="localhost",
        type=str, help="The address this program will listen on")
    parser.add_argument("-u", "--url", nargs=1, default=DEFAULT_URL,
        type=str, help="URL of the ussd airflow server")
    args = parser.parse_args()
    HOST = args.host
    PORT = args.port

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.bind((HOST, PORT))
    sock.listen(5)
    print("Listening")
    conns = []
    try:
        while True:
            (client, address) = sock.accept()
            client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            ct = SupServer(client, args.url)
            conns.append(ct)
            ct.start()
            time.sleep(0.05)
    finally:
        for c in conns:
            c.join()
        sock.close()