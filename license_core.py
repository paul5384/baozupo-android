"""授权码编解码 + 申请文字互通。

主 App 与发码器共用本文件，任何一边改了另一边必须同步。
激活码 = BZP- + 8 组 x 13 字符（13*8=104），字符集去掉易混的 0/O/1/I/L。
"""
import hashlib

CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_IDX = {c: i for i, c in enumerate(CHARS)}
_BASE = len(CHARS)
GROUP = 13
GROUPS = 8
CODE_LEN = GROUP * GROUPS          # 104
PREFIX = "BZP"
# 签名消息域分隔符，绑死用途防止跨协议重放
TAG = "BZP2|"

# 公钥（secp256r1）。私钥只存在于发码器工程，绝不出现在本 App 内。
PUB_X = 0xF10BCF850FEB93E088B3971850AE0CDBF0BC33D9C7B11861EA4B96C12DA12F41
PUB_Y = 0x9A24ADA30AAAC3A3F3E9BC6E3160D5B45A9C876D01B04FCB3BD904A8A26F90BE
PUB = (PUB_X, PUB_Y)

# 申请文字的固定头尾，客户整段复制发给作者，发码器整段粘贴回来解析
REQ_HEAD = "【包租婆授权申请】"
REQ_TAIL = "（以上为设备信息，回复激活码即可解锁付费版）"


def _b2c(data, width=None):
    """字节 -> 字符集串（31 进制大端）。width 指定时左补 CHARS[0]（值为 0）。"""
    v = int.from_bytes(data, "big")
    n = 0
    t = v
    while t:
        t //= _BASE
        n += 1
    if n == 0:
        n = 1
    out = []
    for _ in range(n):
        v, r = divmod(v, _BASE)
        out.append(CHARS[r])
    s = "".join(reversed(out))
    if width is not None:
        if len(s) > width:
            raise ValueError("数值超出 %d 字符容量" % width)
        s = s.rjust(width, CHARS[0])
    return s


def _c2b(s):
    """字符集串 -> 整数（不做字节宽度推断，宽度由调用方按固定格式决定）。"""
    v = 0
    for ch in s:
        if ch not in _IDX:
            raise ValueError("非法字符 %r" % ch)
        v = v * _BASE + _IDX[ch]
    return v


def encode_sig(r, s):
    """(r, s) -> BZP-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"""
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    body = _b2c(raw, CODE_LEN)
    return PREFIX + "-" + "-".join(
        body[i * GROUP:(i + 1) * GROUP] for i in range(GROUPS))


def normalize(inp):
    """容错清洗：去空白/横线/下划线、大写、剥 BZP 前缀。"""
    s = "".join(inp.split())
    for sep in ("-", "_", "."):
        s = s.replace(sep, "")
    s = s.upper()
    if s.startswith(PREFIX):
        s = s[len(PREFIX):]
    return s


def decode_sig(inp):
    """激活码 -> (r, s)。格式不对抛 ValueError。"""
    body = normalize(inp)
    if len(body) != CODE_LEN:
        raise ValueError("长度应为 %d 位，实为 %d 位" % (CODE_LEN, len(body)))
    v = _c2b(body)
    # 固定宽度切分：r 取高 256 位，s 取低 256 位。宽度由格式约定，不做任何估算。
    if v.bit_length() > 512:
        raise ValueError("数值超出 512 位")
    r = v >> 256
    s = v & ((1 << 256) - 1)
    return (r, s)


def code_for_device(device, signfn):
    """发码器用：设备码 -> 激活码。signfn 由发码器传入（持有私钥）。"""
    r, s = signfn(TAG + normalize_device(device))
    return encode_sig(r, s)


def normalize_device(device):
    d = "".join(str(device).split()).upper()
    return d


def check_code(inp, device, verifyfn):
    """主 App 用：验签。返回 (ok, 原因)。"""
    try:
        r, s = decode_sig(inp)
    except ValueError as e:
        return (False, "激活码格式不对（%s）" % e)
    ok = verifyfn(PUB, TAG + normalize_device(device), (r, s))
    if not ok:
        return (False, "激活码与本机设备码不匹配")
    return (True, "")


def make_request(device, note=""):
    """主 App 用：生成发给作者的申请文字。"""
    d = normalize_device(device)
    ts = ""
    try:
        import time
        ts = time.strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    lines = [REQ_HEAD]
    lines.append("设备码：%s-%s" % (d[:4], d[4:]) if len(d) == 8 else "设备码：%s" % d)
    if ts:
        lines.append("申请时间：%s" % ts)
    if note:
        lines.append("备注：%s" % note)
    lines.append(REQ_TAIL)
    return "\n".join(lines)


def parse_request(text):
    """发码器用：从客户发来的整段文字里解析出设备码。返回 (device, note, ok, msg)。"""
    s = (text or "").replace("\r", "")
    if REQ_HEAD not in s:
        # 宽松：只要找到形如 XXXX-XXXX 的 8 位设备码就接受
        for i in range(len(s) - 8):
            seg = s[i:i + 9]
            if seg[4] == "-" and seg.replace("-", "").upper() in (
                    "".join(c for c in s[i:i + 9] if c != "-").upper(),):
                pass
        m = _loose_device(s)
        if m:
            return (m, "", True, "")
        return ("", "", False, "这段文字里没找到设备码")
    note = ""
    dev = ""
    for line in s.split("\n"):
        line = line.strip()
        if line.startswith("设备码："):
            dev = line[4:].strip()
        elif line.startswith("备注："):
            note = line[3:].strip()
    dev = normalize_device(dev)
    if len(dev) != 8:
        m = _loose_device(s)
        if m:
            dev = m
    if not dev:
        return ("", note, False, "没解析出设备码")
    bad = [c for c in dev if c not in _IDX]
    if bad:
        return ("", note, False, "设备码含非法字符 %s" % "".join(bad))
    return (dev, note, True, "")


def _loose_device(s):
    """从任意文本里捞 8 位设备码（XXXX-XXXX 或连续 8 位）。"""
    up = s.upper()
    for i in range(len(up) - 8):
        chunk = up[i:i + 9]
        if len(chunk) == 9 and chunk[4] == "-":
            cand = chunk[:4] + chunk[5:]
            if len(cand) == 8 and all(c in _IDX for c in cand):
                return cand
    run = ""
    for ch in up + " ":
        if ch in _IDX:
            run += ch
            if len(run) == 8:
                return run
        else:
            run = ""
    return ""
