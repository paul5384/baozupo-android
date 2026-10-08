# -*- coding: utf-8 -*-
"""
android_bridge.py —— 把「只有安卓才做得到的事」集中在一处，且全部可降级

三件事：
    1. 扫码：把相机画面交给 ZXing（com.google.zxing:core，随 APK 打进去）解码
    2. 直拨：ACTION_CALL，没权限就退化成 ACTION_DIAL（只打开拨号盘）
    3. 分享：把账单二维码图片 / 文本丢给系统分享面板（微信、QQ、短信都行）

设计原则（踩过坑才这么写）：
    · 每个函数都返回 (是否成功, 说明)，失败绝不抛异常到 UI 层
    · 桌面（Windows 预览）上 jnius 不存在，全部走降级分支，程序照样能跑
    · 扫码失败时不是「报错」，而是引导改用手输 —— 抄表不能因为识别不出来就卡死
"""

import re

from kivy.utils import platform

ANDROID = (platform == "android")


def _jnius():
    """取 jnius 的 autoclass；桌面或打包缺失时返回 None"""
    if not ANDROID:
        return None
    try:
        from jnius import autoclass
        return autoclass
    except Exception:
        return None


def _activity():
    try:
        autoclass = _jnius()
        if not autoclass:
            return None
        return autoclass("org.kivy.android.PythonActivity").mActivity
    except Exception:
        return None


# =================================================================== 扫码
_ZX = None


def _zxing(force=False):
    global _ZX
    if _ZX is not None and not force:
        return _ZX
    autoclass = _jnius()
    if not autoclass:
        return None
    try:
        zx = {
            "src": autoclass("com.google.zxing.RGBLuminanceSource"),
            "bin": autoclass("com.google.zxing.common.HybridBinarizer"),
            "bmp": autoclass("com.google.zxing.BinaryBitmap"),
            "rdr": autoclass("com.google.zxing.MultiFormatReader"),
            "hint": autoclass("com.google.zxing.DecodeHintType"),
            "map": autoclass("java.util.HashMap"),
            "bool": autoclass("java.lang.Boolean"),
        }
        _ZX = zx
        return zx
    except Exception:
        _ZX = None
        return None


def scanner_available():
    """内置识别器是否可用（打不进 ZXing 或跑在桌面上时为 False）"""
    return _zxing() is not None


def camera_ready(skip_request=False):
    """相机能不能用：先看权限，没权限就申请一次。

    第一次申请是异步的（系统弹框），所以这里返回 False 让界面先提示一下，
    用户点了「允许」之后下一帧再进就通了。
    """
    if not ANDROID:
        return False
    try:
        from android.permissions import Permission, check_permission, request_permissions
    except Exception:
        # 老版本 p4a 没有这个模块：只要清单里写了 CAMERA 权限就当它有
        return True
    try:
        if check_permission(Permission.CAMERA):
            return True
        if not skip_request:
            try:
                request_permissions([Permission.CAMERA])
            except Exception:
                pass
    except Exception:
        return True
    return False


def _sample_rows(pixels, w, h, max_dim):
    """把 RGBA 字节按步长抽样成 [[ARGB int, ...], ...]，缩小到 max_dim 以内。
    相机帧往往 1280x720，整幅丢给 JNI 太慢，抽到 ~360px 宽足够识别二维码。"""
    step = max(1, max(w, h) // max_dim)
    sw, sh = w // step, h // step
    rows = []
    for oy in range(sh):
        base = (oy * step) * w * 4
        row = [0] * sw
        for ox in range(sw):
            i = base + (ox * step) * 4
            # RGBA -> 0x00RRGGBB（alpha 置 0：ZXing 只取 RGB，且这样一定是正数
            # int，不会在 jnius 转 Java int 时触发有符号溢出）
            row[ox] = (pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2]
        rows.append(row)
    return rows, sw, sh


def _decode_flat(zx, flat, w, h):
    try:
        source = zx["src"](w, h, flat)
        bitmap = zx["bmp"](zx["bin"](source))
        reader = zx["rdr"]()
        try:
            hints = zx["map"]()
            hints.put(zx["hint"].TRY_HARDER, zx["bool"](True))
            res = reader.decode(bitmap, hints)
        except Exception:
            res = reader.decode(bitmap)
        if res is None:
            return None
        return str(res.getText())
    except Exception:
        return None


def decode_rgba(pixels, w, h):
    """RGBA 字节 -> 二维码文本；识别不出返回 None。
    相机帧的朝向各机型不一样（有的上下翻转、有的左右镜像），四种都试一遍。"""
    zx = _zxing()
    if not zx or not pixels or w < 8 or h < 8:
        return None
    for max_dim in (360, 640):
        try:
            rows, sw, sh = _sample_rows(pixels, w, h, max_dim)
        except Exception:
            return None
        if sw < 8 or sh < 8:
            continue
        flip_v = rows[::-1]
        mirror = [r[::-1] for r in rows]
        both = [r[::-1] for r in flip_v]
        for variant in (rows, flip_v, mirror, both):
            flat = [v for r in variant for v in r]
            txt = _decode_flat(zx, flat, sw, sh)
            if txt:
                return txt
    return None


def grab_texture_pixels(texture):
    """取相机纹理的 RGBA 字节。

    Android 上相机是外部纹理（GL_TEXTURE_EXTERNAL_OES），texture.pixels 往往读
    不出来，所以统一渲染到 FBO 再读回 —— 这条路在真机上才稳。
    返回 (bytes, w, h) 或 None。
    """
    if texture is None:
        return None
    try:
        w, h = texture.size
        if not w or not h:
            return None
    except Exception:
        return None
    try:
        from kivy.graphics.fbo import Fbo
        from kivy.graphics import ClearColor, ClearBuffers, Rectangle
        fbo = Fbo(size=(w, h), with_depthbuffer=False)
        with fbo:
            ClearColor(0, 0, 0, 1)
            ClearBuffers()
            Rectangle(texture=texture, size=(w, h), pos=(0, 0))
        fbo.draw()
        data = fbo.pixels
        try:
            fbo.release()
        except Exception:
            pass
        if data and len(data) >= w * h * 4:
            return data, w, h
    except Exception:
        pass
    try:
        p = texture.pixels
        if p:
            return p, w, h
    except Exception:
        pass
    return None


def scan_via_other_app(on_result):
    """内置识别器不可用时的兜底：调手机上装了的扫码 App（ZXing 那套公开 Intent）。
    on_result(text) 会在拿到结果后回调一次。返回是否成功唤起。"""
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False
    try:
        from android import activity as _act
        Intent = autoclass("android.content.Intent")

        def _cb(request_code, result_code, intent):
            try:
                _act.unbind(on_activity_result=_cb)
            except Exception:
                pass
            try:
                if intent is not None:
                    txt = intent.getStringExtra("SCAN_RESULT")
                    if txt:
                        on_result(str(txt))
                        return
            except Exception:
                pass
            on_result(None)

        _act.bind(on_activity_result=_cb)
        i = Intent("com.google.zxing.client.android.SCAN")
        i.putExtra("SCAN_MODE", "QR_CODE_MODE")
        act.startActivityForResult(i, 0x0000C0DE)
        return True
    except Exception:
        return False


# =================================================================== 电话
def dial(number):
    """直拨。成功返回 (True, 'call'/'dial')，失败返回 (False, 原因)"""
    num = re.sub(r"\D", "", str(number or ""))
    if not num:
        return False, "号码为空"
    if not ANDROID:
        return False, "当前不是安卓环境"
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False, "无法调用系统电话"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        uri = Uri.parse("tel:%s" % num)
        try:
            act.startActivity(Intent(Intent.ACTION_CALL, uri))
            return True, "call"
        except Exception:
            # 没拿到 CALL_PHONE 权限时会走到这里：至少把号码填进拨号盘
            act.startActivity(Intent(Intent.ACTION_DIAL, uri))
            return True, "dial"
    except Exception as e:
        return False, str(e)


def send_sms(number, body=""):
    """打开短信界面（不自动发送，避免误发）"""
    num = re.sub(r"\D", "", str(number or ""))
    if not num or not ANDROID:
        return False, "不可用"
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False, "不可用"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        i = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:%s" % num))
        i.putExtra("sms_body", str(body or ""))
        act.startActivity(i)
        return True, "ok"
    except Exception as e:
        return False, str(e)


# =================================================================== 分享
def share_text(text, title="分享"):
    """纯文本分享（这条路径 100% 可用，作为分享图片的兜底）"""
    if not ANDROID:
        return False, "当前不是安卓环境"
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False, "不可用"
    try:
        Intent = autoclass("android.content.Intent")
        i = Intent(Intent.ACTION_SEND)
        i.setType("text/plain")
        i.putExtra(Intent.EXTRA_TEXT, str(text))
        act.startActivity(Intent.createChooser(i, str(title)))
        return True, "ok"
    except Exception as e:
        return False, str(e)


def share_image(path, text="", title="分享二维码"):
    """分享一张图片。

    Android 7 以后直接把 file:// 塞进 Intent 会被 StrictMode 干掉，所以按顺序试：
      ① FileProvider（最规范，需要 APK 里声明了 provider）
      ② 临时关掉 StrictMode 的「文件 URI 死亡」检查再发 file://
    都失败就返回 False，由调用方退化成纯文本分享。
    """
    if not ANDROID:
        return False, "当前不是安卓环境"
    if not path or not __import__("os").path.exists(path):
        return False, "文件不存在"
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False, "不可用"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        i = Intent(Intent.ACTION_SEND)
        i.setType("image/png")
        uri = None

        # ① FileProvider
        try:
            FileProvider = autoclass("androidx.core.content.FileProvider")
            authority = str(act.getPackageName()) + ".fileprovider"
            uri = FileProvider.getUriForFile(act, authority, File(path))
        except Exception:
            uri = None

        # ② 关掉 StrictMode 后用 file://
        if uri is None:
            try:
                StrictMode = autoclass("android.os.StrictMode")
                Builder = autoclass("android.os.StrictMode$VmPolicy$Builder")
                StrictMode.setVmPolicy(Builder().build())
            except Exception:
                pass
            try:
                uri = Uri.fromFile(File(path))
            except Exception:
                uri = None
        if uri is None:
            return False, "拿不到文件 URI"

        i.putExtra(Intent.EXTRA_STREAM, uri)
        if text:
            i.putExtra(Intent.EXTRA_TEXT, str(text))
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        act.startActivity(Intent.createChooser(i, str(title)))
        return True, "ok"
    except Exception as e:
        return False, str(e)


def open_url(url):
    """用浏览器打开（扫到 URL 形态的表号时用得上）"""
    if not ANDROID or not url:
        return False, "不可用"
    autoclass = _jnius()
    act = _activity()
    if not autoclass or not act:
        return False, "不可用"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(str(url))))
        return True, "ok"
    except Exception as e:
        return False, str(e)
