#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出某个会话（如 md5 群）的完整聊天记录为可读文本。
用法: python export_chat_transcript.py <chat_id> [输出路径]
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
sys.path.insert(0, HERE)
from wechatauto.db import WeChatDB

IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
# 隐私默认策略：dump 默认把明文写到 .wc_cache/export/；若 output/ 下没有，
# 自动在 .wc_cache/export/ 或历史 scripts/export/ 定位（见 _paths.locate_messages_jsonl）。
try:
    from _paths import locate_messages_jsonl as _locate
    if not os.path.exists(IN_PATH):
        _f = _locate()
        if _f:
            IN_PATH = _f
except Exception:
    pass
PREFIX_RE = re.compile(r"^([A-Za-z0-9_@.\-]{3,45}):\s*")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def main():
    if len(sys.argv) < 2:
        print("用法 / Usage: python scripts/export_chat_transcript.py <chat_id> [out_path]")
        print("  <chat_id>  会话 ID（可从 output/manifest.json 或 messages.jsonl 的 chat 字段获取）")
        print("  示例 / Example: python scripts/export_chat_transcript.py wxid_example_000")
        return 1
    chat_id = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.join(SKILL_ROOT, "output", "transcript_%s.md" % chat_id[:8])

    # ---- 昵称映射：contact 表（好友/已知联系人） ----
    nick = {}
    try:
        db = WeChatDB(workdir=os.path.join(SKILL_ROOT, ".wc_cache", "dump"))
        for rel, path, _ in db._db_files:
            if os.path.basename(path) != "contact.db":
                continue
            conn = db._open(rel)
            try:
                for u, n, r in conn.execute(
                        "SELECT username, nick_name, remark FROM contact"):
                    if u:
                        nick[u] = r or n or u
            finally:
                conn.close()
            break
    except Exception as e:
        print("昵称映射不可用（微信未运行?）：%s，改用 wxid 显示" % e)

    # ---- 读取该会话全部消息 ----
    msgs = []
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("chat") != chat_id:
                continue
            msgs.append(rec)
    if not msgs:
        print("没找到该会话的消息：%s" % chat_id)
        return 2
    msgs.sort(key=lambda r: (epoch(r.get("create_time")) or 0, r.get("local_id") or 0))

    def display_name(rec):
        c = rec.get("content") or ""
        m = PREFIX_RE.match(c)
        if m:
            who = m.group(1)
            return nick.get(who, who), c[m.end():]
        s = rec.get("sender_name") or ""
        if rec.get("side") == "self":
            return "我", c
        return (nick.get(s, s) or s), c

    def readable(rec):
        side, mtype, c = rec.get("side"), rec.get("type"), rec.get("content") or ""
        if mtype != "文本" and c.startswith("<"):
            t = TITLE_RE.search(c)
            return "[%s] %s" % (mtype, t.group(1).strip()[:120] if t else "")
        if mtype != "文本" and c.startswith("wxid_"):
            t = TITLE_RE.search(c)
            return "[%s] %s" % (mtype, t.group(1).strip()[:120] if t else "")
        return c

    # ---- 统计 ----
    speaker_cnt = collections.Counter()
    month_cnt = collections.Counter()
    for r in msgs:
        n, _ = display_name(r)
        speaker_cnt[n] += 1
        t = epoch(r.get("create_time"))
        if t:
            month_cnt[datetime.datetime.fromtimestamp(t).strftime("%Y-%m")] += 1

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 聊天记录完整导出：%s\n\n" % chat_id)
        f.write("- 消息总数：%d\n" % len(msgs))
        t0, t1 = epoch(msgs[0].get("create_time")), epoch(msgs[-1].get("create_time"))
        if t0 and t1:
            f.write("- 时间跨度：%s ~ %s\n" % (
                datetime.datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M"),
                datetime.datetime.fromtimestamp(t1).strftime("%Y-%m-%d %H:%M")))
        f.write("- 发言者 Top20：%s\n" % "，".join(
            "%s(%d)" % (n, c) for n, c in speaker_cnt.most_common(20)))
        f.write("- 月度分布：%s\n\n" % "，".join(
            "%s:%d" % (m, c) for m, c in sorted(month_cnt.items())))
        f.write("---\n\n")

        cur_day = None
        for r in msgs:
            t = epoch(r.get("create_time"))
            d = datetime.datetime.fromtimestamp(t) if t else None
            day = d.strftime("%Y-%m-%d") if d else "未知日期"
            if day != cur_day:
                cur_day = day
                f.write("\n## %s\n\n" % day)
            who, content = display_name(r)
            text = readable(r).replace("\r", "")
            ts = d.strftime("%H:%M") if d else "--:--"
            if "\n" in text:
                f.write("- `%s` **%s**：\n" % (ts, who))
                for ln in text.split("\n"):
                    f.write("  > %s\n" % ln)
            else:
                f.write("- `%s` **%s**：%s\n" % (ts, who, text))

    size_mb = os.path.getsize(out_path) / 1048576.0
    print("完成：%d 条消息 -> %s (%.1f MB)" % (len(msgs), out_path, size_mb))
    print("发言者 Top10:", "，".join("%s(%d)" % (n, c) for n, c in speaker_cnt.most_common(10)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
