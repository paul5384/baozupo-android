#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键推 GitHub 并云端构建 APK。
用法:  GITHUB_TOKEN=ghp_xxx python push_and_build.py
- 从环境变量读 token，不写进任何文件
- 建公开仓库 -> push master -> 触发 build-apk.yml -> 等构建 -> 下载 APK 到本地
"""
import os, sys, json, time, subprocess, urllib.request, urllib.error, zipfile, io

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    # 备选：从本地 token 文件读（避免 token 出现在命令行）
    _f = r"C:\Users\L540\android-build\.ghtoken"
    if os.path.exists(_f):
        TOKEN = open(_f, encoding="utf-8").read().strip()
if not TOKEN:
    print("ERROR: 请先设置环境变量 GITHUB_TOKEN"); sys.exit(1)

API = "https://api.github.com"
REPO_NAME = "baozupo-android"
PRIVATE = False
BRANCH = "master"
APP_DIR = r"C:\Users\L540\Desktop\python\包租婆\手机App版"
OUT_APK_DIR = r"C:\Users\L540\Desktop\python\包租婆"

def api(method, path, data=None):
    url = API + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "baozupo-push")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def clean(s):
    """输出脱敏：任何打印里都不出现 token"""
    return s.replace(TOKEN, "***TOKEN***") if s else s

def git(*a):
    r = subprocess.run(["git"] + list(a), capture_output=True, text=True, cwd=APP_DIR)
    print("$ git", " ".join(a), "->", r.returncode)
    if r.stdout.strip(): print(clean(r.stdout.strip()))
    if r.stderr.strip(): print("[e]", clean(r.stderr.strip()))
    return r

# 1) 当前登录身份
st, txt = api("GET", "/user")
if st != 200:
    print("AUTH FAILED:", st, txt); sys.exit(1)
me = json.loads(txt)["login"]
print(">>> 已登录 GitHub 账号:", me)

# 2) 建仓库（已存在则忽略）
st, txt = api("POST", "/user/repos", {
    "name": REPO_NAME, "private": PRIVATE, "auto_init": False,
    "description": "包租婆出租屋管家 安卓原生版 (Kivy)"
})
if st in (201, 200):
    print(">>> 仓库已创建:", REPO_NAME)
elif st == 422:
    print(">>> 仓库已存在，继续")
else:
    print("CREATE REPO FAILED:", st, txt); sys.exit(1)

remote_url = f"https://{TOKEN}@github.com/{me}/{REPO_NAME}.git"
os.chdir(APP_DIR)
git("remote", "remove", "origin")
git("remote", "add", "origin", remote_url)
p = git("push", "-u", "origin", BRANCH)
if p.returncode != 0:
    print("PUSH FAILED"); sys.exit(1)
# 推送后立刻把 token 从 remote 里抹掉
git("remote", "set-url", "origin", f"https://github.com/{me}/{REPO_NAME}.git")
print(">>> 代码已推送，remote 中的 token 已清除")

# 3) 触发 Actions
st, txt = api("POST", f"/repos/{me}/{REPO_NAME}/actions/workflows/build-apk.yml/dispatches", {"ref": BRANCH})
if st not in (204, 200):
    print("DISPATCH FAILED:", st, txt); sys.exit(1)
print(">>> 已触发构建，等待 run 出现...")

# 4) 找到本次 run
run_id = None
for _ in range(30):
    time.sleep(10)
    st, txt = api("GET", f"/repos/{me}/{REPO_NAME}/actions/runs?head_branch={BRANCH}&per_page=5")
    if st == 200:
        runs = json.loads(txt).get("workflow_runs", [])
        if runs:
            run_id = runs[0]["id"]
            print(f">>> run {run_id} status={runs[0]['status']} conclusion={runs[0]['conclusion']}")
            if runs[0]["status"] == "completed":
                break
if not run_id:
    print("未找到 run，请手动到 Actions 查看"); sys.exit(0)

# 5) 等构建完成（APK 构建通常 15~25 分钟）
print(">>> 构建进行中（约 15~25 分钟），开始轮询...")
for _ in range(40):
    time.sleep(45)
    st, txt = api("GET", f"/repos/{me}/{REPO_NAME}/actions/runs/{run_id}")
    if st == 200:
        run = json.loads(txt)
        print(f">>> status={run['status']} conclusion={run['conclusion']}")
        if run["status"] == "completed":
            break
if run.get("conclusion") != "success":
    print(">>> 构建未成功:", run.get("conclusion"))
    print(f">>> 日志: https://github.com/{me}/{REPO_NAME}/actions/runs/{run_id}")
    sys.exit(1)

# 6) 下载 artifact 并解压出 APK
st, txt = api("GET", f"/repos/{me}/{REPO_NAME}/actions/runs/{run_id}/artifacts")
arts = json.loads(txt).get("artifacts", [])
if not arts:
    print(">>> 无 artifact"); sys.exit(1)
art = arts[0]
print(f">>> artifact: {art['name']} (id={art['id']})")

req = urllib.request.Request(f"{API}/repos/{me}/{REPO_NAME}/actions/artifacts/{art['id']}/zip")
req.add_header("Authorization", f"Bearer {TOKEN}")
req.add_header("Accept", "application/vnd.github+json")
req.add_header("User-Agent", "baozupo-push")
with urllib.request.urlopen(req, timeout=120) as r:
    zdata = r.read()
print(f">>> artifact 下载完成: {len(zdata)} bytes")

os.makedirs(OUT_APK_DIR, exist_ok=True)
apks = []
with zipfile.ZipFile(io.BytesIO(zdata)) as z:
    for name in z.namelist():
        if name.lower().endswith(".apk"):
            dest = os.path.join(OUT_APK_DIR, os.path.basename(name))
            with open(dest, "wb") as f:
                f.write(z.read(name))
            apks.append(dest)
            print(">>> 已解出 APK:", dest)

if apks:
    print("\n=== DONE ===")
    for a in apks:
        print("APK:", a)
    print(f"仓库: https://github.com/{me}/{REPO_NAME}")
else:
    print(">>> 压缩包内未找到 .apk，请到仓库 Actions 页面手动下载 artifact")
    print(f">>> https://github.com/{me}/{REPO_NAME}/actions/runs/{run_id}")
