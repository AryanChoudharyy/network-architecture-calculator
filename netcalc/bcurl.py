import argparse
import socket
import sys
from urllib.parse import urlsplit

from .binary import (Frame, ProtocolError, REQUEST, RESPONSE, decode_response, hexdump,
                     read_frame, request_payload)


def parse_url(text):
    url = urlsplit(text if "://" in text else "bc://" + text)
    if url.scheme != "bc" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("use bc://host:port/path or host:port/path")
    return (url.hostname.lower(), url.port or 9000), (url.path or "/index.html") + ("?" + url.query if url.query else "")


def fetch(urls, verbose=False, output=None, diagnostics=None, timeout=30):
    output = output if output is not None else sys.stdout.buffer
    diagnostics = diagnostics if diagnostics is not None else sys.stderr
    parsed = [parse_url(url) for url in urls]
    address = parsed[0][0]
    if any(addr != address for addr, _ in parsed):
        raise ValueError("all URLs must use the same host and port; only one connection is allowed")
    failed = False
    # This is the only connection creation site: no retries, redirects, or reconnects.
    with socket.create_connection(address, timeout=timeout) as client, client.makefile("rb") as stream:
        for request_id, (_, path) in enumerate(parsed, 1):
            authority = f"[{address[0]}]:{address[1]}" if ":" in address[0] else f"{address[0]}:{address[1]}"
            headers = {"host": authority, "user-agent": "bcurl/1", "accept": "*/*"}
            raw = Frame(REQUEST, request_id, request_payload(path, headers)).encode()
            if verbose:
                print(f"> request {request_id}, {len(raw)} bytes\n{hexdump(raw)}", file=diagnostics)
            client.sendall(raw)
            while True:
                frame = read_frame(stream)
                if frame is None:
                    raise ProtocolError("server closed before a response; no reconnect attempted")
                if verbose:
                    print(f"< frame type {frame.kind}, id {frame.request_id}\n{hexdump(frame.encode())}", file=diagnostics)
                if frame.kind not in (REQUEST, RESPONSE):
                    continue
                if frame.kind != RESPONSE or frame.request_id != request_id:
                    raise ProtocolError("unexpected response type or request id")
                status, _, body = decode_response(frame.payload)
                output.write(body)
                output.flush()
                failed |= status >= 400
                break
    return 22 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="Fetch BC/1 files using exactly one TCP connection")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("urls", nargs="+")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    try:
        return fetch(args.urls, args.verbose, timeout=args.timeout)
    except (OSError, EOFError, ProtocolError, ValueError) as exc:
        print(f"bcurl: {exc}", file=sys.stderr)
        return 1
