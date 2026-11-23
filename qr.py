"""A QR code for the pairing link (Einstellungen -> Zugang -> Geraet hinzufuegen): drawn by Kontor itself, standard library only.

ISO/IEC 18004 in the smallest form that link needs: byte mode, error correction level M (15 % of the code may be damaged),
versions 1-10 (up to 213 bytes), the mask with the lowest penalty. The result is a square of modules -- the page draws it as
one SVG path. Nothing is sent anywhere; the code holds only the text given.
"""
from __future__ import annotations

from typing import List, Tuple

# per version (1-10), level M: (EC codewords per block, [(blocks, data codewords per block), ...])
_BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
           6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
           10: (26, [(4, 43), (1, 44)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_LEVEL_M = 0                                  # the two bits of level M in the format information
QUIET = 4                                     # light modules around the code


# -- Reed-Solomon over GF(256), x^8 + x^4 + x^3 + x^2 + 1 -------------------------------------------------------------
def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> List[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def rs_remainder(data: List[int], degree: int) -> List[int]:
    """The error correction codewords of a block."""
    divisor = _rs_divisor(degree)
    result = [0] * degree
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


# -- the code ----------------------------------------------------------------------------------------------------------
def _data_codewords(text: bytes, version: int) -> List[int]:
    ec, groups = _BLOCKS[version]
    capacity = sum(n * k for n, k in groups)
    bits: List[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in range(length - 1, -1, -1))
    put(0b0100, 4)                                            # byte mode
    put(len(text), 8 if version < 10 else 16)
    for b in text:
        put(b, 8)
    put(0, min(4, capacity * 8 - len(bits)))                  # terminator
    put(0, -len(bits) % 8)
    out = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(out) < capacity:
        out.append(pad)
        pad ^= 0xEC ^ 0x11
    return out


def _interleave(data: List[int], version: int) -> List[int]:
    ec, groups = _BLOCKS[version]
    blocks, i = [], 0
    for n, k in groups:
        for _ in range(n):
            blocks.append(data[i:i + k])
            i += k
    eccs = [rs_remainder(b, ec) for b in blocks]
    out = []
    for j in range(max(len(b) for b in blocks)):
        out += [b[j] for b in blocks if j < len(b)]
    for j in range(ec):
        out += [e[j] for e in eccs]
    return out


def format_bits(mask: int) -> int:
    """The 15 bits of format information (level M, the mask), BCH-coded and masked."""
    data = _LEVEL_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def version_bits(version: int) -> int:
    """The 18 bits of version information (versions 7 and up)."""
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return version << 12 | rem


class _Grid:
    def __init__(self, version: int):
        self.version, self.size = version, version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x], self.fixed[y][x] = dark, True

    def functions(self) -> None:
        n = self.size
        for i in range(n):                                    # timing patterns
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):       # finder patterns with their separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _ALIGN[self.version]
        for i, ax in enumerate(pos):                          # alignment patterns (not over the finders)
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, len(pos) - 1), (len(pos) - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)                                        # reserved now, written with the mask chosen
        if self.version >= 7:
            bits = version_bits(self.version)
            for i in range(18):
                a, b, on = n - 11 + i % 3, i // 3, bool((bits >> i) & 1)
                self.set(a, b, on)
                self.set(b, a, on)

    def format(self, mask: int) -> None:
        n, bits = self.size, format_bits(mask)
        bit = lambda i: bool((bits >> i) & 1)
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)                              # the dark module

    def place(self, codewords: List[int]) -> None:
        n, i, total = self.size, 0, len(codewords) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = bool((codewords[i >> 3] >> (7 - (i & 7))) & 1)
                        i += 1
            right -= 2

    def masked(self, mask: int) -> List[List[bool]]:
        test = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
                lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
                lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
        return [[d ^ (not f and test(x, y)) for x, (d, f) in enumerate(zip(row, frow))] for y, (row, frow) in enumerate(zip(self.dark, self.fixed))]


def penalty(m: List[List[bool]]) -> int:
    """The four penalty rules: runs of five and more, 2x2 blocks, finder-like patterns, balance of dark and light."""
    n, score = len(m), 0
    lines = m + [list(col) for col in zip(*m)]
    finder = ([True, False, True, True, True, False, True, False, False, False, False],
              [False, False, False, False, True, False, True, True, True, False, True])
    for line in lines:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
        for i in range(n - 10):
            if line[i:i + 11] in finder:
                score += 40
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, m))
    score += abs(dark * 20 - n * n * 10) // (n * n) * 10
    return score


def matrix(text: str) -> List[List[bool]]:
    """The QR code of text (UTF-8): rows of modules, True = dark, without the quiet zone."""
    raw = text.encode("utf-8")
    version = next((v for v in range(1, 11) if len(raw) <= sum(n * k for n, k in _BLOCKS[v][1]) - (2 if v < 10 else 3)), None)
    if version is None:
        raise ValueError("text too long for a QR code of version 10")
    g = _Grid(version)
    g.functions()
    g.place(_interleave(_data_codewords(raw, version), version))
    best: Tuple[int, int] = (-1, 0)
    for mask in range(8):
        g.format(mask)
        p = penalty(g.masked(mask))
        if best[0] < 0 or p < best[0]:
            best = (p, mask)
    g.format(best[1])
    return g.masked(best[1])


def svg_path(text: str) -> Tuple[int, str]:
    """(side length in modules with the quiet zone, the SVG path of the dark modules): one rectangle per run in a row."""
    m = matrix(text)
    parts = []
    for y, row in enumerate(m):
        x = 0
        while x < len(row):
            if row[x]:
                start = x
                while x < len(row) and row[x]:
                    x += 1
                parts.append("M%d %dh%dv1h-%dz" % (start + QUIET, y + QUIET, x - start, x - start))
            else:
                x += 1
    return len(m) + 2 * QUIET, "".join(parts)
