"""Capture real server bytes and annotate every field in a complete BC/1 exchange."""
from pathlib import Path
import socket
import struct
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from netcalc.binary import Frame, NAMES, hexdump, request_payload
from netcalc.bserve import handler
from netcalc.transport import TCPServer, read_exact


def annotations(raw, response=False):
    result = []
    pos = 0
    def take(n, label, text=None):
        nonlocal pos
        data = raw[pos:pos+n]
        rendered = text if text is not None else (str(int.from_bytes(data, "big")) if "length" in label or label == "Header count" else repr(data))
        result.append(f"| {pos:04x}-{pos+n-1:04x} | {n} | {label} | `{rendered}` |")
        pos += n
        return data
    take(2, "Magic", "BC")
    take(1, "Version", "1")
    take(1, "Frame type", "2 RESPONSE" if response else "1 REQUEST")
    take(4, "Payload length", str(len(raw) - 12))
    take(4, "Request ID", str(int.from_bytes(raw[8:12], "big")))
    if response:
        take(2, "Status", str(int.from_bytes(raw[pos:pos+2], "big")))
    else:
        n = take(1, "Method byte length")[0]
        take(n, "Method")
        n = int.from_bytes(take(2, "Path byte length"), "big")
        take(n, "Path")
    count = take(1, "Header count")[0]
    for _ in range(count):
        tag = raw[pos]
        name = NAMES[tag-1] if tag else "literal"
        take(1, "Header name index", f"{tag}: {name}")
        if not tag:
            n = int.from_bytes(take(2, "Literal name byte length"), "big")
            take(n, "Literal name")
        n = int.from_bytes(take(2, f"{name} value byte length"), "big")
        take(n, f"{name} value")
    if response:
        take(len(raw)-pos, "Exact file body")
    assert pos == len(raw)
    return "| Byte offsets (hex) | Bytes | Field | Value |\n|---|---:|---|---|\n" + "\n".join(result)


def main():
    server = TCPServer(handler(ROOT / "www"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        raw = Frame(1, 1, request_payload("/hello.txt", {"host": "localhost:9000", "user-agent": "bcurl/1", "accept": "*/*", "x-note": "demo"})).encode()
        with socket.create_connection(server.address, timeout=3) as client, client.makefile("rb") as stream:
            client.sendall(raw)
            header = read_exact(stream, 12)
            response = header + read_exact(stream, struct.unpack("!2sBBII", header)[3])
        parts = ["# Annotated BC/1 exchange\n\nCaptured from the real bserve handler over one local TCP connection by `scripts/capture_exchange.py`. The advertised host is illustrative; the capture uses an ephemeral local port. Offsets restart at zero in each frame. No bytes are omitted. The literal `x-note` header demonstrates the fallback encoding. File modification time reflects the sample file at capture time.\n"]
        for label, data, is_response in [("Request", raw, False), ("Response", response, True)]:
            parts.append(f"## {label} ({len(data)} bytes)\n\n```text\n{hexdump(data)}\n```\n\n" + annotations(data, is_response))
        parts.append("\nThe response echoes request ID 1. The final bytes are the complete `www/hello.txt` file. `connection=keep-alive` leaves the same connection available for the next request. All captured bytes are included in the hexadecimal listings above.\n")
        (ROOT / "docs/annotated-hexdump.md").write_text("\n\n".join(parts), encoding="utf-8")
        print(f"Captured {len(raw)} request bytes and {len(response)} response bytes")
    finally:
        server.close()
        thread.join(2)


if __name__ == "__main__":
    main()
