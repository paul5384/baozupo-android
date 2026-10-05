"""生成发码器图标：深色圆角底 + 金色钥匙轮廓（与主 App 的房子图标区分开）。"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "icon.png")
S = 512


def _png(path, w, h, px):
    """用 zlib+struct 手写最小 PNG，避免依赖 PIL。px 是 [r,g,b] 的 callable(x,y)->(r,g,b,a)"""
    import struct
    import zlib

    raw = bytearray()
    for y in range(h):
        raw.append(0)                      # filter type 0
        for x in range(w):
            r, g, b, a = px(x, y)
            raw += bytes((r, g, b, a))

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)   # 8bit RGBA
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def _rounded_alpha(x, y, size, radius):
    """圆角矩形的覆盖率（简单抗锯齿：算到边界 1px 内做线性过渡）。"""
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    dx = x - cx
    dy = y - cy
    d = (dx * dx + dy * dy) ** 0.5
    return max(0.0, min(1.0, radius - d + 0.5))


def _in_circle(x, y, cx, cy, r, soft=1.2):
    d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    return max(0.0, min(1.0, r - d + soft))


def _key(x, y):
    """钥匙：左侧圆环(带孔) + 右侧杆 + 两个向下的齿。"""
    a = 0.0
    # 环
    a = max(a, _in_circle(x, y, 168, 250, 80))
    # 孔（挖掉 -> 减覆盖率）
    a = a * (1.0 - _in_circle(x, y, 168, 250, 34))
    # 杆：从环的右缘一直伸到 410
    if 196 <= x <= 412 and 234 <= y <= 266:
        a = max(a, 1.0)
    # 上齿：从杆往上竖起（末端那格）
    if 336 <= x <= 360 and 190 <= y <= 236:
        a = max(a, 1.0)
    # 下齿：比上齿短一截，避免对称得像扳手
    if 376 <= x <= 400 and 264 <= y <= 308:
        a = max(a, 1.0)
    return min(1.0, a)


def pixel(x, y):
    bg = _rounded_alpha(x, y, S, 96)
    base = (31, 31, 34)
    if bg <= 0:
        return (0, 0, 0, 0)
    k = _key(x, y)
    gold = (232, 178, 66)
    col = tuple(int(base[i] + (gold[i] - base[i]) * k) for i in range(3))
    return (col[0], col[1], col[2], int(255 * bg))


n = _png(OUT, S, S, pixel)

# 启动闪屏沿用图标
pres = os.path.join(HERE, "assets", "presplash.png")
n2 = _png(pres, S, S, pixel)
io.open(os.path.join(HERE, "_icon_out.txt"), "w", encoding="utf-8").write(
    "icon.png %d bytes\npresplash.png %d bytes\n" % (n, n2))
print("icon", n, "presplash", n2)
