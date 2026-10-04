"""在 CI 容器里预检 buildozer.spec 的布尔值合法性。

为什么需要：buildozer 用 configparser.getboolean() 读
  fullscreen / android.allow_backup / android.enable_androidx / android.private_storage
  / android.accept_license / android.accept_sdk_license / android.wakelock
  / android.resizable
不同 Python 版本对字符串布尔的宽容度不同（容器里是 3.14，本地是 3.13）。
一旦某个值不合法，错误会发生在「Package the application」之后、APK 产出之前，
症状只是「bin/ 里没有 APK」，不看完整 traceback 根本定位不到是哪个键。

跑法：python3 prespec.py [buildozer.spec]
退出码 1 = 有问题（并打印具体键值）。
"""
import configparser
import sys

BOOL_KEYS = (
    "fullscreen",
    "android.allow_backup",
    "android.enable_androidx",
    "android.private_storage",
    "android.accept_license",
    "android.accept_sdk_license",
    "android.wakelock",
    "android.resizable",
)

path = sys.argv[1] if len(sys.argv) > 1 else "buildozer.spec"
cp = configparser.ConfigParser()
cp.read(path, encoding="utf-8")

print("prespec: python %s, file %s" % (sys.version.split()[0], path))

if not cp.has_section("app"):
    print("::error::buildozer.spec 缺少 [app] 段")
    raise SystemExit(1)

bad = []
checked = 0
for sec in cp.sections():
    for key, raw in cp.items(sec):
        if key not in BOOL_KEYS:
            continue
        checked += 1
        try:
            cp.getboolean(sec, key, fallback=True)
            print("  OK   %s.%s = %r" % (sec, key, raw))
        except ValueError as e:
            bad.append((sec, key, raw, str(e)))
            print("  FAIL %s.%s = %r  -> %s" % (sec, key, raw, e))

# 顺带检查本机路径残留（云端必然失败）
for sec in cp.sections():
    for key, raw in cp.items(sec):
        if "L540" in str(raw) or ":\\" in str(raw) or ":\\" in str(raw):
            bad.append((sec, key, raw, "含本机 Windows 路径，云端不可用"))
            print("  FAIL %s.%s 含本机路径" % (sec, key))

if bad:
    print("")
    print("::error::buildozer.spec 有 %d 个问题：" % len(bad))
    for sec, key, raw, why in bad:
        print("   %s.%s = %r  -> %s" % (sec, key, raw, why))
    raise SystemExit(1)

print("prespec 通过：检查了 %d 个布尔值，无异常" % checked)
