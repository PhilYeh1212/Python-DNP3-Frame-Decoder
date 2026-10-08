# Python DNP3 Frame Decoder

A small, dependency-free Python reference for the **link layer of DNP3 (IEEE 1815)**:
the CRC-16/DNP checksum, the `05 64` frame header, and the 16-byte data blocks
that every DNP3 frame is built from.

Useful when you need to:

- compute or verify a **DNP3 CRC** in Python
- build a valid link frame for a test harness
- check a captured frame by hand ("is this CRC right?")
- strip the CRCs out of a frame before decoding the layers above

One file, standard library only, Python 3.8+.

## Quick start

```bash
python dnp3_frame.py "05 64 0B C4 0A 00 01 00 AC D1 C0 C0 01 3C 01 06 FF 50"
```

```
Frame (18 bytes): 05 64 0B C4 0A 00 01 00 AC D1 C0 C0 01 3C 01 06 FF 50

  05 64          start bytes
  0B             LEN = 11  (6 bytes of user data)
  C4             CTRL  DIR=1 (master->outstation) PRM=1 FCB=0 FCV=0  UNCONFIRMED_USER_DATA
  0A 00          DEST = 10
  01 00          SRC  = 1
  AC D1          header CRC  OK
  block 1: C0 C0 01 3C 01 06  CRC OK

User data, CRCs removed (6 bytes): C0 C0 01 3C 01 06
Result: all CRCs OK
```

Run the built-in checks:

```bash
python dnp3_frame.py --selftest
```

## Use it as a library

```python
from dnp3_frame import dnp3_crc, build_frame, parse_frame

hex(dnp3_crc(b"123456789"))          # '0xea82' - the standard check value

frame = build_frame(ctrl=0xC9, dest=10, src=1)   # REQUEST_LINK_STATUS
frame.hex(" ").upper()               # '05 64 05 C9 0A 00 01 00 FE DA'

p = parse_frame(frame)
p["crc_ok"], p["dest"], p["src"]     # (True, 10, 1)
```

## The DNP3 link frame in 30 seconds

```
05 64 | LEN | CTRL | DEST (2) | SRC (2) | CRC (2)      10-byte header
[up to 16 bytes of user data][CRC] [up to 16 bytes][CRC] ...
```

- **LEN** counts CTRL + DEST + SRC + user data. The CRC bytes are **not** counted.
- Every 16 bytes of user data is followed by its own 2-byte CRC, so CRCs often land
  in the middle of fields above the link layer.
- All multi-byte fields are little-endian, CRC included (`0xDAFE` is sent as `FE DA`).
- **CRC-16/DNP:** polynomial `0x3D65` (reflected `0xA6BC`), init `0`, output inverted.

## Want the layers above this?

This repo stops at the link layer on purpose. **[DNP3 Study Kit Pro](https://philyeh.gumroad.com/l/dnp3-study-kit)**
covers the rest:

- an interactive Python master GUI that decodes **every byte** of every frame —
  transport, application control, function codes, IIN, object headers, qualifiers,
  point flags and values — color-coded by layer, with hover explanations
- a mock outstation (a small solar-plant RTU) with an event buffer and a
  controllable breaker, so you can walk through integrity polls, CROB controls,
  event polls and CONFIRMs without any hardware
- a printable DNP3 cheat sheet

## License

MIT — see `LICENSE`. Made by Phil Yeh.
