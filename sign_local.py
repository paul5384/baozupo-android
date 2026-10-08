# -*- coding: utf-8 -*-
"""
本机签名脚本 —— 包租婆出租屋管家 APK 的唯一官方签名入口。

背景（为什么签名不在 CI 做）：
    2026-10-08 用户装机报「缺少证书，安装失败」。根因是签名证书被换过：
      - 早前 keystore 走 actions/cache，仓库缓存总量涨到 ~10.4GB 超过 GitHub
        的 10GB 上限，keystore 那条缓存被 LRU 淘汰 → CI 静默重新生成了一把新密钥
        （证书 7cb3ba6d…）→ 与用户手机上旧版证书（4e5692c6…）不一致 → 覆盖安装冲突。
      - 改用仓库 Secret 恢复也不行：实测本仓库的 workflow 只要出现 secrets 上下文
        （不管写在 run 还是 env 里）就被判 startup_failure，整条流水线起不来。
    结论：私钥永不进云端。CI 只负责编译 + 产出未签名包，签名统一在本机跑本脚本。

本脚本做的事（顺序与发码器 resign_local.py 一致）：
    1) 剔除 META-INF 下残留的坏 v1 签名（MANIFEST.MF / *.SF / *.RSA / .DSA / .EC）。
       这类文件带 "X-Android-APK-Signed: 2, 3"，国产 ROM 的安装器读到就报
       「缺少证书 / 没有任何证书」—— 本项目已踩过两次。
    2) zipalign -p -f 4（16KB 页设备需要 4 字节对齐 zip 条目；.so 的 16KB 段对齐
       由 CI 的链接参数保证，与本步骤无关）。
    3) apksigner 只签 v2 + v3，显式 --v1-signing-enabled false。
    4) 硬断言：证书指纹 == 约定值、v2/v3 都签上、META-INF 无 v1 残留、
       版本号正确、包里没有旧版号残留字符串。任一条不过即 exit 1，不出交付件。

用法：
    python sign_local.py <输入.apk> <输出.apk>
    python sign_local.py in.apk out.apk --expect-version 2.1.6
    python sign_local.py in.apk out.apk --expect-version 2.1.6 --old-version 2.1.5
环境变量（可选，覆盖默认路径）：
    BAOZUPO_BT     build-tools 目录（含 zipalign / lib/apksigner.jar）
    BAOZUPO_JAVA   java 可执行文件
    BAOZUPO_KS     keystore 路径
"""
import os
import subprocess
import sys
import zipfile

# ==== 默认工具链（本机实测可用，2026-10-08 验证）====
BT34 = os.environ.get(
    "BAOZUPO_BT",
    r"C:\Users\L540\WorkBuddy\2026-09-23-18-22-57\callguard\_toolchain\sdk\build-tools\34.0.0")
JAVA = os.environ.get(
    "BAOZUPO_JAVA",
    r"C:\Users\L540\WorkBuddy\2026-09-23-18-22-57\callguard\_toolchain\jdk\jdk-17.0.2\bin\java.exe")
KS = os.environ.get("BAOZUPO_KS", r"C:\Users\L540\android-build\baozupo.keystore")

KS_PASS = "pass:baozupo2026"
KEY_PASS = "pass:baozupo2026"
ALIAS = "baozupo"

# 约定证书指纹（CN=Baozupo App）。对不上说明密钥被换过 → 直接失败。
EXPECT_CERT = "b2cc86ab73225363e7a2dfca1817e339062ad2380532627a30ac7cb05ff8bdfe"

V1_ARTIFACTS = ("MANIFEST.MF", ".SF", ".RSA", ".DSA", ".EC")


def die(msg):
    print("!! " + msg)
    return 1


def run(args, note=""):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print("$ %s -> rc=%d" % (note or args[0], r.returncode))
    for stream, name in ((r.stdout, "OUT"), (r.stderr, "ERR")):
        t = (stream or "").strip()
        if t:
            for line in t.splitlines()[:40]:
                print("   %s| %s" % (name, line))
    return r


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
            out_info = zipfile.ZipInfo(name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.create_system = info.create_system
            zout.writestr(out_info, data)
            kept += 1
    zin.close()
    return kept, dropped


def read_manifest_strings(apk):
    """从二进制 AndroidManifest.xml 里揪出所有 UTF-8 / UTF-16 字符串。

    不依赖 aapt（本机 aapt.exe 偶发缺 DLL），直接扫 string pool 原始字节，
    够用来断言 versionName 与「旧版号残留」。"""
    outs = []
    with zipfile.ZipFile(apk) as z:
        if "AndroidManifest.xml" not in z.namelist():
            return outs
        b = z.read("AndroidManifest.xml")
    # UTF-16LE 字符串（每个 ASCII 字符后跟 \x00）
    i = 0
    cur = []
    while i + 1 < len(b):
        ch, z0 = b[i], b[i + 1]
        if z0 == 0 and 0x20 <= ch < 0x7f:
            cur.append(chr(ch))
            i += 2
            continue
        if len(cur) >= 3:
            outs.append("".join(cur))
        cur = []
        i += 1
    if len(cur) >= 3:
        outs.append("".join(cur))
    # UTF-8 字符串（连续可打印 ASCII 段）
    cur = []
    for byte in b:
        if 0x20 <= byte < 0x7f:
            cur.append(chr(byte))
        else:
            if len(cur) >= 3:
                outs.append("".join(cur))
            cur = []
    if len(cur) >= 3:
        outs.append("".join(cur))
    return outs


def main():
    argv = sys.argv[1:]
    expect_version = None
    old_version = None
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--expect-version":
            i += 1
            expect_version = argv[i] if i < len(argv) else None
        elif a.startswith("--expect-version="):
            expect_version = a.split("=", 1)[1]
        elif a == "--old-version":
            i += 1
            old_version = argv[i] if i < len(argv) else None
        elif a.startswith("--old-version="):
            old_version = a.split("=", 1)[1]
        else:
            pos.append(a)
        i += 1

    if len(pos) < 2:
        print(__doc__)
        return 2
    src = os.path.abspath(pos[0])
    dst = os.path.abspath(pos[1])

    zipalign = os.path.join(BT34, "zipalign.exe")
    if not os.path.isfile(zipalign):
        zipalign = os.path.join(BT34, "zipalign")
    apksigner = os.path.join(BT34, "lib", "apksigner.jar")

    if not os.path.isfile(src):
        return die("输入不存在: " + src)
    for tool in (zipalign, apksigner, JAVA, KS):
        if not os.path.isfile(tool):
            return die("缺少工具: " + tool)

    tmp_dir = os.path.dirname(dst) or "."
    cleaned = os.path.join(tmp_dir, "_sign_clean.apk")
    aligned = os.path.join(tmp_dir, "_sign_aligned.apk")

    print("=== 1/5 剔除残留的坏 v1 签名 ===")
    kept, dropped = strip_v1(src, cleaned)
    print("   保留条目 %d，删除 %d：%s" % (kept, len(dropped), dropped or "（无）"))

    print("\n=== 2/5 zipalign ===")
    r = run([zipalign, "-p", "-f", "4", cleaned, aligned], "zipalign")
    if r.returncode != 0 or not os.path.isfile(aligned):
        return die("zipalign 失败")

    print("\n=== 3/5 apksigner: 只签 v2 + v3（不写 v1）===")
    r = run([JAVA, "-jar", apksigner, "sign",
             "--ks", KS, "--ks-pass", KS_PASS, "--key-pass", KEY_PASS,
             "--ks-key-alias", ALIAS,
             "--v1-signing-enabled", "false",
             "--v2-signing-enabled", "true",
             "--v3-signing-enabled", "true",
             "--out", dst, aligned], "apksigner sign")
    if r.returncode != 0 or not os.path.isfile(dst):
        return die("apksigner 失败")

    print("\n=== 4/5 verify ===")
    r = run([JAVA, "-jar", apksigner, "verify", "-v", "--print-certs", dst], "verify")
    out = r.stdout or ""
    fails = []

    if r.returncode != 0:
        fails.append("apksigner verify 返回非 0")
    if "v2 scheme (APK Signature Scheme v2): true" not in out:
        fails.append("v2 未签上")
    if "v3 scheme (APK Signature Scheme v3): true" not in out:
        fails.append("v3 未签上")
    if EXPECT_CERT not in out.replace(":", "").lower():
        fails.append("证书指纹不是约定那把（%s…）" % EXPECT_CERT[:16])

    with zipfile.ZipFile(dst) as z:
        left = [n for n in z.namelist()
                if n.startswith("META-INF/") and n.endswith(V1_ARTIFACTS)]
    print("   META-INF 残留的 v1 文件:", left or "（无，干净）")
    if left:
        fails.append("仍有 v1 残留 → 真机可能报「缺少证书」")

    print("\n=== 5/5 内容断言 ===")
    names = read_manifest_strings(dst)
    joined = "\n".join(names)
    if expect_version:
        if expect_version in joined:
            print("   版本号 %s 已确认" % expect_version)
        else:
            fails.append("manifest 里找不到版本号 %s" % expect_version)
    if old_version:
        stale = [s for s in names if old_version in s and s != old_version]
        if old_version in joined:
            fails.append("manifest 里仍有旧版号 %s 残留: %s" % (old_version, stale[:5]))
        else:
            print("   未见旧版号 %s 残留" % old_version)

    print("\n==== 结果 ====")
    if fails:
        for f in fails:
            print("   FAIL:", f)
        print("交付件未通过断言，已保留输出供排查:", dst)
        for f in (cleaned, aligned):
            try:
                os.remove(f)
            except OSError:
                pass
        return 1

    print("   OK  证书指纹 =", EXPECT_CERT)
    print("   输出:", dst, os.path.getsize(dst), "bytes")
    for f in (cleaned, aligned):
        try:
            os.remove(f)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
