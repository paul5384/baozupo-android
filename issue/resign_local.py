# -*- coding: utf-8 -*-
"""
给发码器 APK 做一次「干净重签」。

根因（2026-10-05 用户报「没有任何证书，安装失败」）：
    buildozer 出包时已经用过 jarsigner 做了 v1 签名，
    随后 CI 又跑 zipalign —— zipalign 改动条目偏移，v1 摘要随之失效，
    但 META-INF 下那份**损坏的** v1 签名文件（MANIFEST.MF / *.SF / *.RSA）
    还留在包里。接着 apksigner 只补了 v2/v3，不会去修 v1。
    结果：包里同时存在
      - 一份坏的 v1（摘要对不上）
      - 一份好的 v2/v3
    手机文件管理器 / 安装器优先读 META-INF 里的 v1 证书，读到坏的
    就报「没有任何证书」，不再回退到 v2/v3 —— 于是 apksigner verify
    明明 Verifies，真机却死活装不上。

    横向对照坐实了这一点：
      - 早期能正常安装的版本，META-INF 里**只有** app-metadata.properties，
        压根没有 v1 签名文件（纯 v2 签名）
      - 后来装不上的版本，META-INF 里都多了 BAOZUPO.SF / .RSA / MANIFEST.MF
        （即那份坏 v1）

修法：先把 v1 残留彻底删掉，再 zipalign，最后只签 v2+v3 ——
    **不再写 v1**。产出与「早期能装的版本」同构。

    注意：别试图补一份"正确的 v1"。实测 build-tools 34 的 apksigner
    在 minSdk>=24 的 APK 上，即使显式 --v1-signing-enabled true，
    写出来的 SF 也只标 "X-Android-APK-Signed: 2, 3"，v1 恒为 false；
    用 jarsigner 补了真 v1 后，再跑 apksigner 又会把 v1 文件删掉。
    所以「不要 v1」才是这套工具链下唯一干净的状态。

用法：python resign_local.py <输入.apk> <输出.apk>
"""
import os
import shutil
import subprocess
import sys
import zipfile

BT34 = r"C:\Users\L540\WorkBuddy\2026-09-23-18-22-57\callguard\_toolchain\sdk\build-tools\34.0.0"
JAVA17 = r"C:\Users\L540\WorkBuddy\2026-09-23-18-22-57\callguard\_toolchain\jdk\jdk-17.0.2\bin\java.exe"
ZIPALIGN = os.path.join(BT34, "zipalign.exe")
APKSIGNER = os.path.join(BT34, "lib", "apksigner.jar")

KS = r"C:\Users\L540\android-build\baozupo.keystore"
KS_PASS = "pass:baozupo2026"
KEY_PASS = "pass:baozupo2026"
ALIAS = "baozupo"

# 旧 v1 签名的残留，必须清掉；META-INF 下的其它文件（如 gradle 元数据）保留
V1_ARTIFACTS = ("MANIFEST.MF", ".SF", ".RSA", ".DSA", ".EC")


def strip_v1(src, dst):
    """重建 zip，剔除 META-INF 下的 v1 签名文件，其余条目原样保留。"""
    zin = zipfile.ZipFile(src)
    kept, dropped = 0, []
    with zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            name = info.filename
            if name.startswith("META-INF/") and name.endswith(V1_ARTIFACTS):
                dropped.append(name)
                continue
            data = zin.read(name)
            # 关键：沿用原来的压缩方式与对齐标记，别让 zipalign 白做
            out_info = zipfile.ZipInfo(name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.create_system = info.create_system
            zout.writestr(out_info, data)
            kept += 1
    zin.close()
    return kept, dropped


def run(args, note=""):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print("$ %s -> rc=%d" % (note, r.returncode))
    for stream, name in ((r.stdout, "OUT"), (r.stderr, "ERR")):
        t = (stream or "").strip()
        if t:
            for line in t.splitlines()[:30]:
                print("   %s| %s" % (name, line))
    return r


def main():
    if len(sys.argv) < 3:
        print("用法: python resign_local.py <输入.apk> <输出.apk>")
        return 1
    src = os.path.abspath(sys.argv[1])
    dst = os.path.abspath(sys.argv[2])
    tmp_dir = os.path.dirname(dst)
    cleaned = os.path.join(tmp_dir, "_resign_clean.apk")
    aligned = os.path.join(tmp_dir, "_resign_aligned.apk")

    if not os.path.isfile(src):
        print("输入不存在:", src)
        return 1
    for tool in (ZIPALIGN, APKSIGNER, JAVA17, KS):
        if not os.path.isfile(tool):
            print("缺少工具:", tool)
            return 1

    print("=== 1/4 剔除残留的坏 v1 签名 ===")
    kept, dropped = strip_v1(src, cleaned)
    print("   保留条目 %d，删除 %d：%s" % (kept, len(dropped), dropped))
    if not dropped:
        print("   !! 包里本来就没有 v1 残留，签名问题另有原因")

    print()
    print("=== 2/4 zipalign ===")
    r = run([ZIPALIGN, "-p", "-f", "4", cleaned, aligned], "zipalign")
    if r.returncode != 0 or not os.path.isfile(aligned):
        print("!! zipalign 失败")
        return 1

    print()
    print("=== 3/4 apksigner: 只签 v2 + v3（不写 v1）===")
    r = run([JAVA17, "-jar", APKSIGNER, "sign",
             "--ks", KS,
             "--ks-pass", KS_PASS,
             "--key-pass", KEY_PASS,
             "--ks-key-alias", ALIAS,
             "--v1-signing-enabled", "false",
             "--v2-signing-enabled", "true",
             "--v3-signing-enabled", "true",
             "--out", dst, aligned], "apksigner")
    if r.returncode != 0 or not os.path.isfile(dst):
        print("!! apksigner 失败")
        return 1

    print()
    print("=== 4/4 verify ===")
    r = run([JAVA17, "-jar", APKSIGNER, "verify", "-v", "--print-certs", dst],
            "verify")
    print()
    ok = r.returncode == 0

    # 硬断言 1：v2/v3 必须签上
    out = (r.stdout or "")
    if "v2 scheme (APK Signature Scheme v2): true" not in out:
        print("!! v2 未签上，交付件不可用")
        ok = False

    # 硬断言 2：META-INF 里绝不能再有 v1 残留 —— 这正是真机报
    # 「没有任何证书」的元凶，比 verify 的返回值更关键
    z = zipfile.ZipFile(dst)
    left = [n for n in z.namelist()
            if n.startswith("META-INF/") and n.endswith(V1_ARTIFACTS)]
    z.close()
    print("META-INF 残留的 v1 文件:", left or "（无，干净）")
    if left:
        print("!! 仍有 v1 残留，真机大概率还是装不上")
        ok = False

    print("结果:", "OK" if ok else "FAILED")
    print("输出:", dst, os.path.getsize(dst) if os.path.isfile(dst) else "-")

    for f in (cleaned, aligned):
        try:
            os.remove(f)
        except OSError:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
