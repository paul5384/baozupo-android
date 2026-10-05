#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清掉已经推到公开仓库上的本机调试产物。

背景：仓库 paul5384/baozupo-android 是 **public**，而早先的推送脚本
只排除了 _test_/_repro_/_depcheck/_probe_ 前缀，结果 _allverify.txt、
_sigchk.txt 之类带着本机路径（C:\\Users\\L540\\...）和证书指纹的日志
被一起推了上去。这里用 Git Data API 一次性删除。

删除 = 在 tree 里把对应 path 的 sha 置为 null。

用法：python cleanup_remote.py [--apply]
      不带 --apply 只打印将要删除的清单。
"""
import io
import json
import sys
import urllib.request

TOKEN = io.open(r"C:\Users\L540\android-build\.ghtoken",
                encoding="utf-8").read().strip()
API = "https://api.github.com"
REPO = "baozupo-android"
BRANCH = "issue-apk"
OWNER = "paul5384"

# 只删这些：下划线开头的本机产物 + 根目录散落的 txt 日志
PREFIXES = ("issue/_",)
SUFFIXES = (".txt", ".log")


def api(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "bzq-cleanup")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def main():
    apply = "--apply" in sys.argv

    ref = api("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH))
    head_sha = ref["object"]["sha"]
    commit = api("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO, head_sha))
    base_tree = commit["tree"]["sha"]
    print("分支 %s 当前 commit %s" % (BRANCH, head_sha[:8]))

    tree = api("GET", "/repos/%s/%s/git/trees/%s?recursive=1"
               % (OWNER, REPO, BRANCH))
    paths = [x["path"] for x in tree.get("tree", [])]
    victims = sorted(p for p in paths
                     if p.startswith(PREFIXES) or p.endswith(SUFFIXES))

    print("待删除 %d 个：" % len(victims))
    for v in victims:
        print("   ", v)
    if not victims:
        print("（没有需要清理的）")
        return 0
    if not apply:
        print()
        print("这是预演。加 --apply 才真正删除。")
        return 0

    # sha 置 null 即删除
    entries = [{"path": p, "mode": "100644", "type": "blob", "sha": None}
               for p in victims]
    new_tree = api("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
                   {"base_tree": base_tree, "tree": entries})
    new_commit = api("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO), {
        "message": "清理误推到公开仓库的本机调试日志",
        "tree": new_tree["sha"],
        "parents": [head_sha],
    })
    api("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH),
        {"sha": new_commit["sha"]})
    print("已删除并推送 commit %s" % new_commit["sha"][:8])
    print("注意：git 历史里仍可翻到这些文件，需要的话得重写历史（force push）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
