#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于 WechatVibe 导出的 messages.jsonl，对你的微信沟通行为做四维自我分析。

输入:  export/messages.jsonl  (由 _dump_chats.py 在已登录微信的桌面会话生成)
输出:  export/analysis.json            原始指标
       export/analysis_report.md      文字报告(表格+结论)
       export/analysis_report.html    交互式图表(Chart.js)

四维:
  1) 沟通主动性与回复模式  - 自/他消息占比、会话发起方、回复时延、回复率
  2) 情绪表达与稳定性      - 情感倾向(启发式词典)、波动率、emoji/标点强度
  3) 时间与精力分配        - 活跃时段、星期分布、每日量、精力投入Top聊天
  4) 关系维护质量          - 互惠比、被忽略的会话、静默天数、寒暄频率

说明: 情感为离线中文词典启发式打分(非模型推理)，仅作行为趋势参考。
"""
import sys, os, re, json, math, time, random, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
DEFAULT_IN = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
DEFAULT_OUTDIR = os.path.join(SKILL_ROOT, "output")
# 隐私默认策略：dump 默认把明文写到 .wc_cache/export/；若 output/ 下没有，
# 自动在 .wc_cache/export/ 或历史 scripts/export/ 定位（见 _paths.locate_messages_jsonl）。
try:
    from _paths import locate_messages_jsonl as _locate
    if not os.path.exists(DEFAULT_IN):
        _f = _locate()
        if _f:
            DEFAULT_IN = _f
except Exception:
    pass

THREAD_GAP = 6 * 3600  # 超过 6 小时无消息视为新会话线程

# ---- 启发式情感词典（适量常用词，离线、轻量）----
POS_WORDS = set("开心 高兴 快乐 喜欢 爱 赞 棒 好 不错 完美 哈哈 嘻嘻 满意 幸福 期待 谢谢 感谢 加油 支持 厉害 漂亮 可爱 暖 感动 舒服 轻松 稳 香 绝 妙 牛 顶 耶 嘻 嗨 愉快 欣慰 荣幸 美好 顺利 幸运 强 优秀 温馨 甜蜜".split())
NEG_WORDS = set("烦 生气 生气了 气 怒 难过 伤心 失望 无奈 累 困 病 痛 苦 惨 糟 差 讨厌 烦人 焦虑 压力 崩溃 孤独 委屈 后悔 愧疚 担心 害怕 怕 愁 衰 烂 坑 扯 无语 醉 服 裂 崩 麻 烦死了 气死 哭 恨 恶 厌 丧 抑郁 烦躁".split())
GREET_RE = re.compile(r"(早安|早呀|早上好|晚安|晚好|在吗|在不|在不在|最近怎|咋样|吃饭|吃了吗|忙吗|忙不|最近好|好久不见|最近在|身体|注意身体|休息)")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F"
    "\U0000FE00-\U0000FE0F\U0001F1E6-\U0001F1FF\u2600-\u27BF]"
)
# 退群/解散的群：chat 名只剩 md5（不带 @chatroom），靠内容特征识别
MD5_NAME_RE = re.compile(r"^[0-9a-f]{32}$")
PREFIX_RE = re.compile(r"^([A-Za-z0-9_@.\-]{3,45}):")
GROUP_SIG_RE = re.compile(r"(移出群聊|移出了群聊|解散|不是微信朋友关系|已被群主|群主已将|你已退出群聊)")

def epoch(v):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v > 1e11:
        v = v / 1000.0
    return v

def day_key(t):
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d")

def dow(t):
    return datetime.datetime.fromtimestamp(t).weekday()  # 0=Mon

def sentiment(text):
    """返回 (score, pos_hit, neg_hit) 启发式情感分。"""
    if not text:
        return 0, 0, 0
    toks = re.findall(r"[\w\u4e00-\u9fff]+", text)
    pos = sum(1 for w in toks if w in POS_WORDS)
    neg = sum(1 for w in toks if w in NEG_WORDS)
    # 多字短语做子串匹配（覆盖「烦死了」「讨厌」等连写情形）
    for w in POS_WORDS:
        if len(w) >= 2 and w in text:
            pos += 1
    for w in NEG_WORDS:
        if len(w) >= 2 and w in text:
            neg += 1
    return pos - neg, pos, neg

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        sys.stderr.write("找不到 %s，请先运行 dump-chats.cmd 导出。\n" % args.inp)
        return 2
    os.makedirs(args.outdir, exist_ok=True)

    NOW = time.time()
    total = 0
    self_n = 0
    them_n = 0
    type_self = collections.Counter()
    type_them = collections.Counter()
    hour_self = [0] * 24
    dow_self = [0] * 7
    date_self = collections.Counter()
    date_sent_sum = {}
    date_sent_n = {}
    words_self = 0
    words_them = 0
    emoji_self = 0
    excl_self = 0
    quest_self = 0
    sent_pos_total = 0
    sent_neg_total = 0
    sent_text_n = 0

    # 全局回复时延蓄水池（用于分位数估计）
    lat_res = []
    LAT_CAP = 400000
    lat_count = 0
    lat_sum = 0.0
    lat_sumsq = 0.0

    chats = {}  # chat -> record

    def get_chat(chat, name):
        if chat not in chats:
            is_group = chat.endswith("@chatroom") or chat.startswith("@@")
            chats[chat] = {
                "chat": chat, "name": name, "is_group": is_group,
                "n_self": 0, "n_them": 0, "words_self": 0, "words_them": 0,
                "first_time": None, "last_time": None,
                "lat_n": 0, "lat_sum": 0.0, "lat_min": None, "lat_max": 0.0,
                "them_lat_n": 0, "them_lat_sum": 0.0,
                "threads_self_init": 0, "threads_them_init": 0, "thread_count": 0,
                "ignored_threads": 0, "greet_self": 0, "greet_them": 0,
                "sent_sum": 0.0, "sent_n": 0,
                "prefixes": set(), "grp_sig": 0,
            }
        return chats[chat]

    # 流式：每个聊天的消息在文件中连续且按时间升序，故可按 chat 切换维护线程状态
    cur_chat = None
    last_t = None
    last_side = None
    thr_init = None
    thr_self_replied = False

    def close_thread(r):
        nonlocal thr_init, thr_self_replied
        if thr_init == "them" and not thr_self_replied:
            r["ignored_threads"] += 1
        thr_init = None
        thr_self_replied = False

    t0 = time.time()
    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            chat = rec.get("chat")
            name = rec.get("chat_name") or chat
            side = rec.get("side")
            ctype = rec.get("type")
            content = rec.get("content")
            t = epoch(rec.get("create_time"))

            r = get_chat(chat, name)

            if chat != cur_chat:
                if cur_chat is not None and cur_chat in chats:
                    close_thread(chats[cur_chat])
                cur_chat = chat
                last_t = None
                last_side = None
                thr_init = None
                thr_self_replied = False

            if side == "self":
                self_n += 1
                r["n_self"] += 1
                type_self[ctype] += 1
                if t is not None:
                    hour_self[datetime.datetime.fromtimestamp(t).hour] += 1
                    dow_self[dow(t)] += 1
                    date_self[day_key(t)] += 1
                if ctype == "文本" and isinstance(content, str):
                    words_self += len(content)
                    r["words_self"] += len(content)
                    s, p, ng = sentiment(content)
                    if p or ng:
                        date_sent_sum[day_key(t)] = date_sent_sum.get(day_key(t), 0) + s
                        date_sent_n[day_key(t)] = date_sent_n.get(day_key(t), 0) + 1
                    sent_pos_total += p
                    sent_neg_total += ng
                    sent_text_n += 1
                    if EMOJI_RE.search(content):
                        emoji_self += 1
                    if "！" in content or "!" in content:
                        excl_self += 1
                    if "？" in content or "?" in content:
                        quest_self += 1
                    if GREET_RE.search(content):
                        r["greet_self"] += 1
            else:
                them_n += 1
                r["n_them"] += 1
                type_them[ctype] += 1
                if ctype == "文本" and isinstance(content, str):
                    words_them += len(content)
                    r["words_them"] += len(content)
                    if GREET_RE.search(content):
                        r["greet_them"] += 1
                # 退群/解散群识别：md5 名会话的内容特征
                if MD5_NAME_RE.match(chat or "") and isinstance(content, str):
                    m2 = PREFIX_RE.match(content)
                    if m2:
                        r["prefixes"].add(m2.group(1))
                    if GROUP_SIG_RE.search(content[:120]):
                        r["grp_sig"] = 1

            if t is not None:
                if r["first_time"] is None or t < r["first_time"]:
                    r["first_time"] = t
                if r["last_time"] is None or t > r["last_time"]:
                    r["last_time"] = t

            # 线程 / 回复时延（带乱序保护：跨分片 sort_seq 与时间可能不一致）
            if t is not None:
                if last_t is None:
                    # 该聊天第一条有效消息 → 线程发起
                    thr_init = side
                    thr_self_replied = (side == "self")
                    if side == "self":
                        r["threads_self_init"] += 1
                    else:
                        r["threads_them_init"] += 1
                    r["thread_count"] += 1
                elif t >= last_t:
                    gap = t - last_t
                    if gap > THREAD_GAP:
                        close_thread(r)
                        thr_init = side
                        thr_self_replied = (side == "self")
                        if side == "self":
                            r["threads_self_init"] += 1
                        else:
                            r["threads_them_init"] += 1
                        r["thread_count"] += 1
                    else:
                        if side == "self" and last_side == "them":
                            # 你回复对方
                            thr_self_replied = True
                            lat_count += 1
                            lat_sum += gap
                            lat_sumsq += gap * gap
                            if len(lat_res) < LAT_CAP:
                                lat_res.append(gap)
                            else:
                                lat_res[random.randrange(LAT_CAP)] = gap
                            r["lat_n"] += 1
                            r["lat_sum"] += gap
                            if r["lat_min"] is None or gap < r["lat_min"]:
                                r["lat_min"] = gap
                            if gap > r["lat_max"]:
                                r["lat_max"] = gap
                        elif side == "them" and last_side == "self":
                            r["them_lat_n"] += 1
                            r["them_lat_sum"] += gap
                # else: t < last_t 时间回跳（跨分片乱序），跳过线程/时延计算
                last_t = t
                last_side = side

    if cur_chat is not None and cur_chat in chats:
        close_thread(chats[cur_chat])

    # ---------- 汇总派生指标 ----------
    span_days = 0
    if chats:
        all_first = [r["first_time"] for r in chats.values() if r["first_time"]]
        all_last = [r["last_time"] for r in chats.values() if r["last_time"]]
        if all_first and all_last:
            g_first = min(all_first)
            g_last = max(all_last)
            span_days = max(1, (g_last - g_first) / 86400.0)

    active_days = len(date_self)
    global_lat_median = global_lat_p90 = global_lat_mean = None
    if lat_res:
        lat_res.sort()
        n = len(lat_res)
        global_lat_median = lat_res[n // 2]
        global_lat_p90 = lat_res[min(n - 1, int(n * 0.9))]
        global_lat_mean = lat_sum / max(1, lat_count)

    # 每日情感序列（用于波动率）
    daily_means = []
    for d in sorted(date_sent_sum.keys()):
        if date_sent_n[d]:
            daily_means.append(date_sent_sum[d] / date_sent_n[d])
    sent_volatility = _std(daily_means) if len(daily_means) > 1 else 0.0

    busiest_hour = int(max(range(24), key=lambda h: hour_self[h]))
    busiest_dow = int(max(range(7), key=lambda d: dow_self[d]))
    DOW_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    # 退群/解散群重分类：md5 名 + 多发言人前缀(≥3) 或系统退群特征
    reclassified = 0
    for r in chats.values():
        if MD5_NAME_RE.match(r["chat"]) and (len(r["prefixes"]) >= 3 or r["grp_sig"]):
            r["is_group"] = True
            r["name"] = "已退群_" + r["chat"][:8]
            reclassified += 1

    # 排序：按总消息量
    ranked = sorted(chats.values(), key=lambda r: -(r["n_self"] + r["n_them"]))

    # 一维：主动/回复（群聊与 1:1 分口径，避免大群稀释）
    grp = [r for r in chats.values() if r["is_group"]]
    one = [r for r in chats.values() if not r["is_group"]]

    def _scope(rs):
        s = sum(r["n_self"] for r in rs)
        t = sum(r["n_them"] for r in rs)
        return {
            "chats": len(rs), "self_messages": s, "them_messages": t,
            "self_ratio": round(s / max(1, s + t), 4),
            "self_initiated_threads": sum(r["threads_self_init"] for r in rs),
            "them_initiated_threads": sum(r["threads_them_init"] for r in rs),
        }

    dim1 = {
        "total_messages": total,
        "self_messages": self_n,
        "them_messages": them_n,
        "self_ratio": round(self_n / max(1, total), 4),
        "global_reply_latency_sec": {
            "median": global_lat_median, "mean": global_lat_mean, "p90": global_lat_p90,
        },
        "type_distribution_self": dict(type_self.most_common(10)),
        "group_scope": _scope(grp),
        "one2one_scope": _scope(one),
    }

    # 二维：情绪
    dim2 = {
        "sent_text_messages": sent_text_n,
        "pos_cue_total": sent_pos_total,
        "neg_cue_total": sent_neg_total,
        "pos_rate": round(sent_pos_total / max(1, sent_pos_total + sent_neg_total), 4),
        "neg_rate": round(sent_neg_total / max(1, sent_pos_total + sent_neg_total), 4),
        "daily_sentiment_volatility": round(sent_volatility, 4),
        "emoji_rate": round(emoji_self / max(1, self_n), 4),
        "exclamation_rate": round(excl_self / max(1, self_n), 4),
        "question_rate": round(quest_self / max(1, self_n), 4),
        "daily_sentiment": [
            {"date": d, "mean": round(date_sent_sum[d] / date_sent_n[d], 3)}
            for d in sorted(date_sent_sum.keys())
        ],
    }

    # 三维：时间/精力
    dim3 = {
        "span_days": round(span_days, 1),
        "active_days": active_days,
        "msgs_per_active_day": round(self_n / max(1, active_days), 1),
        "busiest_hour": busiest_hour,
        "busiest_dow": busiest_dow,
        "hour_histogram": hour_self,
        "dow_histogram": {"labels": DOW_CN, "values": dow_self},
        "top_energy_chats": [
            {"name": r["name"], "chat": r["chat"], "self_msgs": r["n_self"],
             "them_msgs": r["n_them"], "words_sent": r["words_self"]}
            for r in ranked[:20]
        ],
        "top_energy_1to1": [
            {"name": r["name"], "chat": r["chat"], "self_msgs": r["n_self"],
             "them_msgs": r["n_them"], "words_sent": r["words_self"]}
            for r in sorted(
                (r for r in chats.values() if not r["is_group"]),
                key=lambda r: -r["n_self"])[:15]
        ],
    }

    # 四维：关系维护（聚焦 1:1；排除你从未发言/仅偶尔回过的单向推送类会话）
    all_1to1 = [r for r in chats.values()
                if not r["is_group"] and (r["n_self"] + r["n_them"]) >= 20]
    one_way = [r for r in all_1to1 if r["n_self"] < 5]
    one2one = [r for r in all_1to1 if r["n_self"] >= 5]
    rel_rows = []
    for r in one2one:
        tot = r["n_self"] + r["n_them"]
        self_ratio = r["n_self"] / max(1, tot)
        reply_rate = None
        if r["threads_them_init"]:
            replied = r["threads_them_init"] - r["ignored_threads"]
            reply_rate = round(replied / r["threads_them_init"], 3)
        silence = None
        if r["last_time"]:
            silence = round((NOW - r["last_time"]) / 86400.0, 1)
        mean_reply = (r["lat_sum"] / r["lat_n"]) if r["lat_n"] else None
        rel_rows.append({
            "name": r["name"], "chat": r["chat"], "total": tot,
            "self_ratio": round(self_ratio, 3),
            "reply_rate": reply_rate,
            "mean_reply_min": round(mean_reply / 60.0, 1) if mean_reply else None,
            "greet_self": r["greet_self"],
            "silence_days": silence,
            "sent_mean": round(r["sent_sum"] / max(1, r["sent_n"]), 3) if r["sent_n"] else 0.0,
        })
    rel_rows.sort(key=lambda x: -x["total"])
    neglected = [x for x in rel_rows if (x["silence_days"] or 0) > 30 and (x["reply_rate"] or 1) < 0.7]
    dim4 = {
        "one2one_count": len(one2one),
        "one_way_excluded": len(one_way),
        "reclassified_groups": reclassified,
        "relationships": rel_rows[:40],
        "neglected_1to1": neglected[:20],
    }

    analysis = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_messages": total, "self_messages": self_n, "them_messages": them_n,
            "chats": len(chats), "span_days": round(span_days, 1),
            "self_ratio": dim1["self_ratio"],
            "active_days": active_days,
        },
        "dim1_communication": dim1,
        "dim2_emotion": dim2,
        "dim3_time_energy": dim3,
        "dim4_relationship": dim4,
    }

    with open(os.path.join(args.outdir, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    _write_md(analysis, os.path.join(args.outdir, "analysis_report.md"))
    _write_html(analysis, os.path.join(args.outdir, "analysis_report.html"))

    sys.stderr.write("[analyze] 处理 %d 条消息 / %d 个会话, 用时 %.1fs\n" % (total, len(chats), time.time() - t0))
    sys.stderr.write("[analyze] 报告: analysis.json / analysis_report.md / analysis_report.html\n")
    return 0


def _std(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _fmt_min(sec):
    if sec is None:
        return "—"
    if sec < 60:
        return "%.0f秒" % sec
    if sec < 3600:
        return "%.1f分" % (sec / 60.0)
    if sec < 86400:
        return "%.1f时" % (sec / 3600.0)
    return "%.1f天" % (sec / 86400.0)


def _write_md(a, path):
    s = a["summary"]
    d1, d2, d3, d4 = a["dim1_communication"], a["dim2_emotion"], a["dim3_time_energy"], a["dim4_relationship"]
    L = []
    L.append("# 微信沟通行为自我分析报告\n")
    L.append("生成时间：%s  ｜ 数据跨度约 %.0f 天  ｜ 活跃 %d 天\n" % (
        a["generated_at"], s["span_days"], s["active_days"]))
    L.append("消息总量 **%d**（你 %d / 对方 %d，你占比 **%.1f%%**），覆盖 **%d** 个会话。\n" % (
        s["total_messages"], s["self_messages"], s["them_messages"], s["self_ratio"] * 100, s["chats"]))

    L.append("## 一、沟通主动性与回复模式\n")
    gl = d1["global_reply_latency_sec"]
    gs, os_ = d1["group_scope"], d1["one2one_scope"]
    L.append("**群聊口径**（%d 个群）：你发 %d / 对方发 %d，你占比 **%.1f%%**；线程由你发起 %d 次 / 对方发起 %d 次。" % (
        gs["chats"], gs["self_messages"], gs["them_messages"], gs["self_ratio"] * 100,
        gs["self_initiated_threads"], gs["them_initiated_threads"]))
    L.append("\n**1:1 口径**（%d 个会话）：你发 %d / 对方发 %d，你占比 **%.1f%%**；线程由你发起 %d 次 / 对方发起 %d 次。" % (
        os_["chats"], os_["self_messages"], os_["them_messages"], os_["self_ratio"] * 100,
        os_["self_initiated_threads"], os_["them_initiated_threads"]))
    L.append("\n- 你的整体回复时延（1:1+群内被@后跟帖）：中位 **%s**，均值 %s，P90 %s。" % (
        _fmt_min(gl["median"]), _fmt_min(gl["mean"]), _fmt_min(gl["p90"])))
    td = d1["type_distribution_self"]
    L.append("- 你发送消息类型分布（Top）：" + "，".join("%s %d" % (k, v) for k, v in td.items()) + "。\n")

    L.append("## 二、情绪表达与稳定性\n")
    L.append("- 正面线索 %d 次 / 负面线索 %d 次，正向率 **%.1f%%**。" % (
        d2["pos_cue_total"], d2["neg_cue_total"], d2["pos_rate"] * 100))
    L.append("- 每日情感波动率（跨天标准差）**%.3f**，数值越低越平稳。" % d2["daily_sentiment_volatility"])
    L.append("- 表达强度：emoji 率 %.1f%%，感叹号率 %.1f%%，问号率 %.1f%%。\n" % (
        d2["emoji_rate"] * 100, d2["exclamation_rate"] * 100, d2["question_rate"] * 100))

    L.append("## 三、时间与精力分配\n")
    L.append("- 日均发送 **%.1f** 条；最活跃时段 **%02d:00**，最活跃星期 **%s**。" % (
        d3["msgs_per_active_day"], d3["busiest_hour"], d3["dow_histogram"]["labels"][d3["busiest_dow"]]))
    L.append("- 精力投入 Top 聊天·群聊（按你发送量）：\n")
    L.append("| 会话 | 你发 | 对方发 | 字数 |")
    L.append("|---|---|---|---|")
    for c in d3["top_energy_chats"][:10]:
        L.append("| %s | %d | %d | %d |" % (c["name"], c["self_msgs"], c["them_msgs"], c["words_sent"]))
    L.append("")
    L.append("- 精力投入 Top·1:1（按你发送量）：\n")
    L.append("| 会话 | 你发 | 对方发 | 字数 |")
    L.append("|---|---|---|---|")
    for c in d3["top_energy_1to1"][:10]:
        L.append("| %s | %d | %d | %d |" % (c["name"], c["self_msgs"], c["them_msgs"], c["words_sent"]))
    L.append("")

    L.append("## 四、关系维护质量（1:1 会话，已排除单向/推送类及已退出的群）\n")
    L.append("- 纳入统计的 1:1 关系 **%d** 个（另排除单向/推送类 %d 个；**识别出已退群/解散的群 %d 个**，已归入群聊口径）。\n" % (
        d4["one2one_count"], d4["one_way_excluded"], d4["reclassified_groups"]))
    L.append("| 关系 | 总量 | 你占比 | 回复率 | 平均回复 | 寒暄 | 静默(天) |")
    L.append("|---|---|---|---|---|---|---|")
    for x in d4["relationships"][:15]:
        L.append("| %s | %d | %.0f%% | %s | %s | %d | %s |" % (
            x["name"], x["total"], x["self_ratio"] * 100,
            ("%.0f%%" % (x["reply_rate"] * 100)) if x["reply_rate"] is not None else "—",
            _fmt_min(x["mean_reply_min"] * 60) if x["mean_reply_min"] else "—",
            x["greet_self"], x["silence_days"] if x["silence_days"] is not None else "—"))
    if d4["neglected_1to1"]:
        L.append("\n- ⚠️ 疑似被冷落/久未互动的 1:1 关系（静默>30天且回复率<70%）：")
        for x in d4["neglected_1to1"][:10]:
            L.append("  - %s（静默 %.0f 天，你占比 %.0f%%）" % (x["name"], x["silence_days"], x["self_ratio"] * 100))
    else:
        L.append("\n- 未发现明显被冷落的 1:1 关系。")

    L.append("\n---\n*情感为离线词典启发式打分，仅供行为趋势参考，非心理学诊断。*")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---- HTML 模板（纯字符串，用 .replace 注入，避免 % 与 {} 冲突）----
_HTML_HEAD = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信沟通行为自我分析</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f6f7fb;color:#222;margin:0;padding:24px}
.card{background:#fff;border-radius:14px;box-shadow:0 2px 10px #0001;padding:18px;margin:16px 0}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:18px 0 8px;color:#1f6feb}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.kpi{background:#eef3ff;border-radius:10px;padding:12px}.kpi b{font-size:20px;color:#1f6feb}
canvas{max-height:320px}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #e3e6ee;padding:6px 8px;text-align:left}.neg{color:#c0392b}.pos{color:#1e8449}</style></head>
<body>
<h1>微信沟通行为自我分析</h1>
<div class="grid">
  <div class="kpi">消息总量<b>/*TOTAL*/</b></div>
  <div class="kpi">你占比<b>/*RATIO*/%</b></div>
  <div class="kpi">会话数<b>/*CHATS*/</b></div>
  <div class="kpi">活跃天数<b>/*DAYS*/</b></div>
</div>
<div class="card"><h2>三、时间与精力分配</h2>
  <div class="grid"><div><b>每日活跃时段</b><canvas id="hour"></canvas></div>
  <div><b>星期分布</b><canvas id="dow"></canvas></div></div>
  <b>精力投入 Top10 聊天</b><canvas id="energy"></canvas>
</div>
<div class="card"><h2>四、关系维护质量（1:1）</h2>
  <table><thead><tr><th>关系</th><th>总量</th><th>你占比</th><th>回复率</th><th>平均回复</th><th>静默(天)</th></tr></thead><tbody>"""

_HTML_TAIL = """</tbody></table>
</div>
<script>
const data = /*DATA*/;
new Chart(document.getElementById('hour'), {type:'bar',data:{labels:[...Array(24).keys()].map(h=>h+':00'),datasets:[{label:'你发送量',data:data.hour,backgroundColor:'#1f6feb'}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
new Chart(document.getElementById('dow'), {type:'bar',data:{labels:data.dow_labels,datasets:[{label:'你发送量',data:data.dow_values,backgroundColor:'#27ae60'}]},options:{plugins:{legend:{display:false}}}});
new Chart(document.getElementById('energy'),{type:'bar',data:{labels:data.energy.map(c=>c.name),datasets:[{label:'你发',data:data.energy.map(c=>c.self_msgs),backgroundColor:'#1f6feb'},{label:'对方发',data:data.energy.map(c=>c.them_msgs),backgroundColor:'#e67e22'}]},options:{indexAxis:'y'}});
</script></body></html>"""


def _write_html(a, path):
    d3 = a["dim3_time_energy"]
    d4 = a["dim4_relationship"]
    rel = d4["relationships"][:30]
    rows = "".join(
        "<tr><td>%s</td><td>%d</td><td>%.0f%%</td><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>" % (
            x["name"], x["total"], x["self_ratio"] * 100,
            ("%.0f%%" % (x["reply_rate"] * 100)) if x["reply_rate"] is not None else "—",
            _fmt_min(x["mean_reply_min"] * 60) if x["mean_reply_min"] else "—",
            "neg" if (x["silence_days"] or 0) > 30 else "",
            x["silence_days"] if x["silence_days"] is not None else "—",
        ) for x in rel
    )
    payload = {
        "hour": d3["hour_histogram"],
        "dow_labels": d3["dow_histogram"]["labels"],
        "dow_values": d3["dow_histogram"]["values"],
        "energy": d3["top_energy_chats"][:10],
    }
    html = _HTML_HEAD + rows + _HTML_TAIL
    html = (html
            .replace("/*TOTAL*/", str(a["summary"]["total_messages"]))
            .replace("/*RATIO*/", str(round(a["summary"]["self_ratio"] * 100, 1)))
            .replace("/*CHATS*/", str(a["summary"]["chats"]))
            .replace("/*DAYS*/", str(a["summary"]["active_days"]))
            .replace("/*DATA*/", json.dumps(payload, ensure_ascii=False)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    sys.exit(main())
