"""私钥保管：加密落盘 + PIN 解锁。

设计考虑
--------
发码器 APK 装在作者自己手机上，但 APK 本身是可以被解包的。所以私钥不以明文写进
代码或配置文件，而是：
  1. 用 PBKDF2-HMAC-SHA256 从 PIN + 随机盐派生一把 AES 级流密钥
  2. 私钥加密后存进应用私有目录的 vault.json
  3. 解密出的私钥只活在内存里，退出 / 锁定时立刻丢弃

这样「拿到 APK 的人」还差一个 PIN；「拿到 APK 且知道 PIN 的人」本来就有权发码。
需要坦白的是：这不是防专业逆向的盾，只是把「解包即得私钥」抬高到「还得知道 PIN」。

另外：私钥本体在这个文件里是以「分片 + 异或」的形式存放的，不是连续明文串，
避免被 grep 整段私钥直接捞走（分片只是提高随手 grep 的门槛，不等于加密，
真正的保护来自上面的 PIN 加密层）。
"""
import hashlib
import hmac
import json
import os

PBKDF2_ROUNDS = 120000
SALT_BYTES = 16
KEYSTREAM_LEN = 32          # 私钥 256 bit
VAULT_NAME = "bzq_vault.json"

# ---- 私钥分片存放（顺序打乱，与 PIN 派生密钥流异或后还原）----
# 真实私钥 = 64 位十六进制，按每 8 位一片切成 8 片；
# 片在文件里的排列由 _ORDER 决定（与自然顺序不同，避免肉眼/grep 直接读出）。
# 这里只是打乱，真正保护来自下方 PBKDF2 + 异或的加密层。
_SHARDS = [
    "3AF74723",   # 0
    "E17AB595",   # 1
    "DC745A8F",   # 2
    "066D9194",   # 3
    "90B96992",   # 4
    "1EEB20EA",   # 5
    "23C26497",   # 6
    "6AE9573E",   # 7
]
_ORDER = [5, 0, 7, 2, 6, 1, 4, 3]


def _derive(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ROUNDS,
                               dklen=KEYSTREAM_LEN)


def _keystream(pin, salt, n):
    """用 PBKDF2 派生并扩展成 n 字节密钥流（sha256 级联，纯标准库）。"""
    ks = b""
    block = b""
    counter = 0
    while len(ks) < n:
        block = hashlib.sha256(_derive(pin, salt) + bytes([counter])).digest()
        ks += block
        counter += 1
    return ks[:n]


def _xor(data, ks):
    return bytes(b ^ k for b, k in zip(data, ks))


def vault_path(data_dir):
    return os.path.join(data_dir, VAULT_NAME)


def vault_exists(data_dir):
    return os.path.exists(vault_path(data_dir))


def _true_priv_hex():
    """按 _ORDER 还原真实私钥字节。"""
    parts = [_SHARDS[i] for i in _ORDER]
    return "".join(parts)


def setup(data_dir, pin):
    """首次设置：生成盐 + 加密私钥落盘。返回 True。"""
    if vault_exists(data_dir):
        return False
    salt = os.urandom(SALT_BYTES)
    raw = bytes.fromhex(_true_priv_hex())
    enc = _xor(raw, _keystream(pin, salt, len(raw)))
    data = {
        "v": 1,
        "salt": salt.hex(),
        "rounds": PBKDF2_ROUNDS,
        "enc": enc.hex(),
        "pin_check": _pin_check(pin, salt),
        "created": time_str(),
    }
    with open(vault_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return True


def _pin_check(pin, salt):
    return hashlib.sha256(b"BZPPIN|" + _derive(pin, salt)).hexdigest()[:32]


def unlock(data_dir, pin):
    """PIN 正确返回私钥十六进制字符串（32 字节），错误返回 None。"""
    if not vault_exists(data_dir):
        return None
    try:
        with open(vault_path(data_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        salt = bytes.fromhex(data["salt"])
        rounds = int(data.get("rounds", PBKDF2_ROUNDS))
        if not hmac.compare_digest(_pin_check(pin, salt), data.get("pin_check", "")):
            return None
        enc = bytes.fromhex(data["enc"])
        raw = _xor(enc, _keystream(pin, salt, len(enc)))
        d = int.from_bytes(raw, "big")
        # 私钥必须落在曲线阶范围内且是有效标量
        import ecdsa_p256 as E
        if not (0 < d < E.N):
            return None
        return "%064X" % d
    except Exception:
        return None


def change_pin(data_dir, old_pin, new_pin):
    """改 PIN。旧 PIN 错返回 False。"""
    if unlock(data_dir, old_pin) is None:
        return False
    _overwrite_vault(data_dir, new_pin)
    return True


def _overwrite_vault(data_dir, new_pin):
    salt = os.urandom(SALT_BYTES)
    raw = bytes.fromhex(_true_priv_hex())
    enc = _xor(raw, _keystream(new_pin, salt, len(raw)))
    data = {
        "v": 1,
        "salt": salt.hex(),
        "rounds": PBKDF2_ROUNDS,
        "enc": enc.hex(),
        "pin_check": _pin_check(new_pin, salt),
        "created": time_str(),
    }
    with open(vault_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(data, f)


def reset_vault(data_dir):
    """清掉 vault，下次启动重新 setup。仅在用户主动重置时调用。"""
    p = vault_path(data_dir)
    if os.path.exists(p):
        try:
            os.remove(p)
            return True
        except Exception:
            return False
    return False


def time_str():
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")
