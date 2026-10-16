#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a privacy-safe distribution zip of the wechat-self-analysis skill.

Drops everything that could leak the author's real data:
  * sample_reports/   -> replaced by a placeholder README (no real reports)
  * output/           -> analysis output (may contain real messages)
  * .wc_cache/        -> decrypted DB caches
  * __pycache__ / .git / *.part / lock files

Keeps: SKILL.md, config.json, requirements.txt, references/, scripts/.
Outputs a `wechat-self-analysis_clean.zip` next to this script (no real data inside).
"""
import os
import zipfile

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_ZIP = os.path.join(SKILL_DIR, "wechat-self-analysis_clean.zip")

# directories to skip entirely (checked at ANY nesting level, not just top)
SKIP_DIRS = {"sample_reports", "output", ".wc_cache", "__pycache__", ".git", "export"}
# files to skip (by name)
SKIP_FILES = {".dump.lock", "wechat-self-analysis_clean.zip"}
# suffix to skip
SKIP_SUFFIXES = (".part",)

PLACEHOLDER = (
    "# sample_reports/ 已被移除\n\n"
    "本目录在对外发布的干净版技能中**刻意留空**，以避免泄露作者本人的真实聊天数据。\n\n"
    "安装本技能后，请用你自己运行脚本生成的 `output/` 产物作为格式参考，\n"
    "或运行各分析脚本生成属于你自己的样例。\n\n"
    "详见 SKILL.md 的「样例报告」与「隐私红线」两节。\n"
)


def collect(skill_dir):
    kept = []
    for root, dirs, files in os.walk(skill_dir):
        parts = os.path.relpath(root, skill_dir).split(os.sep)
        if any(p in SKIP_DIRS for p in parts):   # 任意层级命中敏感目录都跳过
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn in SKIP_FILES or fn.endswith(SKIP_SUFFIXES):
                continue
            full = os.path.join(root, fn)
            arc = os.path.relpath(full, skill_dir)
            kept.append(arc)
    return sorted(kept)


def main():
    files = collect(SKILL_DIR)
    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for arc in files:
            z.write(os.path.join(SKILL_DIR, arc), arcname=os.path.join("wechat-self-analysis", arc))
        z.writestr(os.path.join("wechat-self-analysis", "sample_reports", "README.md"), PLACEHOLDER)
    size = os.path.getsize(OUT_ZIP)
    print("Built: %s" % OUT_ZIP)
    print("Size: %.1f KB" % (size / 1024.0))
    print("Files included: %d (+1 placeholder README)" % len(files))
    with zipfile.ZipFile(OUT_ZIP) as z:
        bad = [n for n in z.namelist()
               if n.startswith("wechat-self-analysis/sample_reports/")
               and n != "wechat-self-analysis/sample_reports/README.md"]
        if bad:
            print("WARNING: unexpected files in sample_reports/: %s" % bad)
        else:
            print("Privacy check OK: sample_reports/ contains only the placeholder README.")


if __name__ == "__main__":
    main()
