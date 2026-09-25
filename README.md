# Network Architecture Calculator

A complete implementation of **both pages** of the supplied assignment: a socket-only HTTP/1.1 calculator and a specified binary file-transfer protocol with server and client. Python 3.10 or newer. No web framework, HTTP server library, or third-party runtime dependencies.

## Run the calculator

From this directory, in one terminal:

```powershell
./run.ps1 calculator.py
```

In another terminal:

```powershell
./run.ps1 demo.py
./run.ps1 demo.py --pipeline
curl.exe "http://127.0.0.1:8080/div?a=9&b=3"
```

The Windows launcher finds installed Python or this workspace's bundled Python automatically. If PowerShell blocks local scripts, use `powershell -ExecutionPolicy Bypass -File ./run.ps1 calculator.py`. On macOS/Linux, replace `./run.ps1` with `python3`. Direct `python calculator.py` or `py -3 calculator.py` also works when installed. The server defaults to `127.0.0.1:8080`; use `--host`, `--port`, and `--timeout` to override. Stop with Ctrl+C.

| Request | Status | Body |
|---|---|---|
| `GET /add?a=2&b=3` | 200 | `5` |
| `GET /sub?a=10&b=4` | 200 | `6` |
| `GET /mul?a=6&b=7` | 200 | `42` |
| `GET /div?a=9&b=3` | 200 | `3` |
| `GET /div?a=1&b=0` | 400 | Division by zero |
| `GET /add?a=x&b=3` | 400 | Invalid numeric input |
| `GET /pow?a=2&b=8` | 404 | Unknown operation |
| `POST /add` | 405 | Only GET is supported |
| Request without Host | 400 | Host required |

Responses are plain text with byte-accurate Content-Length. Application errors keep the socket open, including missing Host. Request bodies are consumed before dispatch, even for rejected methods. A buffered input stream preserves unread bytes for the next request. No calculation reads until EOF.

**Optional features included:** case-insensitive Connection: close tokens; a configurable 30-second socket inactivity timeout; chunked request bodies with extensions and trailers; ordered pipelining. Responses use Content-Length, so chunked response encoding is unnecessary. Expect: 100-continue is supported. Idle or incomplete requests do not block other clients.

HTTP limits: 16 KiB request line, 16 KiB headers, 1 MiB decoded body, 64 concurrent clients. Conflicting length headers, bad chunk framing, and other errors that prevent locating the next request return an error and close. HTTP/1.1 origin-form is supported; other versions return 505. This is the assignment's HTTP subset, not a general-purpose production HTTP server.

Numbers use decimal arithmetic at 50 significant digits, accepting signed decimals and scientific notation. Inputs are limited to 128 characters and three exponent digits; NaN and infinity are rejected. Duplicate/missing operands and extra query parameters return 400. Encode a literal plus sign as `%2B`. Repeating division is rounded to 50 significant digits.

## Run the binary project

Start the file server:

```powershell
./run.ps1 bserve.py ./www 9000
```

Fetch files in another terminal:

```powershell
./run.ps1 bcurl.py -v localhost:9000/index.html
./run.ps1 bcurl.py -v localhost:9000/hello.txt localhost:9000/index.html
```

Windows also has `./bserve.cmd ./www 9000` and `./bcurl.cmd -v localhost:9000/index.html`. On Unix, run `chmod +x bserve bcurl` once to use the assignment's exact `./bserve` and `./bcurl` commands.

The client makes exactly one TCP connection for all supplied URLs, writes response bodies unchanged to stdout, and prints verbose frame dumps to stderr. Multiple bodies are concatenated without separators. All URLs must have the same host and port. It never reconnects, follows redirects, or silently retries. Exit codes: 0 success, 22 any 4xx/5xx response, 1 transport/protocol failure, 2 invalid CLI arguments. A browser or ordinary curl cannot speak BC/1; use bcurl.

The file server keeps connections open after 200, 400, and 404 responses when framing remains recoverable. It skips unknown frame types exactly by length, handles fragmented and pipelined frames, rejects traversal (including percent-encoded traversal and symlinks outside the root), and sends file bytes unchanged. A `connection: close` binary header is also supported. Serve a trusted, static root: protection against another local process changing symlinks during a file read is outside this assignment's scope.

## Submission files

- `docs/protocol.pdf`: the requested **two-page** standalone wire specification.
- `docs/protocol.md`: editable version of the same specification.
- `docs/annotated-hexdump.md`: a complete real request/response capture, annotated field by field.
- `docs/request.bin`, `docs/response.bin`: original captured bytes.
- `calculator.py`, `bserve.py`, `bcurl.py`, `netcalc/`: runnable implementation.
- `tests/test_network.py`: TCP integration and interoperability checks.
- `docs/requirements.md`: assignment requirements mapped to implementation and evidence.

## Verify

```powershell
./run.ps1 verify.py
```

The tests use temporary directories and ephemeral ports; no running server is required. They cover the assignment sequence on one socket, errors followed by successful requests, fragmentation, pipelining, body consumption, chunking, close, timeout, binary byte preservation, path safety, frame recovery, unknown-frame skipping in both directions, verbose output, CLI exit codes, and exactly one client connection. Independent hand-built wire messages test both peers without relying exclusively on shared encoder/decoder code.

You can also run `python3 -m unittest discover -s tests -v`. To regenerate the live capture: `./run.ps1 scripts/capture_exchange.py`. To regenerate the PDF: install the development-only `reportlab` package and run `./run.ps1 scripts/build_spec.py`. Neither package installation nor PDF tooling is needed to run the project or tests.

## Architecture and design decisions

`transport.py` owns sockets and bounded per-client threads. `http.py` handles text framing and arithmetic. `binary.py` owns BC/1 framing and header encoding. `bserve.py` serves a root directory, and `bcurl.py` implements the one-connection client. BC/1 is a custom educational protocol, not HTTP/2 or interoperable binary HTTP.

The 30-second inactivity timeout allows an interactive demonstration without holding abandoned sockets indefinitely; it is not an absolute whole-message deadline. The server caps simultaneous connections at 64. Oversized binary envelopes close after 400 because buffering or draining arbitrary advertised lengths would permit resource exhaustion. Complete, bounded malformed frames recover at the known next boundary.

References used for framing rationale: [RFC 9112, HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html), [RFC 9113, HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html). The custom BC/1 contract is fully defined in the included specification.
