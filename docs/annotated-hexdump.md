# Annotated BC/1 exchange

Captured from the real bserve handler over one local TCP connection by `scripts/capture_exchange.py`. The advertised host is illustrative; the capture uses an ephemeral local port. Offsets restart at zero in each frame. No bytes are omitted. The literal `x-note` header demonstrates the fallback encoding. File modification time reflects the sample file at capture time.


## Request (77 bytes)

```text
0000  42 43 01 01 00 00 00 41 00 00 00 01 03 47 45 54  |BC.....A.....GET|
0010  00 0a 2f 68 65 6c 6c 6f 2e 74 78 74 04 01 00 0e  |../hello.txt....|
0020  6c 6f 63 61 6c 68 6f 73 74 3a 39 30 30 30 02 00  |localhost:9000..|
0030  07 62 63 75 72 6c 2f 31 03 00 03 2a 2f 2a 00 00  |.bcurl/1...*/*..|
0040  06 78 2d 6e 6f 74 65 00 04 64 65 6d 6f           |.x-note..demo|
```

| Byte offsets (hex) | Bytes | Field | Value |
|---|---:|---|---|
| 0000-0001 | 2 | Magic | `BC` |
| 0002-0002 | 1 | Version | `1` |
| 0003-0003 | 1 | Frame type | `1 REQUEST` |
| 0004-0007 | 4 | Payload length | `65` |
| 0008-000b | 4 | Request ID | `1` |
| 000c-000c | 1 | Method byte length | `3` |
| 000d-000f | 3 | Method | `b'GET'` |
| 0010-0011 | 2 | Path byte length | `10` |
| 0012-001b | 10 | Path | `b'/hello.txt'` |
| 001c-001c | 1 | Header count | `4` |
| 001d-001d | 1 | Header name index | `1: host` |
| 001e-001f | 2 | host value byte length | `14` |
| 0020-002d | 14 | host value | `b'localhost:9000'` |
| 002e-002e | 1 | Header name index | `2: user-agent` |
| 002f-0030 | 2 | user-agent value byte length | `7` |
| 0031-0037 | 7 | user-agent value | `b'bcurl/1'` |
| 0038-0038 | 1 | Header name index | `3: accept` |
| 0039-003a | 2 | accept value byte length | `3` |
| 003b-003d | 3 | accept value | `b'*/*'` |
| 003e-003e | 1 | Header name index | `0: literal` |
| 003f-0040 | 2 | Literal name byte length | `6` |
| 0041-0046 | 6 | Literal name | `b'x-note'` |
| 0047-0048 | 2 | literal value byte length | `4` |
| 0049-004c | 4 | literal value | `b'demo'` |

## Response (117 bytes)

```text
0000  42 43 01 02 00 00 00 69 00 00 00 01 00 c8 07 04  |BC.....i........|
0010  00 0a 74 65 78 74 2f 70 6c 61 69 6e 05 00 02 31  |..text/plain...1|
0020  33 06 00 08 62 73 65 72 76 65 2f 31 07 00 0a 6b  |3...bserve/1...k|
0030  65 65 70 2d 61 6c 69 76 65 08 00 08 6e 6f 2d 73  |eep-alive...no-s|
0040  74 6f 72 65 0a 00 01 31 09 00 1d 46 72 69 2c 20  |tore...1...Fri, |
0050  32 35 20 53 65 70 20 32 30 32 36 20 30 37 3a 31  |25 Sep 2026 07:1|
0060  39 3a 32 34 20 47 4d 54 48 65 6c 6c 6f 2c 20 42  |9:24 GMTHello, B|
0070  43 2f 31 21 0a                                   |C/1!.|
```

| Byte offsets (hex) | Bytes | Field | Value |
|---|---:|---|---|
| 0000-0001 | 2 | Magic | `BC` |
| 0002-0002 | 1 | Version | `1` |
| 0003-0003 | 1 | Frame type | `2 RESPONSE` |
| 0004-0007 | 4 | Payload length | `105` |
| 0008-000b | 4 | Request ID | `1` |
| 000c-000d | 2 | Status | `200` |
| 000e-000e | 1 | Header count | `7` |
| 000f-000f | 1 | Header name index | `4: content-type` |
| 0010-0011 | 2 | content-type value byte length | `10` |
| 0012-001b | 10 | content-type value | `b'text/plain'` |
| 001c-001c | 1 | Header name index | `5: content-length` |
| 001d-001e | 2 | content-length value byte length | `2` |
| 001f-0020 | 2 | content-length value | `12595` |
| 0021-0021 | 1 | Header name index | `6: server` |
| 0022-0023 | 2 | server value byte length | `8` |
| 0024-002b | 8 | server value | `b'bserve/1'` |
| 002c-002c | 1 | Header name index | `7: connection` |
| 002d-002e | 2 | connection value byte length | `10` |
| 002f-0038 | 10 | connection value | `b'keep-alive'` |
| 0039-0039 | 1 | Header name index | `8: cache-control` |
| 003a-003b | 2 | cache-control value byte length | `8` |
| 003c-0043 | 8 | cache-control value | `b'no-store'` |
| 0044-0044 | 1 | Header name index | `10: x-request-id` |
| 0045-0046 | 2 | x-request-id value byte length | `1` |
| 0047-0047 | 1 | x-request-id value | `b'1'` |
| 0048-0048 | 1 | Header name index | `9: last-modified` |
| 0049-004a | 2 | last-modified value byte length | `29` |
| 004b-0067 | 29 | last-modified value | `b'Fri, 25 Sep 2026 07:19:24 GMT'` |
| 0068-0074 | 13 | Exact file body | `b'Hello, BC/1!\n'` |


The response echoes request ID 1. The final bytes are the complete `www/hello.txt` file. `connection=keep-alive` leaves the same connection available for the next request. All captured bytes are included in the hexadecimal listings above.
