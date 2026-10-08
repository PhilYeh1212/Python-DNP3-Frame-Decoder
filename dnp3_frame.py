"""
dnp3_frame.py — DNP3 CRC-16 and link-layer frame decoder in pure Python
=======================================================================

A small, dependency-free reference for the bottom layer of DNP3 (IEEE 1815):

  * CRC-16/DNP                      (verified against the standard check value)
  * Link frame builder              (05 64 header + 16-byte blocks + CRCs)
  * Link frame parser               (verifies every CRC, strips them out)
  * Control byte decoder            (DIR / PRM / FCB / FCV / function)

It deliberately stops at the link layer. Decoding the transport header,
application layer, IIN bits and objects is covered by the full
DNP3 Study Kit Pro: https://philyeh.gumroad.com/l/dnp3-study-kit

Usage:
    python dnp3_frame.py "05 64 05 C9 0A 00 01 00 FE DA"
    python dnp3_frame.py --selftest

Author: Phil Yeh — MIT License
"""

import struct
import sys

# ------------------------------------------------------------------------------
#  CRC-16/DNP: poly 0x3D65 (reflected 0xA6BC), init 0, output inverted,
#  transmitted low byte first. Check value: CRC(b"123456789") == 0xEA82
# ------------------------------------------------------------------------------

def _build_table():
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA6BC if (crc & 1) else (crc >> 1)
        table.append(crc)
    return table


_TABLE = _build_table()


def dnp3_crc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = (crc >> 8) ^ _TABLE[(crc ^ b) & 0xFF]
    return (~crc) & 0xFFFF


# ------------------------------------------------------------------------------
#  Link layer
# ------------------------------------------------------------------------------

START = b"\x05\x64"
BLOCK = 16

PRIMARY_FC = {0: "RESET_LINK_STATES", 2: "TEST_LINK_STATES", 3: "CONFIRMED_USER_DATA",
              4: "UNCONFIRMED_USER_DATA", 9: "REQUEST_LINK_STATUS"}
SECONDARY_FC = {0: "ACK", 1: "NACK", 11: "LINK_STATUS", 15: "NOT_SUPPORTED"}


def build_frame(ctrl: int, dest: int, src: int, user_data: bytes = b"") -> bytes:
    """Wrap user data in a link frame. LEN counts CTRL+DEST+SRC+data, not CRCs."""
    if len(user_data) > 250:
        raise ValueError("a link frame carries at most 250 bytes of user data")
    header = START + bytes([5 + len(user_data), ctrl]) + struct.pack("<HH", dest, src)
    frame = header + struct.pack("<H", dnp3_crc(header))
    for i in range(0, len(user_data), BLOCK):
        chunk = user_data[i:i + BLOCK]
        frame += chunk + struct.pack("<H", dnp3_crc(chunk))
    return frame


def frame_length(len_byte: int) -> int:
    """Total bytes on the wire for a given LEN field."""
    n = max(0, len_byte - 5)
    return 10 + n + 2 * ((n + BLOCK - 1) // BLOCK)


def describe_ctrl(c: int) -> str:
    primary = bool(c & 0x40)
    name = (PRIMARY_FC if primary else SECONDARY_FC).get(c & 0x0F, f"FC {c & 0x0F}")
    bits = (f"FCB={int(bool(c & 0x20))} FCV={int(bool(c & 0x10))}" if primary
            else f"DFC={int(bool(c & 0x10))}")
    return (f"DIR={int(bool(c & 0x80))} ({'master->outstation' if c & 0x80 else 'outstation->master'}) "
            f"PRM={int(primary)} {bits}  {name}")


def parse_frame(frame: bytes) -> dict:
    """Parse one frame, verify every CRC, return the fields and the clean user data."""
    if len(frame) < 10 or frame[:2] != START:
        raise ValueError("not a DNP3 frame: must start with 05 64")
    length, ctrl = frame[2], frame[3]
    dest, src = struct.unpack("<HH", frame[4:8])
    result = {
        "len": length, "ctrl": ctrl, "dest": dest, "src": src,
        "header_crc_ok": struct.unpack("<H", frame[8:10])[0] == dnp3_crc(frame[:8]),
        "blocks": [],
    }
    user, pos, remaining = b"", 10, length - 5
    while remaining > 0:
        take = min(BLOCK, remaining)
        chunk, crc = frame[pos:pos + take], frame[pos + take:pos + take + 2]
        if len(chunk) < take or len(crc) < 2:
            raise ValueError("frame is truncated")
        result["blocks"].append((chunk, struct.unpack("<H", crc)[0] == dnp3_crc(chunk)))
        user += chunk
        pos += take + 2
        remaining -= take
    result["user_data"] = user
    result["crc_ok"] = result["header_crc_ok"] and all(ok for _, ok in result["blocks"])
    return result


# ------------------------------------------------------------------------------
#  Command line
# ------------------------------------------------------------------------------

def _hex(b: bytes) -> str:
    return b.hex(" ").upper()


def explain(frame: bytes) -> str:
    p = parse_frame(frame)
    lines = [
        f"Frame ({len(frame)} bytes): {_hex(frame)}",
        "",
        f"  05 64          start bytes",
        f"  {p['len']:02X}             LEN = {p['len']}  ({p['len'] - 5} bytes of user data)",
        f"  {p['ctrl']:02X}             CTRL  {describe_ctrl(p['ctrl'])}",
        f"  {_hex(frame[4:6])}          DEST = {p['dest']}",
        f"  {_hex(frame[6:8])}          SRC  = {p['src']}",
        f"  {_hex(frame[8:10])}          header CRC  {'OK' if p['header_crc_ok'] else 'BAD'}",
    ]
    for i, (chunk, ok) in enumerate(p["blocks"], 1):
        lines.append(f"  block {i}: {_hex(chunk)}  CRC {'OK' if ok else 'BAD'}")
    lines.append("")
    if p["user_data"]:
        lines.append(f"User data, CRCs removed ({len(p['user_data'])} bytes): {_hex(p['user_data'])}")
        lines.append("  -> transport header, application layer and objects are not decoded here.")
        lines.append("     Full byte-by-byte decoding: https://philyeh.gumroad.com/l/dnp3-study-kit")
    else:
        lines.append("No user data: a link-layer-only frame.")
    lines.append(f"Result: {'all CRCs OK' if p['crc_ok'] else 'CRC ERROR - a receiver would discard this frame'}")
    return "\n".join(lines)


def selftest() -> bool:
    checks = [
        ("CRC check value", dnp3_crc(b"123456789") == 0xEA82),
        ("link status request", _hex(build_frame(0xC9, 10, 1)) == "05 64 05 C9 0A 00 01 00 FE DA"),
        ("read class 0", _hex(build_frame(0xC4, 10, 1, bytes.fromhex("C0C0013C0106")))
         == "05 64 0B C4 0A 00 01 00 AC D1 C0 C0 01 3C 01 06 FF 50"),
        ("frame length", frame_length(0x42) == 79),
    ]
    big = build_frame(0x44, 1, 10, bytes(range(40)))
    checks.append(("multi-block round trip", parse_frame(big)["user_data"] == bytes(range(40))))
    bad = bytearray(big)
    bad[20] ^= 0xFF
    checks.append(("corruption detected", not parse_frame(bytes(bad))["crc_ok"]))
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return all(ok for _, ok in checks)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    if sys.argv[1] == "--selftest":
        sys.exit(0 if selftest() else 1)
    print(explain(bytes.fromhex(" ".join(sys.argv[1:]).replace(" ", ""))))
