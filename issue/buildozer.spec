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
source.include_patterns = fonts/*,assets/*

version = 1.0

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
android.allow_backup = False
android.accept_sdk_license = True
android.wakelock = False
android.logcat_filters = *:S python:D
android.private_storage = True
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
