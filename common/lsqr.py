"""Tiny dependency-free QR Code generator (byte mode, error-correction level M, versions 1-10).

Enough for Wi-Fi join codes (up to 213 bytes).  Algorithm follows the QR Code Model 2 standard
(ISO/IEC 18004): Reed-Solomon over GF(256)/0x11D, 8 mask patterns scored with the four penalty rules.

    make_qr("hello")                   -> list of rows, each a list of bool (True = dark), no quiet zone
    wifi_payload(ssid, psk)            -> "WIFI:T:WPA;S:...;P:...;;"
    to_text(matrix)                    -> terminal rendering (half-block characters, quiet zone included)
    to_pbm(matrix, scale=8)            -> bytes of a PBM image (for tests / tools)
"""

# error-correction codewords per block / number of blocks, level M, index = version (1..10)
_ECC_PER_BLOCK = (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
_NUM_BLOCKS = (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
MAX_VERSION = 10
_FORMAT_BITS_M = 0           # level M indicator bits (00)


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        r -= (25 * n - 10) * n - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _NUM_BLOCKS[ver]


def _rs_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _rs_mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _rs_mul(root, 2)
    return res


def _rs_remainder(data, divisor):
    res = [0] * len(divisor)
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i, coef in enumerate(divisor):
            res[i] ^= _rs_mul(coef, factor)
    return res


def _add_ecc_and_interleave(data, ver):
    nblocks, eclen = _NUM_BLOCKS[ver], _ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    nshort = nblocks - raw % nblocks
    shortlen = raw // nblocks
    div = _rs_divisor(eclen)
    blocks, k = [], 0
    for i in range(nblocks):
        dat = list(data[k:k + shortlen - eclen + (0 if i < nshort else 1)])
        k += len(dat)
        ecc = _rs_remainder(dat, div)
        if i < nshort:
            dat.append(0)
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != shortlen - eclen or j >= nshort:
                out.append(blk[i])
    return out


def _align_positions(ver):
    if ver == 1:
        return []
    n = ver // 7 + 2
    size = ver * 4 + 17
    step = 26 if ver == 32 else (ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    return list(reversed([size - 7 - i * step for i in range(n - 1)] + [6]))


class _Grid:
    def __init__(self, ver):
        self.ver, self.size = ver, ver * 4 + 17
        self.m = [[False] * self.size for _ in range(self.size)]
        self.fn = [[False] * self.size for _ in range(self.size)]

    def setfn(self, x, y, dark):
        self.m[y][x] = dark
        self.fn[y][x] = True

    def draw_function_patterns(self):
        s = self.size
        for i in range(s):
            self.setfn(6, i, i % 2 == 0)
            self.setfn(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (s - 4, 3), (3, s - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < s and 0 <= y < s:
                        self.setfn(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver)
        n = len(pos)
        for i in range(n):
            for j in range(n):
                if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.setfn(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                b = (bits >> i) & 1 == 1
                a, c = self.size - 11 + i % 3, i // 3
                self.setfn(a, c, b)
                self.setfn(c, a, b)

    def draw_format(self, mask):
        data = _FORMAT_BITS_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        g = lambda i: (bits >> i) & 1 == 1   # noqa: E731
        s = self.size
        for i in range(6):
            self.setfn(8, i, g(i))
        self.setfn(8, 7, g(6))
        self.setfn(8, 8, g(7))
        self.setfn(7, 8, g(8))
        for i in range(9, 15):
            self.setfn(14 - i, 8, g(i))
        for i in range(8):
            self.setfn(s - 1 - i, 8, g(i))
        for i in range(8, 15):
            self.setfn(8, s - 15 + i, g(i))
        self.setfn(8, s - 8, True)

    def draw_codewords(self, data):
        s, i = self.size, 0
        for right in range(s - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = s - 1 - vert if upward else vert
                    if not self.fn[y][x] and i < len(data) * 8:
                        self.m[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1

    def apply_mask(self, mask):
        for y in range(self.size):
            for x in range(self.size):
                inv = (
                    (x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0,
                    (x // 3 + y // 2) % 2 == 0, x * y % 2 + x * y % 3 == 0,
                    (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
                if inv and not self.fn[y][x]:
                    self.m[y][x] = not self.m[y][x]

    def penalty(self):
        s, m, score = self.size, self.m, 0
        lines = [row for row in m] + [[m[y][x] for y in range(s)] for x in range(s)]
        pat_a = [True, False, True, True, True, False, True, False, False, False, False]
        pat_b = list(reversed(pat_a))
        for line in lines:
            run = 1
            for i in range(1, s):
                if line[i] == line[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + run - 5
                    run = 1
            if run >= 5:
                score += 3 + run - 5
            for i in range(s - 10):
                w = line[i:i + 11]
                if w == pat_a or w == pat_b:
                    score += 40
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(r) for r in m)
        total = s * s
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score


def make_qr(text):
    data = text.encode("utf-8")
    for ver in range(1, MAX_VERSION + 1):
        cc = 8 if ver <= 9 else 16
        if 4 + cc + len(data) * 8 <= _data_codewords(ver) * 8:
            break
    else:
        raise ValueError(f"text too long for a version-{MAX_VERSION} QR code ({len(data)} bytes)")
    bits = []

    def put(val, n):
        bits.extend((val >> i) & 1 for i in reversed(range(n)))
    put(0b0100, 4)
    put(len(data), cc)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(cw) < _data_codewords(ver):
        cw.append(pad)
        pad ^= 0xEC ^ 0x11
    g = _Grid(ver)
    g.draw_function_patterns()
    g.draw_codewords(_add_ecc_and_interleave(cw, ver))
    best, best_pen = 0, None
    for mask in range(8):
        g.apply_mask(mask)
        g.draw_format(mask)
        pen = g.penalty()
        if best_pen is None or pen < best_pen:
            best, best_pen = mask, pen
        g.apply_mask(mask)           # undo
    g.apply_mask(best)
    g.draw_format(best)
    return g.m


def _esc(s):
    for ch in '\\;,:"':
        s = s.replace(ch, "\\" + ch)
    return s


def wifi_payload(ssid, psk, hidden=False):
    """Standard Wi-Fi join string understood by Android and iOS cameras."""
    auth = "WPA" if psk else "nopass"
    return f"WIFI:T:{auth};S:{_esc(ssid)};" + (f"P:{_esc(psk)};" if psk else "") + ("H:true;" if hidden else "") + ";"


def to_text(matrix, quiet=4, ansi=True):
    """Terminal rendering: two module rows per text line using half blocks.
    ansi=True forces black-on-white so it scans on dark and light terminals alike."""
    n = len(matrix)
    size = n + 2 * quiet

    def dark(x, y):
        return 0 <= x - quiet < n and 0 <= y - quiet < n and matrix[y - quiet][x - quiet]
    out = []
    for y in range(0, size, 2):
        line = ""
        for x in range(size):
            top, bot = dark(x, y), dark(x, y + 1)
            line += "█" if top and bot else "▀" if top else "▄" if bot else " "
        out.append(f"\x1b[30;47m{line}\x1b[0m" if ansi else line)
    return "\n".join(out)


def to_pbm(matrix, scale=8, quiet=4):
    n = len(matrix)
    size = (n + 2 * quiet) * scale
    rows = []
    for y in range(size):
        my = y // scale - quiet
        row = []
        for x in range(size):
            mx = x // scale - quiet
            row.append("1" if 0 <= mx < n and 0 <= my < n and matrix[my][mx] else "0")
        rows.append("".join(row))
    return f"P1\n{size} {size}\n".encode() + "\n".join(rows).encode() + b"\n"


if __name__ == "__main__":      # python3 lsqr.py "text"   |   python3 lsqr.py --wifi SSID [PASSWORD]
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--wifi":
        txt = wifi_payload(args[1], args[2] if len(args) > 2 else "")
    else:
        txt = " ".join(args) or "https://qgis.org"
    print(to_text(make_qr(txt), ansi=sys.stdout.isatty()))
