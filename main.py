# -*- coding: utf-8 -*-
"""
包租婆出租屋管家 · 安卓版（Kivy）  v2.1.0
================================================================================
这是「打包成 APK 之前的源代码」。
  · 想先在电脑上看效果：直接 `python main.py`（需 pip install kivy）
  · 想打成能装到手机上的 APK：见同目录《打包APK说明.md》

数据存放：应用私有目录 baozupo_data.json（安卓上不会被清理，卸载才会删）
备份格式：与电脑版《包租婆电脑版.py》的「备份数据 / 恢复数据」完全一致，
          两个版本可以互相导入导出，实现手机 ↔ 电脑数据互通。
================================================================================
"""

import os
import sys
import time
import json
import io
import traceback
from datetime import datetime, timedelta

# ==============================================================================
# 【诊断引导块 A】—— 在任何 Kivy 代码之前建立日志 / 阶段记录 / 崩溃逃生通道
# 目的：定位"显示启动图后闪退"。不依赖数据线，靠三条通道把信息送出来：
#   1) 手机剪贴板（每次阶段推进都刷新，你粘贴出来即可）
#   2) 文件（应用外部私有目录 / 内部私有目录 / sdcard）
#   3) 崩溃时弹一个错误界面（截图即可）
# 问题定位后，把「诊断引导块 A/B/C」三块整段删除即可恢复干净版本。
# ==============================================================================
DIAG_VERSION = "2.1.1-diag"
_DIAG_LINES = []
_DIAG_FILES = []
_DIAG_STAGE = "S0 脚本开始执行"


def _diag_collect_paths():
    """列出所有可能可写的日志路径（按成功率排序）"""
    out = []
    for env in ("ANDROID_PRIVATE", "ANDROID_ARGUMENT"):
        try:
            p = os.environ.get(env)
            if p and os.path.isdir(p):
                out.append(os.path.join(p, "baozupo_log.txt"))
        except Exception:
            pass
    try:
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        d = act.getExternalFilesDir(None)
        if d is not None:
            out.append(os.path.join(d.getAbsolutePath(), "baozupo_log.txt"))
    except Exception:
        pass
    for d in ("/sdcard/Download", "/storage/emulated/0/Download", "/sdcard"):
        try:
            if os.path.isdir(d):
                out.append(os.path.join(d, "baozupo_log.txt"))
        except Exception:
            pass
    try:
        out.append(os.path.join(os.path.expanduser("~"), "baozupo_log.txt"))
    except Exception:
        pass
    uniq = []
    for p in out:
        if p not in uniq:
            uniq.append(p)
    return uniq


def _diag_write(text):
    """写一行日志：内存 + 所有可写文件"""
    try:
        _DIAG_LINES.append(text)
        if len(_DIAG_LINES) > 400:
            del _DIAG_LINES[:100]
    except Exception:
        pass
    for path in _DIAG_FILES:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def _diag_init_log():
    """逐个尝试打开日志文件，第一个成功的作为主日志"""
    for p in _diag_collect_paths():
        try:
            d = os.path.dirname(p)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write("\n\n########## %s 启动 %s ##########\n"
                        % (DIAG_VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            _DIAG_FILES.append(p)
        except Exception:
            continue
    _diag_write("日志文件候选: %s" % (_DIAG_FILES or "全部不可写"))


def _diag_clip(text):
    """把文本放进系统剪贴板（安卓）。任何失败都静默忽略。"""
    try:
        from jnius import autoclass, cast
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        Context = autoclass("android.content.Context")
        cm = cast("android.content.ClipboardManager",
                  activity.getSystemService(Context.CLIPBOARD_SERVICE))
        ClipData = autoclass("android.content.ClipData")
        cm.setPrimaryClip(ClipData.newPlainText("baozupo-diag", text))
        return True
    except Exception:
        return False


def _diag_report(stage, extra=""):
    """记录阶段：写日志 + 刷新剪贴板（剪贴板里永远保留『最后到达阶段』）"""
    global _DIAG_STAGE
    _DIAG_STAGE = stage
    _diag_write("[阶段] %s %s" % (stage, extra))
    tail = "\n".join(_DIAG_LINES[-25:])
    _diag_clip("【包租婆诊断 %s】\n最后到达阶段: %s\n\n----- 日志尾部 -----\n%s\n"
               "------------------\n(完整日志: %s)"
               % (DIAG_VERSION, stage, tail, (_DIAG_FILES[0] if _DIAG_FILES else "无")))


def _diag_env_dump():
    """环境信息：出问题时用来判断是不是版本/机型/权限相关"""
    info = []
    try:
        info.append("python: %s" % sys.version.replace("\n", " "))
    except Exception:
        pass
    try:
        import platform as _pf
        info.append("machine: %s" % _pf.machine())
        info.append("release: %s" % _pf.release())
        info.append("android_ver: %s" % os.environ.get("ANDROID_ARGUMENT", ""))
    except Exception:
        pass
    try:
        info.append("sys.path: %s" % sys.path[:6])
    except Exception:
        pass
    try:
        ap = os.environ.get("ANDROID_PRIVATE", "")
        info.append("ANDROID_PRIVATE: %s" % ap)
        if ap and os.path.isdir(ap):
            info.append("private dir 内容: %s" % sorted(os.listdir(ap))[:30])
    except Exception as e:
        info.append("private dir 读取失败: %r" % (e,))
    try:
        info.append("BASE_DIR: %s" % _diag_base_dir())
    except Exception:
        pass
    for line in info:
        _diag_write("  " + str(line))


def _diag_base_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return "?"


_diag_init_log()

# ---- native 崩溃取证：faulthandler（SIGSEGV / SIGABRT 等）----
try:
    import faulthandler
    _FAULT_FILE = (os.path.join(os.path.dirname(_DIAG_FILES[0]), "baozupo_crash.txt")
                   if _DIAG_FILES else None)
    if _FAULT_FILE:
        _FF = open(_FAULT_FILE, "a", buffering=1)
        _FF.write("\n\n===== 启动 %s =====\n" % datetime.now().strftime("%m-%d %H:%M:%S"))
        faulthandler.enable(file=_FF, all_threads=True)
        _diag_write("faulthandler -> %s" % _FAULT_FILE)
        # 把上一次的 native 崩溃栈回放进剪贴板（粘贴即可看到，不需要数据线）
        try:
            _prev = io.open(_FAULT_FILE, encoding="utf-8", errors="replace").read()
            if "Current thread" in _prev or "Fatal Python error" in _prev:
                _diag_clip("【上次 native 崩溃栈】\n" + _prev[-3000:])
        except Exception:
            pass
except Exception as _e:
    _diag_write("faulthandler 启用失败: %r" % (_e,))
_diag_write("=" * 60)
_diag_write("诊断版启动 %s" % DIAG_VERSION)
_diag_env_dump()
_diag_report("S0 诊断块初始化完成")
# ==============================================================================
# 【filetype 兜底】Kivy 2.3.1 的 kivy/core/image/__init__.py 会 import filetype，
# 而本地 kivy recipe 为了绕开 charset_normalizer 装不上，去掉了 python_depends，
# 于是 filetype 不会自动进 APK（真机报错：No module named 'filetype'）。
# 解决办法：把 filetype 源码随工程一起打包，并在导入 kivy 前确保它在 sys.path 里。
# ==============================================================================
try:
    _BD = os.path.dirname(os.path.abspath(__file__))
    if _BD not in sys.path:
        sys.path.insert(0, _BD)
    import filetype as _ft
    _diag_write("filetype 可用: %s" % getattr(_ft, "__file__", "?"))
except Exception as _e:
    _diag_write("!! filetype 不可用: %r" % (_e,))
    _diag_report("S0.1 filetype 不可用: %r" % (_e,))

_diag_report("S1 开始导入 Kivy")


# ==============================================================================
# 诊断引导块 A2：崩溃取证 + 细粒度导入
#   上一版证据：日志停在 S1.2，且没有 traceback（裸 import 抛异常会直接杀进程）。
#   本版：每条 import 单独 try，失败立即写 traceback + 剪贴板 + 弹 AlertDialog。
# ==============================================================================
def _diag_alert(text):
    """安卓上弹一个可长按复制的对话框；任何失败都静默。"""
    try:
        from jnius import autoclass, PythonJavaClass, java_method
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        AlertDialog = autoclass("android.app.AlertDialog")
        builder = AlertDialog.Builder(act)
        builder.setTitle("启动失败诊断")
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
            Toast.makeText(act, autoclass("java.lang.String")(text[:200]),
                           Toast.LENGTH_LONG).show()
        except Exception:
            pass


def _diag_crash(stage, err):
    """崩溃取证：日志 + 剪贴板 + 弹窗，然后退出。"""
    try:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    except Exception:
        tb = repr(err)
    msg = "【包租婆诊断 %s】\n崩溃阶段: %s\n\n%s" % (DIAG_VERSION, stage, tb)
    _diag_write("!! 崩溃 %s\n%s" % (stage, tb))
    for path in _DIAG_FILES:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass
    _diag_clip(msg)
    _diag_alert(msg)
    sys.exit(1)


def _diag_step(stage, code):
    """执行一条 import 语句（用 exec 注入模块全局），失败立刻取证。"""
    _diag_report(stage)
    try:
        exec(code, globals())
    except BaseException as _e:
        _diag_crash(stage, _e)


_diag_report("S1.1 导入 kivy 基础包")
try:
    import kivy
except BaseException as _e:
    _diag_crash("S1.1 import kivy", _e)
_diag_report("S1.1 OK kivy=%s" % getattr(kivy, "__version__", "?"))

# ---- S1.1.x 环境取证：native 库目录 / dlopen 能力 / bundle 完整性 ----
_diag_report("S1.1.A 探测 nativeLibraryDir")
try:
    from jnius import autoclass
    _act = autoclass("org.kivy.android.PythonActivity").mActivity
    _nd = _act.getApplicationInfo().nativeLibraryDir
    _diag_write("nativeLibraryDir: %s" % _nd)
    try:
        _diag_write("nativeLibs: %s" % sorted(os.listdir(_nd)))
    except Exception as _e:
        _diag_write("nativeLibs 读取失败: %r" % (_e,))
except Exception as _e:
    _diag_write("nativeLibraryDir 获取失败: %r" % (_e,))

_diag_report("S1.1.B 测试 dlopen libpython3.11.so")
try:
    import ctypes
    _h = ctypes.CDLL("libpython3.11.so")
    _diag_write("dlopen libpython3.11.so: OK -> %s" % _h)
except Exception as _e:
    _diag_write("dlopen libpython3.11.so 失败: %r" % (_e,))
    _diag_report("S1.1.B dlopen 失败: %r" % (_e,))

_diag_report("S1.1.C 检查 kivy 包完整性")
try:
    _kd = os.path.dirname(os.path.abspath(kivy.__file__))
    _diag_write("kivy dir: %s" % _kd)
    _diag_write("kivy 顶层: %s" % sorted(os.listdir(_kd))[:40])
    for _sub in ("core", "graphics", "uix", "lib"):
        _diag_write("  %s 存在: %s" % (_sub, os.path.isdir(os.path.join(_kd, _sub))))
    _diag_write("  _clock.so 存在: %s" % os.path.isfile(os.path.join(_kd, "_clock.so")))
except Exception as _e:
    _diag_write("kivy 目录探测失败: %r" % (_e,))


_diag_step("S1.2.1 kivy.utils", "from kivy.utils import platform")
_diag_step("S1.2.2 kivy.logger", "from kivy.logger import Logger")
_diag_step("S1.2.3 kivy.config", "from kivy.config import Config")
_diag_step("S1.2.4 kivy.clock (_clock.so)", "from kivy.clock import Clock")
_diag_step("S1.2.5 kivy.metrics (_metrics.so)", "from kivy.metrics import dp, sp")
_diag_step("S1.2.6 kivy.graphics (graphics/*.so)", "import kivy.graphics")
_diag_step("S1.2.7 kivy.core.window (_window_sdl2.so + SDL2)", "from kivy.core.window import Window")
_diag_step("S1.2.8 kivy.lang", "from kivy.lang import Builder")
_diag_step("S1.2.9 kivy.properties (properties.so)",
           "from kivy.properties import StringProperty, ListProperty, NumericProperty, BooleanProperty, ObjectProperty")
_diag_step("S1.2.10 kivy.event (_event.so)", "from kivy.event import EventDispatcher")
_diag_step("S1.2.11 kivy.app (含 kivy.base/input)", "from kivy.app import App")
_diag_step("S1.3 kivy.core.text (text_layout.so)", "from kivy.core.text import LabelBase")
_diag_step("S1.4 kivy.core.clipboard", "from kivy.core.clipboard import Clipboard")
_diag_step("S1.5 kivy.uix 基础控件",
           "from kivy.uix.boxlayout import BoxLayout; from kivy.uix.gridlayout import GridLayout; from kivy.uix.label import Label; from kivy.uix.button import Button; from kivy.uix.textinput import TextInput")
_diag_step("S1.6 kivy.uix 高级控件",
           "from kivy.uix.spinner import Spinner; from kivy.uix.checkbox import CheckBox; from kivy.uix.popup import Popup; from kivy.uix.scrollview import ScrollView; from kivy.uix.widget import Widget")
_diag_step("S1.7 kivy.uix.screenmanager",
           "from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition")
_diag_step("S1.8 kivy.uix.recycleview",
           "from kivy.uix.recycleview import RecycleView; from kivy.uix.recycleview.views import RecycleDataViewBehavior; from kivy.uix.behaviors import ButtonBehavior")
_diag_report("S1.9 全部 kivy 子模块导入完成")

# ---- 诊断引导块 B：Kivy 导入成功 ----
try:
    import kivy as _kivy_mod
    _diag_report("S2 Kivy 导入成功", "kivy=%s" % getattr(_kivy_mod, "__version__", "?"))
except Exception as _e:
    _diag_report("S2 Kivy 导入异常", repr(_e))

# ==============================================================================
# 一、基础信息与主题色
# ==============================================================================
APP_NAME = "包租婆出租屋管家"
VERSION = "2.1.3"
AUTHOR = "Paul"
CONTACT = "15880355384"

C_PRIMARY = (0.184, 0.310, 0.310, 1)
C_ACCENT = (0.290, 0.486, 0.349, 1)
C_BG = (0.949, 0.960, 0.953, 1)
C_CARD = (1, 1, 1, 1)
C_TEXT = (0.133, 0.188, 0.180, 1)
C_MUTED = (0.478, 0.545, 0.533, 1)
C_LINE = (0.863, 0.886, 0.878, 1)
C_DANGER = (0.753, 0.314, 0.302, 1)
C_WARN = (0.851, 0.643, 0.255, 1)
C_INFO = (0.243, 0.420, 0.478, 1)

# 弹窗内部配色：Kivy 弹窗面板是深灰色，里面的文字必须用亮色才看得清
POPUP_LABEL_C = (0.84, 0.89, 0.88, 1)   # 字段标签
POPUP_TEXT_C = (0.93, 0.95, 0.95, 1)    # 正文
BTN_NEUTRAL_C = (0.58, 0.63, 0.61, 1)   # 「取消」类按钮背景（深一点，白字才清楚）

CARD_COLORS = [
    (0.184, 0.310, 0.310, 1), (0.290, 0.486, 0.349, 1), (0.243, 0.420, 0.478, 1),
    (0.541, 0.427, 0.231, 1), (0.478, 0.290, 0.420, 1), (0.361, 0.514, 0.455, 1),
    (0.208, 0.408, 0.349, 1), (0.612, 0.400, 0.267, 1), (0.322, 0.475, 0.435, 1),
    (0.427, 0.349, 0.478, 1),
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KV_FILE = os.path.join(BASE_DIR, "baozupo.kv")

# ==============================================================================
# 二、中文字体注册（关键！Kivy 自带字体不含汉字，不注册会全是方框）
# ==============================================================================
def register_cjk_font():
    """按 内置字体 → 安卓系统字体 → Windows 字体 的顺序找一个能显示中文的字体"""
    candidates = [
        os.path.join(BASE_DIR, "fonts", "simhei.ttf"),
        os.path.join(BASE_DIR, "fonts", "DroidSansFallback.ttf"),
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansChinese.ttf",
        "/system/fonts/NotoSansSC-Regular.otf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                # 同一个字体同时注册为常规/粗体，避免 bold:True 时找不到 Roboto-Bold 又退回方框
                LabelBase.register(name="Roboto", fn_regular=path,
                                   fn_bold=path, fn_italic=path, fn_bolditalic=path)
                return path
        except Exception:
            continue
    return None


FONT_PATH = register_cjk_font()
# ---- 诊断：字体是否找到（找不到只会显示方框，不会闪退，但一并记录）----
_diag_report("S3 中文字体注册", "FONT_PATH=%s" % (FONT_PATH or "未找到"))

# ==============================================================================
# 三、存储目录
# ==============================================================================
def _try_makedirs(p):
    try:
        os.makedirs(p, exist_ok=True)
        return os.path.isdir(p) and os.access(p, os.W_OK)
    except Exception:
        return False


def app_data_dir():
    """应用私有目录：数据文件放这里，最安全"""
    if platform == "android":
        try:
            from android.storage import app_storage_path
            d = app_storage_path()
            if _try_makedirs(d):
                return d
        except Exception:
            pass
    d = os.path.join(os.path.expanduser("~"), ".baozupo")
    _try_makedirs(d)
    return d


def public_dirs():
    """外部存储候选目录（用来放导出的备份，方便用数据线/微信传回电脑）"""
    ds = []
    if platform == "android":
        ds += ["/sdcard/Download", "/sdcard/包租婆备份", "/sdcard/Documents",
               "/sdcard", "/storage/emulated/0/Download"]
    else:
        ds += [os.path.join(os.path.expanduser("~"), "Desktop", "包租婆备份"),
               os.path.join(os.path.expanduser("~"), "Desktop")]
    ds.append(app_data_dir())
    out = []
    for d in ds:
        if os.path.isdir(d) and os.access(d, os.W_OK) and d not in out:
            out.append(d)
    return out


DATA_FILE = os.path.join(app_data_dir(), "baozupo_data.json")
_diag_report("S4 数据目录就绪", "DATA_FILE=%s" % DATA_FILE)

# ==============================================================================
# 四、数据层
# ==============================================================================
EMPTY_DATA = {"houses": [], "tenants": [], "payments": [], "utilities": []}


def is_number(s):
    try:
        float(s)
        return True
    except Exception:
        return False


def normalize_yn(v):
    """把历史数据里 True/False/1/0/'有'/'无' 统一成「有」或「无」
    （老版本写进 JSON 的是布尔值，直接显示会变成 厨: True 卫: False 很难看）"""
    if isinstance(v, bool):
        return "有" if v else "无"
    s = str(v).strip()
    low = s.lower()
    if low in ("true", "1", "yes", "y", "有"):
        return "有"
    if low in ("false", "0", "no", "n", "无", ""):
        return "无"
    return s


def room_key(h):
    """房间号自然排序：1-602 排在 1-19013 前面（纯字符串排序会把 1-19013 放最前）"""
    room = str(h.get("room", ""))
    parts = []
    num = ""
    for ch in room:
        if ch.isdigit():
            num += ch
        else:
            if num:
                parts.append((1, int(num), ""))
                num = ""
            parts.append((0, 0, ch))
    if num:
        parts.append((1, int(num), ""))
    while parts and parts[-1][0] == 0 and parts[-1][2] in ("", " "):
        parts.pop()
    return (str(h.get("address", "")), parts)


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calc_end_date(start_date, rent_type):
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        return (s + timedelta(days=30 if rent_type == "月租" else 365)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def gen_months(n=12):
    now = datetime.now()
    y, m, res = now.year, now.month, []
    for _ in range(n):
        res.append("%d-%02d" % (y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return res[::-1]


class Store(object):
    """所有数据的读写都在这里，格式与电脑版一致"""

    def __init__(self):
        self.data = json.loads(json.dumps(EMPTY_DATA))
        self.settings = {"month_advance": 1, "year_advance": 7,
                         "price_water": 3.5, "price_elec": 0.65}
        self.users = []
        self.load()

    # ---------- 读写 ----------
    def load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self._absorb(raw)
        except Exception:
            pass

    def _absorb(self, raw):
        d = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if isinstance(d, dict):
            for k in EMPTY_DATA:
                v = d.get(k)
                self.data[k] = v if isinstance(v, list) else []
        # 统一「有/无」，兼容老版本写进去的 True/False
        for h in self.data["houses"]:
            if isinstance(h, dict):
                for k in ("kitchen", "toilet", "balcony"):
                    h[k] = normalize_yn(h.get(k, "无"))
        if isinstance(raw.get("settings"), dict):
            self.settings.update(raw["settings"])
        if isinstance(raw.get("users"), list):
            self.users = raw["users"]

    def save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.payload(), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def payload(self):
        return {"data": self.data, "settings": self.settings, "users": self.users,
                "app": "baozupo", "version": VERSION, "export_time": now_str()}

    # ---------- 查询 ----------
    def houses(self):
        return self.data["houses"]

    def current_tenant(self, room):
        for t in self.data["tenants"]:
            if str(t.get("room")) == str(room) and not t.get("is_leave", False):
                return t
        return None

    def tenants_of(self, room):
        return [t for t in self.data["tenants"] if str(t.get("room")) == str(room)]

    def pays_of(self, room):
        return [p for p in self.data["payments"] if str(p.get("room")) == str(room)]

    def utils_of(self, room):
        return [u for u in self.data["utilities"] if str(u.get("room")) == str(room)]

    def find_house(self, room):
        for h in self.data["houses"]:
            if str(h.get("room")) == str(room):
                return h
        return None

    def addresses(self):
        return sorted({str(h.get("address", "")) for h in self.data["houses"] if h.get("address")})

    # ---------- 用户 ----------
    def ensure_default_user(self):
        if not self.users:
            self.users = [{"username": "admin", "password": "123456"}]
            self.save()
            return True
        return False

    def verify_login(self, u, p):
        return any(x.get("username") == u and x.get("password") == p for x in self.users)

    def register(self, u, p):
        if any(x.get("username") == u for x in self.users):
            return False
        self.users.append({"username": u, "password": p})
        self.save()
        return True

    def change_password(self, u, old, new):
        for x in self.users:
            if x.get("username") == u and x.get("password") == old:
                x["password"] = new
                self.save()
                return True
        return False

    # ---------- 统计 ----------
    def _snapshot_stats(self):
        """「当前快照」类指标：房间数 / 在租 / 押金 / 月租合计 —— 与统计区间无关"""
        houses = self.data["houses"]
        total = len(houses)
        rented = len([h for h in houses if h.get("status") == "已租"])
        deposit = sum(float(t.get("deposit", 0)) for t in self.data["tenants"]
                      if not t.get("is_leave", False) and is_number(t.get("deposit")))
        rent_sum = sum(float(h["price"]) for h in houses
                       if h.get("status") == "已租" and is_number(h.get("price")))
        return total, rented, deposit, rent_sum

    def _money_of(self, prefix):
        """按前缀累加收租与水电：prefix 可以是 '2026-03'（月）也可以是 '2026'（年）"""
        paid = sum(float(p.get("money", 0)) for p in self.data["payments"]
                   if str(p.get("date", "")).startswith(prefix) and is_number(p.get("money")))
        elec = water = 0.0
        for u in self.data["utilities"]:
            if str(u.get("month", "")).startswith(prefix) \
                    and is_number(u.get("elec")) and is_number(u.get("water")):
                elec += float(u["elec"])
                water += float(u["water"])
        return paid, elec, water

    def stats(self, ym):
        """按月统计（原有行为不变）"""
        total, rented, deposit, rent_sum = self._snapshot_stats()
        paid_rent, elec, water = self._money_of(str(ym))
        return {
            "总房间": str(total), "已租": str(rented), "空闲": str(total - rented),
            "已收押金": "%.0f元" % deposit, "月租合计": "%.0f元" % rent_sum,
            "已收租金": "%.0f元" % paid_rent, "未收租金": "%.0f元" % max(0.0, rent_sum - paid_rent),
            "已收电费": "%.0f元" % elec, "已收水费": "%.0f元" % water,
            "当月总收费": "%.0f元" % (paid_rent + elec + water),
        }

    def stats_year(self, year):
        """按年统计：房间/押金是快照，收租与水电按整年累加；
        年租合计 = 在租房月租 × 12，未收 = 年应收 - 当年已收"""
        total, rented, deposit, rent_sum = self._snapshot_stats()
        paid_rent, elec, water = self._money_of(str(year))
        year_rent = rent_sum * 12
        return {
            "总房间": str(total), "已租": str(rented), "空闲": str(total - rented),
            "已收押金": "%.0f元" % deposit, "月租合计": "%.0f元" % year_rent,
            "已收租金": "%.0f元" % paid_rent, "未收租金": "%.0f元" % max(0.0, year_rent - paid_rent),
            "已收电费": "%.0f元" % elec, "已收水费": "%.0f元" % water,
            "当月总收费": "%.0f元" % (paid_rent + elec + water),
        }

    def data_months(self, n=12):
        """可选月份：最近 n 个月 + 数据里出现过的所有月份（去重，倒序）。
        只给最近 12 个月的话，「往年」那几个月的数据在按月视图里根本选不到。"""
        ms = set(gen_months(n))
        for p in self.data.get("payments", []):
            d = str(p.get("date", ""))
            if len(d) >= 7 and d[:4].isdigit() and d[5:7].isdigit():
                ms.add(d[:7])
        for u in self.data.get("utilities", []):
            mo = str(u.get("month", ""))
            if len(mo) >= 7 and mo[:4].isdigit() and mo[5:7].isdigit():
                ms.add(mo[:7])
        return sorted(ms, reverse=True)

    def data_years(self, n=6):
        """可选年份：数据里出现过的年份 + 最近 n 年（去重，倒序）"""
        years = set()
        for p in self.data.get("payments", []):
            d = str(p.get("date", ""))
            if len(d) >= 4 and d[:4].isdigit():
                years.add(d[:4])
        for u in self.data.get("utilities", []):
            mo = str(u.get("month", ""))
            if len(mo) >= 4 and mo[:4].isdigit():
                years.add(mo[:4])
        now_y = datetime.now().year
        for i in range(n):
            years.add(str(now_y - i))
        return sorted(years, reverse=True)

    def range_records(self, prefix):
        """统计区间内的明细流水：收租 + 水电，用于导出"""
        pays = [p for p in self.data.get("payments", [])
                if str(p.get("date", "")).startswith(prefix)]
        utils = [u for u in self.data.get("utilities", [])
                 if str(u.get("month", "")).startswith(prefix)]
        try:
            pays.sort(key=lambda x: (str(x.get("date", "")), room_key({"room": x.get("room", "")})))
        except Exception:
            pass
        try:
            utils.sort(key=lambda x: (str(x.get("month", "")), room_key({"room": x.get("room", "")})))
        except Exception:
            pass
        return pays, utils

    def reminders(self):
        """返回 [(房间, 姓名, 到期日, 剩余天数)]，包含已过期"""
        out = []
        today = datetime.now().date()
        for t in self.data["tenants"]:
            if t.get("is_leave", False):
                continue
            od = t.get("out_date", "")
            try:
                d = datetime.strptime(od, "%Y-%m-%d").date()
            except Exception:
                continue
            adv = int(t.get("month_advance", self.settings.get("month_advance", 1))) \
                if t.get("rent_type") == "月租" else int(t.get("year_advance", self.settings.get("year_advance", 7)))
            left = (d - today).days
            if left <= adv:
                out.append((str(t.get("room")), str(t.get("name")), od, left))
        out.sort(key=lambda x: x[3])
        return out


# ==============================================================================
# 五、通用 UI 组件
# ==============================================================================
class StatCard(BoxLayout):
    label = StringProperty("")
    value = StringProperty("0")
    bg = ListProperty([0.18, 0.31, 0.31, 1])


class HouseCard(RecycleDataViewBehavior, BoxLayout):
    room = StringProperty("")
    address = StringProperty("")
    status = StringProperty("")
    line1 = StringProperty("")
    line2 = StringProperty("")
    line3 = StringProperty("")
    line4 = StringProperty("")
    # 没有在租租客时，卡片上的「收租 / 水电」按钮置灰，避免空闲房凭空缴费
    has_tenant = BooleanProperty(False)
    card_bg = ListProperty([1, 1, 1, 1])
    tag_bg = ListProperty([0.29, 0.49, 0.35, 1])
    tag_fg = ListProperty([1, 1, 1, 1])

    # 双击卡片（按钮区除外）打开「查看详情」
    # 不用 touch.is_double_tap：部分输入后端不设置该标志，自己按「时间 + 位置」判定更可靠
    _TAP_GAP = 0.45        # 两次点击最大间隔（秒）
    _TAP_DIST = 40         # 两次点击最大位移（dp），避免滚动/拖动被误判

    def __init__(self, **kw):
        super(HouseCard, self).__init__(**kw)
        self._last_tap = 0.0
        self._last_pos = (0, 0)

    def _in_button_row(self, pos):
        """底部 dp(34) 的按钮行 + padding：这一区域交给四个按钮，不参与双击"""
        return pos[1] <= self.y + dp(48)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not self._in_button_row(touch.pos):
            now = time.time()
            dx = abs(touch.pos[0] - self._last_pos[0])
            dy = abs(touch.pos[1] - self._last_pos[1])
            if now - self._last_tap < self._TAP_GAP and dx < dp(self._TAP_DIST) \
                    and dy < dp(self._TAP_DIST):
                self._last_tap = 0.0
                app = App.get_running_app()
                if app is not None and self.room:
                    app.open_detail(self.room)
                return True
            self._last_tap = now
            self._last_pos = touch.pos
        return super(HouseCard, self).on_touch_down(touch)


class TenantCard(RecycleDataViewBehavior, BoxLayout):
    name = StringProperty("")
    room = StringProperty("")
    line1 = StringProperty("")
    line2 = StringProperty("")
    line3 = StringProperty("")
    tag = StringProperty("")
    tag_bg = ListProperty([0.29, 0.49, 0.35, 1])


class NavBtn(ButtonBehavior, BoxLayout):
    text = StringProperty("")
    screen = StringProperty("")
    active = BooleanProperty(False)


class BottomNav(BoxLayout):
    pass


class ColorRow(BoxLayout):
    """带圆角底色的一行提示条"""
    bg = ListProperty([1, 1, 1, 1])

    def __init__(self, text="", bg=(1, 1, 1, 1), **kw):
        kw.setdefault("orientation", "horizontal")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(42))
        kw.setdefault("padding", [dp(10), 0])
        super(ColorRow, self).__init__(**kw)
        self.bg = list(bg)
        lab = Label(text=text, font_size=sp(13), color=C_TEXT, halign="left", valign="middle")
        lab.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self.add_widget(lab)


class Root(BoxLayout):
    pass


class LoginScreen(Screen):
    pass


class HomeScreen(Screen):
    def on_pre_enter(self, *a):
        App.get_running_app().build_home()


class HousesScreen(Screen):
    def on_pre_enter(self, *a):
        App.get_running_app().refresh_houses()


class TenantsScreen(Screen):
    def on_pre_enter(self, *a):
        App.get_running_app().refresh_tenants()


class MineScreen(Screen):
    def on_pre_enter(self, *a):
        App.get_running_app().refresh_mine()


def mk_input(hint="", text="", password=False, readonly=False):
    ti = TextInput(hint_text=hint, text=text, multiline=False, password=password,
                   size_hint_y=None, height=dp(44), font_size=sp(15),
                   background_color=C_CARD, foreground_color=C_TEXT,
                   cursor_color=C_ACCENT, readonly=readonly,
                   padding=[dp(10), dp(10), dp(10), dp(10)])
    return ti


def mk_spinner(values, text=""):
    return Spinner(text=text or (values[0] if values else ""), values=values,
                   size_hint_y=None, height=dp(44), font_size=sp(15), color=C_TEXT)


def text_lines_h(text, font_size, max_w, min_h=0):
    """按 max_w 宽度排版后，这段文字实际要占多少像素高。

    为什么必须量：表单里的字段标签是「固定 height」的 Label，Kivy 既不裁剪也不撑高，
    一旦中文长标签（如「入住日期 YYYY-MM-DD」「月租金元（只填数字）」）在半宽格里
    折行，第二行会直接画到下边的输入框上 —— 真机上看到的就是「字重叠」。
    提早按真实排版量出高度把行高留够，桌面和手机都不会挤。
    """
    if not text or max_w <= 1:
        return max(min_h, font_size * 1.4)
    try:
        from kivy.core.text import Label as CoreLabel
        probe = CoreLabel(text=text, font_size=font_size, text_size=(max_w, None))
        probe.refresh()
        h = probe.texture.size[1] if probe.texture else 0
        return max(min_h, h)
    except Exception:
        return max(min_h, font_size * 1.4)


class FormDialog(Popup):
    """通用表单弹窗：每个字段「标签在上、输入框在下」，手机上最清晰
    fields = [{key,label,kind,values,value,hint,readonly,half,on_change}]
      kind      : text / num / password / combo
      half      : True 时与相邻的 half 字段并排一行（省高度）
      on_change : 下拉框选中后的回调 (widget, text, all_widgets)
    """

    # 注意：整体尺寸不能写死像素。曾写成 ROW_H = 68（原始像素），在 density≈2.75
    # 的真机上 68px 根本装不下 dp(20) 的标签 + dp(44) 的输入框（共约 175px），
    # 于是「添加房间 / 修改密码 / 全局提醒设置」的表单全部挤在一起重叠。
    # 现在全部改为实例化时用 dp() 计算，桌面（density=1）与手机表现一致。

    POPUP_W = 0.94          # 与下面 self.size_hint_x 保持一致

    def __init__(self, title, fields, on_submit, submit_text="保存", **kw):
        super(FormDialog, self).__init__(**kw)
        self.ctl_h = dp(44)                           # 输入框 / 下拉框高
        self.title = title
        self.title_size = sp(16)
        self.auto_dismiss = False
        self._on_submit = on_submit
        self._widgets = {}

        # 预先算出「全宽 / 半宽」两种格子各自有多少横向空间，用来预判标签是否折行
        inner_w = Window.width * self.POPUP_W - dp(16)      # root 左右各 dp(8) padding
        half_w = (inner_w - dp(8)) / 2.0                    # 半宽行内部 spacing dp(8)

        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None, padding=[0, 0])
        grid.bind(minimum_height=grid.setter("height"))

        cells = [(f, self._make_cell(f, half_w if f.get("half") else inner_w))
                 for f in fields]

        i = 0
        while i < len(cells):
            f, cell = cells[i]
            nxt = cells[i + 1] if i + 1 < len(cells) else None
            if f.get("half"):
                row_h = cell.height
                if nxt is not None and nxt[0].get("half"):
                    row_h = max(cell.height, nxt[1].height)
                    cell.height = nxt[1].height = row_h
                    row = BoxLayout(orientation="horizontal", size_hint_y=None,
                                    height=row_h, spacing=dp(8))
                    row.add_widget(cell)
                    row.add_widget(nxt[1])
                    grid.add_widget(row)
                    i += 2
                    continue
                row = BoxLayout(orientation="horizontal", size_hint_y=None,
                                height=row_h, spacing=dp(8))
                row.add_widget(cell)
                row.add_widget(Widget())
                grid.add_widget(row)
                i += 1
                continue
            grid.add_widget(cell)
            i += 1

        body_h = dp(74) + sum(c.height for c in grid.children) + dp(56)
        max_h = Window.height * 0.95
        self.size_hint = (self.POPUP_W, None)
        self.height = min(body_h, max_h)

        root = BoxLayout(orientation="vertical", spacing=dp(4),
                         padding=[dp(8), dp(10), dp(8), dp(8)])
        if body_h > max_h:
            sv = ScrollView(do_scroll_x=False)
            sv.add_widget(grid)
            root.add_widget(sv)
        else:
            root.add_widget(grid)
            root.add_widget(Widget())

        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_cancel = Button(text="取消", font_size=sp(15), background_color=BTN_NEUTRAL_C,
                          color=(1, 1, 1, 1))
        b_cancel.bind(on_release=lambda *_: self.dismiss())
        b_ok = Button(text=submit_text, font_size=sp(15), background_color=C_ACCENT,
                      color=(1, 1, 1, 1))
        b_ok.bind(on_release=lambda *_: self._submit())
        bar.add_widget(b_cancel)
        bar.add_widget(b_ok)
        root.add_widget(bar)
        self.content = root

    def _make_cell(self, f, avail_w):
        lab_fs = sp(12)
        lab_h = max(dp(20), text_lines_h(f.get("label", ""), lab_fs, avail_w) + dp(4))
        row_h = lab_h + self.ctl_h + dp(6)
        cell = BoxLayout(orientation="vertical", size_hint_y=None, height=row_h,
                         spacing=dp(2))
        lab = Label(text=f.get("label", ""), size_hint_y=None, height=lab_h,
                    font_size=lab_fs, color=POPUP_LABEL_C, halign="left", valign="top",
                    shorten=True, shorten_from="right")
        lab.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        cell.add_widget(lab)
        if f.get("kind") == "combo":
            w = mk_spinner(f.get("values") or [""], str(f.get("value", "")))
        else:
            w = mk_input(f.get("hint", ""), str(f.get("value", "")),
                         password=(f.get("kind") == "password"),
                         readonly=bool(f.get("readonly")))
        self._widgets[f["key"]] = w
        cell.add_widget(w)
        cb = f.get("on_change")
        if cb:
            w.bind(text=lambda inst, val, fn=cb: fn(inst, val, self._widgets))
        return cell

    def _submit(self):
        vals = {k: str(w.text).strip() for k, w in self._widgets.items()}
        if self._on_submit(vals) is not False:
            self.dismiss()


def info_popup(title, message, on_close=None, btn="知道了", extra_btn=None):
    """extra_btn=(按钮文字, 回调)：用于「查看详情时顺手导出」这类场景。"""
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    sv = ScrollView(do_scroll_x=False)
    lab = Label(text=message, size_hint_y=None, font_size=sp(14), color=POPUP_TEXT_C,
                halign="left", valign="top")
    lab.bind(width=lambda w, *_: setattr(w, "text_size", (w.width, None)))
    lab.bind(texture_size=lambda w, *_: setattr(w, "height", w.texture_size[1]))
    sv.add_widget(lab)
    box.add_widget(sv)
    # 高度跟着文案走：写死 0.7 屏高时短提示下面一大片空白，长提示又被压扁
    _w = Window.width * 0.92 - dp(20)
    _bh = text_lines_h(message, sp(14), _w, min_h=dp(60))
    _h = min(max(dp(200), _bh + dp(46) + dp(60) + (dp(50) if extra_btn else 0)),
             Window.height * 0.88)
    p = Popup(title=title, title_size=sp(16), content=box, size_hint=(0.92, None),
              height=_h, auto_dismiss=True)
    if extra_btn:
        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        b2 = Button(text=extra_btn[0], font_size=sp(15),
                    background_color=C_INFO, color=(1, 1, 1, 1))
        b2.bind(on_release=lambda *_: extra_btn[1]())
        b1 = Button(text=btn, size_hint_x=0.45, font_size=sp(15),
                    background_color=C_ACCENT, color=(1, 1, 1, 1))
        bar.add_widget(b2)
        bar.add_widget(b1)
        box.add_widget(bar)
        b1.bind(on_release=lambda *_: p.dismiss())
    else:
        b = Button(text=btn, size_hint_y=None, height=dp(46), font_size=sp(15),
                   background_color=C_ACCENT, color=(1, 1, 1, 1))
        box.add_widget(b)
        b.bind(on_release=lambda *_: p.dismiss())
    if on_close:
        p.bind(on_dismiss=lambda *_: on_close())
    p.open()
    return p


def confirm_popup(title, message, on_yes, yes_text="确定", danger=False):
    box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
    # ★ 文案不再「写死 dp(230) 塞进剩余空间」：像「重复收租？」这种会把历史上每笔
    #   记录逐行列出来的长文案，塞进固定高度就会被压扁成一片重叠。
    #   现在：文字自己测高 → 包 ScrollView → 弹窗高度跟着文案走（最多占 92% 屏高）。
    sv = ScrollView(do_scroll_x=False)
    lab = Label(text=message, size_hint_y=None, font_size=sp(14), color=POPUP_TEXT_C,
                halign="left", valign="top")
    lab.bind(width=lambda w, *_: setattr(w, "text_size", (w.width, None)))
    lab.bind(texture_size=lambda w, *_: setattr(w, "height", w.texture_size[1]))
    sv.add_widget(lab)
    box.add_widget(sv)
    bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    b_no = Button(text="取消", font_size=sp(15), background_color=BTN_NEUTRAL_C,
                  color=(1, 1, 1, 1))
    b_yes = Button(text=yes_text, font_size=sp(15),
                   background_color=C_DANGER if danger else C_ACCENT, color=(1, 1, 1, 1))
    bar.add_widget(b_no)
    bar.add_widget(b_yes)
    box.add_widget(bar)

    body_w = Window.width * 0.9 - dp(20)
    body_h = text_lines_h(message, sp(14), body_w, min_h=dp(60))
    # 余量给足（标题栏 + 按钮栏 + 内边距 + 半行），否则最后一行会被切一半
    h = min(max(dp(260), body_h + dp(48) + dp(88)), Window.height * 0.92)

    p = Popup(title=title, title_size=sp(16), content=box, size_hint=(0.9, None),
              height=h, auto_dismiss=False)
    b_no.bind(on_release=lambda *_: p.dismiss())
    b_yes.bind(on_release=lambda *_: (p.dismiss(), on_yes()))
    p.open()
    return p


# ==============================================================================
# 六、主应用
# ==============================================================================
class BaozupoApp(App):
    version = StringProperty(VERSION)
    login_user = StringProperty("")
    stat_ym = StringProperty(datetime.now().strftime("%Y-%m"))
    # 「按月 / 按年」两种统计口径：按年时用它选年份，可查往年
    stat_mode = StringProperty("按月")
    stat_year = StringProperty(str(datetime.now().year))
    filter_status = StringProperty("全部")
    search_key = StringProperty("")

    def load_kv(self, filename=None):
        """关掉 Kivy 的 kv 自动加载，统一在 build() 里显式加载，避免解析两次"""
        return

    def build(self):
        _diag_report("S5 进入 build()")
        self.title = APP_NAME
        self.store = Store()
        first = self.store.ensure_default_user()
        _diag_report("S5.1 数据层初始化完成")
        if platform == "android":
            try:
                Window.softinput_mode = "below_target"
            except Exception:
                pass

        if not os.path.exists(KV_FILE):
            _diag_report("S5.2 缺少 kv 文件", KV_FILE)
            return Label(text="缺少界面文件 baozupo.kv，\n请确认它和 main.py 在同一个目录里。")
        _diag_report("S5.2 加载界面文件", KV_FILE)
        Builder.load_file(KV_FILE)
        _diag_report("S5.3 界面文件解析完成")

        root = Root()                       # 规则已在上面注册，这里直接实例化即可
        self.root_widget = root
        self.sm = root.ids.sm
        self.nav = root.ids.nav
        self.sm.transition = NoTransition()
        # 底部导航按钮在 Python 里绑定点击（KV 里对自定义 ButtonBehavior 绑定 on_release 解析不稳定）
        for btn in self.nav.children:
            if isinstance(btn, NavBtn):
                btn.bind(on_release=lambda inst: self.go(inst.screen))
        self.sm.bind(current=self._sync_nav)
        if first:
            self.set_login_hint("首次使用可先用 admin / 123456 登录，或点下方注册新账号")
        self._sync_nav()
        Window.bind(on_keyboard=self.on_hardware_back)
        _diag_report("S6 UI 构建完成，返回根组件")
        return root

    def on_start(self):
        _diag_report("S7 应用已进入前台（on_start）")

    # ------------------------------------------------------------------ 导航
    def _sync_nav(self, *a):
        cur = self.sm.current
        self.nav.opacity = 1 if cur in ("home", "houses", "tenants", "mine") else 0
        self.nav.disabled = cur == "login"
        self.nav.height = dp(56) if cur != "login" else 0
        for btn in self.nav.children:
            if isinstance(btn, NavBtn):
                btn.active = (btn.screen == cur)
        Clock.schedule_once(self._sync_nav_again, 0)

    def _sync_nav_again(self, *a):
        for btn in self.nav.children:
            if isinstance(btn, NavBtn):
                btn.active = (btn.screen == self.sm.current)

    def go(self, name):
        if self.sm.current == name:
            return
        self.sm.current = name
        self._sync_nav()

    def on_hardware_back(self, window, key, *largs):
        if key != 27:
            return False
        if self.sm.current != "home":
            self.go("home")
            return True
        return False

    # ------------------------------------------------------------------ 登录
    def set_login_hint(self, text, color=None):
        try:
            lab = self.sm.get_screen("login").ids.hint
            lab.text = text
            lab.color = color or C_DANGER
        except Exception:
            pass

    def do_login(self, user, pwd):
        user, pwd = (user or "").strip(), (pwd or "").strip()
        if not user or not pwd:
            self.set_login_hint("账号和密码不能为空")
            return
        if self.store.verify_login(user, pwd):
            self.login_user = user
            self.set_login_hint("")
            self.go("home")
        else:
            self.set_login_hint("账号或密码错误")

    def open_register(self):
        def submit(v):
            u, p = v.get("u", ""), v.get("p", "")
            if not u or not p:
                self.toast("账号和密码不能为空")
                return False
            if self.store.register(u, p):
                info_popup("注册成功", "账号「%s」已创建，现在可以直接登录。" % u)
                return True
            self.toast("该账号已存在")
            return False

        FormDialog("注册新账号", [
            {"key": "u", "label": "账号", "kind": "text", "hint": "请输入账号"},
            {"key": "p", "label": "密码", "kind": "password", "hint": "请输入密码"},
        ], submit, submit_text="注册").open()

    def logout(self):
        def yes():
            self.login_user = ""
            self.go("login")
            self.set_login_hint("已退出登录")
        confirm_popup("退出登录", "确定要退出当前账号吗？", yes, yes_text="退出")

    def toast(self, msg, title="提示"):
        info_popup(title, msg)

    # ------------------------------------------------------------------ 首页
    def build_home(self):
        if getattr(self, "sm", None) is None:
            return          # KV 初始化阶段会提前触发一次，此时界面还没装配好，直接跳过
        self.store.load()
        body = self.sm.get_screen("home").ids.body
        body.clear_widgets()

        # 统计区间切换：按月（含往月 12 个月） / 按年（含往年）
        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6), padding=[dp(2), dp(2)])
        lab = Label(text="统计区间", size_hint_x=None, width=dp(64), font_size=sp(13), color=C_MUTED)
        bar.add_widget(lab)
        mode_spn = mk_spinner(["按月", "按年"], self.stat_mode)
        mode_spn.size_hint_x = None
        mode_spn.width = dp(76)
        mode_spn.bind(text=self.on_stat_mode_change)
        bar.add_widget(mode_spn)
        if self.stat_mode == "按年":
            years = self.store.data_years()
            if self.stat_year not in years:
                years = years + [self.stat_year]
            y_spn = mk_spinner(years, self.stat_year)
            y_spn.bind(text=self.on_year_change)
            bar.add_widget(y_spn)
        else:
            months = self.store.data_months()      # 含数据里出现过的往月，不只是最近 12 个月
            m_spn = mk_spinner(months, self.stat_ym if self.stat_ym in months else months[0])
            m_spn.bind(text=self.on_month_change)
            bar.add_widget(m_spn)
        btn_exp = Button(text="导出", size_hint_x=None, width=dp(58), font_size=sp(13),
                         background_color=C_INFO, color=(1, 1, 1, 1))
        btn_exp.bind(on_release=lambda *_: self.export_stats())
        bar.add_widget(btn_exp)
        body.add_widget(bar)

        # 统计卡片（一行 5 个 × 2 行）
        grid = GridLayout(cols=5, spacing=dp(6), size_hint_y=None, padding=[0, dp(2)])
        grid.bind(minimum_height=grid.setter("height"))
        # (显示标签, 数据键) —— 注意按年时标签要改叫「年租合计 / 当年总收费」，
        # 但数据键仍是 stats_year 返回的「月租合计 / 当月总收费」，两者必须映射对，
        # 否则卡片会取不到值而显示 0（曾因此把 25200 显示成 0）。
        if self.stat_mode == "按年":
            data = self.store.stats_year(self.stat_year)
            cards = [("总房间", "总房间"), ("已租", "已租"), ("空闲", "空闲"),
                     ("已收押金", "已收押金"), ("年租合计", "月租合计"),
                     ("已收租金", "已收租金"), ("未收租金", "未收租金"),
                     ("已收电费", "已收电费"), ("已收水费", "已收水费"),
                     ("当年总收费", "当月总收费")]
            title = "实时统计（%s 年）" % self.stat_year
        else:
            data = self.store.stats(self.stat_ym)
            cards = [(k, k) for k in ["总房间", "已租", "空闲", "已收押金", "月租合计",
                                      "已收租金", "未收租金", "已收电费", "已收水费", "当月总收费"]]
            title = "实时统计（%s）" % self.stat_ym
        for i, (lab, dk) in enumerate(cards):
            grid.add_widget(StatCard(label=lab, value=data.get(dk, "0"),
                                     bg=CARD_COLORS[i % len(CARD_COLORS)], height=dp(58)))
        body.add_widget(grid)
        # 标题栏同步显示当前统计区间（KV 里是写死的「实时统计」）
        try:
            self.sm.get_screen("home").ids.title.text = title
        except Exception:
            pass

        # 到期提醒
        rem = self.store.reminders()
        body.add_widget(self._section("到期提醒", "%d 条" % len(rem)))
        if not rem:
            body.add_widget(self._hint("暂无临近到期的租客"))
        else:
            for room, name, od, left in rem[:8]:
                txt = "%s · %s    到期 %s    %s" % (
                    room, name, od,
                    ("已过期 %d 天" % -left) if left < 0 else ("还剩 %d 天" % left))
                bg = (0.99, 0.92, 0.92, 1) if left < 0 else (0.99, 0.97, 0.89, 1)
                body.add_widget(self._row_card(txt, bg))

        # 快捷操作（含全局搜索）
        body.add_widget(self._section("快捷操作", ""))
        actions = [("搜索 房间 / 租客", self.open_global_search),
                   ("＋ 添加新房", lambda: self.open_house_form("add")),
                   ("房屋租金一览", lambda: self.go("houses")),
                   ("租客列表", lambda: self.go("tenants")),
                   ("导出 / 导入备份", self.open_backup_menu),
                   ("导出当前统计", self.export_stats)]
        rows = (len(actions) + 1) // 2
        quick = GridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                           height=rows * dp(56) + (rows - 1) * dp(8))
        for text, cb in actions:
            b = Button(text=text, font_size=sp(14),
                       background_color=C_INFO if text.startswith("搜索") else C_ACCENT,
                       color=(1, 1, 1, 1))
            b.bind(on_release=lambda inst, f=cb: f())
            quick.add_widget(b)
        body.add_widget(quick)

        # 数据文件路径只在「关于」里显示，首页不再占用版面

    def on_month_change(self, spinner, text):
        if not text or text == self.stat_ym:
            return
        self.stat_ym = text
        self.build_home()

    def on_stat_mode_change(self, spinner, text):
        """按月 <-> 按年：切换后重画首页（下拉框内容变了，必须重建）"""
        if not text or text == self.stat_mode:
            return
        self.stat_mode = text
        self.build_home()

    def on_year_change(self, spinner, text):
        if not text or text == self.stat_year:
            return
        self.stat_year = text
        self.build_home()

    # ---------------------------------------------------------- 搜索
    def house_haystack(self, h):
        """一套房的可搜索文本：房间号 / 地址 / 状态 / 面积 / 租金 / 配套 / 当前租客"""
        room = str(h.get("room", ""))
        t = self.store.current_tenant(room)
        return " ".join([room, str(h.get("address", "")), str(h.get("status", "")),
                         str(h.get("area", "")), str(h.get("price", "")),
                         str(h.get("kitchen", "")), str(h.get("toilet", "")),
                         str(h.get("balcony", "")),
                         (t or {}).get("name", ""), (t or {}).get("tel", "")]).lower()

    def match_tokens(self, hay, key):
        """多关键词 AND：空格分隔，全部命中才算匹配（如「张三 138」）"""
        key = (key or "").strip().lower()
        if not key:
            return True
        return all(tok in hay for tok in key.split())

    def _search_row(self, text, sub, on_hit, bg=(1, 1, 1, 1)):
        """搜索结果行：主标题 + 副标题，整行可点。

        注意：不要在 Button 里嵌 BoxLayout 装两个 Label —— Button 本身继承自 Label，
        它会把子控件按自己的「文字区」摆放，实测两行文字会被挤到右边、甚至整行空白。
        直接给 Button 一个多行 text，配 halign/valign + text_size 即可。
        """
        b = Button(text="%s\n%s" % (text, sub), size_hint_y=None, height=dp(58),
                   font_size=sp(13), background_normal="", background_color=bg,
                   color=C_TEXT, halign="left", valign="middle")
        b.bind(size=lambda w, *_: setattr(w, "text_size", (w.width - dp(16), w.height)))
        b.bind(on_release=on_hit)
        return b

    def open_global_search(self, *a):
        """首页快捷操作里的搜索：一次搜「房屋」和「租客」，点结果直接进详情"""
        self.store.load()
        p = Popup(title="搜索", title_size=sp(16), size_hint=(0.94, 0.86), auto_dismiss=True)
        root = BoxLayout(orientation="vertical", spacing=dp(6),
                         padding=[dp(8), dp(8), dp(8), dp(8)])
        ti = mk_input("房间号 / 地址 / 租客姓名 / 电话", "")
        ti.height = dp(46)
        root.add_widget(ti)

        res = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        res.bind(minimum_height=res.setter("height"))
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(res)
        root.add_widget(sv)

        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        b_house = Button(text="在房屋页查看", font_size=sp(14), background_color=C_ACCENT,
                         color=(1, 1, 1, 1))
        b_close = Button(text="关闭", font_size=sp(14), background_color=BTN_NEUTRAL_C,
                         color=(1, 1, 1, 1))
        bar.add_widget(b_house)
        bar.add_widget(b_close)
        root.add_widget(bar)

        def jump_houses(*_):
            p.dismiss()
            self.goto_houses_with(ti.text or "")

        def render(*_):
            key = (ti.text or "").strip()
            res.clear_widgets()
            if not key:
                tip = Label(text="输入关键词自动搜索。\n支持空格分隔多个词，如「张三 138」。",
                            font_size=sp(12), color=C_MUTED, halign="left", valign="top",
                            size_hint_y=None, height=dp(50))
                tip.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
                res.add_widget(tip)
                return
            hits_h, hits_t = [], []
            for h in sorted(self.store.houses(), key=room_key):
                if self.match_tokens(self.house_haystack(h), key):
                    hits_h.append(h)
            for t in self.store.data.get("tenants", []):
                hay = " ".join([str(t.get("name", "")), str(t.get("tel", "")),
                                str(t.get("room", "")), str(t.get("rent_type", ""))]).lower()
                if self.match_tokens(hay, key):
                    hits_t.append(t)
            if not hits_h and not hits_t:
                none = Label(text="没有找到匹配的结果", font_size=sp(13), color=C_MUTED,
                             size_hint_y=None, height=dp(40))
                res.add_widget(none)
                return

            head = Label(text="房屋 %d 套" % len(hits_h), font_size=sp(12), color=C_PRIMARY,
                         halign="left", size_hint_y=None, height=dp(24))
            head.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            res.add_widget(head)
            for h in hits_h[:30]:
                room = str(h.get("room", ""))
                t = self.store.current_tenant(room)
                sub = "%s · %s元/月 · %s" % (
                    h.get("address", ""), h.get("price", ""),
                    ("租客 %s" % t.get("name", "")) if t else "空闲")
                res.add_widget(self._search_row(
                    "房间 %s  %s" % (room, h.get("status", "")), sub,
                    lambda inst, r=room: (p.dismiss(), self.open_detail(r))))

            head2 = Label(text="租客 %d 人" % len(hits_t), font_size=sp(12), color=C_PRIMARY,
                          halign="left", size_hint_y=None, height=dp(24))
            head2.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            res.add_widget(head2)
            for t in hits_t[:30]:
                room = str(t.get("room", ""))
                sub = "房间 %s · %s · 入住 %s" % (room, t.get("rent_type", ""), t.get("in_date", ""))
                res.add_widget(self._search_row(
                    "%s  %s" % (t.get("name", ""), t.get("tel", "")), sub,
                    lambda inst, r=room: (p.dismiss(), self.open_detail(r)),
                    bg=(0.97, 0.98, 0.97, 1)))

        ti.bind(text=lambda *_: render())
        b_close.bind(on_release=lambda *_: p.dismiss())
        b_house.bind(on_release=jump_houses)
        render()
        p.content = root
        p.open()

    def goto_houses_with(self, key):
        """带着关键词跳到房屋页（先把词写进输入框，再刷新，顺序不能反）"""
        self.search_key = key or ""
        try:
            ti = self.sm.get_screen("houses").ids.search
            if ti.text != self.search_key:
                ti.text = self.search_key
        except Exception:
            pass
        self.go("houses")
        self.refresh_houses()

    def on_search_change(self, text):
        """房屋页输入框变化即过滤（原来只有按回车才触发，用户以为搜索没反应）"""
        self.search_key = text or ""
        self.refresh_houses()

    def search_from_input(self, *a):
        """「搜索」按键：显式从输入框取值再过滤，不依赖 kv 的 on_text 绑定"""
        try:
            self.search_key = self.sm.get_screen("houses").ids.search.text or ""
        except Exception:
            pass
        self.refresh_houses()

    def clear_search(self, *a):
        self.goto_houses_with("")

    # ---------------------------------------------------------- 统计导出
    def stat_range_label(self):
        return ("%s 年" % self.stat_year) if self.stat_mode == "按年" else self.stat_ym

    def stat_range_prefix(self):
        return str(self.stat_year) if self.stat_mode == "按年" else str(self.stat_ym)

    def export_stats(self, *a):
        """导出当前统计区间的汇总 + 明细流水为 CSV（Excel 直接可开）"""
        self.store.load()
        import csv as _csv
        prefix = self.stat_range_prefix()
        label = self.stat_range_label()
        data = (self.store.stats_year(self.stat_year) if self.stat_mode == "按年"
                else self.store.stats(self.stat_ym))
        # 同 build_home：标签与数据键要一一对应（按年时「年租合计」取「月租合计」）。
        # 这里刻意不写嵌套三元——括号一多就容易漏，分开赋值最稳。
        base_keys = ["总房间", "已租", "空闲", "已收押金", "月租合计",
                     "已收租金", "未收租金", "已收电费", "已收水费", "当月总收费"]
        if self.stat_mode == "按年":
            pairs = list(zip(["总房间", "已租", "空闲", "已收押金", "年租合计",
                              "已收租金", "未收租金", "已收电费", "已收水费", "当年总收费"],
                             base_keys))
        else:
            pairs = [(k, k) for k in base_keys]
        pays, utils = self.store.range_records(prefix)

        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["统计区间", label])
        w.writerow([])
        w.writerow(["指标", "数值"])
        for lab, dk in pairs:
            w.writerow([lab, data.get(dk, "0")])
        w.writerow([])
        w.writerow(["【收租明细】共 %d 笔" % len(pays)])
        w.writerow(["房间号", "租客", "金额(元)", "日期"])
        for p in pays:
            w.writerow([str(p.get("room", "")), str(p.get("name", "")),
                        str(p.get("money", "")), str(p.get("date", ""))])
        w.writerow([])
        w.writerow(["【水电明细】共 %d 笔" % len(utils)])
        w.writerow(["房间号", "月份", "电费(元)", "水费(元)"])
        for u in utils:
            w.writerow([str(u.get("room", "")), str(u.get("month", "")),
                        str(u.get("elec", "")), str(u.get("water", ""))])
        # BOM：不加 Excel 打开中文全是乱码
        out = "\ufeff" + buf.getvalue()
        name = "统计_%s.csv" % (label.replace(" ", "").replace("-", ""))
        path = self._write_public(name, out)
        if path:
            info_popup("导出成功",
                       "「%s」的统计数据已保存到：\n%s\n\n"
                       "汇总 10 项 · 收租 %d 笔 · 水电 %d 笔，\n用 Excel / WPS 打开即可。"
                       % (label, path, len(pays), len(utils)))
        else:
            self.toast("导出失败：没有可写的存储目录")

    def _section(self, title, right=""):
        row = BoxLayout(size_hint_y=None, height=dp(34))
        lab = Label(text=title, font_size=sp(15), color=C_PRIMARY, halign="left", valign="middle")
        lab.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        row.add_widget(lab)
        if right:
            r = Label(text=right, font_size=sp(12), color=C_MUTED, size_hint_x=None,
                      width=dp(90), halign="right", valign="middle")
            r.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            row.add_widget(r)
        return row

    def _hint(self, text):
        lab = Label(text=text, font_size=sp(12), color=C_MUTED, halign="left", valign="middle",
                    size_hint_y=None, height=dp(30))
        lab.bind(width=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        return lab

    def _row_card(self, text, bg=(1, 1, 1, 1)):
        return ColorRow(text=text, bg=bg)

    # ------------------------------------------------------------------ 房屋
    def refresh_houses(self):
        if getattr(self, "sm", None) is None:
            return
        self.store.load()
        scr = self.sm.get_screen("houses")
        # 搜索词以 self.search_key 为准，不再从输入框回读：
        # 旧实现每次都 ti.text -> search_key，会把程序设置的关键词（如首页搜索带过来的）
        # 直接覆盖掉，表现为「点了搜索但列表没变」。输入框那边由 on_text 回调负责同步进来。
        key = (self.search_key or "").strip().lower()
        filt = self.filter_status
        rows = []
        houses = sorted(self.store.houses(), key=room_key)
        for h in houses:
            room = str(h.get("room", ""))
            st = h.get("status", "空闲")
            if filt != "全部" and st != filt:
                continue
            t = self.store.current_tenant(room)
            # 原来只能整串匹配（"张三 138" 搜不到），现在支持空格分词 + 全字段（含配套）
            if not self.match_tokens(self.house_haystack(h), key):
                continue
            rented = (st == "已租")
            fac = "厨:%s  卫:%s  阳台:%s" % (h.get("kitchen", "无"), h.get("toilet", "无"),
                                            h.get("balcony", "无"))
            line3, line4 = "", ""
            if rented and t:
                line2 = "租客 %s  %s" % (t.get("name", ""), t.get("tel", ""))
                # ★ 原来「入住 + 到期 + 押金 + 最近收租」全挤一行，手机窄屏放不下会被截断，
                #   现在拆成两行，各字段都完整可见
                line3 = "入住 %s → 到期 %s" % (t.get("in_date", ""), t.get("out_date", ""))
                line4 = "押金 %s元" % t.get("deposit", "0")
            elif rented:
                line2 = "已租（无租客记录）"
            else:
                line2 = "空闲中 · 点击下方「租客」登记入住"
            pays = self.store.pays_of(room)
            if pays:
                line4 = (line4 + "   最近收租 " + str(pays[-1].get("date", ""))).strip()
            rows.append({
                "room": room, "address": str(h.get("address", "")), "status": st,
                "has_tenant": bool(t),
                "line1": "%s㎡ · %s元/月 · %s" % (h.get("area", ""), h.get("price", ""), fac),
                "line2": line2, "line3": line3, "line4": line4,
                "tag_bg": list(C_ACCENT) if rented else [0.61, 0.67, 0.65, 1],
                "card_bg": [1, 1, 1, 1],
            })
        rv = scr.ids.rv
        rv.data = rows
        tip = "共 %d 套（状态：%s）" % (len(rows), filt)
        if key:
            tip += "  搜索「%s」" % (self.search_key or "").strip()
        scr.ids.count.text = tip
        if not rows:
            rv.data = []

    def on_filter_change(self, spinner, text):
        if not text:
            return
        self.filter_status = text
        self.refresh_houses()

    def open_house_form(self, mode, room=None):
        """mode: add / edit。添加时自动带入「最近一套房」的信息，并支持按小区一键带出配置"""
        self.store.load()
        addrs = self.store.addresses()
        base = {"addr": "", "room": "", "area": "", "price": "",
                "kitchen": "无", "toilet": "无", "balcony": "无", "status": "空闲"}

        if mode == "edit" and room:
            h = self.store.find_house(room)
            if not h:
                self.toast("找不到该房间，可能已被删除")
                return
            base.update({"addr": str(h.get("address", "")), "room": str(h.get("room", "")),
                         "area": str(h.get("area", "")), "price": str(h.get("price", "")),
                         "kitchen": str(h.get("kitchen", "无")), "toilet": str(h.get("toilet", "无")),
                         "balcony": str(h.get("balcony", "无")), "status": str(h.get("status", "空闲"))})
        elif self.store.houses():
            # ★ 添加新房时「获取当前房屋信息」：默认继承最近一套房的地址与配套
            last = self.store.houses()[-1]
            base.update({"addr": str(last.get("address", "")),
                         "area": str(last.get("area", "")), "price": str(last.get("price", "")),
                         "kitchen": str(last.get("kitchen", "无")),
                         "toilet": str(last.get("toilet", "无")),
                         "balcony": str(last.get("balcony", "无"))})

        def fill_by_addr(w, val, ws):
            """从「已有小区」下拉里选一个小区，自动带出该小区最近一套房的配置"""
            if not val or val == "不选择":
                return
            ws["addr"].text = val
            same = [h for h in self.store.houses() if str(h.get("address", "")) == val]
            if not same:
                return
            last = same[-1]
            ws["area"].text = str(last.get("area", ""))
            ws["price"].text = str(last.get("price", ""))
            ws["kitchen"].text = normalize_yn(last.get("kitchen", "无"))
            ws["toilet"].text = normalize_yn(last.get("toilet", "无"))
            ws["balcony"].text = normalize_yn(last.get("balcony", "无"))

        fields = [
            {"key": "addr", "label": "房屋地址", "kind": "text",
             "value": base["addr"], "hint": "例如 上富佳苑"},
            {"key": "pick", "label": "已有小区快速带入（选填）", "kind": "combo",
             "values": ["不选择"] + addrs, "value": "不选择", "on_change": fill_by_addr},
            {"key": "room", "label": "房间号", "kind": "text", "value": base["room"],
             "half": True},
            {"key": "area", "label": "面积（㎡）", "kind": "text",
             "value": base["area"], "half": True},
            {"key": "price", "label": "月租金（元）", "kind": "text",
             "value": base["price"], "half": True},
            {"key": "status", "label": "状态", "kind": "combo", "values": ["空闲", "已租"],
             "value": base["status"], "half": True},
            {"key": "kitchen", "label": "带厨房", "kind": "combo", "values": ["有", "无"],
             "value": base["kitchen"], "half": True},
            {"key": "toilet", "label": "带卫生间", "kind": "combo", "values": ["有", "无"],
             "value": base["toilet"], "half": True},
            {"key": "balcony", "label": "带阳台", "kind": "combo", "values": ["有", "无"],
             "value": base["balcony"], "half": True},
        ]

        def submit(v):
            addr = (v.get("addr") or "").strip()
            room_no = (v.get("room") or "").strip()
            area, price = v.get("area", ""), v.get("price", "")
            if not addr:
                self.toast("请填写房屋地址")
                return False
            if not room_no or not area or not price:
                self.toast("房间号 / 面积 / 月租金 不能为空")
                return False
            if not is_number(area) or not is_number(price):
                self.toast("面积和月租金必须是数字，不要带㎡或元")
                return False
            self.store.load()
            if mode == "add":
                if self.store.find_house(room_no):
                    self.toast("房间号「%s」已存在" % room_no)
                    return False
                self.store.houses().append({
                    "address": addr, "room": room_no, "area": area, "price": price,
                    "kitchen": v.get("kitchen", "无"), "toilet": v.get("toilet", "无"),
                    "balcony": v.get("balcony", "无"), "status": v.get("status", "空闲")})
            else:
                h = self.store.find_house(room)
                if not h:
                    self.toast("找不到该房间")
                    return False
                # ★ 房间号可修改：改号时先查重，再把它名下所有关联记录一起迁移
                if str(room_no) != str(room):
                    if self.store.find_house(room_no):
                        self.toast("房间号「%s」已被占用，请换一个" % room_no)
                        return False
                    old_no = str(room)
                    for t in self.store.data["tenants"]:
                        if str(t.get("room")) == old_no:
                            t["room"] = room_no
                    for p in self.store.data["payments"]:
                        if str(p.get("room")) == old_no:
                            p["room"] = room_no
                    for u in self.store.data["utilities"]:
                        if str(u.get("room")) == old_no:
                            u["room"] = room_no
                    h["room"] = room_no
                h.update({"address": addr, "area": area, "price": price,
                          "kitchen": v.get("kitchen", "无"), "toilet": v.get("toilet", "无"),
                          "balcony": v.get("balcony", "无"), "status": v.get("status", "空闲")})
            self.store.save()
            self.refresh_houses()
            if mode == "add":
                self.toast("保存成功")
            elif str(room_no) != str(room):
                self.toast("房间号已由「%s」改为「%s」" % (room, room_no))
            else:
                self.toast("房间「%s」已修改" % room_no)
            return True

        FormDialog("添加新房" if mode == "add" else "修改房屋 - %s" % room,
                   fields, submit).open()

    # ------------- 单套房子的各种操作 -------------
    def house_action(self, action, room):
        fn = {"tenant": self.open_tenant_form, "pay": self.open_pay_form,
              "util": self.open_util_form, "more": self.open_more_menu}.get(action)
        if fn:
            fn(room)

    def open_more_menu(self, room):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        items = [
            ("查看详情", lambda: self.open_detail(room)),
            ("修改房屋", lambda: self.open_house_form("edit", room)),
            ("以此为模板新增同款房", lambda: self.open_house_form("add")),
            ("设置该租客提醒天数", lambda: self.open_warn_setting(
                self.store.current_tenant(room))),
            ("一键退租", lambda: self.do_evict(room)),
            ("删除记录…", lambda: self.open_delete_choose(room)),
        ]
        p = Popup(title="%s · 更多操作" % room, title_size=sp(16),
                  size_hint=(0.9, 0.78), auto_dismiss=True)
        for text, cb in items:
            b = Button(text=text, size_hint_y=None, height=dp(46), font_size=sp(15),
                       background_color=C_ACCENT if text != "删除记录…" else C_DANGER,
                       color=(1, 1, 1, 1))
            b.bind(on_release=lambda inst, f=cb: (p.dismiss(), f()))
            box.add_widget(b)
        p.content = box
        p.open()

    # ------------------------------------------------------------------ 导出
    def _write_public(self, name, content):
        """把文本写到手机可访问的公共目录，返回保存路径；全失败返回 None。"""
        for d in public_dirs():
            try:
                path = os.path.join(d, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return path
            except Exception:
                continue
        return None

    def export_tenants_csv(self, *a):
        """导出全部租客（含历史）为 CSV，Excel/WPS 可直接打开。"""
        self.store.load()
        import csv as _csv
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["房间号", "姓名", "电话", "入住日期", "到期日期", "租期",
                    "押金(元)", "状态", "剩余天数"])
        ts = self.store.data.get("tenants", [])
        try:
            ts = sorted(ts, key=lambda x: room_key(x.get("room", "")))
        except Exception:
            pass
        for t in ts:
            left = ""
            try:
                d = datetime.strptime(t.get("out_date", ""), "%Y-%m-%d").date()
                left = str((d - datetime.now().date()).days)
            except Exception:
                pass
            w.writerow([str(t.get("room", "")), str(t.get("name", "")), str(t.get("tel", "")),
                        str(t.get("in_date", "")), str(t.get("out_date", "")),
                        str(t.get("rent_type", "")), str(t.get("deposit", "0")),
                        "已退租" if t.get("is_leave", False) else "在租", left])
        # BOM：不加的话 Excel 打开中文全是乱码
        data = "\ufeff" + buf.getvalue()
        name = "租客名单_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M")
        path = self._write_public(name, data)
        if path:
            info_popup("导出成功", "租客名单已保存到：\n%s\n\n共 %d 条记录，"
                                   "用 Excel / WPS 打开即可。" % (path, len(ts)))
        else:
            self.toast("导出失败：没有可写的存储目录")

    def open_detail(self, room):
        self.store.load()
        h = self.store.find_house(room)
        if not h:
            self.toast("找不到该房间")
            return
        lines = ["【房屋信息】",
                 "地址：%s" % h.get("address", ""),
                 "房间号：%s        面积：%s㎡        月租金：%s元" % (
                     h.get("room", ""), h.get("area", ""), h.get("price", "")),
                 "配套：厨房 %s / 卫生间 %s / 阳台 %s" % (
                     h.get("kitchen", "无"), h.get("toilet", "无"), h.get("balcony", "无")),
                 "状态：%s" % h.get("status", ""), "", "【历届租客】"]
        ts = self.store.tenants_of(room)
        if not ts:
            lines.append("（暂无）")
        for t in ts:
            end = t.get("leave_date", "") if t.get("is_leave", False) else t.get("out_date", "")
            lines.append("· %s %s  %s ~ %s  %s  押金%s元%s" % (
                t.get("name", ""), t.get("tel", ""), t.get("in_date", ""), end,
                t.get("rent_type", ""), t.get("deposit", "0"),
                "（已退租）" if t.get("is_leave", False) else ""))
        lines += ["", "【房租缴费记录】"]
        ps = self.store.pays_of(room)
        if not ps:
            lines.append("（暂无）")
        fee = 0.0
        for p in ps:
            if is_number(p.get("money")):
                fee += float(p["money"])
            lines.append("· %s  %s元  %s" % (p.get("date", ""), p.get("money", ""), p.get("name", "")))
        lines.append("合计：%.0f 元" % fee)
        lines += ["", "【水电记录】"]
        us = self.store.utils_of(room)
        if not us:
            lines.append("（暂无）")
        for u in us:
            lines.append("· %s  电费 %s元  水费 %s元" % (u.get("month", ""), u.get("elec", ""), u.get("water", "")))

        def do_export():
            name = "房间%s_详情_%s.txt" % (room.replace("/", "-"),
                                          datetime.now().strftime("%Y%m%d_%H%M"))
            path = self._write_public(name, "\n".join(lines))
            if path:
                info_popup("导出成功", "「%s」的详情已保存到：\n%s" % (room, path))
            else:
                self.toast("导出失败：没有可写的存储目录")

        info_popup("%s · 房间详情" % room, "\n".join(lines),
                   extra_btn=("导出为 TXT", do_export))

    def open_tenant_form(self, room):
        self.store.load()
        h = self.store.find_house(room)
        if not h:
            self.toast("找不到该房间")
            return
        t = self.store.current_tenant(room)
        base = {"name": "", "tel": "", "in_date": today_str(), "rent_type": "月租", "deposit": ""}
        if t:
            base.update({"name": str(t.get("name", "")), "tel": str(t.get("tel", "")),
                         "in_date": str(t.get("in_date", today_str())),
                         "rent_type": str(t.get("rent_type", "月租")),
                         "deposit": str(t.get("deposit", ""))})

        fields = [
            {"key": "name", "label": "租客姓名", "kind": "text", "value": base["name"],
             "hint": "必填", "half": True},
            {"key": "tel", "label": "联系电话", "kind": "text", "value": base["tel"],
             "hint": "必填", "half": True},
            {"key": "in_date", "label": "入住日期", "kind": "text",
             "value": base["in_date"], "hint": "YYYY-MM-DD", "half": True},
            {"key": "rent_type", "label": "租期类型", "kind": "combo", "values": ["月租", "年租"],
             "value": base["rent_type"], "half": True},
            {"key": "deposit", "label": "押金（元）", "kind": "text", "value": base["deposit"],
             "hint": "只填数字", "half": True},
        ]

        def submit(v):
            name, tel = v.get("name", ""), v.get("tel", "")
            ind, dep = v.get("in_date", ""), v.get("deposit", "")
            rt = v.get("rent_type", "月租")
            if not name or not tel or not ind or not dep:
                self.toast("请把信息填写完整")
                return False
            if not is_number(dep):
                self.toast("押金必须是数字")
                return False
            try:
                datetime.strptime(ind, "%Y-%m-%d")
            except Exception:
                self.toast("入住日期格式应为 YYYY-MM-DD")
                return False
            out = calc_end_date(ind, rt)
            self.store.load()
            cur = self.store.current_tenant(room)
            if cur:
                cur.update({"name": name, "tel": tel, "in_date": ind, "out_date": out,
                            "rent_type": rt, "deposit": dep})
            else:
                for old in self.store.tenants_of(room):
                    if not old.get("is_leave", False):
                        old["is_leave"] = True
                        old["leave_date"] = today_str()
                self.store.data["tenants"].append({
                    "name": name, "tel": tel, "room": room, "in_date": ind, "out_date": out,
                    "rent_type": rt, "deposit": dep,
                    "month_advance": self.store.settings.get("month_advance", 1),
                    "year_advance": self.store.settings.get("year_advance", 7),
                    "is_leave": False})
            hh = self.store.find_house(room)
            if hh:
                hh["status"] = "已租"
            self.store.save()
            self.refresh_houses()
            self.toast("保存成功\n到期日期：%s" % out)
            return True

        FormDialog("租客登记 - %s" % room, fields, submit).open()

    def require_tenant(self, room, action="缴费"):
        """取该房当前在租的租客。

        空闲房（或状态是「已租」但没登记过租客）——不能收费/记水电，
        因为没租客就没法把这笔账挂到谁头上。这里统一拦下来并引导去登记。
        返回租客 dict；没有则返回 None。
        """
        self.store.load()
        t = self.store.current_tenant(room)
        if t:
            return t
        box = {}

        def go_regist():
            if box.get("p"):
                box["p"].dismiss()
            self.open_tenant_form(room)

        box["p"] = info_popup(
            "请添加租客",
            "「%s」现在没有在租的租客，无法%s。\n\n"
            "请先在「租客登记」里把租客姓名、电话、\n"
            "入住日期、押金登记好，之后就能%s了。" % (room, action, action),
            btn="知道了", extra_btn=("去登记租客", go_regist))
        return None

    def open_pay_form(self, room):
        self.store.load()
        # ★ 空闲房不允许收租：没有租客就先引导去登记，不再直接进表单
        t = self.require_tenant(room, "收租")
        if not t:
            return
        h = self.store.find_house(room)
        suggest = str(h.get("price", "")) if h else ""
        # 本月已收过就在标题上先预警，别等提交才说
        this_month = datetime.now().strftime("%Y-%m")
        paid_this_month = [p for p in self.store.pays_of(room)
                           if str(p.get("date", ""))[:7] == this_month]
        who = "%s  %s" % (t.get("name", ""), t.get("tel", ""))
        fields = [
            {"key": "who", "label": "租客（自动带入）", "kind": "text",
             "value": who.strip(), "readonly": True},
            {"key": "money", "label": "缴费金额", "kind": "text", "value": suggest,
             "hint": "元", "half": True},
            {"key": "date", "label": "缴费日期", "kind": "text", "value": today_str(),
             "hint": "YYYY-MM-DD", "half": True},
        ]
        title = "房租缴费 - %s (%s)%s" % (
            room, t.get("name", ""), "  ·本月已收" if paid_this_month else "")

        def submit(v):
            money, date = v.get("money", ""), v.get("date", "")
            if not money or not date or not is_number(money):
                self.toast("金额必须是数字，日期不能为空")
                return False
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except Exception:
                self.toast("日期格式应为 YYYY-MM-DD")
                return False

            def do_add():
                self.store.load()
                # 用表单打开那一刻带出来的租客，避免中途又被改成别的人
                cur = self.store.current_tenant(room) or {}
                self.store.data["payments"].append({
                    "room": room,
                    "name": cur.get("name") or t.get("name", "未知"),
                    "tel": cur.get("tel") or t.get("tel", ""),
                    "money": money, "date": date})
                self.store.save()
                self.refresh_houses()
                if dup:
                    self.toast("已补记：%s %s 元\n（该月原来已收 %s 元）"
                               % (date, money, "、".join(str(p.get("money", "")) for p in dup)))
                else:
                    self.toast("收租成功：%s 元" % money)
                dlg.dismiss()

            # 同月重复收租：明确告知上次金额/日期，要确认才入账（防手抖记两笔）
            dup = [p for p in self.store.pays_of(room)
                   if str(p.get("date", ""))[:7] == date[:7]]
            if dup:
                confirm_popup(
                    "重复收租？",
                    "「%s」在 %s 已经记过 %d 笔：\n%s\n\n"
                    "现在还要再记 %s 元（%s）吗？\n"
                    "（如果是补差价 / 分批收，点「仍然记录」；\n  手滑了就点「取消」）"
                    % (room, date[:7], len(dup),
                       "\n".join("· %s  %s元" % (p.get("date", ""), p.get("money", "")) for p in dup),
                       money, date),
                    lambda: do_add(), yes_text="仍然记录")
                return False      # 先不关表单，等用户确认
            do_add()
            return True

        dlg = FormDialog(title, fields, submit)
        dlg.open()

    def open_util_form(self, room):
        self.store.load()
        # ★ 空闲房不能记水电：没有租客就没人对得上这笔账
        t = self.require_tenant(room, "记录水电")
        if not t:
            return
        us = self.store.utils_of(room)
        last = us[-1] if us else {}
        fields = [
            {"key": "who", "label": "租客（自动带入）", "kind": "text",
             "value": ("%s  %s" % (t.get("name", ""), t.get("tel", ""))).strip(),
             "readonly": True},
            {"key": "month", "label": "统计月份", "kind": "text",
             "value": str(last.get("month") or datetime.now().strftime("%Y-%m")),
             "hint": "YYYY-MM"},
            {"key": "elec", "label": "电费", "kind": "text", "value": str(last.get("elec", "")),
             "hint": "元", "half": True},
            {"key": "water", "label": "水费", "kind": "text", "value": str(last.get("water", "")),
             "hint": "元", "half": True},
        ]

        def submit(v):
            month, elec, water = v.get("month", ""), v.get("elec", ""), v.get("water", "")
            if not month or not elec or not water:
                self.toast("请填写完整")
                return False
            if not is_number(elec) or not is_number(water):
                self.toast("电费和水费必须是数字")
                return False
            self.store.load()
            self.store.data["utilities"] = [
                u for u in self.store.data["utilities"]
                if not (str(u.get("room")) == str(room) and str(u.get("month")) == month)]
            self.store.data["utilities"].append(
                {"room": room, "month": month, "elec": elec, "water": water,
                 "name": t.get("name", ""), "tel": t.get("tel", "")})
            self.store.save()
            self.refresh_houses()
            self.toast("水电记录已保存")
            return True

        FormDialog("水电记录 - %s (%s)" % (room, t.get("name", "")), fields, submit).open()

    def do_evict(self, room):
        def yes():
            self.store.load()
            found = False
            for t in self.store.data["tenants"]:
                if str(t.get("room")) == str(room) and not t.get("is_leave", False):
                    t["is_leave"] = True
                    t["leave_date"] = today_str()
                    found = True
            h = self.store.find_house(room)
            if h:
                h["status"] = "空闲"
            self.store.save()
            self.refresh_houses()
            self.toast("已退租" if found else "该房间状态已置为空闲")
        confirm_popup("一键退租", "确定把「%s」退租吗？\n该租客会被标记为已退租，房间变为空闲。" % room,
                      yes, yes_text="确定退租", danger=True)

    def open_delete_choose(self, room):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        lab = Label(text="要删除「%s」的哪些数据？可多选：" % room, size_hint_y=None, height=dp(40),
                    font_size=sp(14), color=C_TEXT)
        box.add_widget(lab)
        opts = [("1. 删除房间信息", "house"), ("2. 删除租客信息", "tenants"),
                ("3. 删除房租缴费记录", "payments"), ("4. 删除水电缴费记录", "utilities")]
        cbs = {}
        for text, key in opts:
            row = BoxLayout(size_hint_y=None, height=dp(42))
            cb = CheckBox(size_hint_x=None, width=dp(44))
            cbs[key] = cb
            row.add_widget(cb)
            row.add_widget(Label(text=text, font_size=sp(14), color=C_TEXT))
            box.add_widget(row)

        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_no = Button(text="取消", font_size=sp(15), background_color=BTN_NEUTRAL_C,
                      color=(1, 1, 1, 1))
        b_yes = Button(text="确认删除", font_size=sp(15), background_color=C_DANGER, color=(1, 1, 1, 1))
        bar.add_widget(b_no)
        bar.add_widget(b_yes)
        box.add_widget(bar)

        p = Popup(title="删除选项", title_size=sp(16), content=box,
                  size_hint=(0.92, None), height=dp(360), auto_dismiss=False)

        def do_delete():
            chosen = [k for k, cb in cbs.items() if cb.active]
            if not chosen:
                self.toast("请至少选择一项")
                return
            p.dismiss()
            self.store.load()

            def yes():
                self.store.load()
                if "house" in chosen:
                    self.store.data["houses"] = [h for h in self.store.data["houses"]
                                                 if str(h.get("room")) != str(room)]
                if "tenants" in chosen:
                    self.store.data["tenants"] = [t for t in self.store.data["tenants"]
                                                  if str(t.get("room")) != str(room)]
                if "payments" in chosen:
                    self.store.data["payments"] = [x for x in self.store.data["payments"]
                                                   if str(x.get("room")) != str(room)]
                if "utilities" in chosen:
                    self.store.data["utilities"] = [x for x in self.store.data["utilities"]
                                                    if str(x.get("room")) != str(room)]
                self.store.save()
                self.refresh_houses()
                self.toast("删除完成")
            confirm_popup("确认删除", "确定删除「%s」选中的 %d 项数据？此操作不可撤销。"
                          % (room, len(chosen)), yes, yes_text="删除", danger=True)

        b_no.bind(on_release=lambda *_: p.dismiss())
        b_yes.bind(on_release=lambda *_: do_delete())
        p.open()

    # ------------------------------------------------------------------ 租客
    def refresh_tenants(self):
        if getattr(self, "sm", None) is None:
            return
        self.store.load()
        rows = []
        live = [t for t in self.store.data["tenants"] if not t.get("is_leave", False)]
        hist = [t for t in self.store.data["tenants"] if t.get("is_leave", False)]
        for t in live + hist:
            room = str(t.get("room", ""))
            h = self.store.find_house(room) or {}
            left = ""
            try:
                d = datetime.strptime(t.get("out_date", ""), "%Y-%m-%d").date()
                n = (d - datetime.now().date()).days
                left = ("已过期 %d 天" % -n) if n < 0 else ("还剩 %d 天" % n)
            except Exception:
                pass
            rows.append({
                "name": str(t.get("name", "")), "room": room,
                "line1": "%s · %s   押金 %s元" % (t.get("in_date", ""), t.get("rent_type", ""),
                                                t.get("deposit", "0")),
                # ★ 拆两行：原来「电话 + 到期 + 还剩」挤一行，手机窄屏会折行溢出
                #   （Label 只有一行高度，第二行文字画到卡片外 → 看起来和别的字重叠）
                "line2": "电话 %s" % t.get("tel", ""),
                "line3": "到期 %s · %s" % (t.get("out_date", ""), left or "未填到期日"),
                "tag": "已退租" if t.get("is_leave", False) else "在租",
                "tag_bg": [0.61, 0.67, 0.65, 1] if t.get("is_leave", False) else list(C_ACCENT),
            })
        scr = self.sm.get_screen("tenants")
        scr.ids.rv.data = rows
        scr.ids.count.text = "在租 %d 人 · 历史 %d 人" % (len(live), len(hist))

    # ------------------------------------------------------------------ 我的
    def refresh_mine(self):
        if getattr(self, "sm", None) is None:
            return
        self.store.load()
        scr = self.sm.get_screen("mine")
        scr.ids.count.text = "登录账号：%s" % (self.login_user or "-")
        # 数据文件路径统一只在「关于」里显示（见 about()）
        scr.ids.info.text = ("%s v%s\n字体：%s" % (
            APP_NAME, VERSION, FONT_PATH or "未找到中文字体"))

    def open_warn_setting(self, tenant=None):
        sett = self.store.settings
        base_m = str(tenant.get("month_advance", sett.get("month_advance", 1))) if tenant \
            else str(sett.get("month_advance", 1))
        base_y = str(tenant.get("year_advance", sett.get("year_advance", 7))) if tenant \
            else str(sett.get("year_advance", 7))

        def submit(v):
            try:
                m, y = int(v.get("m", "")), int(v.get("y", ""))
                if m < 0 or y < 0:
                    raise ValueError
            except Exception:
                self.toast("请输入合法的天数（非负整数）")
                return False
            self.store.load()
            if tenant:
                room, name = tenant.get("room"), tenant.get("name")
                tgt = next((t for t in self.store.data["tenants"]
                            if str(t.get("room")) == str(room) and t.get("name") == name
                            and not t.get("is_leave", False)), None)
                if tgt:
                    tgt["month_advance"], tgt["year_advance"] = m, y
            else:
                self.store.settings["month_advance"] = m
                self.store.settings["year_advance"] = y
            self.store.save()
            self.toast("提醒天数已保存")
            return True

        FormDialog("租客提醒设置" if tenant else "全局到期提醒设置", [
            {"key": "m", "label": "月租提前", "kind": "text", "value": base_m, "hint": "天"},
            {"key": "y", "label": "年租提前", "kind": "text", "value": base_y, "hint": "天"},
        ], submit).open()

    def open_change_pwd(self):
        def submit(v):
            old, new, cfm = v.get("old", ""), v.get("new", ""), v.get("cfm", "")
            if not old or not new or not cfm:
                self.toast("请填写完整")
                return False
            if new != cfm:
                self.toast("两次输入的新密码不一致")
                return False
            if self.store.change_password(self.login_user, old, new):
                self.toast("密码修改成功")
                return True
            self.toast("原密码错误")
            return False

        FormDialog("修改密码", [
            {"key": "old", "label": "当前密码", "kind": "password"},
            {"key": "new", "label": "新密码", "kind": "password"},
            {"key": "cfm", "label": "确认新密码", "kind": "password"},
        ], submit).open()

    # ------------------------------------------------------------------ 备份 / 恢复
    def open_backup_menu(self, *a):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        p = Popup(title="数据备份 / 导入", title_size=sp(16), size_hint=(0.9, 0.72),
                  auto_dismiss=True)
        actions = [
            ("导出备份到手机存储", self.do_backup),
            ("复制全部数据到剪贴板", self.copy_data),
            ("从手机存储导入备份", self.do_restore),
            ("从剪贴板导入数据", self.paste_data),
        ]
        for text, cb in actions:
            b = Button(text=text, size_hint_y=None, height=dp(48), font_size=sp(15),
                       background_color=C_ACCENT if "导入" in text else C_INFO,
                       color=(1, 1, 1, 1))
            b.bind(on_release=lambda inst, f=cb: (p.dismiss(), f()))
            box.add_widget(b)
        lab = Label(text="导出的 JSON 可直接在电脑版「恢复数据」里导入，\n"
                         "电脑版「备份数据」导出的 JSON 也能在这里导入。",
                    font_size=sp(11), color=C_MUTED)
        box.add_widget(lab)
        p.content = box
        p.open()

    def do_backup(self):
        self.store.load()
        name = "包租婆备份_%s.json" % datetime.now().strftime("%Y%m%d_%H%M")
        saved = []
        for d in public_dirs():
            try:
                path = os.path.join(d, name)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.store.payload(), f, ensure_ascii=False, indent=2)
                saved.append(path)
                break
            except Exception:
                continue
        if saved:
            info_popup("导出成功", "备份已保存到：\n%s\n\n"
                                   "用数据线 / 微信「文件传输助手」把这个文件发到电脑，\n"
                                   "在电脑版里点「恢复数据」选中它即可同步。" % saved[0])
        else:
            self.toast("导出失败：没有可写的存储目录")

    def copy_data(self):
        try:
            Clipboard.copy(json.dumps(self.store.payload(), ensure_ascii=False))
            self.toast("已复制到剪贴板，可以粘贴到电脑上保存成 .json 再导入")
        except Exception as e:
            self.toast("复制失败：%s" % e)

    def _scan_json(self):
        found = []
        for d in public_dirs():
            try:
                for fn in sorted(os.listdir(d), reverse=True):
                    if fn.lower().endswith(".json"):
                        p = os.path.join(d, fn)
                        if os.path.isfile(p):
                            found.append(p)
            except Exception:
                continue
        return found[:40]

    def do_restore(self):
        files = self._scan_json()
        if not files:
            self.toast("在手机存储里没找到 .json 备份文件。\n请先把备份文件放到「Download」文件夹。")
            return
        box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8))
        sv = ScrollView(do_scroll_x=False)
        lst = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        lst.bind(minimum_height=lst.setter("height"))
        p = Popup(title="选择要导入的备份文件", title_size=sp(15), content=box,
                  size_hint=(0.94, 0.8), auto_dismiss=True)
        for path in files:
            b = Button(text=os.path.basename(path), size_hint_y=None, height=dp(46),
                       font_size=sp(13), background_color=C_INFO, color=(1, 1, 1, 1))
            b.bind(on_release=lambda inst, pp=path: (p.dismiss(), self._import_file(pp)))
            lst.add_widget(b)
        sv.add_widget(lst)
        box.add_widget(sv)
        p.open()

    def _import_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            self.toast("读取失败：%s" % e)
            return

        def yes():
            self.store.load()
            self.store._absorb(raw)
            self.store.save()

            def done():
                self.refresh_houses()
                self.build_home()
                self.toast("导入完成")
            info_popup("导入完成",
                       "已导入：房屋 %d 套 / 租客 %d 条 / 房租 %d 条 / 水电 %d 条"
                       % (len(self.store.data["houses"]), len(self.store.data["tenants"]),
                          len(self.store.data["payments"]), len(self.store.data["utilities"])),
                       on_close=done)
        confirm_popup("确认导入", "导入会覆盖当前全部数据（建议先导出一次备份）。\n文件：%s\n\n继续？"
                      % os.path.basename(path), yes, yes_text="覆盖导入", danger=True)

    def paste_data(self):
        try:
            txt = Clipboard.paste()
            raw = json.loads(txt)
        except Exception:
            self.toast("剪贴板里没有可用的 JSON 数据")
            return

        def yes():
            self.store.load()
            self.store._absorb(raw)
            self.store.save()
            self.refresh_houses()
            self.build_home()
            self.toast("导入完成")
        confirm_popup("确认导入", "导入会覆盖当前全部数据，继续？", yes, yes_text="覆盖导入", danger=True)

    def clear_data(self):
        def yes():
            self.store.data = json.loads(json.dumps(EMPTY_DATA))
            self.store.save()
            self.refresh_houses()
            self.build_home()
            self.toast("已清空所有房屋/租客/缴费数据")
        confirm_popup("清空数据", "将删除所有房屋、租客、缴费、水电记录（账号和设置保留）。\n"
                                 "此操作不可撤销！", yes, yes_text="确认清空", danger=True)

    def about(self):
        info_popup("关于", "%s\n版本 v%s\n作者 %s\n联系方式 %s\n\n"
                           "· 电脑版与手机版数据格式完全通用，可互相导入导出\n"
                           "· 数据保存在手机应用私有目录，卸载 App 会一并删除\n"
                           "· 建议定期「导出备份」并把文件传到电脑留档\n\n"
                           "【数据文件位置】\n%s"
                           % (APP_NAME, VERSION, AUTHOR, CONTACT, DATA_FILE))

    # ------------------------------------------------------------------ 异常兜底
    def handle_exception(self, inst, exc):
        try:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _diag_report("X 运行期异常（Kivy 捕获）", type(exc).__name__)
            _diag_write(tb)
            _diag_clip("【包租婆崩溃】%s\n\n%s" % (type(exc).__name__, tb[:1500]))
            with open(os.path.join(app_data_dir(), "error.log"), "a", encoding="utf-8") as f:
                f.write("\n=== %s ===\n%s\n" % (now_str(), tb))
        except Exception:
            pass
        return False


# ==============================================================================
# 【诊断引导块 C】崩溃逃生界面：即使主程序起不来，也让错误看得见
# ==============================================================================
def _diag_show_crash(text):
    """用最小代价的 Kivy 界面显示错误（可由用户长按复制 / 截图）"""
    _diag_clip("【包租婆崩溃】\n" + text[-1500:])
    try:
        from kivy.base import runTouchApp
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput
        from kivy.core.text import LabelBase

        try:
            if FONT_PATH:
                LabelBase.register(name="DiagFont", fn_regular=FONT_PATH)
        except Exception:
            pass

        ti = TextInput(text=text[-6000:], readonly=True, font_size=sp(11))
        try:
            if FONT_PATH:
                ti.font_name = "DiagFont"
        except Exception:
            pass
        sv = ScrollView()
        sv.add_widget(ti)
        runTouchApp(sv)
    except Exception as e2:
        _diag_write("崩溃界面也起不来: %r" % (e2,))


if __name__ == "__main__":
    _diag_report("S8 准备启动主程序")
    try:
        BaozupoApp().run()
        _diag_report("S9 主程序正常退出")
    except BaseException as e:
        tb = traceback.format_exc()
        try:
            _diag_write("!!! 启动失败: %s" % tb)
            _diag_report("S9 主程序异常退出", type(e).__name__)
        except Exception:
            pass
        _diag_show_crash(
            "包租婆 %s 启动失败\n\n阶段: %s\n\n%s\n\n日志文件:\n%s\n\n"
            "请把本页截图，或长按复制内容发给开发者。"
            % (DIAG_VERSION, _DIAG_STAGE, tb, "\n".join(_DIAG_FILES) or "（无法写入任何文件）"))
