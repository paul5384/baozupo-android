#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把发码器推到 baozupo-android 的 issue-apk 分支，云端构建并下载 APK。

用法:  python push_issue_and_build.py

仓库布局（分支 issue-apk）:
    /fonts/simhei.ttf     <- 与主 App 共用，CI 里 cp 到 issue/fonts/
    /issue/...            <- 本工程的全部源码
token 来自 C:\\Users\\L540\\android-build\\.ghtoken，不写进任何文件、不进日志。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile

TOKEN_FILE = r"C:\Users\L540\android-build\.ghtoken"
TOKEN = os.environ.get("GITHUB_TOKEN") or ""
if not TOKEN and os.path.isfile(TOKEN_FILE):
    TOKEN = io.open(TOKEN_FILE, encoding="utf-8").read().strip()
if not TOKEN:
    print("ERROR: 找不到 GitHub token"); sys.exit(1)

API = "https://api.github.com"
REPO = "baozupo-android"
BRANCH = "issue-apk"
WORKFLOW = "build-issue-apk.yml"
SRC = r"C:\Users\L540\Desktop\python\包租婆\发码器"
TMP = r"C:\Users\L540\Desktop\python\包租婆\_issue_push"
OUT_DIR = r"C:\Users\L540\Desktop\python\包租婆"

IGNORE_DIRS = {".git", "__pycache__", ".buildozer", "bin", ".signing",
               "_kivy_src", "_localdata", "_exp"}
# 这个仓库是 public：任何下划线开头的本机调试产物一律不推。
# 之前只排除了 _test_/_repro_/_depcheck/_probe_，结果 _allverify.txt、
# _sigchk.txt 之类带着本机路径和证书指纹的日志全被推上了公开仓库。
IGNORE_PREFIX = ("_",)
IGNORE_FILE = {"bzq_probe.txt", "bzq_diag.txt", "build.log", "prespec.py"}
IGNORE_SUFFIX = (".log", ".txt")


def clean(s):
    return s.replace(TOKEN, "***TOKEN***") if s else s


def api(method, path, data=None, raw=False):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "bzq-issue-push")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, (r.read() if raw else r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def git(*a, cwd=TMP, retry=3):
    """跑一条 git。

    两个踩过的坑：
      1) 命令参数里含 token（remote add），打印前必须过 clean()，否则 token 落盘
      2) 本机 git 走 SSL 会偶发 unexpected eof，重试通常就好
    """
    last = None
    for attempt in range(retry):
        r = subprocess.run(["git"] + list(a), capture_output=True, text=True,
                           cwd=cwd)
        last = r
        if r.returncode == 0:
            break
        time.sleep(3)
    safe_args = clean(" ".join(a))
    r = last
    out = clean((r.stdout or "") + (r.stderr or "")).strip()
    print("$ git %s -> %d" % (safe_args, r.returncode))
    if out:
        print("   " + out.replace("\n", "\n   ")[:1500])
    return r


def build_pairs():
    """列出要推的文件：远端路径 -> 本地路径。

    走 REST tree API（不是 git）：本机有强制代理，git 的 CONNECT 会被拒
    （"CONNECT tunnel failed, response 502"），而 urllib 能正常穿过去。
    所以复用 awesome skill 里的 scripts/ghci.py 做原子提交。
    """
    pairs = []
    for root, dirs, files in os.walk(SRC):
        rel = os.path.relpath(root, SRC)
        if rel == ".":
            rel = ""
        parts = rel.split(os.sep) if rel else []
        if any(p in IGNORE_DIRS for p in parts):
            continue
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f in IGNORE_FILE or f.startswith(IGNORE_PREFIX) \
                    or f.endswith(IGNORE_SUFFIX):
                continue
            local = os.path.join(root, f)
            remote = "/".join(["issue"] + parts + [f])
            pairs.append((remote, local))
    # 9.7MB 的 simhei.ttf 不重推：CI 会从仓库根 ../fonts/simhei.ttf 拷过来
    pairs = [p for p in pairs if not p[0].startswith("issue/fonts/")]
    return pairs


def push_via_api(pairs):
    sys.path.insert(0, r"C:\Users\L540\.workbuddy\skills\kivy-apk-github-actions\scripts")
    os.environ["GH_REPO"] = "%s/%s" % (ME, REPO)
    os.environ["GH_BRANCH"] = BRANCH
    os.environ["GH_TOKEN_FILE"] = TOKEN_FILE
    os.environ["COMMIT_MSG"] = "v1.2 修复 filetype 缺失导致的启动闪退"
    import ghci
    return ghci.cmd_push(pairs)


def main():
    st, txt = api("GET", "/user")
    if st != 200:
        print("AUTH FAILED", st, txt[:300]); sys.exit(1)
    me = json.loads(txt)["login"]
    print(">>> GitHub 账号:", me)
    globals()["ME"] = me

    pairs = build_pairs()
    print(">>> 待推送 %d 个文件（已排除 fonts/ 与本地调试产物）" % len(pairs))
    # 硬断言：filetype 必须带着，否则真机必闪退
    ft = [p for p in pairs if p[0].startswith("issue/filetype/")]
    print(">>> 其中 filetype 文件 %d 个" % len(ft))
    assert ft, "filetype 一个都没进列表！真机会立刻闪退"
    assert any(p[0] == "issue/main.py" for p in pairs), "main.py 丢了"

    rc = push_via_api(pairs)
    if rc != 0:
        print("!!! PUSH FAILED"); sys.exit(1)
    print(">>> 推送完成（REST tree 原子提交）")

    st, txt = api("POST",
                  "/repos/%s/%s/actions/workflows/%s/dispatches" % (me, REPO, WORKFLOW),
                  {"ref": BRANCH})
    if st not in (204, 200):
        print("DISPATCH FAILED", st, txt[:300]); sys.exit(1)
    print(">>> 已触发构建")

    run_id = None
    for _ in range(30):
        time.sleep(8)
        st, txt = api("GET", "/repos/%s/%s/actions/runs?head_branch=%s"
                      "&per_page=3" % (me, REPO, BRANCH))
        if st == 200:
            runs = json.loads(txt).get("workflow_runs", [])
            if runs:
                run_id = runs[0]["id"]
                print(">>> run %s status=%s" % (run_id, runs[0]["status"]))
                break
    if not run_id:
        print("未找到 run"); sys.exit(1)

    print(">>> 等待构建（约 15~25 分钟）...")
    for _ in range(60):
        time.sleep(45)
        st, txt = api("GET", "/repos/%s/%s/actions/runs/%s" % (me, REPO, run_id))
        if st == 200:
            run = json.loads(txt)
            print(">>> status=%s conclusion=%s" % (run["status"], run["conclusion"]))
            if run["status"] == "completed":
                break
    if run.get("conclusion") != "success":
        print("!!! 构建失败: %s" % run.get("conclusion"))
        print("日志: https://github.com/%s/%s/actions/runs/%s" % (me, REPO, run_id))
        # 顺手把 build.log 拉下来看看最后几行
        st, txt = api("GET", "/repos/%s/%s/actions/runs/%s/artifacts"
                      % (me, REPO, run_id))
        arts = json.loads(txt).get("artifacts", []) if st == 200 else []
        for a in arts:
            if "buildlog" in a["name"]:
                st2, blob = api("GET", "/repos/%s/%s/actions/artifacts/%d/zip"
                                % (me, REPO, a["id"]), raw=True)
                if st2 == 200:
                    try:
                        with zipfile.ZipFile(io.BytesIO(blob)) as z:
                            nm = [x for x in z.namelist() if x.endswith("build.log")]
                            if nm:
                                log = z.read(nm[0]).decode("utf-8", "replace")
                                log = re.sub(r"\x1b\[[0-9;]*m", "", log)
                                tail = [x for x in log.splitlines() if x.strip()][-25:]
                                print("--- build.log 末尾 ---")
                                for l in tail:
                                    print("   ", l[:160])
                    except Exception as e:
                        print("读 build.log 失败:", e)
        sys.exit(1)

    st, txt = api("GET", "/repos/%s/%s/actions/runs/%s/artifacts"
                  % (me, REPO, run_id))
    arts = [a for a in json.loads(txt).get("artifacts", [])
            if "buildlog" not in a["name"]]
    if not arts:
        print("无 artifact"); sys.exit(1)
    art = arts[0]
    print(">>> artifact:", art["name"])
    st, blob = api("GET", "/repos/%s/%s/actions/artifacts/%d/zip"
                   % (me, REPO, art["id"]), raw=True)
    if st != 200:
        # 401 通常不是权限问题：artifact 下载 URL 会 302 到带签名的 CDN 地址，
        # urllib 自动重定向时会把 Authorization 头一起带过去，签发方直接 401。
        # 必须自己拦下 Location，然后**不带 auth** 去取真实内容。
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        for attempt in range(4):
            try:
                real = None
                loc = API + "/repos/%s/%s/actions/artifacts/%d/zip" % (
                    me, REPO, art["id"])
                req = urllib.request.Request(loc)
                req.add_header("Authorization", "Bearer " + TOKEN)
                req.add_header("Accept", "application/vnd.github+json")
                req.add_header("User-Agent", "bzq-issue-push")
                opener = urllib.request.build_opener(_NoRedirect)
                try:
                    opener.open(req)
                except urllib.error.HTTPError as e:
                    real = e.headers.get("Location")
                if not real:
                    raise RuntimeError("拿不到重定向地址")
                with urllib.request.urlopen(real, timeout=180) as r:
                    blob = r.read()
                print(">>> artifact 已下载（走签名 URL，未带 auth）: %d bytes"
                      % len(blob))
                break
            except Exception as e:
                print("   下载重试 %d: %r" % (attempt + 1, repr(e)[:120]))
                time.sleep(5)
        else:
            print("!!! 下载 artifact 失败"); sys.exit(1)
    apks = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.lower().endswith(".apk"):
                dest = os.path.join(
                    OUT_DIR, "包租婆授权码发码器-v1.2-arm64.apk")
                with open(dest, "wb") as f:
                    f.write(z.read(name))
                apks.append(dest)
                print(">>> 已保存:", dest, os.path.getsize(dest))
    if apks:
        print("\n=== DONE ===")
        for a in apks:
            print("APK:", a)
    else:
        print(">>> 压缩包内无 apk")


if __name__ == "__main__":
    main()
