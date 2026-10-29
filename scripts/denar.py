#!/usr/bin/env python3
"""Extract the single regular file stored in a NAR archive to stdout.

Usage:
    curl -fL <file.nar> | python3 denar.py | tar -xz -C /tmp/avf

Only stdlib, streams (constant memory) so multi-GB archives are fine.
"""
import struct
import sys


def read_exact(stream, n):
    chunks = []
    remaining = n
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError(f"unexpected EOF ({n - remaining}/{n} bytes read)")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_str(stream):
    (length,) = struct.unpack("<Q", read_exact(stream, 8))
    if length > 1 << 30:
        raise ValueError(f"implausible NAR string length: {length}")
    data = read_exact(stream, length)
    padding = (-length) % 8
    if padding:
        read_exact(stream, padding)
    return data


def main():
    inp = sys.stdin.buffer
    out = sys.stdout.buffer
    if read_str(inp) != b"nix-archive-1":
        raise ValueError("not a NAR archive (bad magic)")
    if read_str(inp) != b"(":
        raise ValueError("malformed NAR (expected open paren)")
    if read_str(inp) != b"type":
        raise ValueError("malformed NAR (expected 'type')")
    if read_str(inp) != b"regular":
        raise ValueError("NAR node is not a single regular file")
    while True:
        token = read_str(inp)
        if token == b"executable":
            read_str(inp)  # empty value
        elif token == b"contents":
            # NAR ints are raw little-endian uint64 (no length prefix)
            (size,) = struct.unpack("<Q", read_exact(inp, 8))
            remaining = size
            while remaining:
                chunk = inp.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("unexpected EOF inside file contents")
                out.write(chunk)
                remaining -= len(chunk)
            out.flush()
            padding = (-size) % 8
            if padding:
                read_exact(inp, padding)
        elif token == b")":
            break
        else:
            raise ValueError(f"unexpected NAR token: {token!r}")


main()
