"""BC/1 wire codec. See docs/protocol.md for the independent wire contract."""
from dataclasses import dataclass
import re
import struct

from .transport import read_exact

HEADER = struct.Struct("!2sBBII")
MAX_PAYLOAD = 8 * 1024 * 1024
REQUEST, RESPONSE = 1, 2
NAMES = ("host", "user-agent", "accept", "content-type", "content-length", "server",
         "connection", "cache-control", "last-modified", "x-request-id")
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9a-z-]+")


class ProtocolError(ValueError):
    pass


class FrameError(ProtocolError):
    def __init__(self, message, request_id=0, fatal=False):
        super().__init__(message)
        self.request_id, self.fatal = request_id, fatal


@dataclass
class Frame:
    kind: int
    request_id: int
    payload: bytes

    def encode(self):
        if len(self.payload) > MAX_PAYLOAD:
            raise ProtocolError("payload exceeds 8 MiB")
        return HEADER.pack(b"BC", 1, self.kind, len(self.payload), self.request_id) + self.payload


def read_frame(stream):
    first = stream.read(1)
    if not first:
        return None
    header = first + read_exact(stream, HEADER.size - 1)
    magic, version, kind, size, request_id = HEADER.unpack(header)
    if size > MAX_PAYLOAD:
        raise FrameError("payload exceeds 8 MiB", request_id, True)
    payload = read_exact(stream, size)
    if magic != b"BC" or version != 1:
        raise FrameError("invalid magic or version", request_id)
    return Frame(kind, request_id, payload)


class Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if self.pos + size > len(self.data):
            raise ProtocolError("truncated payload field")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return int.from_bytes(self.take(2), "big")

    def text(self, size):
        try:
            return self.take(size).decode("utf-8")
        except UnicodeError as exc:
            raise ProtocolError("invalid UTF-8") from exc


def sized(text, width=2):
    data = text.encode("utf-8")
    if len(data) >= 1 << (width * 8):
        raise ProtocolError("text field too long")
    return len(data).to_bytes(width, "big") + data


def validate_header(name, value):
    if not TOKEN.fullmatch(name) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ProtocolError("invalid header name or value")


def encode_headers(headers):
    if len(headers) > 64:
        raise ProtocolError("too many headers")
    result = bytearray([len(headers)])
    for name, value in headers.items():
        validate_header(name, value)
        if name in NAMES:
            result.append(NAMES.index(name) + 1)
        else:
            result.append(0)
            result.extend(sized(name))
        result.extend(sized(value))
    return bytes(result)


def decode_headers(cursor):
    count = cursor.u8()
    if count > 64:
        raise ProtocolError("too many headers")
    result = {}
    for _ in range(count):
        tag = cursor.u8()
        if tag > len(NAMES):
            raise ProtocolError("unknown header index; use literal encoding")
        name = NAMES[tag - 1] if tag else cursor.text(cursor.u16())
        value = cursor.text(cursor.u16())
        validate_header(name, value)
        if name in result:
            raise ProtocolError("duplicate header")
        result[name] = value
    return result


def request_payload(path, headers, method="GET"):
    return sized(method, 1) + sized(path) + encode_headers(headers)


def decode_request(payload):
    cursor = Cursor(payload)
    method = cursor.text(cursor.u8())
    path = cursor.text(cursor.u16())
    headers = decode_headers(cursor)
    if cursor.pos != len(payload) or not re.fullmatch(r"[A-Z]+", method):
        raise ProtocolError("invalid request method or trailing bytes")
    if not path.startswith("/") or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in path):
        raise ProtocolError("invalid path")
    if not headers.get("host"):
        raise ProtocolError("host required")
    return method, path, headers


def response_payload(status, headers, body):
    return struct.pack("!H", status) + encode_headers(headers) + body


def decode_response(payload):
    cursor = Cursor(payload)
    status = cursor.u16()
    headers = decode_headers(cursor)
    body = cursor.take(len(payload) - cursor.pos)
    if not 100 <= status <= 599 or headers.get("content-length") != str(len(body)):
        raise ProtocolError("invalid status or content-length")
    if headers.get("connection", "keep-alive") not in ("keep-alive", "close"):
        raise ProtocolError("invalid connection value")
    return status, headers, body


def hexdump(data):
    lines = []
    for offset in range(0, len(data), 16):
        part = data[offset:offset + 16]
        chars = "".join(chr(c) if 32 <= c < 127 else "." for c in part)
        lines.append(f"{offset:04x}  {part.hex(' '):47}  |{chars}|")
    return "\n".join(lines)
