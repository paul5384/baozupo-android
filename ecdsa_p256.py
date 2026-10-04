"""ECDSA P-256 (secp256r1) 纯 Python 实现。

不依赖任何第三方库（int 大数运算 + pow 足够）。两个用途：
- 签发端（授权码生成器，私钥 d 持有）
- 验签端（主 App，只持有公钥 Q）

坐标用 Jacobian 投影，避免点乘过程中反复求模逆；只有在需要取 x 时才转回仿射。
"""
import hashlib
import hmac

# 曲线参数 y^2 = x^3 - 3x + b (mod p)
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _dbl(pt):
    """Jacobian 倍点，针对 a = -3 的优化公式。pt=(X,Y,Z)，None 表示无穷远点。"""
    x1, y1, z1 = pt
    if z1 == 0 or y1 == 0:
        return (0, 0, 0)
    delta = z1 * z1 % P
    gamma = y1 * y1 % P
    beta = x1 * gamma % P
    alpha = 3 * (x1 - delta) * (x1 + delta) % P
    x3 = (alpha * alpha - 8 * beta) % P
    z3 = ((y1 + z1) * (y1 + z1) - gamma - delta) % P
    y3 = (alpha * (4 * beta - x3) - 8 * gamma * gamma) % P
    return (x3, y3, z3)


def _add(p1, p2):
    """Jacobian 加点，add-2007-bl 公式。"""
    if p1[2] == 0:
        return p2
    if p2[2] == 0:
        return p1
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    z1z1 = z1 * z1 % P
    z2z2 = z2 * z2 % P
    u1 = x1 * z2z2 % P
    u2 = x2 * z1z1 % P
    s1 = y1 * z2 * z2z2 % P
    s2 = y2 * z1 * z1z1 % P
    h = (u2 - u1) % P
    r = (s2 - s1) % P
    if h == 0:
        if r == 0:
            return _dbl(p1)
        return (0, 0, 0)
    i = 4 * h * h % P
    j = h * i % P
    rr = 2 * r % P
    v = u1 * i % P
    x3 = (rr * rr - j - 2 * v) % P
    y3 = (rr * (v - x3) - 2 * s1 * j) % P
    z3 = ((z1 + z2) * (z1 + z2) - z1z1 - z2z2) * h % P
    return (x3, y3, z3)


def to_affine(pt):
    """Jacobian -> 仿射 (x, y)，无穷远点返回 None。"""
    x, y, z = pt
    if z == 0:
        return None
    zi = pow(z, P - 2, P)
    zi2 = zi * zi % P
    return (x * zi2 % P, y * zi2 % P * zi % P)


def _mul(k, pt):
    """标量乘，double-and-add。"""
    if k % N == 0 or pt[2] == 0:
        return (0, 0, 0)
    r = (0, 0, 0)
    q = pt
    while k:
        if k & 1:
            r = _add(r, q)
        q = _dbl(q)
        k >>= 1
    return r


G = (GX, GY, 1)


def is_on_curve(x, y):
    return (y * y - (x * x * x + A * x + B)) % P == 0


def _bits2int(bs):
    v = int.from_bytes(bs, "big")
    excess = len(bs) * 8 - N.bit_length()
    if excess > 0:
        v >>= excess
    return v


def _rfc6979_k(d, msg_hash):
    """RFC 6979 确定性 k。不依赖随机源，同一 (私钥, 消息) 永远得到同一签名。"""
    hlen = 32
    x = d.to_bytes(32, "big")
    h1 = _bits2int(msg_hash).to_bytes(32, "big")
    v = b"\x01" * hlen
    k = b"\x00" * hlen
    k = hmac.new(k, v + b"\x00" + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        t = b""
        while len(t) < hlen:
            v = hmac.new(k, v, hashlib.sha256).digest()
            t += v
        cand = _bits2int(t)
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def pubkey(d):
    """私钥 -> 公钥仿射坐标 (x, y)。"""
    aff = to_affine(_mul(d, G))
    if aff is None:
        raise ValueError("私钥非法")
    return aff


def sign(d, message):
    """签名任意 str/bytes，返回 (r, s)。"""
    if isinstance(message, str):
        message = message.encode("utf-8")
    h = hashlib.sha256(message).digest()
    z = _bits2int(h)
    k = _rfc6979_k(d, h)
    pt = _mul(k, G)
    aff = to_affine(pt)
    if aff is None:
        raise ValueError("签名失败")
    r = aff[0] % N
    if r == 0:
        raise ValueError("签名失败 r=0")
    s = (pow(k, N - 2, N) * (z + r * d)) % N
    if s == 0:
        raise ValueError("签名失败 s=0")
    # 强制 low-s，消除 s 与 n-s 的符号二义性（比特币惯例，防签名可延展）
    if s > N // 2:
        s = N - s
    return (r, s)


def verify(pub, message, sig):
    """公钥验签。pub=(x,y)，sig=(r,s)。失败一律返回 False，不抛异常。"""
    try:
        if isinstance(message, str):
            message = message.encode("utf-8")
        qx, qy = pub
        r, s = sig
        if not (1 <= r < N and 1 <= s < N):
            return False
        # 强制 low-s：ECDSA 里 (r, n-s) 数学上是等价签名，不拒就等于允许签名被随意改写
        if s > N // 2:
            return False
        if not is_on_curve(qx, qy):
            return False
        h = hashlib.sha256(message).digest()
        z = _bits2int(h)
        w = pow(s, N - 2, N)
        u1 = z * w % N
        u2 = r * w % N
        pt = _add(_mul(u1, G), _mul(u2, (qx, qy, 1)))
        aff = to_affine(pt)
        if aff is None:
            return False
        return aff[0] % N == r
    except Exception:
        return False
