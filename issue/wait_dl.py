#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
等指定 run 跑完，再下载 artifact，最后做「v1 残留」硬断言。

之所以要这个脚本：CI 一次构建 15~25 分钟，人工盯不划算；而产物是否真的
可安装，光看 run 绿不绿没用 —— 必须拆包确认 META-INF 里没有 v1 残留。

用法：python wait_dl.py <run_id> <输出.apk>
"""
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

TOKEN = io.open(r"C:\Users\L540\android-build\.ghtoken", encoding="utf-8").read().strip()
REPO = "paul5384/baozupo-android"
GHCIs = r"C:\Users\L540\.workbuddy\skills\kivy-apk-github-actions\scripts\ghci.py"
PY = r"C:\Users\L540\.workbuddy\binaries\python\versions\3.13.12\python.exe"
V1 = ("MANIFEST.MF", ".SF", ".RSA", ".DSA", ".EC")


def api(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://api.github.com" + path,
                                 data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "wait-dl")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=90)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    raw = r.read()
    return r.status, (json.loads(raw) if raw else None)


def steps_of(run_id):
    """看 step 名字 —— 判断跑的是不是新版 workflow 的最快办法"""
    st, j = api("/repos/%s/actions/runs/%s/jobs?per_page=5" % (REPO, run_id))
    if st != 200:
        return []
    names = []
    for job in j.get("jobs", []):
        for s in job.get("steps", []):
            names.append(s.get("name"))
    return names


def main():
    run_id = sys.argv[1]
    out = sys.argv[2]
    print(">>> 等待 run", run_id)
    last = None
    for _ in range(120):
        st, d = api("/repos/%s/actions/runs/%s" % (REPO, run_id))
        if st != 200:
            print("查询失败", st, str(d)[:200]); return 1
        status = d.get("status")
        concl = d.get("conclusion")
        if status == "completed":
            print(">>> 完成:", concl)
            if concl != "success":
                print("!! 构建失败，去看日志")
                return 1
            break
        if status != last:
            print("   status=%s" % status)
            last = status
        time.sleep(20)
    else:
        print("!! 超时")
        return 1

    # 关键校验：跑的必须带「干净签名」这个 step 名，否则说明还是旧 workflow
    names = steps_of(run_id)
    print(">>> steps:", [n for n in names if "签名" in n or "打包" in n])
    if not any("干净签名" in n for n in names):
        print("!! step 名里没有「干净签名」—— 跑的还是旧 workflow，产物不可用")
        return 1
    print(">>> 确认跑的是新 workflow")

    tmp = out + ".zip"
    env = dict(os.environ)
    env["GH_REPO"] = "paul5384/baozupo-android"
    env["GH_BRANCH"] = "issue-apk"
    env["GH_TOKEN_FILE"] = r"C:\Users\L540\android-build\.ghtoken"
    r = subprocess.run([PY, GHCIs, "download", run_id, "bzq-issue-apk", tmp],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    print(r.stdout[-1500:])
    if not os.path.isfile(tmp):
        print("!! 下载失败"); print(r.stderr[-800:]); return 1
    print(">>> 已下载", os.path.getsize(tmp), "bytes")

    z = zipfile.ZipFile(tmp)
    apk_name = None
    for n in z.namelist():
        if n.endswith(".apk"):
            apk_name = n
            break
    if not apk_name:
        print("!! zip 里没有 apk:", z.namelist()[:10]); return 1
    with open(out, "wb") as f:
        f.write(z.read(apk_name))
    z.close()
    os.remove(tmp)
    print(">>> APK:", out, os.path.getsize(out))

    # 硬断言：v1 残留必须为空
    z = zipfile.ZipFile(out)
    mi = [n for n in z.namelist() if n.startswith("META-INF/")]
    left = [n for n in mi if n.endswith(V1)]
    z.close()
    print(">>> META-INF:", mi)
    print(">>> v1 残留:", left or "（无，干净）")
    if left:
        print("!! 仍有 v1 残留，真机装不上")
        return 1
    print("=== OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
