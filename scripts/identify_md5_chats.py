#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""破解 messages.jsonl 中显示为 32 位 md5 的会话身份。

原理: 微信 4.x 把会话消息存为 Msg_<md5(微信号)> 表；导出时 md5→微信号
反查只用了 contact.db + session.db。本脚本：
  1) 扩大破解面: contact.db / session.db / message_resource.db 全库所有含
     username 列的表全量抽取，md5 撞库；
  2) 撞不出的，从 messages.jsonl 抽典型消息(首2+最长3+末3)供人工辨认。
输出: export/md5_identity_report.md
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
from wechatauto.db import WeChatDB, _md5_hex

IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
OUT_MD = os.path.join(SKILL_ROOT, "output", "md5_identity_report.md")
MD5_RE = re.compile(r"^[0-9a-f]{32}$")


def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def main():
    # ---- Pass 1: 找出所有 md5 名会话 + 统计 + 采样 ----
    stats = {}  # chat -> dict
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            chat = rec.get("chat", "")
            if not MD5_RE.match(chat):
                continue
            s = stats.get(chat)
            if s is None:
                s = stats[chat] = {
                    "total": 0, "self_n": 0, "them_n": 0,
                    "first_t": None, "last_t": None,
                    "first2": [], "longest3": [], "last3": collections.deque(maxlen=3),
                }
            s["total"] += 1
            if rec.get("side") == "self":
                s["self_n"] += 1
            else:
                s["them_n"] += 1
            t = epoch(rec.get("create_time"))
            if t:
                if s["first_t"] is None or t < s["first_t"]:
                    s["first_t"] = t
                if s["last_t"] is None or t > s["last_t"]:
                    s["last_t"] = t
            item = (t, rec.get("side"), rec.get("type"), rec.get("content") or "")
            if len(s["first2"]) < 2:
                s["first2"].append(item)
            l3 = s["longest3"]
            if len(l3) < 3:
                l3.append((len(item[3]), item))
                l3.sort(key=lambda x: -x[0])
            elif len(item[3]) > l3[-1][0]:
                l3[-1] = (len(item[3]), item)
                l3.sort(key=lambda x: -x[0])
            s["last3"].append(item)

    targets = set(stats.keys())
    if not targets:
        print("没有发现 md5 名会话")
        return 0
    print("发现 %d 个 md5 名会话" % len(targets))

    # ---- Pass 2: 全库撞 md5 ----
    db = WeChatDB(workdir=os.path.join(SKILL_ROOT, ".wc_cache", "dump"))
    cands = set()
    table_seen = []
    for rel, path, _ in db._db_files:
        base = os.path.basename(path)
        if base not in ("contact.db", "session.db", "message_resource.db"):
            continue
        try:
            conn = db._open(rel)
        except Exception as e:
            print("跳过 %s: %s" % (rel, e))
            continue
        try:
            for (tname,) in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                cols = [r[1] for r in conn.execute('PRAGMA table_info("%s")' % tname)]
                if "username" in cols:
                    table_seen.append("%s.%s" % (base, tname))
                    try:
                        for (u,) in conn.execute('SELECT username FROM "%s"' % tname):
                            if u:
                                cands.add(u)
                    except Exception:
                        continue
        finally:
            conn.close()

    md5_to_user = {}
    for u in cands:
        m = _md5_hex(u.encode())
        if m in targets:
            md5_to_user.setdefault(m, u)
    print("候选 username %d 个（来自 %s）" % (len(cands), ", ".join(table_seen)))
    print("撞库解析 %d/%d" % (len(md5_to_user), len(targets)))

    # ---- 昵称反查 ----
    def nick_of(user):
        for rel, path, _ in db._db_files:
            if os.path.basename(path) != "contact.db":
                continue
            conn = db._open(rel)
            try:
                row = conn.execute(
                    "SELECT nick_name, remark FROM contact WHERE username=? LIMIT 1",
                    (user,)).fetchone()
            finally:
                conn.close()
            if row:
                return (row["remark"] or row["nick_name"] or user), row["nick_name"] or ""
            break
        return user, ""

    # ---- 报告 ----
    L = ["# md5 会话身份破解报告\n"]
    L.append("共 %d 个会话显示为 md5；全库撞库解析 %d 个，其余靠消息内容人工辨认。\n" % (
        len(targets), len(md5_to_user)))
    for chat in sorted(targets, key=lambda c: -stats[c]["total"]):
        s = stats[chat]
        L.append("## %s\n" % chat)
        rng = ""
        if s["first_t"] and s["last_t"]:
            rng = "%s ~ %s" % (
                datetime.datetime.fromtimestamp(s["first_t"]).strftime("%Y-%m-%d"),
                datetime.datetime.fromtimestamp(s["last_t"]).strftime("%Y-%m-%d"))
        L.append("- 消息 %d 条（你 %d / 对方 %d），时间跨度 %s" % (
            s["total"], s["self_n"], s["them_n"], rng))
        if chat in md5_to_user:
            user = md5_to_user[chat]
            nick, raw = nick_of(user)
            extra = ("（原始昵称: %s）" % raw) if raw and raw != nick else ""
            L.append("- **已破解**: 微信号 `%s`，昵称/备注「%s」%s" % (user, nick, extra))
        else:
            L.append("- ❌ 撞库未中（联系人大概率已被删除/注销，或为已移除的公众号）")
        seen = set()
        L.append("- 典型消息：")
        for tag, items in (("首", s["first2"]),
                           ("长", [x[1] for x in s["longest3"]]),
                           ("末", list(s["last3"]))):
            for it in items:
                key = (it[0], it[3][:50])
                if key in seen:
                    continue
                seen.add(key)
                t, side, mtype, content = it
                ts = datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else "?"
                c = content.replace("\n", " ")[:150]
                who = "我" if side == "self" else "TA"
                L.append("  - `%s`[%s][%s] %s：%s" % (ts, tag, who, mtype, c))
        L.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("报告: %s" % OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
