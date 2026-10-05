# -*- coding: utf-8 -*-
"""
包租婆授权码发码器（作者专用）  v1.2
================================================================================
只装在作者自己手机上。客户手机上的《包租婆出租屋管家》只含公钥，
私钥只在本 App 内，且经 PIN 加密后落盘。

用法
----
1. 首次打开：设置一个 6 位 PIN（记住它，忘了只能清数据重来）
2. 平时：输入 PIN 解锁
3. 把客户发来的「授权申请」文字整段粘贴进来 → 自动识别设备码
4. 点「生成激活码」→ 复制话术 → 微信发给客户
5. 客户在 App 里粘贴激活码 → 永久解锁

数据
----
  · vault.json   加密后的私钥
  · history.json 发码历史（设备码 / 激活码 / 时间 / 备注）
================================================================================
"""

import io
import json
import os
import sys
import time
import traceback

# ==============================================================================
# 【诊断引导块】必须排在任何 kivy import 之前。
#
# 这就是 v1.0 / v1.1「点开就闪退、界面上一次错误都看不到」的最终根因：
#   kivy 2.3.1 的 kivy/core/image/__init__.py 里有 import filetype，
#   而本项目用的本地 kivy recipe 去掉了 python_depends，filetype 不会自动进包；
#   APK 里没有 filetype -> import kivy.core.image 抛 ModuleNotFoundError。
#   裸 import 失败会**直接把进程杀掉**，Python 层任何 try/except 都来不及接管，
#   所以既看不到 Kivy 的错误页，也没有 traceback —— 表现就是「静默闪退」。
#
# 两条对策：
#   ① 把 filetype 源码随工程打包，并在导入 kivy 之前塞进 sys.path（主 App 已验证）
#   ② 每条 kivy import 单独包一层，失败立刻取证：日志 + 剪贴板 + 原生弹窗
#      （用 jnius 直调 Android API，不依赖 Kivy，Kivy 挂了也照样弹得出来）
# ==============================================================================
APP_TITLE = "包租婆发码器"
VERSION = "1.2"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "simhei.ttf")

_STAGE = "S0 脚本开始执行"
_LINES = []
_FILES = []


def _diag_paths():
    """列出所有可能可写的日志路径（按成功率排序）"""
    out = []
    for env in ("ANDROID_PRIVATE", "ANDROID_ARGUMENT", "ANDROID_APP_PATH",
                "EXTERNAL_STORAGE", "HOME", "TMPDIR"):
        try:
            p = os.environ.get(env)
            if p:
                out.append(os.path.join(p, "bzq_diag.txt"))
                out.append(os.path.join(os.path.dirname(p.rstrip("/")),
                                        "bzq_diag.txt"))
        except Exception:
            pass
    for d in ("/sdcard/Download", "/storage/emulated/0/Download",
              "/data/local/tmp"):
        out.append(os.path.join(d, "bzq_diag.txt"))
    out.append(os.path.join(BASE_DIR, "bzq_diag.txt"))
    uniq = []
    for p in out:
        if p and p not in uniq:
            uniq.append(p)
    return uniq


def _diag_write(text):
    try:
        _LINES.append(text)
        if len(_LINES) > 400:
            del _LINES[:-400]
    except Exception:
        pass
    for p in _FILES:
        try:
            with io.open(p, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def _diag_init():
    for p in _diag_paths():
        try:
            d = os.path.dirname(p)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with io.open(p, "a", encoding="utf-8") as f:
                f.write("\n##### 发码器 %s 启动 %s #####\n"
                        % (VERSION, time.strftime("%Y-%m-%d %H:%M:%S")))
            _FILES.append(p)
        except Exception:
            continue
    _diag_write("日志文件候选: %s" % (_FILES or "全部不可写"))


def _is_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_APP_PATH" in os.environ


def _diag_clip(text):
    """原生剪贴板（不经 Kivy）：Kivy 崩了也能把线索带出来。"""
    if not _is_android():
        return
    try:
        from jnius import autoclass, cast
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        Context = autoclass("android.content.Context")
        cm = cast("android.content.ClipboardManager",
                  act.getSystemService(Context.CLIPBOARD_SERVICE))
        ClipData = autoclass("android.content.ClipData")
        S = autoclass("java.lang.String")
        cm.setPrimaryClip(ClipData.newPlainText(S("发码器诊断"),
                                                S(text[:4000])))
    except Exception:
        pass


def _diag_alert(text):
    """原生 AlertDialog，失败降级 Toast。必须在 UI 线程 show。"""
    if not _is_android():
        return
    try:
        from jnius import autoclass, PythonJavaClass, java_method
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        AlertDialog = autoclass("android.app.AlertDialog")
        builder = AlertDialog.Builder(act)
        builder.setTitle("发码器启动失败")
        builder.setMessage(text[:3000])
        builder.setPositiveButton("关闭", None)

        class _Run(PythonJavaClass):
            __javainterfaces__ = ["java/lang/Runnable"]

            @java_method("()V")
            def run(self):
                try:
                    builder.show()
                except Exception:
                    pass

        act.runOnUiThread(_Run())
    except Exception:
        try:
            from jnius import autoclass
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            Toast = autoclass("android.widget.Toast")
            S = autoclass("java.lang.String")
            Toast.makeText(act, S(text[:150]), Toast.LENGTH_LONG).show()
        except Exception:
            pass


def _diag_env():
    try:
        _diag_write("python: %s" % sys.version.replace("\n", " "))
        _diag_write("argv: %r" % (sys.argv,))
        _diag_write("platform: %s" % sys.platform)
        _diag_write("__file__: %s" % os.path.abspath(__file__))
        try:
            _diag_write("cwd: %s" % os.getcwd())
        except Exception:
            pass
        for k in sorted(os.environ):
            if k.startswith("ANDROID") or k in ("EXTERNAL_STORAGE", "TMPDIR",
                                                "HOME", "P4A_BOOTSTRAP",
                                                "KIVY_WINDOW", "PYTHONHOME"):
                _diag_write("  %s = %r" % (k, os.environ.get(k)))
        for sub in ("filetype", "fonts"):
            _diag_write("  dir %s/: %s" % (sub,
                        os.path.isdir(os.path.join(BASE_DIR, sub))))
    except Exception:
        pass


def _diag_crash(stage, err):
    """崩溃取证：日志 + 剪贴板 + 原生弹窗，然后退出。"""
    try:
        tb = "".join(traceback.format_exception(type(err), err,
                                                err.__traceback__))
    except Exception:
        tb = repr(err)
    msg = "【发码器 %s】\n崩溃阶段: %s\n\n%s" % (VERSION, stage, tb)
    _diag_write("!! 崩溃 %s\n%s" % (stage, tb))
    _diag_clip(msg)
    _diag_alert(msg)
    try:
        time.sleep(3)   # 给 UI 线程时间把弹窗画出来
    except Exception:
        pass
    # 不用 sys.exit：p4a 下 SystemExit 同样会被吞成「无声闪退」
    os._exit(1)


def _diag_step(stage, code):
    """执行一条 import（用 exec 注入模块全局），失败立刻取证。"""
    global _STAGE
    _STAGE = stage
    _diag_write(">> " + stage)
    try:
        exec(code, globals())
    except BaseException as _e:
        _diag_crash(stage, _e)


_diag_init()
_diag_env()
_diag_write("发码器 %s 开始启动" % VERSION)

# ---- filetype 兜底：缺它，下面的 S1.10 会直接把进程带走 ----
try:
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    import filetype as _ft
    _diag_write("filetype OK -> %s" % getattr(_ft, "__file__", "?"))
except BaseException as _e:
    _diag_write("!! filetype 不可用: %r" % (_e,))
    # 不在这里退出：交给下面 S1.10 取证，好让用户看到真实 traceback

_diag_step("S1.1 import kivy", "import kivy")
_diag_write("     kivy=%s" % getattr(kivy, "__version__", "?"))
_diag_step("S1.2 kivy.utils", "from kivy.utils import platform")
_diag_step("S1.3 kivy.config", "from kivy.config import Config")
_diag_step("S1.4 kivy.clock", "from kivy.clock import Clock")
_diag_step("S1.5 kivy.metrics", "from kivy.metrics import dp, sp")
_diag_step("S1.6 kivy.core.window (SDL2 窗口)",
           "import kivy.core.window as _winmod")
_diag_step("S1.7 kivy.graphics", "import kivy.graphics")
_diag_step("S1.8 kivy.core.text", "from kivy.core.text import LabelBase")
_diag_step("S1.9 kivy.core.clipboard",
           "from kivy.core.clipboard import Clipboard")
_diag_step("S1.10 kivy.core.image（filetype 缺失就死在这一步）",
           "import kivy.core.image as _imgmod")
_diag_step("S1.11 kivy.app", "from kivy.app import App")
_diag_step("S1.12 kivy.uix 基础控件",
           "from kivy.uix.boxlayout import BoxLayout; "
           "from kivy.uix.button import Button; "
           "from kivy.uix.label import Label; "
           "from kivy.uix.textinput import TextInput")
_diag_step("S1.13 kivy.uix 弹窗/滚动",
           "from kivy.uix.popup import Popup; "
           "from kivy.uix.scrollview import ScrollView")
_diag_step("S2 业务模块",
           "import ecdsa_p256 as E; import license_core as LC; "
           "import vault as V")
_diag_write("S3 全部 import 完成")

# 颜色（与主 App 同一套暖色系）
C_BG = (0.16, 0.16, 0.18, 1)
C_CARD = (0.22, 0.22, 0.25, 1)
C_TEXT = (0.94, 0.94, 0.95, 1)
C_MUTED = (0.68, 0.68, 0.72, 1)
C_ACCENT = (0.85, 0.64, 0.26, 1)
C_INFO = (0.25, 0.47, 0.78, 1)
C_OK = (0.25, 0.60, 0.35, 1)
C_WARN = (0.80, 0.35, 0.32, 1)

HISTORY_FILE = "bzq_history.json"


def _try_makedirs(p):
    try:
        os.makedirs(p, exist_ok=True)
        return os.path.isdir(p) and os.access(p, os.W_OK)
    except Exception:
        return False


def data_dir():
    """应用私有目录。

    真机闪退的修法：这里原来直接 `from android.storage import app_storage_path`，
    任何一步失败（模块缺失 / pyjnius 未就绪 / 路径不可写）都会让 build() 抛异常，
    表现为「点开就闪退」。现在按 主App 同样的方式做三层兜底：
      ① android.storage.app_storage_path 且可写
      ② expanduser("~")/.bzqissue 且可写
      ③ 最后退到 app 私有目录下的 _localdata（buildozer 已建好）
    任何一层都不抛异常。
    """
    cands = []
    if platform == "android":
        try:
            from android.storage import app_storage_path
            cands.append(app_storage_path())
        except Exception:
            pass
    cands.append(os.path.join(os.path.expanduser("~"), ".bzqissue"))
    cands.append(os.path.join(BASE_DIR, "_localdata"))
    for d in cands:
        try:
            if d and _try_makedirs(d):
                return d
        except Exception:
            continue
    # 全部失败：返回一个必然可写的临时目录，宁可功能异常也不要闪退
    import tempfile
    d = tempfile.mkdtemp(prefix="bzq_")
    return d


def ensure_dir():
    return data_dir()


def now_str():
    return time.strftime("%Y-%m-%d %H:%M")


def walk_widgets(w, out=None):
    """深度遍历控件树（含 Popup，不含 Window 内部那些无关 widget）。"""
    if out is None:
        out = []
    if w is None:
        return out
    out.append(w)
    for c in (getattr(w, "children", None) or []):
        walk_widgets(c, out)
    return out


def toast(app, msg):
    lbl = Label(text=msg, size_hint_y=None, height=dp(44), font_size=sp(13),
                color=C_TEXT, halign="center", valign="middle")
    lbl.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
    p = Popup(title="", content=lbl, size_hint=(0.9, None), height=dp(120),
              auto_dismiss=True)
    p.open()
    Clock.schedule_once(lambda *_: p.dismiss(), 1.6)


class IssueApp(App):
    """发码器主应用。状态机：setup -> lock -> unlocked"""

    def __init__(self, **kw):
        super(IssueApp, self).__init__(**kw)
        self.title = APP_TITLE
        self.priv = None            # 解锁后的私钥十六进制；锁定时为 None
        self.dirty = False          # 私钥是否在内存里
        self.history = []
        self.root_box = None

    # ------------------------------------------------------------------ 数据
    def load_history(self):
        p = os.path.join(ensure_dir(), HISTORY_FILE)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        else:
            self.history = []

    def save_history(self):
        p = os.path.join(ensure_dir(), HISTORY_FILE)
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.history[-500:], f)
        except Exception:
            pass

    def issue(self, device, note=""):
        """签发一个激活码。返回 (code, msg)"""
        device = LC.normalize_device(device)
        if len(device) != 8:
            return ("", "设备码必须是 8 位（现在是 %d 位）" % len(device))
        bad = [c for c in device if c not in LC.CHARS]
        if bad:
            return ("", "设备码含无法识别的字符：%s" % "".join(bad))
        if not self.priv:
            return ("", "尚未解锁")
        try:
            dk = int(self.priv, 16)
            code = LC.code_for_device(device, lambda m: E.sign(dk, m))
        except Exception as e:
            return ("", "签名失败：%s" % e)
        # 自检：立刻用公钥验一遍，绝不把坏码发给客户
        ok, why = LC.check_code(code, device, E.verify)
        if not ok:
            return ("", "内部自检未通过，已拦截：%s" % why)
        self.history.insert(0, {
            "device": device, "code": code, "at": now_str(), "note": note or "",
        })
        self.save_history()
        return (code, "")

    def make_msg(self, device, code, note=""):
        dev = "-".join([device[:4], device[4:]])
        return ("您的包租婆授权已开通：\n\n"
                "设备码：%s\n"
                "激活码：%s\n\n"
                "【怎么用】\n"
                "打开「包租婆出租屋管家」→ 我的 → 升级付费版\n"
                "把上面激活码整段复制，粘到输入框 → 点「激活」\n\n"
                "（激活码较长，请整段复制，不要手动逐字输入）"
                % (dev, code))

    # ------------------------------------------------------------------ 界面
    def build(self):
        # 分步打点：真机闪退时靠 lines 判断崩在哪一步
        _diag_write(">> B1 build() entered")
        try:
            if FONT_PATH and os.path.exists(FONT_PATH):
                _diag_write("     B2 字体存在 size=%d"
                            % os.path.getsize(FONT_PATH))
                LabelBase.register(name="CN", fn_regular=FONT_PATH)
                _diag_write("     B3 字体注册完成")
            else:
                _diag_write("     B2 字体缺失 %r" % (FONT_PATH,))
            self.load_history()
            _diag_write("     B4 历史载入 %d 条" % len(self.history))
            d = ensure_dir()
            _diag_write("     B5 数据目录 %r" % (d,))
            if not V.vault_exists(d):
                _diag_write("     B6 无 vault -> 首次设置界面")
                self.root_box = self.ui_setup()
            else:
                _diag_write("     B6 有 vault -> 解锁界面")
                self.root_box = self.ui_lock()
            _diag_write("     B7 界面构建完成")
            return self.root_box
        except BaseException as _e:
            _diag_crash("build() 阶段 %s" % _STAGE, _e)

    def _lbl(self, text, size=13, color=None, h=None, align="left"):
        # 注意：默认参数里绝不能写 dp()，类体在 import 时求值，
        # 而 dp() 需要已初始化的窗口，导入阶段就会 sys.exit(1)
        if h is None:
            h = dp(30)
        l = Label(text=text, size_hint_y=None, height=h, font_size=sp(size),
                  color=color or C_TEXT, halign=align, valign="middle")
        l.bind(width=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        l.bind(texture_size=lambda w, *_: setattr(w, "height", max(h, w.texture_size[1])))
        return l

    def _btn(self, text, cb, color=None, h=None, size=15):
        if h is None:
            h = dp(46)
        b = Button(text=text, size_hint_y=None, height=h, font_size=sp(size),
                   background_color=color or C_ACCENT, color=(1, 1, 1, 1))
        b.bind(on_release=cb)
        return b
    # ---------------- 首次设置 PIN
    def ui_setup(self):
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        box.add_widget(self._lbl("首次使用 · 设置 PIN", 18, C_ACCENT, dp(44), "center"))
        box.add_widget(self._lbl(
            "这个 PIN 用来解锁私钥，请务必记住。\n"
            "忘记 PIN 只能清空本 App 数据重来，已发出的激活码不受影响。",
            12.5, C_MUTED, dp(60)))
        ti = TextInput(hint_text="设置 6 位数字 PIN", password=True, multiline=False,
                       size_hint_y=None, height=dp(46), font_size=sp(16),
                       background_color=(1, 1, 1, 0.12), foreground_color=C_TEXT,
                       hint_text_color=C_MUTED, padding=[dp(12), dp(12)])
        box.add_widget(ti)
        self._setup_ti = ti

        def do_setup(*_):
            pin = (ti.text or "").strip()
            if not (pin.isdigit() and len(pin) == 6):
                toast(self, "请输入 6 位数字 PIN")
                return
            d = ensure_dir()
            V.setup(d, pin)
            self.priv = V.unlock(d, pin)
            toast(self, "设置完成，已解锁")
            self.switch(self.ui_main())

        box.add_widget(self._btn("确定并进入", do_setup, C_OK))
        return box

    # ---------------- 解锁
    def ui_lock(self):
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        box.add_widget(self._lbl("输入 PIN 解锁", 18, C_ACCENT, dp(44), "center"))
        box.add_widget(self._lbl("私钥已加密保存在本机，输错 5 次请稍后再试",
                                 12.5, C_MUTED, dp(30)))
        ti = TextInput(hint_text="6 位 PIN", password=True, multiline=False,
                       size_hint_y=None, height=dp(46), font_size=sp(16),
                       background_color=(1, 1, 1, 0.12), foreground_color=C_TEXT,
                       hint_text_color=C_MUTED, padding=[dp(12), dp(12)])
        box.add_widget(ti)
        self._lock_ti = ti
        self._fail = 0

        def do_unlock(*_):
            pin = (ti.text or "").strip()
            d = ensure_dir()
            dhex = V.unlock(d, pin)
            if not dhex:
                self._fail += 1
                if self._fail >= 5:
                    toast(self, "连续输错 5 次，请稍后再试")
                    self._fail = 0
                else:
                    toast(self, "PIN 不对（%d/5）" % self._fail)
                ti.text = ""
                return
            self.priv = dhex
            self.dirty = True
            toast(self, "已解锁")
            self.switch(self.ui_main())

        box.add_widget(self._btn("解锁", do_unlock, C_OK))
        box.add_widget(self._btn("忘记 PIN（清空本机数据）",
                                 lambda *_: self.confirm_reset(), C_WARN, dp(42), 13))
        return box

    def switch(self, newbox):
        self.root_box.clear_widgets()
        self.root_box.add_widget(newbox)

    def confirm_reset(self):
        wrap = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        wrap.add_widget(self._lbl(
            "将清空本 App 的 PIN 与发码历史，私钥会用默认分片重新初始化。\n"
            "已发给客户的激活码不受影响。", 13, C_TEXT, dp(70)))
        bar = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None,
                        height=dp(46))

        def do_reset(*_):
            V.reset_vault(ensure_dir())
            p.dismiss()
            self.priv = None
            self.switch(self.ui_setup())

        b1 = self._btn("取消", p.dismiss, C_INFO, dp(44), 14)
        b2 = self._btn("确认清空", do_reset, C_WARN, dp(44), 14)
        bar.add_widget(b1)
        bar.add_widget(b2)
        wrap.add_widget(bar)
        p = Popup(title="确认清空", content=wrap, size_hint=(0.9, None),
                  height=dp(240), auto_dismiss=False)
        p.open()

    # ---------------- 主界面
    def ui_main(self):
        sv = ScrollView(do_scroll_x=False)
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10),
                          padding=dp(14))
        inner.bind(minimum_height=inner.setter("height"))

        inner.add_widget(self._lbl("发码器 %s" % VERSION, 17, C_ACCENT, dp(38)))

        # 1) 粘贴客户申请
        inner.add_widget(self._lbl("① 粘贴客户的授权申请文字", 14, C_TEXT, dp(30)))
        ti = TextInput(hint_text="把客户发来的整段文字粘到这里", multiline=True,
                       size_hint_y=None, height=dp(110), font_size=sp(13),
                       background_color=(1, 1, 1, 0.10), foreground_color=C_TEXT,
                       hint_text_color=C_MUTED, padding=[dp(10), dp(10)])
        inner.add_widget(ti)
        self._req_ti = ti

        def do_parse(*_):
            text = ti.text or ""
            dev, note, ok, msg = LC.parse_request(text)
            if not ok:
                toast(self, msg)
                return
            self._dev = dev
            self._note = note
            self.show_code(dev, note)

        inner.add_widget(self._btn("识别设备码", do_parse, C_INFO, dp(42), 14))

        # 2) 手动输入
        inner.add_widget(self._lbl("或手动输入 8 位设备码", 13, C_MUTED, dp(26)))
        ti2 = TextInput(hint_text="例如 ABCD-2345", multiline=False,
                        size_hint_y=None, height=dp(44), font_size=sp(15),
                        background_color=(1, 1, 1, 0.10), foreground_color=C_TEXT,
                        hint_text_color=C_MUTED, padding=[dp(12), dp(12)])
        inner.add_widget(ti2)
        self._man_ti = ti2

        def do_manual(*_):
            dev = LC.normalize_device(ti2.text or "")
            if len(dev) != 8:
                toast(self, "设备码必须是 8 位")
                return
            self.show_code(dev, "")

        inner.add_widget(self._btn("手动出码", do_manual, C_INFO, dp(42), 14))

        # 3) 历史
        inner.add_widget(self._lbl("② 发码历史（最近 %d 条）" % len(self.history),
                                   14, C_TEXT, dp(34)))
        inner.add_widget(self.ui_history())

        sv.add_widget(inner)
        return sv

    def ui_history(self):
        if not self.history:
            h = self._lbl("还没有发过码", 12.5, C_MUTED, dp(30))
            h._bzq_hist = True
            return h
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))
        box._bzq_hist = True
        for h in self.history[:30]:
            dev = h.get("device", "")
            devs = "-".join([dev[:4], dev[4:]]) if len(dev) == 8 else dev
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(58),
                            padding=dp(8))
            t1 = self._lbl("%s   %s" % (devs, h.get("at", "")), 12, C_TEXT, dp(24))
            t2 = self._lbl(h.get("code", ""), 10.5, C_MUTED, dp(26))
            row.add_widget(t1)
            row.add_widget(t2)

            def mk(h=h):
                def cb(*_):
                    Clipboard.copy(self.make_msg(h.get("device", ""), h.get("code", ""),
                                                 h.get("note", "")))
                    toast(self, "话术已复制，可直接发给客户")
                return cb
            b = self._btn("复制话术", mk(), C_OK, dp(30), 12)
            row.add_widget(b)
            box.add_widget(row)
        return box

    # ---------------- 出码结果
    def show_code(self, device, note):
        code, err = self.issue(device, note)
        dev = "-".join([device[:4], device[4:]]) if len(device) == 8 else device
        if err:
            self.show_popup("出码失败", err, dev, "", [])
            return
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        body.add_widget(self._lbl("设备码 %s" % dev, 14, C_TEXT, dp(28), "center"))
        code_lbl = self._lbl(code, 11, C_ACCENT, dp(120), "center")
        body.add_widget(code_lbl)
        bar = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None,
                        height=dp(46))

        def cp_code(*_):
            Clipboard.copy(code)
            toast(self, "激活码已复制")

        def cp_msg(*_):
            Clipboard.copy(self.make_msg(device, code, note))
            toast(self, "完整话术已复制，可直接发给客户")

        b1 = self._btn("复制激活码", cp_code, C_INFO, dp(44), 13)
        b2 = self._btn("复制话术", cp_msg, C_OK, dp(44), 13)
        bar.add_widget(b1)
        bar.add_widget(b2)
        body.add_widget(bar)
        p = Popup(title="出码成功（已自检通过）", content=body, size_hint=(0.94, None),
                  height=dp(300), auto_dismiss=False)
        p.open()
        # 刷新历史
        try:
            self.refresh_history()
        except Exception:
            pass

    def refresh_history(self):
        """出码后把主界面的历史区块换新，否则用户看不到刚发的码。"""
        try:
            if self.root_box is None:
                return
            for w in walk_widgets(self.root_box):
                if getattr(w, "_bzq_hist", False) and w.parent is not None:
                    idx = w.parent.children.index(w)
                    w.parent.remove_widget(w)
                    w.parent.add_widget(self.ui_history(), index=idx)
                    return
        except Exception:
            pass

    def show_popup(self, title, msg, dev, code, extra):
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        if dev:
            body.add_widget(self._lbl("设备码 %s" % dev, 14, C_TEXT, dp(28), "center"))
        body.add_widget(self._lbl(msg, 12.5, C_WARN, dp(60), "center"))
        body.add_widget(self._btn("知道了", lambda *_: body.parent.dismiss(), C_INFO,
                                  dp(44), 14))
        p = Popup(title=title, content=body, size_hint=(0.9, None), height=dp(240),
                  auto_dismiss=False)
        p.open()

    def on_stop(self):
        # 退出时立刻丢弃内存里的私钥
        self.priv = None
        self.dirty = False

    # ------------------------------------------------------------------ 异常兜底
    def handle_exception(self, inst, exc):
        """Kivy 运行期异常兜底：写日志 + 剪贴板，绝不让 App 静默死掉。"""
        try:
            tb = "".join(traceback.format_exception(type(exc), exc,
                                                     exc.__traceback__))
            _diag_write("!! 运行期异常（Kivy 捕获）: %s\n%s"
                        % (type(exc).__name__, tb))
            _diag_clip("【发码器错误】%s\n\n%s" % (type(exc).__name__, tb[:2500]))
            _diag_alert("【发码器运行出错】\n%s\n%s" % (type(exc).__name__, tb[:2000]))
            try:
                Clipboard.copy("【发码器错误】%s\n\n%s"
                               % (type(exc).__name__, tb[:1200]))
            except Exception:
                pass
        except Exception:
            pass
        return False


def _extra_dirs():
    """额外的、用户用文件管理器能看到的目录。

    Android 11+ 的分区存储下，写 /sdcard 根目录需要权限（发码器故意不申请），
    但 app 专属外部目录（/storage/emulated/0/Android/data/<pkg>/files）
    不需要任何权限，用文件管理器「内部存储 → Android → data → 包租婆发码器」能看到。
    """
    out = []
    if platform == "android":
        for mod, fn in (("android.storage", "app_storage_path"),
                        ("android", "get_external_files_dir")):
            try:
                m = __import__(mod, fromlist=[fn])
                f = getattr(m, fn, None)
                if f is None:
                    continue
                d = f(None) if fn == "get_external_files_dir" else f()
                if d:
                    out.append(d)
                    out.append(os.path.dirname(d))   # Android/data/<pkg>
            except Exception:
                continue
    for p in ("/sdcard", "/storage/emulated/0"):
        try:
            out.append(p)
            out.append(os.path.join(p, "Download"))
        except Exception:
            pass
    return out


def _err_log(text):
    """记录一条错误。统一走诊断通道，全失败也无所谓（不能因日志再崩）。"""
    try:
        _diag_write(text)
        return True
    except Exception:
        return False


def _show_crash(text):
    """崩溃逃生界面：即使主程序起不来，也让错误看得见（可截图/复制）。"""
    try:
        from kivy.base import runTouchApp

        try:
            if FONT_PATH and os.path.exists(FONT_PATH):
                LabelBase.register(name="CN", fn_regular=FONT_PATH)
        except Exception:
            pass

        ti = TextInput(text=text[-5000:], readonly=True, font_size=sp(11),
                       background_color=(0.1, 0.1, 0.12, 1),
                       foreground_color=C_TEXT)
        try:
            ti.font_name = "CN"
        except Exception:
            pass
        sv = ScrollView()
        sv.add_widget(ti)
        runTouchApp(sv)
    except Exception:
        # 连界面都起不来，至少把内容复制到剪贴板
        try:
            Clipboard.copy("【发码器崩溃】\n" + text[-1500:])
        except Exception:
            pass


def main():
    _diag_write(">> M1 main() entered")
    app = IssueApp()
    _diag_write("     M2 app 构造完成")
    try:
        app.run()
    except BaseException as _e:
        # Kivy 的 App.run() 在部分失败路径下走 sys.exit()，try/except 抓不到，
        # 这里统一转成异常，好让外层有机会取证。
        raise RuntimeError("app.run() 失败: %r" % (_e,))
    _diag_write("     M3 app.run() 正常返回")


if __name__ == "__main__":
    # 启动失败不要直接闪退：日志 + 剪贴板 + 原生弹窗 + Kivy 错误界面。
    # 真机「点开就闪退」时，这一层是唯一能拿到原因的地方。
    try:
        main()
    except BaseException as _e:
        try:
            _tb = traceback.format_exc()
            _msg = "【发码器 %s 启动失败】\n阶段: %s\n\n%s" % (VERSION, _STAGE, _tb)
            _diag_write("!! 启动失败\n%s" % _tb)
            _diag_clip(_msg)
            _diag_alert(_msg)
        except Exception:
            pass
        try:
            _show_crash(
                "包租婆发码器 %s 启动失败\n\n%s\n\n"
                "启动阶段记录:\n%s\n\n"
                "请截图此页面发给开发者。\n"
                "（同样的内容也已写进剪贴板，和 bzq_diag.txt）"
                % (VERSION, traceback.format_exc(), "\n".join(_LINES[-40:])))
        except Exception:
            os._exit(1)
