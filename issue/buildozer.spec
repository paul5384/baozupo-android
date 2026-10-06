[app]

# ==============================================================================
# 包租婆授权码发码器（作者专用）· 安卓打包配置
# ==============================================================================
#  ⚠ 这个 APK 里含有私钥，只能装在作者自己手机上，绝不能发给客户。
#     私钥经 PIN + PBKDF2 加密后落盘，APK 内只有打乱分片，
#     但仍需假定「拿到 APK 的人可能会尝试逆向」。
# ==============================================================================

title = 包租婆发码器
package.name = bzqissue
package.domain = org.baozupo

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,ttf,json,atlas,ico
source.include_patterns = fonts/*,assets/*,filetype/*,filetype/types/*

# 注意这三行的来历（v1.0/v1.1 真机闪退的根因就在这）：
#   kivy 2.3.1 的 kivy/core/image/__init__.py 第 65 行裸写
#   `from filetype import guess_extension`，而本地 kivy recipe 去掉了
#   python_depends，filetype 不会自动进包，APK 里没有它就 ImportError，
#   裸 import 失败直接杀进程 => 界面上一次错误都看不到，只有「闪退」。
#   所以：① filetype 必须随源码打包（上面的 include_patterns）
#        ② main.py 在 import kivy 之前先把它塞进 sys.path
#
# CI 专用的 spec 自检脚本、测试文件、本机调试产物，不必进包
# 注意：这里必须写成一行。试过用反斜杠续行，configparser 会把 '\' 和换行
# 原样塞进值里（'...*.log,\\\nbzq_probe.txt...'），exclude 规则直接失效。
source.exclude_patterns = prespec.py,_depcheck.py,_test_*.py,_probe_test.py,shots/*,*.log,bzq_probe.txt,probe_*.txt,bzq_diag.txt,_kivy_src/*,_*.txt,cleansign.py,resign_local.py

version = 1.4

requirements = hostpython3==3.11.9,python3==3.11.9,kivy

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
presplash.color = #1F1F22

# ------------------------------------------------------------------ 安卓参数
android.api = 34
android.minapi = 24
android.accept_license = yes
android.ndk = 25b

# 用本机已下好的 SDK / NDK / JDK（与主 App 同一套）
android.sdk_path = C:/Users/L540/android-build/android-sdk
android.ndk_path = C:/Users/L540/android-build/android-ndk/android-ndk-r25b
java.home = C:/Users/L540/android-build/jdk
android.archs = arm64-v8a
p4a.local_recipes = ./recipes

# 发码器不读写 sdcard，只要剪贴板权限
android.permissions = INTERNET

# 不允许备份，避免私钥 vault 被系统同步出去
# 写成 0/1 而不是 true/false：buildozer 用 configparser.getboolean() 读它，
# 各版本对字符串布尔的宽容度不同（3.14 就因为 False 直接抛 ValueError），
# 而 0/1 是所有版本都无条件接受的写法。
# 症状极隐蔽：错误发生在「Package the application」之后、APK 产出之前，
# 表现为「bin/ 里没有 APK」，不看完整 traceback 根本找不到根因。
android.allow_backup = 0
android.accept_sdk_license = True
android.wakelock = False
android.logcat_filters = *:S python:D
android.private_storage = True
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
