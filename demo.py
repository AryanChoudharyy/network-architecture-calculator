"""Run the assignment's marking sequence on exactly one TCP connection."""
import argparse
import socket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--pipeline", action="store_true")
    args = parser.parse_args()
    cases = [("GET", "/add?a=2&b=3", 200, b"5"), ("GET", "/sub?a=10&b=4", 200, b"6"),
             ("GET", "/mul?a=6&b=7", 200, b"42"), ("GET", "/div?a=1&b=0", 400, None),
             ("GET", "/pow?a=2&b=8", 404, None), ("POST", "/add", 405, None)]
    requests = [f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n".encode()
                for method, path, _, _ in cases]
    with socket.create_connection((args.host, args.port), timeout=5) as client, client.makefile("rb") as stream:
        if args.pipeline:
            client.sendall(b"".join(requests))
        for raw, (method, path, expected, result) in zip(requests, cases):
            if not args.pipeline:
                client.sendall(raw)
            status = int(stream.readline().split()[1])
            headers = {}
            while (line := stream.readline()) != b"\r\n":
                if not line:
                    raise RuntimeError("connection closed early")
                name, value = line.split(b":", 1)
                headers[name.lower()] = value.strip()
            body = stream.read(int(headers[b"content-length"]))
            if status != expected or (result is not None and body != result):
                raise RuntimeError(f"unexpected result: {status}, {body!r}")
            print(f"{method} {path} -> {status} {body.decode()}")
        client.sendall(b"GET /add?a=0&b=0 HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        if not stream.readline().startswith(b"HTTP/1.1 200 "):
            raise RuntimeError("connection did not survive")
        print("socket still open: True (verified by one final probe)")
        print("1 TCP handshake, 6 assignment responses + 1 verification probe")


if __name__ == "__main__":
    main()
