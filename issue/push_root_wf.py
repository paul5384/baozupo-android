#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 workflow 推到**仓库根目录** .github/workflows/。

为什么单独写这个脚本（2026-10-05 踩坑）：
    GitHub Actions 只读取仓库根的 .github/workflows/，子目录下的
    .github/workflows/ **永远不会被识别**。本项目源码都在 issue/ 子目录，
    于是出现了两份 workflow：
        .github/workflows/build-issue-apk.yml        <- 真正生效（旧版）
        issue/.github/workflows/build-issue-apk.yml  <- 我一直在改，从不执行
    症状极具迷惑性：push 成功、CI 绿、APK 也产出了，但改动「看起来没生效」——
    因为跑的压根是另一份文件。判据：看 job 里 step 的**名字**，
    名字还是旧的就说明跑的是旧 workflow。

本脚本同时删掉 issue/.github/ 下那份误导性副本。

用法：python push_root_wf.py [--dispatch]
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN_FILE = r"C:\Users\L540\android-build\.ghtoken"
REPO_OWNER = "paul5384"          # 会被 /user 返回值校正
REPO = "baozupo-android"
BRANCH = "issue-apk"

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_WF = os.path.join(HERE, ".github", "workflows", "build-issue-apk.yml")
REMOTE_WF = ".github/workflows/build-issue-apk.yml"
DEAD_WF = "issue/.github/workflows/build-issue-apk.yml"


class GH(object):
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None, raw=False):
        url = "https://api.github.com" + path
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "push-root-wf")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            r = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        payload = r.read()
        if raw:
            return r.status, payload
        # 204 No Content 是空响应体（dispatches 就是这样），别硬解 JSON
        if not payload:
            return r.status, None
        try:
            return r.status, json.loads(payload.decode("utf-8"))
        except ValueError:
            return r.status, payload.decode("utf-8", "replace")


def main():
    token = io.open(TOKEN_FILE, encoding="utf-8").read().strip()
    gh = GH(token)

    st, me = gh.call("GET", "/user")
    if st != 200:
        print("!! token 失效", st, str(me)[:200])
        return 1
    owner = me["login"]
    print(">>> GitHub 账号:", owner)

    if not os.path.isfile(LOCAL_WF):
        print("!! 本地没有", LOCAL_WF)
        return 1
    content = io.open(LOCAL_WF, encoding="utf-8").read()

    # 0) YAML 粗检：至少能被 PyYAML 之外的方式确认不是空文件
    if "runs-on" not in content or "jobs:" not in content:
        print("!! workflow 内容看起来不对")
        return 1
    print(">>> 本地 workflow %d 字节" % len(content))

    # 1) 当前分支 tip
    st, ref = gh.call("GET", "/repos/%s/%s/git/ref/heads/%s"
                      % (owner, REPO, BRANCH))
    if st != 200:
        print("!! 取 ref 失败", st)
        return 1
    base_sha = ref["object"]["sha"]
    print(">>> 分支 tip:", base_sha[:8])

    # 1.5) 远端现状：根 workflow 是否已一致？误导副本是否还在？
    #      重复运行会 422（对不存在的文件再发一次 sha:null 删除 ->
    #      GitRPC::BadObjectState），所以必须先查再决定动不动。
    st, cur = gh.call("GET", "/repos/%s/%s/contents/%s?ref=%s"
                      % (owner, REPO, REMOTE_WF, BRANCH))
    cur_content = ""
    if st == 200:
        cur_content = base64.b64decode(cur["content"]).decode("utf-8")
    st2, dead = gh.call("GET", "/repos/%s/%s/contents/%s?ref=%s"
                        % (owner, REPO, DEAD_WF, BRANCH))
    dead_exists = (st2 == 200)
    print(">>> 远端根 workflow 一致:", cur_content == content,
          "| 误导副本仍在:", dead_exists)
    if cur_content == content and not dead_exists:
        print(">>> 无需提交，直接进入 dispatch")
        return dispatch(gh, owner)

    # 2) 上传 blob
    st, blob = gh.call("POST", "/repos/%s/%s/git/blobs" % (owner, REPO),
                       {"content": content, "encoding": "utf-8"})
    if st not in (200, 201):
        print("!! blob 上传失败", st, str(blob)[:200])
        return 1
    blob_sha = blob["sha"]
    print(">>> blob:", blob_sha[:8])

    # 3) 构造 tree：写入根 workflow +（若仍在）删除 issue/ 下那份
    entries = [{"path": REMOTE_WF, "mode": "100644", "type": "blob",
                "sha": blob_sha}]
    if dead_exists:
        entries.append({"path": DEAD_WF, "mode": "100644", "type": "blob",
                        "sha": None})
    st, tree = gh.call("POST", "/repos/%s/%s/git/trees" % (owner, REPO), {
        "base_tree": base_sha,
        "tree": entries,
    })
    if st not in (200, 201):
        print("!! tree 失败", st, str(tree)[:300])
        return 1
    print(">>> tree:", tree["sha"][:8])

    # 4) commit
    st, commit = gh.call("POST", "/repos/%s/%s/git/commits" % (owner, REPO), {
        "message": "workflow 移到仓库根 .github/workflows/（子目录那份从不生效）"
                   "；签名改为 cleansign.py 只签 v2+v3",
        "tree": tree["sha"],
        "parents": [base_sha],
    })
    if st not in (200, 201):
        print("!! commit 失败", st, str(commit)[:300])
        return 1
    print(">>> commit:", commit["sha"][:8])

    # 5) 移动分支指针
    st, r = gh.call("PATCH", "/repos/%s/%s/git/refs/heads/%s"
                    % (owner, REPO, BRANCH), {"sha": commit["sha"]})
    if st != 200:
        print("!! 更新 ref 失败", st, str(r)[:300])
        return 1
    print(">>> 已推送 %s -> %s" % (REMOTE_WF, commit["sha"][:8]))

    # 6) 校验：远端根 workflow 内容必须与本地一致
    st, f = gh.call("GET", "/repos/%s/%s/contents/%s?ref=%s"
                    % (owner, REPO, REMOTE_WF, BRANCH))
    if st == 200:
        remote = base64.b64decode(f["content"]).decode("utf-8")
        same = remote == content
        print(">>> 校验远端根 workflow 一致:", same)
        if not same:
            print("!! 不一致，别急着构建")
            return 1
    else:
        print("!! 读回失败", st)
        return 1

    if "--dispatch" in sys.argv:
        return dispatch(gh, owner)
    return 0


def dispatch(gh, owner):
    """手动触发一次构建。注意只触发一次 —— 之前 push + dispatch 打出两个
    并发 run，取错产物就白等一场。"""
    st, d = gh.call("POST",
                    "/repos/%s/%s/actions/workflows/build-issue-apk.yml/"
                    "dispatches" % (owner, REPO), {"ref": BRANCH})
    print(">>> dispatch:", st,
          "(204 = 已触发)" if st == 204 else str(d)[:300])
    if st != 204:
        return 1
    import time
    time.sleep(8)
    st, runs = gh.call("GET", "/repos/%s/%s/actions/runs?branch=%s&per_page=2"
                       % (owner, REPO, BRANCH))
    for x in runs.get("workflow_runs", []):
        print("    run %s | %s | %s" % (x["id"], x["status"], x["conclusion"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
