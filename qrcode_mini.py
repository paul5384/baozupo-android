# -*- coding: utf-8 -*-
"""
qrcode_mini.py —— 零依赖二维码生成器（只用标准库，可直接打进 APK）

为什么不用现成的 qrcode / pillow：
    打包安卓 APK 时每多一个三方依赖就多一处失败点（pillow 要编 C，
    p4a 上经常卡在 wheel / ndk）。而这个 App 只需要「把一段账单文本
    变成一张二维码 PNG」，用标准库 300 行就能做完，还能少给 APK 塞几 MB。

实现范围：
    · 字节模式（UTF-8），中文可直接编码
    · 版本 1~10，纠错等级 L / M / Q / H 自动选
    · 8 种掩码按 ISO 罚分规则自动挑最优
    · 输出 PNG（自己用 zlib 拼 IHDR/IDAT/IEND）

对外接口：
    make_matrix(text)          -> (matrix, version)   matrix[y][x] 为 True 表示深色
    qr_png_bytes(text, ...)    -> bytes               直接给 Kivy Image / 写文件用
    write_png(text, path, ...) -> True/False

仅本地校验用的对照：与 PyPI 的 qrcode 库生成的矩阵、以及 OpenCV 的
解码器都做过交叉验证（见 _test_v216.py），运行时不依赖它们。
"""

import struct
import zlib

# ---------------------------------------------------------------- 常量表
# 每个版本的总码字数（数据 + 纠错），索引 = 版本号
_TOTAL_CODEWORDS = [0, 26, 44, 70, 100, 134, 172, 196, 242, 292, 346]

# 每个「纠错块」里纠错码字的个数：[版本1..版本10]
_ECC_PER_BLOCK = {
    "L": [7, 10, 15, 20, 26, 18, 20, 24, 30, 18],
    "M": [10, 16, 26, 18, 24, 16, 18, 22, 22, 26],
    "Q": [13, 22, 18, 26, 18, 24, 18, 22, 20, 24],
    "H": [17, 28, 22, 16, 22, 28, 26, 26, 24, 28],
}

# 该版本被切成几个纠错块
_NUM_BLOCKS = {
    "L": [1, 1, 1, 1, 1, 2, 2, 2, 2, 4],
    "M": [1, 1, 1, 2, 2, 4, 4, 4, 5, 5],
    "Q": [1, 1, 2, 2, 4, 4, 6, 6, 8, 8],
    "H": [1, 1, 2, 4, 4, 4, 5, 6, 8, 8],
}

_ECL_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

# 校正图形（Alignment Pattern）中心坐标
_ALIGN_CENTERS = {
    1: (), 2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30),
    6: (6, 34), 7: (6, 22, 38), 8: (6, 24, 42), 9: (6, 26, 46),
    10: (6, 28, 50),
}

_MAX_VERSION = 10

# ---------------------------------------------------------------- GF(256)
_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D          # x^8 + x^4 + x^3 + x^2 + 1
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gen_poly(n):
    """RS 生成多项式 ∏(x - α^i)，i=0..n-1。返回低次在前的系数表，长度 n+1，末位为 1"""
    g = [1]
    for i in range(n):
        a = _EXP[i]
        ng = [0] * (len(g) + 1)
        for k in range(len(g)):
            ng[k + 1] ^= g[k]              # 乘 x
            ng[k] ^= _mul(g[k], a)         # 乘 α^i
        g = ng
    return g


def _rs_remainder(data, ec_n):
    """系统码：算出 ec_n 个纠错码字（data 为高次在前的码字列表）"""
    gen = _gen_poly(ec_n)                  # gen[i] 是 x^i 的系数，gen[ec_n] == 1
    res = [0] * ec_n
    for d in data:
        factor = d ^ res[0]
        res = res[1:] + [0]
        if factor:
            for i in range(ec_n):
                res[i] ^= _mul(gen[ec_n - 1 - i], factor)
    return res


# ---------------------------------------------------------------- 容量 / 选版
def _data_codewords(version, ecl):
    total = _TOTAL_CODEWORDS[version]
    ec_total = _ECC_PER_BLOCK[ecl][version - 1] * _NUM_BLOCKS[ecl][version - 1]
    return total - ec_total


def _payload_bits(nbytes, version):
    """编码 nbytes 个字节需要的总比特数（含模式指示符和字符计数）"""
    return 4 + (8 if version < 10 else 16) + nbytes * 8


def _fit_version(nbytes, ecl):
    for v in range(1, _MAX_VERSION + 1):
        if _payload_bits(nbytes, v) <= _data_codewords(v, ecl) * 8:
            return v
    return None


# ---------------------------------------------------------------- 比特流
def _to_bits(data_bytes, version, ecl):
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(0b0100, 4)                                   # 字节模式
    put(len(data_bytes), 8 if version < 10 else 16)  # 字符计数
    for b in data_bytes:
        put(b, 8)

    cap_bits = _data_codewords(version, ecl) * 8
    # 结束符（最多 4 个 0，放不下就截断）
    for _ in range(min(4, cap_bits - len(bits))):
        bits.append(0)
    while len(bits) % 8:
        bits.append(0)
    # 填充码字 0xEC / 0x11 交替
    pads = (0xEC, 0x11)
    i = 0
    while len(bits) < cap_bits:
        put(pads[i % 2], 8)
        i += 1
    return bits


def _bits_to_bytes(bits):
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for j in range(8):
            v = (v << 1) | bits[i + j]
        out.append(v)
    return list(out)


def _interleave(data_cw, version, ecl):
    """按块切分 + 纠错 + 交织，返回最终码字序列"""
    ecw = _ECC_PER_BLOCK[ecl][version - 1]
    nb = _NUM_BLOCKS[ecl][version - 1]
    data_total = _data_codewords(version, ecl)
    short_len = data_total // nb
    num_short = nb - data_total % nb           # 前 num_short 块短一个码字

    blocks, pos = [], 0
    for i in range(nb):
        ln = short_len if i < num_short else short_len + 1
        blocks.append(data_cw[pos:pos + ln])
        pos += ln
    ec_blocks = [_rs_remainder(b, ecw) for b in blocks]

    out = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ecw):
        for b in ec_blocks:
            out.append(b[i])
    return out


# ---------------------------------------------------------------- 矩阵
def _format_bits(ecl, mask):
    data = (_ECL_BITS[ecl] << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(version):
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return (version << 12) | rem


def _new_module_set(size):
    return ([[False] * size for _ in range(size)],
            [[False] * size for _ in range(size)])


def _finder(m, f, size, cx, cy):
    """定位图形 7x7 + 分隔符 1 圈（分隔符也算功能区，数据不能占用）"""
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            x, y = cx + dx, cy + dy
            if 0 <= x < size and 0 <= y < size:
                f[y][x] = True
                # 7x7 定位图形：外环(d=3)深、d=2 浅、中心 3x3（d=0/1）深
                m[y][x] = max(abs(dx), abs(dy)) in (0, 1, 3)


def _alignment(m, f, size, centers):
    cs = list(centers)
    if not cs:
        return
    lo, hi = cs[0], cs[-1]
    for cy in cs:
        for cx in cs:
            if (cx == lo and cy == lo) or (cx == lo and cy == hi) \
                    or (cx == hi and cy == lo):
                continue                      # 这三个位置和定位图形重叠
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    x, y = cx + dx, cy + dy
                    f[y][x] = True
                    m[y][x] = max(abs(dx), abs(dy)) != 1


def _draw_function(m, f, size, version):
    _finder(m, f, size, 3, 3)
    _finder(m, f, size, size - 4, 3)
    _finder(m, f, size, 3, size - 4)

    # 定时图形
    for i in range(size):
        for (x, y) in ((i, 6), (6, i)):
            if not f[y][x]:
                f[y][x] = True
                m[y][x] = (i % 2 == 0)

    _alignment(m, f, size, _ALIGN_CENTERS[version])

    # 预留「格式信息」区（先画 0，后面再写真实值）
    for i in range(9):
        if i != 6:
            f[8][i] = True
            f[i][8] = True
    for i in range(8):
        f[8][size - 1 - i] = True
        f[size - 1 - i][8] = True

    # 版本信息区（v7 及以上）
    if version >= 7:
        vb = _version_bits(version)
        for i in range(18):
            bit = ((vb >> i) & 1) == 1
            a, b = size - 11 + i % 3, i // 3
            f[b][a] = f[a][b] = True
            m[b][a] = m[a][b] = bit

    m[size - 8][8] = True        # 固定深色模块
    f[size - 8][8] = True


def _draw_format(m, f, size, ecl, mask):
    bits = _format_bits(ecl, mask)

    def bit(i):
        return ((bits >> i) & 1) == 1

    for i in range(6):
        m[i][8] = bit(i)                     # 注意：Nayuki 里是 (x=8, y=i)
    m[7][8] = bit(6)
    m[8][8] = bit(7)
    m[8][7] = bit(8)
    for i in range(9, 15):
        m[8][14 - i] = bit(i)

    for i in range(8):
        m[8][size - 1 - i] = bit(i)
    for i in range(8, 15):
        m[size - 15 + i][8] = bit(i)
    m[size - 8][8] = True


def _draw_codewords(m, f, size, codewords):
    i = 0
    total_bits = len(codewords) * 8
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = (size - 1 - vert) if upward else vert
                if not f[y][x] and i < total_bits:
                    m[y][x] = ((codewords[i >> 3] >> (7 - (i & 7))) & 1) == 1
                    i += 1
        right -= 2


def _mask_bit(mask, x, y):
    if mask == 0:
        return (x + y) % 2 == 0
    if mask == 1:
        return y % 2 == 0
    if mask == 2:
        return x % 3 == 0
    if mask == 3:
        return (x + y) % 3 == 0
    if mask == 4:
        return (x // 3 + y // 2) % 2 == 0
    if mask == 5:
        return x * y % 2 + x * y % 3 == 0
    if mask == 6:
        return (x * y % 2 + x * y % 3) % 2 == 0
    return ((x + y) % 2 + x * y % 3) % 2 == 0


def _apply_mask(m, f, size, mask):
    for y in range(size):
        for x in range(size):
            if not f[y][x] and _mask_bit(mask, x, y):
                m[y][x] = not m[y][x]


def _lines(m, size):
    """把矩阵按行、按列拆成序列，给罚分规则用"""
    for y in range(size):
        yield [m[y][x] for x in range(size)]
    for x in range(size):
        yield [m[y][x] for y in range(size)]


_FINDER_LIKE = [True, False, True, True, True, False, True,
                False, False, False, False]
_FINDER_LIKE_REV = _FINDER_LIKE[::-1]


def _penalty(m, size):
    p = 0
    for line in _lines(m, size):
        # 规则 1：同色连续 5 个以上
        run, cur = 0, None
        for v in line + [None]:
            if v == cur:
                run += 1
                if run == 5:
                    p += 3
                elif run > 5:
                    p += 1
            else:
                cur, run = v, 1
        # 规则 3：类定位图形 1:1:3:1:1（两边各留 4 个浅色的那两种写法）
        n = len(line)
        for i in range(n - 10):
            seg = line[i:i + 11]
            if seg == _FINDER_LIKE or seg == _FINDER_LIKE_REV:
                p += 40

    # 规则 2：2x2 同色块
    for y in range(size - 1):
        for x in range(size - 1):
            c = m[y][x]
            if c == m[y][x + 1] and c == m[y + 1][x] and c == m[y + 1][x + 1]:
                p += 3

    # 规则 4：深浅比例偏离 50%
    dark = sum(1 for row in m for v in row if v)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    p += max(0, k) * 10
    return p


def make_matrix(text, ecl=None):
    """生成二维码矩阵，返回 (matrix, version, mask)；放不下返回 (None, None, None)"""
    if isinstance(text, str):
        data = list(text.encode("utf-8"))
    else:
        data = list(text)

    levels = [ecl] if ecl else ["M", "Q", "H", "L"]
    version = None
    for lv in levels:
        v = _fit_version(len(data), lv)
        if v:
            version, ecl = v, lv
            break
    if version is None:
        return None, None, None

    size = version * 4 + 17
    m, f = _new_module_set(size)
    _draw_function(m, f, size, version)

    bits = _to_bits(data, version, ecl)
    codewords = _interleave(_bits_to_bytes(bits), version, ecl)
    _draw_codewords(m, f, size, codewords)

    best, best_penalty, best_mask = None, None, 0
    for mask in range(8):
        trial = [row[:] for row in m]
        _apply_mask(trial, f, size, mask)
        # 格式信息本身也算在罚分里（不同掩码格式位不同）
        _draw_format(trial, f, size, ecl, mask)
        p = _penalty(trial, size)
        if best_penalty is None or p < best_penalty:
            best, best_penalty, best_mask = trial, p, mask
    return best, version, best_mask


# ---------------------------------------------------------------- PNG 输出
def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def matrix_to_png_bytes(matrix, scale=8, border=4,
                        dark=(0, 0, 0), light=(255, 255, 255)):
    """把矩阵渲染成 PNG 字节流（每模块 scale 个像素，四周留 border 个模块白边）"""
    n = len(matrix)
    width = (n + 2 * border) * scale
    raw = bytearray()
    dark_b, light_b = bytes(dark), bytes(light)
    for my in range(-border, n + border):
        line = bytearray()
        for mx in range(-border, n + border):
            inside = 0 <= my < n and 0 <= mx < n
            line += (dark_b if (inside and matrix[my][mx]) else light_b) * scale
        for _ in range(scale):
            raw.append(0)            # PNG 过滤器类型 0（None）
            raw += line
    ihdr = struct.pack(">IIBBBBB", width, width, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def qr_png_bytes(text, scale=8, border=4, ecl=None):
    m, _v, _mk = make_matrix(text, ecl)
    if m is None:
        return None
    return matrix_to_png_bytes(m, scale=scale, border=border)


def write_png(text, path, scale=8, border=4, ecl=None):
    """把文本编码成二维码并写成 PNG 文件，成功 True"""
    try:
        data = qr_png_bytes(text, scale=scale, border=border, ecl=ecl)
        if not data:
            return False
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # 自检：控制台打印一个 40 字符宽的 ASCII 预览
    m, v, mk = make_matrix("包租婆账单|房间101|2026-10|水费35元|电费78元|合计113元")
    print("version", v, "mask", mk)
    if m:
        for row in m:
            print("".join("##" if c else "  " for c in row))
