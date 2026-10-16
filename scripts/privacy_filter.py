#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy_filter.py —— 明文聊天记录的【脱敏】工具（P1-05）。

本技能导出的 messages.jsonl 含大量真实个人信息（手机号、身份证、银行卡、
邮箱、wxid、QQ、网址，以及对话里的姓名/公司/地址）。在把任何派生数据对外
分享、截图、写文章或提交 issue 之前，请先用本工具脱敏。

设计原则
--------
1. 高精度的「强 PII」默认全量脱敏：手机号 / 身份证 / 银行卡 / 邮箱 / wxid /
   QQ / 网址。这些用正则即可高置信识别，误伤低。
2. 「弱 PII」（姓名 / 公司 / 地址）不做盲目猜测（NER 误伤高），改为由你显式
   提供词表（--names 名单文件），只替换你点名要替换的词。这样即安全又可控。
3. 脱敏是把命中内容替换成类型标签，例如 <PHONE> / <IDCARD>；原始值不保留。

用法
----
  # 脱敏一份明文 jsonl，输出到新文件，并打印各类命中统计
  python privacy_filter.py messages.jsonl -o messages_redacted.jsonl --summary

  # 额外替换指定姓名/公司/地址词表（每行一个词）
  python privacy_filter.py messages.jsonl -o out.jsonl --names my_names.txt

  # 仅测试单条文本（不读写文件）
  python privacy_filter.py --text "我的手机13800138000，邮箱a@b.com"

也可在代码里直接调用：  from privacy_filter import redact_text
"""
import sys, os, re, json, argparse


# ── 强 PII 正则（顺序很重要：长的/特定的先匹配，避免被短的吞噬）──
PATTERNS = [
    ("IDCARD", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),          # 18 位身份证
    ("BANK",   re.compile(r"(?<!\d)\d{16,19}(?!\d)")),            # 16-19 位银行卡
    ("PHONE",  re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),          # 大陆手机号 11 位
    ("EMAIL",  re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("WXID",   re.compile(r"\bwxid_[A-Za-z0-9]{6,}\b")),
    ("QQ",     re.compile(r"(?i)\bqq[:：]?\s*\d{5,12}\b")),       # 仅当显式带 "QQ" 标签
    ("URL",    re.compile(r"https?://[^\s]+")),
]

# 弱 PII 词表脱敏（由用户显式提供）
NAME_RE_CACHE = {}


def _name_regex(names):
    """把名单词编译成一个 alternation 正则（按长度降序，长词优先）。"""
    key = tuple(sorted(names, key=len, reverse=True))
    if key not in NAME_RE_CACHE:
        esc = [re.escape(n) for n in key if n]
        NAME_RE_CACHE[key] = re.compile("|".join(esc)) if esc else None
    return NAME_RE_CACHE[key]


def redact_text(text, names=None):
    """对一段文本做脱敏，返回 (clean_text, counts_dict)。

    names: 可选的「弱 PII」替换词表（姓名/公司/地址等），传 list[str]。
    强 PII 用固定正则全量替换；弱 PII 仅替换词表里点名的词。
    统计在「逐步脱敏后的文本」上进行，避免 18 位身份证被 BANK 规则重复计数。
    """
    if not text:
        return text, {}
    counts = {}
    s = text
    for tag, pat in PATTERNS:
        found = pat.findall(s)
        if found:
            counts[tag] = counts.get(tag, 0) + len(found)
            s = pat.sub("<%s>" % tag, s)
    # 弱 PII（显式词表）
    if names:
        rx = _name_regex(names)
        if rx:
            found = rx.findall(s)
            if found:
                counts["NAME"] = counts.get("NAME", 0) + len(found)
            s = rx.sub("<NAME>", s)
    return s, counts


def redact_record(rec, names=None):
    """对一条 jsonl 记录脱敏：处理 content / chat_name / sender_name 字段。"""
    if not isinstance(rec, dict):
        return rec, {}
    total = {}
    if "content" in rec and isinstance(rec["content"], str):
        rec["content"], c = redact_text(rec["content"], names=names)
        total.update(c)
    for fld in ("chat_name", "sender_name"):
        if fld in rec and isinstance(rec[fld], str) and names:
            rx = _name_regex(names)
            if rx and rx.search(rec[fld]):
                rec[fld] = rx.sub("<NAME>", rec[fld])
    return rec, total


def main():
    ap = argparse.ArgumentParser(description="明文聊天记录脱敏工具")
    ap.add_argument("input", nargs="?", help="输入 messages.jsonl（或任意文本文件）")
    ap.add_argument("-o", "--output", help="脱敏后输出路径")
    ap.add_argument("--text", help="直接对一段文本脱敏并打印结果（不读写文件）")
    ap.add_argument("--names", help="弱 PII 词表文件（每行一个姓名/公司/地址），可选")
    ap.add_argument("--summary", action="store_true", help="打印各类 PII 命中统计")
    args = ap.parse_args()

    names = None
    if args.names:
        try:
            with open(args.names, "r", encoding="utf-8") as f:
                names = [ln.strip() for ln in f if ln.strip()]
        except OSError as e:
            sys.stderr.write("[privacy] 无法读取词表 %s: %s\n" % (args.names, e))
            return 2

    if args.text is not None:
        clean, counts = redact_text(args.text, names=names)
        print(clean)
        if args.summary:
            print("命中统计:", counts or "无")
        return 0

    if not args.input:
        ap.print_help()
        return 1

    out_path = args.output or (args.input + ".redacted")
    total_counts = {}
    n_in = n_out = 0
    try:
        fin = open(args.input, "r", encoding="utf-8")
    except OSError as e:
        sys.stderr.write("[privacy] 无法读取输入 %s: %s\n" % (args.input, e))
        return 2

    with fin:
        fout = open(out_path, "w", encoding="utf-8")
        with fout:
            for line in fin:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    rec, c = redact_record(rec, names=names)
                    fout.write(json.dumps(rec, ensure_ascii=False))
                    fout.write("\n")
                except json.JSONDecodeError:
                    # 非 JSON 行：当纯文本脱敏
                    clean, c = redact_text(line, names=names)
                    fout.write(clean)
                    fout.write("\n")
                n_in += 1
                n_out += 1
                for k, v in c.items():
                    total_counts[k] = total_counts.get(k, 0) + v

    sys.stderr.write("[privacy] 已处理 %d 行 -> %s\n" % (n_in, out_path))
    if args.summary:
        sys.stderr.write("[privacy] 命中统计: %s\n" % (total_counts or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
