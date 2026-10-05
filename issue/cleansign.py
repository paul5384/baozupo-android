#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI 里的「干净签名」：剔除坏 v1 残留 → zipalign → 只签 v2+v3。

为什么必须这么绕（2026-10-05 真机报「没有任何证书，安装失败」）：
    buildozer 出包时已经用 jarsigner 做过 v1 签名，
    随后我们跑 zipalign —— zipalign 改动条目偏移，v1 摘要随之失效，
    但 META-INF 下那份**损坏的** v1 文件（MANIFEST.MF / *.SF / *.RSA）
    还留在包里。apksigner 只补 v2/v3，不会去修它。
    手机文件管理器优先读 META-INF 的 v1 证书，读到坏的就说
    「没有任何证书」，不再回退到 v2/v3 —— apksigner verify 明明
    Verifies，真机却装不上。

    横向对照坐实：早期能装的版本，META-INF 里压根没有 v1 签名文件；
    后来装不上的版本全都带着那三份残留。

也别试图补一份「正确的 v1」：实测 build-tools 34 的 apksigner 在
minSdk>=24 的 APK 上，即便显式 --v1-signing-enabled true，写出的 SF
也只标 "X-Android-APK-Signed: 2, 3"，v1 恒为 false；先用 jarsigner
补真 v1 再跑 apksigner，apksigner 又会把 v1 文件删掉。所以这套工具链下
「不要 v1」才是唯一干净的状态。

用法：
    python3 cleansign.py <输入.apk> <输出.apk> <build-tools目录> <keystore> \
                         <storepass> <keypass> <alias>
"""
import os
import subprocess
import sys
import zipfile

# 旧 v1 签名的残留；META-INF 下的其它文件（gradle 元数据等）保留
V1_ARTIFACTS = ("MANIFEST.MF", ".SF", ".RSA", ".DSA", ".EC")


def strip_v1(src, dst):
    zin = zipfile.ZipFile(src)
    kept, dropped = 0, []
    with zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            name = info.filename
            if name.startswith("META-INF/") and name.endswith(V1_ARTIFACTS):
                dropped.append(name)
                continue
            out_info = zipfile.ZipInfo(name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.create_system = info.create_system
            zout.writestr(out_info, zin.read(name))
            kept += 1
    zin.close()
    return kept, dropped


def main():
    if len(sys.argv) < 8:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    bt, ks = sys.argv[3], sys.argv[4]
    storepass, keypass, alias = sys.argv[5], sys.argv[6], sys.argv[7]

    base = os.path.dirname(os.path.abspath(dst))
    cleaned = os.path.join(base, "_cs_clean.apk")
    aligned = os.path.join(base, "_cs_aligned.apk")

    zipalign = os.path.join(bt, "zipalign")
    apksigner = os.path.join(bt, "apksigner")
    if not os.path.isfile(zipalign):
        print("!! 找不到 zipalign:", zipalign)
        return 1

    print("=== 1/3 剔除坏 v1 残留 ===")
    kept, dropped = strip_v1(src, cleaned)
    print("   保留 %d 条目，删除 %d：%s" % (kept, len(dropped), dropped))
    if not dropped:
        print("   （本就没有 v1 残留，仍继续走对齐+签名）")

    print("=== 2/3 zipalign ===")
    r = subprocess.run([zipalign, "-p", "-f", "4", cleaned, aligned])
    if r.returncode != 0:
        print("!! zipalign 失败")
        return 1

    print("=== 3/3 apksigner: 只签 v2+v3 ===")
    if os.path.isfile(apksigner):
        cmd = [apksigner]
    else:
        # 某些镜像只有 jar，没有启动脚本
        cmd = ["java", "-cp", os.path.join(bt, "lib", "apksigner.jar"),
               "com.android.apksigner.ApkSignerTool"]
    r = subprocess.run(cmd + ["sign",
                              "--ks", ks,
                              "--ks-pass", "pass:" + storepass,
                              "--key-pass", "pass:" + keypass,
                              "--ks-key-alias", alias,
                              "--v1-signing-enabled", "false",
                              "--v2-signing-enabled", "true",
                              "--v3-signing-enabled", "true",
                              "--out", dst, aligned])
    if r.returncode != 0 or not os.path.isfile(dst):
        print("!! apksigner 失败")
        return 1

    # 硬断言：META-INF 里绝不能留下 v1 文件，否则真机还是报「没有证书」
    z = zipfile.ZipFile(dst)
    left = [n for n in z.namelist()
            if n.startswith("META-INF/") and n.endswith(V1_ARTIFACTS)]
    z.close()
    print("META-INF 残留 v1 文件:", left or "（无，干净）")
    if left:
        print("!! 仍有 v1 残留，这个包真机装不上")
        return 1

    for f in (cleaned, aligned):
        try:
            os.remove(f)
        except OSError:
            pass
    print("OK ->", dst, os.path.getsize(dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
