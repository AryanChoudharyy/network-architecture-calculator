"""Shared TCP lifecycle; all application framing lives in the protocol modules."""
import socket
import threading


class TCPServer:
    def __init__(self, handler, host="127.0.0.1", port=8080, timeout=30.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.handler = handler
        self.timeout = timeout
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen(64)
        self.listener.settimeout(0.2)
        self.address = self.listener.getsockname()
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.clients = set()
        self.slots = threading.BoundedSemaphore(64)

    def serve_forever(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stopped.is_set():
                    break
                raise
            if not self.slots.acquire(blocking=False):
                client.close()
                continue
            with self.lock:
                self.clients.add(client)
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client):
        try:
            with client:
                client.settimeout(self.timeout)
                self.handler(client)
        except (OSError, EOFError):
            pass  # Disconnects and idle timeouts belong to this connection only.
        finally:
            with self.lock:
                self.clients.discard(client)
            self.slots.release()

    def close(self):
        self.stopped.set()
        self.listener.close()
        with self.lock:
            for client in list(self.clients):
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


def run(server, label):
    print(f"{label} listening on {server.address[0]}:{server.address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


def read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        part = stream.read(length - len(data))
        if not part:
            raise EOFError("truncated message")
        data.extend(part)
    return bytes(data)
