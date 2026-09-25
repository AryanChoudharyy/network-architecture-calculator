"""Real TCP integration checks, including independently constructed wire messages."""
import io
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from netcalc import binary
from netcalc.bcurl import fetch
from netcalc.bserve import handler
from netcalc.http import handle
from netcalc.transport import TCPServer


def request(target="/add?a=2&b=3", method="GET", headers=b"Host: localhost\r\n", body=b""):
    return f"{method} {target} HTTP/1.1\r\n".encode() + headers + b"\r\n" + body


def http_response(stream, head=False):
    first = stream.readline()
    if not first:
        raise AssertionError("connection closed before response")
    status = int(first.split()[1])
    headers = {}
    while True:
        line = stream.readline()
        if line == b"\r\n":
            break
        if not line:
            raise AssertionError("truncated response headers")
        k, v = line.split(b":", 1)
        headers[k.lower()] = v.strip()
    body = stream.read(int(headers[b"content-length"])) if not head else b""
    return status, headers, body


class LiveServer(unittest.TestCase):
    def start(self, callback, timeout=2):
        server = TCPServer(callback, port=0, timeout=timeout)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        self.addCleanup(server.close)
        return server

    def connect(self, server):
        client = socket.create_connection(server.address, timeout=2)
        self.addCleanup(client.close)
        stream = client.makefile("rb")
        self.addCleanup(stream.close)
        return client, stream


class HTTPTests(LiveServer):
    def setUp(self):
        self.server = self.start(handle)

    def test_assignment_sequence_single_socket(self):
        client, stream = self.connect(self.server)
        cases = [("/add?a=2&b=3", "GET", 200, b"5"), ("/sub?a=10&b=4", "GET", 200, b"6"),
                 ("/mul?a=6&b=7", "GET", 200, b"42"), ("/div?a=9&b=3", "GET", 200, b"3"),
                 ("/div?a=1&b=0", "GET", 400, None), ("/add?a=x&b=3", "GET", 400, None),
                 ("/pow?a=2&b=8", "GET", 404, None), ("/add", "POST", 405, None)]
        for target, method, expected, value in cases:
            client.sendall(request(target, method))
            status, headers, body = http_response(stream)
            self.assertEqual(status, expected)
            self.assertEqual(headers[b"connection"], b"keep-alive")
            if value is not None:
                self.assertEqual(body, value)
        client.sendall(request(headers=b""))
        self.assertEqual(http_response(stream)[0], 400)
        client.sendall(request())
        self.assertEqual(http_response(stream)[2], b"5")

    def test_pipelining_body_and_error_drain(self):
        client, stream = self.connect(self.server)
        body = b"GET /this-is-body HTTP/1.1\r\n\r\n\x00\xff"
        client.sendall(request(method="POST", headers=f"Host: x\r\nContent-Length: {len(body)}\r\n".encode(), body=body)
                       + request("/sub?a=10&b=4") + request("/mul?a=6&b=7") + request())
        self.assertEqual(http_response(stream)[0], 405)
        self.assertEqual([http_response(stream)[2] for _ in range(3)], [b"6", b"42", b"5"])

    def test_fragmented_request(self):
        client, stream = self.connect(self.server)
        for byte in request(headers=b"hOsT: x\r\nContent-Length: 3\r\n", body=b"abc"):
            client.sendall(bytes([byte]))
        self.assertEqual(http_response(stream)[2], b"5")

    def test_chunked_extensions_trailers_then_next_request(self):
        client, stream = self.connect(self.server)
        client.sendall(request(method="POST", headers=b"Host: x\r\nTransfer-Encoding: chunked\r\n",
                               body=b"3;name=value\r\nabc\r\n2\r\nde\r\n0\r\nX-Trace: yes\r\n\r\n") + request())
        self.assertEqual(http_response(stream)[0], 405)
        self.assertEqual(http_response(stream)[2], b"5")

    def test_expect_continue(self):
        client, stream = self.connect(self.server)
        client.sendall(request(headers=b"Host: x\r\nContent-Length: 3\r\nExpect: 100-continue\r\n"))
        self.assertEqual(stream.readline(), b"HTTP/1.1 100 Continue\r\n")
        self.assertEqual(stream.readline(), b"\r\n")
        client.sendall(b"abc")
        self.assertEqual(http_response(stream)[2], b"5")

    def test_connection_close(self):
        client, stream = self.connect(self.server)
        client.sendall(request(headers=b"Host: x\r\nConnection: keep-alive, CLOSE\r\n"))
        status, headers, body = http_response(stream)
        self.assertEqual((status, body, headers[b"connection"]), (200, b"5", b"close"))
        self.assertEqual(stream.read(1), b"")

    def test_bad_framing_is_fatal(self):
        for fields in [b"Content-Length: -1\r\n", b"Content-Length: 2\r\nContent-Length: 3\r\n",
                       b"Content-Length: 0\r\nTransfer-Encoding: chunked\r\n", b"Bad Header: x\r\n"]:
            with self.subTest(fields=fields):
                client, stream = self.connect(self.server)
                client.sendall(request(headers=b"Host: x\r\n" + fields))
                status, headers, _ = http_response(stream)
                self.assertEqual(status, 400)
                self.assertEqual(headers[b"connection"], b"close")
                self.assertEqual(stream.read(1), b"")

    def test_limits_and_invalid_chunk(self):
        cases = [(request(headers=b"Host: x\r\nContent-Length: 1048577\r\n"), 413),
                 (request(headers=b"Host: x\r\nX: " + b"a" * 17000 + b"\r\n"), 431),
                 (request(headers=b"Host: x\r\nTransfer-Encoding: chunked\r\n", body=b"zz\r\n"), 400)]
        for data, expected in cases:
            client, stream = self.connect(self.server)
            client.sendall(data)
            self.assertEqual(http_response(stream)[0], expected)

    def test_arithmetic_and_validation(self):
        client, stream = self.connect(self.server)
        for query, status, result in [("/add?a=0.1&b=0.2", 200, b"0.3"), ("/mul?a=-2.5&b=4", 200, b"-10"),
                                       ("/div?a=1&b=4", 200, b"0.25"), ("/add?a=1", 400, None),
                                       ("/add?a=NaN&b=2", 400, None), ("/add?a=1&a=2&b=3", 400, None)]:
            client.sendall(request(query))
            actual, _, body = http_response(stream)
            self.assertEqual(actual, status)
            if result:
                self.assertEqual(body, result)

    def test_head_does_not_desynchronize(self):
        client, stream = self.connect(self.server)
        client.sendall(request(method="HEAD") + request())
        self.assertEqual(http_response(stream, head=True)[0], 405)
        self.assertEqual(http_response(stream)[2], b"5")

    def test_idle_client_does_not_block_others(self):
        idle, _ = self.connect(self.server)
        idle.sendall(b"GET ")
        client, stream = self.connect(self.server)
        client.sendall(request())
        self.assertEqual(http_response(stream)[2], b"5")

    def test_idle_timeout(self):
        client, stream = self.connect(self.start(handle, timeout=0.1))
        self.assertEqual(stream.read(1), b"")


# Hand-built BC/1 requests do not rely on the production encoder.
def wire_request(path=b"/hello.txt", request_id=1, kind=1, payload=None):
    if payload is None:
        payload = b"\x03GET" + struct.pack("!H", len(path)) + path + b"\x01\x01\x00\x01x"
    return struct.pack("!2sBBII", b"BC", 1, kind, len(payload), request_id) + payload


def wire_response(stream):
    header = stream.read(12)
    magic, version, kind, length, request_id = struct.unpack("!2sBBII", header)
    if (magic, version, kind) != (b"BC", 1, 2):
        raise AssertionError("invalid response envelope")
    payload = io.BytesIO(stream.read(length))
    status = int.from_bytes(payload.read(2), "big")
    count = payload.read(1)[0]
    headers = {}
    names = ["host", "user-agent", "accept", "content-type", "content-length", "server", "connection",
             "cache-control", "last-modified", "x-request-id"]
    for _ in range(count):
        tag = payload.read(1)[0]
        name = names[tag - 1] if tag else payload.read(int.from_bytes(payload.read(2), "big")).decode()
        value = payload.read(int.from_bytes(payload.read(2), "big")).decode()
        headers[name] = value
    body = payload.read()
    if headers["content-length"] != str(len(body)):
        raise AssertionError("body length mismatch")
    return request_id, status, headers, body


class BinaryTests(LiveServer):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "hello.txt").write_bytes(b"Hello, BC/1!\n")
        (self.root / "raw.bin").write_bytes(bytes(range(256)))
        self.server = self.start(handler(self.root))

    def test_pipeline_unknown_frame_malformed_and_recovery(self):
        client, stream = self.connect(self.server)
        client.sendall(wire_request() + wire_request(kind=99, payload=b"arbitrary\x00bytes")
                       + wire_request(request_id=2, payload=b"\xff")
                       + wire_request(b"/missing", 3) + wire_request(b"/raw.bin", 4))
        replies = [wire_response(stream) for _ in range(4)]
        self.assertEqual([(r[0], r[1]) for r in replies], [(1, 200), (2, 400), (3, 404), (4, 200)])
        self.assertEqual(replies[0][3], b"Hello, BC/1!\n")
        self.assertEqual(replies[3][3], bytes(range(256)))

    def test_fragmented_frame(self):
        client, stream = self.connect(self.server)
        for byte in wire_request():
            client.sendall(bytes([byte]))
        self.assertEqual(wire_response(stream)[1], 200)

    def test_bad_magic_recovery(self):
        client, stream = self.connect(self.server)
        client.sendall(b"XX" + wire_request()[2:] + wire_request(request_id=2))
        self.assertEqual(wire_response(stream)[1], 400)
        self.assertEqual(wire_response(stream)[1], 200)

    def test_oversized_frame(self):
        client, stream = self.connect(self.server)
        client.sendall(struct.pack("!2sBBII", b"BC", 1, 1, binary.MAX_PAYLOAD + 1, 7))
        response = wire_response(stream)
        self.assertEqual(response[1], 400)
        self.assertEqual(response[2]["connection"], "close")
        self.assertEqual(stream.read(1), b"")

    def test_truncated_frame(self):
        client, stream = self.connect(self.server)
        client.sendall(wire_request()[:-2])
        client.shutdown(socket.SHUT_WR)
        self.assertEqual(wire_response(stream)[1], 400)

    def test_path_restrictions(self):
        client, stream = self.connect(self.server)
        for path in [b"/../secret", b"/%2e%2e/secret", b"/C:/Windows", b"/a%5c..%5csecret", b"/%00", b"/%zz"]:
            client.sendall(wire_request(path))
            self.assertEqual(wire_response(stream)[1], 400, path)
        client.sendall(wire_request())
        self.assertEqual(wire_response(stream)[1], 200)

    def test_literal_headers_and_close(self):
        client, stream = self.connect(self.server)
        headers = {"host": "x", "x-example": "hello", "connection": "close"}
        client.sendall(binary.Frame(1, 5, binary.request_payload("/hello.txt", headers)).encode())
        self.assertEqual(wire_response(stream)[1], 200)
        self.assertEqual(stream.read(1), b"")

    def test_client_one_connection_multiple_urls_verbose_and_error_exit(self):
        output, diagnostics = io.BytesIO(), io.StringIO()
        base = f"127.0.0.1:{self.server.address[1]}"
        original = socket.create_connection
        with patch("netcalc.bcurl.socket.create_connection", wraps=original) as connect:
            status = fetch([base + "/hello.txt", base + "/missing", base + "/raw.bin"], True, output, diagnostics)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(status, 22)
        self.assertEqual(output.getvalue(), b"Hello, BC/1!\nNot found\n" + bytes(range(256)))
        self.assertEqual(diagnostics.getvalue().count("> request"), 3)
        self.assertEqual(diagnostics.getvalue().count("< frame"), 3)

    def test_client_cli_stdout_and_exit_codes(self):
        base = f"127.0.0.1:{self.server.address[1]}"
        for path, expected in [("/raw.bin", 0), ("/missing", 22)]:
            result = subprocess.run([sys.executable, "bcurl.py", "-v", base + path], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, expected, result.stderr)
            if expected == 0:
                self.assertEqual(result.stdout, bytes(range(256)))
            self.assertIn(b"0000", result.stderr)

    def test_client_rejects_cross_origin_before_connect(self):
        with patch("netcalc.bcurl.socket.create_connection") as connect:
            with self.assertRaises(ValueError):
                fetch(["localhost:9000/a", "localhost:9001/b"])
            connect.assert_not_called()

    def test_client_skips_unknown_response_using_independent_peer(self):
        def peer(client):
            with client.makefile("rb") as stream:
                header = stream.read(12)
                _, _, _, length, request_id = struct.unpack("!2sBBII", header)
                stream.read(length)
                unknown = struct.pack("!2sBBII", b"BC", 1, 88, 3, 0) + b"xyz"
                payload = b"\x00\xc8\x01\x05\x00\x013abc"
                client.sendall(unknown + struct.pack("!2sBBII", b"BC", 1, 2, len(payload), request_id) + payload)
        server = self.start(peer)
        output, diag = io.BytesIO(), io.StringIO()
        self.assertEqual(fetch([f"127.0.0.1:{server.address[1]}/a"], True, output, diag), 0)
        self.assertEqual(output.getvalue(), b"abc")
        self.assertIn("frame type 88", diag.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
