[app]
# ==============================================================================
# 包租婆出租屋管家 · 安卓打包配置（buildozer.spec）
# 打包命令： buildozer -v android debug
# 出来的 APK 在  bin/  目录下，文件名类似 baozupo-2.1.0-arm64-v8a_armeabi-v7a-debug.apk
# 详细步骤见同目录《打包APK说明.md》
# ==============================================================================

title = 包租婆出租屋管家
package.name = baozupo
package.domain = org.baozupo

source.dir = .
# 必须带 ttf，否则中文字体不会被打进 APK；kv 是界面文件，json 是备份文件
source.include_exts = py,kv,png,jpg,jpeg,ttf,json,atlas,ico
source.include_patterns = fonts/*,assets/*

version = 2.1.0

# kivy 是必须的；不加多余依赖，打包最不容易失败
requirements = python3,kivy

orientation = portrait
fullscreen = 0

# 图标和启动闪屏
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
presplash.color = #2F4F4F

# ------------------------------------------------------------------ 安卓参数
# 这里故意把 targetSdk 定在 29：
#   配合 READ/WRITE_EXTERNAL_STORAGE 权限，APK 才能直接读写手机里的
#   /sdcard/Download 目录，从而「导出备份 → 传到电脑 → 电脑版导入」。
#   如果你要上架 Google Play，需要把 android.api 提到 34 并改用应用私有目录。
android.api = 34
android.minapi = 24
android.accept_license = yes
android.ndk = 25b

# 使用本机已下载好的 SDK / NDK / JDK，避免 buildozer 联网重复下载
android.sdk_path = C:/Users/L540/android-build/android-sdk
android.ndk_path = C:/Users/L540/android-build/android-ndk/android-ndk-r25b
java.home = C:/Users/L540/android-build/jdk
# 同时出 64 位和 32 位，兼容新老手机（只想要 64 位可以删掉 armeabi-v7a，包会小一半）
android.archs = arm64-v8a
# 本地 recipe 覆盖：recipes/kivy/__init__.py 去掉了 python_depends，
# 避免 p4a 给 APK 强塞 requests/charset-normalizer 等（2026-09 其 android wheel
# 会触发 pip "not a supported wheel on this platform" 构建失败）
p4a.local_recipes = ./recipes
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, INTERNET

android.allow_backup = True
android.accept_sdk_license = True
android.wakelock = False
android.logcat_filters = *:S python:D

# 让 buildozer 自动把权限弹出框处理掉，省得卡住
android.private_storage = True

# 中文应用名在部分桌面（如 MIUI）上更稳
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
