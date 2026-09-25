# Assignment completion map

The supplied PDF has two separate assignment pages. Both are implemented; no framework or reference solution was used.

| Requirement | Implementation / deliverable | Verification |
|---|---|---|
| Raw socket, any language, no framework | Python standard library; netcalc/transport.py | No third-party runtime imports |
| Four arithmetic GET endpoints | netcalc/http.py | Assignment sequence and decimal tests |
| 400 invalid operands / zero divisor | calculate() | Arithmetic validation tests |
| 404 unknown route | calculate() | Same-socket sequence |
| 405 unsupported method | calculate(), Allow: GET | POST body drained before next request |
| 400 missing Host | calculate() | Error followed by successful request |
| One TCP connection for all requests | Persistent handle() loop | Assignment sequence and demo.py |
| Consume exactly Content-Length bytes | consume_body(), read_exact() | Embedded fake request in body, next request intact |
| Optional Connection: close | Response then shutdown | Close and HEAD tests |
| Optional defensible idle timeout | Configurable 30 seconds | Idle timeout and concurrent-client tests |
| Optional chunked encoding | Chunked request decoding, trailers | Chunk extensions and following request test |
| Optional ordered pipelining | Sequential parse/respond loop | Batched requests and demo.py --pipeline |
| Binary server root/port command | bserve.py, bserve / bserve.cmd | Temporary-root live TCP tests |
| Binary file response with status/headers | BC/1 response codec | Independent wire decoder, all 256 byte values |
| 404 absent file, 400 malformed frame | bserve handler | Error recovery and subsequent success |
| Binary server remains connected | Repeated frame loop | Pipelined success/error/unknown frames |
| Client builds binary requests | bcurl.py | CLI and independent-peer tests |
| Body to stdout, -v dumps every frame | bcurl fetch() | Separate stdout/stderr assertions |
| Nonzero exit on 4xx/5xx | Exit 22 | CLI 404 test; same branch handles 500 |
| Client never opens second connection | Single create_connection call | Three URLs with call-count assertion |
| Fixed-size header, widths defended | docs/protocol.pdf, 12-byte envelope | Independent hand-built envelopes |
| Ten indexed header names, literal fallback | binary.NAMES, header codec | Literal header request, real capture |
| Unknown types MUST be skipped | Both server and client read loops | Independent unknown-frame tests both ways |
| Two-page standalone specification | docs/protocol.pdf (+ editable Markdown) | PDF page count and rendered layout review |
| Program submission | Entry points, netcalc/, sample www/ | Automated integration suite |
| Annotated full request/response | docs/annotated-hexdump.md and .bin files | Generated from live socket capture |

The assignment's paired-author workflow cannot be recreated by a single implementation. Independent hand-built wire tests are included to check the written protocol beyond encoder/decoder round trips; a separate peer implementation can use the standalone specification.
