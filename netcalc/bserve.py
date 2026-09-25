import argparse
from email.utils import formatdate
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote_to_bytes, urlsplit

from .binary import (Frame, FrameError, ProtocolError, MAX_PAYLOAD, REQUEST, RESPONSE,
                     decode_request, read_frame, response_payload)
from .transport import TCPServer, run


def file_response(root, method, target):
    if method != "GET":
        return 405, b"Only GET is supported\n", "text/plain", None
    try:
        url = urlsplit(target)
        if url.netloc or url.fragment or re.search(r"%(?![0-9a-fA-F]{2})", url.path):
            raise ValueError()
        path = unquote_to_bytes(url.path).decode("utf-8")
        if "\\" in path or ":" in path or "\x00" in path or ".." in path.split("/"):
            raise ValueError()
        candidate = (root / path.lstrip("/")).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError()
        if not candidate.is_file():
            return 404, b"Not found\n", "text/plain", None
        with candidate.open("rb") as source:
            body = source.read(MAX_PAYLOAD - 4096 + 1)
        if len(body) > MAX_PAYLOAD - 4096:
            return 413, b"File exceeds frame limit\n", "text/plain", None
        return 200, body, mimetypes.guess_type(candidate.name)[0] or "application/octet-stream", candidate.stat().st_mtime
    except (ValueError, UnicodeError):
        return 400, b"Invalid or unsafe path\n", "text/plain", None
    except FileNotFoundError:
        return 404, b"Not found\n", "text/plain", None
    except OSError:
        return 500, b"Unable to read file\n", "text/plain", None


def send_response(client, request_id, status, body, content_type="text/plain", modified=None, close=False):
    headers = {"content-type": content_type, "content-length": str(len(body)), "server": "bserve/1",
               "connection": "close" if close else "keep-alive", "cache-control": "no-store",
               "x-request-id": str(request_id)}
    if modified is not None:
        headers["last-modified"] = formatdate(modified, usegmt=True)
    client.sendall(Frame(RESPONSE, request_id, response_payload(status, headers, body)).encode())


def handler(root):
    root = Path(root).resolve()

    def handle(client):
        with client.makefile("rb") as stream:
            while True:
                try:
                    frame = read_frame(stream)
                    if frame is None:
                        return
                    if frame.kind not in (REQUEST, RESPONSE):
                        continue  # Complete payload already consumed, including unknown frames.
                    if frame.kind != REQUEST or frame.request_id == 0:
                        raise FrameError("expected request with nonzero id", frame.request_id)
                    try:
                        method, path, headers = decode_request(frame.payload)
                        if headers.get("connection", "keep-alive") not in ("keep-alive", "close"):
                            raise ProtocolError("invalid connection value")
                    except ProtocolError as exc:
                        raise FrameError(str(exc), frame.request_id) from exc
                    close = headers.get("connection") == "close"
                    status, body, content_type, modified = file_response(root, method, path)
                    send_response(client, frame.request_id, status, body, content_type, modified, close)
                    if close:
                        return
                except FrameError as exc:
                    send_response(client, exc.request_id, 400, b"Malformed frame\n", close=exc.fatal)
                    if exc.fatal:
                        return
                except EOFError:
                    # A peer that half-closes mid-frame can still receive an error.
                    send_response(client, 0, 400, b"Truncated frame\n", close=True)
                    return
    return handle


def main():
    parser = argparse.ArgumentParser(description="BC/1 persistent binary file server")
    parser.add_argument("root", type=Path)
    parser.add_argument("port", type=int, nargs="?", default=9000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("root must be an existing directory")
    run(TCPServer(handler(args.root), args.host, args.port, args.timeout), "BC/1 file server")
