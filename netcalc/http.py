"""Deliberately small HTTP/1.1 parser, implemented directly over TCP."""
import argparse
from decimal import Decimal, DecimalException, localcontext
import re
from urllib.parse import parse_qs, urlsplit

from .transport import TCPServer, read_exact, run

MAX_HEADERS = 16384
MAX_BODY = 1024 * 1024
TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?")
REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
           413: "Content Too Large", 417: "Expectation Failed", 431: "Request Header Fields Too Large",
           501: "Not Implemented", 505: "HTTP Version Not Supported"}


class HTTPError(Exception):
    def __init__(self, status=400):
        self.status = status


def line(stream, limit=MAX_HEADERS):
    value = stream.readline(limit + 1)
    if len(value) > limit:
        raise HTTPError(431)
    if not value.endswith(b"\r\n"):
        raise HTTPError()
    return value[:-2]


def fields(stream):
    headers = {}
    size = 0
    while True:
        raw = line(stream)
        size += len(raw) + 2
        if size > MAX_HEADERS:
            raise HTTPError(431)
        if not raw:
            return headers
        name, sep, value = raw.partition(b":")
        if not sep or not TOKEN.fullmatch(name):
            raise HTTPError()
        if any(c < 32 and c != 9 or c == 127 for c in value):
            raise HTTPError()
        headers.setdefault(name.decode("ascii").lower(), []).append(value.strip().decode("latin-1"))


def consume_body(stream, headers, client):
    lengths = headers.get("content-length", [])
    transfer = headers.get("transfer-encoding", [])
    if transfer and lengths:
        raise HTTPError()  # Ambiguous framing cannot safely reuse a connection.
    if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0])):
        raise HTTPError()
    size = int(lengths[0]) if lengths else 0
    if size > MAX_BODY:
        raise HTTPError(413)
    if transfer and (len(transfer) != 1 or transfer[0].lower() != "chunked"):
        raise HTTPError(501)
    if "expect" in headers:
        if headers["expect"] != ["100-continue"]:
            raise HTTPError(417)
        client.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
    if not transfer:
        read_exact(stream, size)
        return
    total = 0
    while True:
        chunk_line = line(stream)
        size_text, _, extension = chunk_line.partition(b";")
        if not re.fullmatch(rb"[0-9a-fA-F]{1,8}", size_text) or any(c < 32 or c == 127 for c in extension):
            raise HTTPError()
        size = int(size_text, 16)
        total += size
        if total > MAX_BODY:
            raise HTTPError(413)
        if size == 0:
            trailers = fields(stream)
            if set(trailers) & {"content-length", "transfer-encoding", "host", "connection"}:
                raise HTTPError()
            return
        read_exact(stream, size)
        if read_exact(stream, 2) != b"\r\n":
            raise HTTPError()


def calculate(method, target, headers):
    if len(headers.get("host", [])) != 1 or not headers["host"][0] or re.search(r"[\s,/@]", headers["host"][0]):
        return 400, b"Host header required and must be valid"
    if method != "GET":
        return 405, b"Only GET is supported"
    try:
        url = urlsplit(target)
        if not target.startswith("/") or url.netloc or url.fragment:
            return 400, b"Use an origin-form request target"
        if url.path not in ("/add", "/sub", "/mul", "/div"):
            return 404, b"Unknown operation"
        args = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
        if set(args) != {"a", "b"} or any(len(v) != 1 for v in args.values()):
            return 400, b"Provide exactly one a and one b"
        values = [args[key][0] for key in ("a", "b")]
        if any(len(v) > 128 or not NUMBER.fullmatch(v) for v in values):
            return 400, b"Operands must be finite decimal numbers"
        with localcontext() as context:
            context.prec = 50
            a, b = map(Decimal, values)
            if url.path == "/div" and b == 0:
                return 400, b"Division by zero"
            result = {"/add": lambda: a + b, "/sub": lambda: a - b,
                      "/mul": lambda: a * b, "/div": lambda: a / b}[url.path]()
            text = format(result, "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return 200, ("0" if result == 0 else text).encode("ascii")
    except (ValueError, DecimalException):
        return 400, b"Invalid operands or query"


def response(client, status, body, close=False, head=False):
    headers = [f"HTTP/1.1 {status} {REASONS[status]}", f"Content-Length: {len(body)}",
               "Content-Type: text/plain; charset=utf-8", "Connection: " + ("close" if close else "keep-alive")]
    if status == 405:
        headers.append("Allow: GET")
    client.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + (b"" if head else body))


def handle(client):
    with client.makefile("rb") as stream:
        while True:
            method = ""
            try:
                first = stream.readline(MAX_HEADERS + 1)
                if not first:
                    return
                if len(first) > MAX_HEADERS:
                    raise HTTPError(431)
                if not first.endswith(b"\r\n"):
                    raise HTTPError()
                parts = first[:-2].split(b" ")
                if len(parts) != 3 or not TOKEN.fullmatch(parts[0]):
                    raise HTTPError()
                method, target, version = [p.decode("ascii") for p in parts]
                if any(ord(c) < 33 or ord(c) == 127 for c in target):
                    raise HTTPError()
                if version != "HTTP/1.1":
                    raise HTTPError(505)
                headers = fields(stream)
                consume_body(stream, headers, client)
                close = "close" in {v.strip().lower() for h in headers.get("connection", []) for v in h.split(",")}
                status, body = calculate(method, target, headers)
                response(client, status, body, close, method == "HEAD")
                if close:
                    return
            except (HTTPError, UnicodeError, EOFError) as exc:
                status = exc.status if isinstance(exc, HTTPError) else 400
                response(client, status, REASONS[status].encode(), True, method == "HEAD")
                return


def main():
    parser = argparse.ArgumentParser(description="Socket-only persistent HTTP/1.1 calculator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--timeout", type=float, default=30, help="seconds of socket inactivity")
    args = parser.parse_args()
    run(TCPServer(handle, args.host, args.port, args.timeout), "Calculator")
