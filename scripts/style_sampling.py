#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""沟通风格分析素材包：按 8 类场景抽样（带上下文）+ 语言指纹量化。

输出: export/_style_samples.txt      供 LLM 通读的素材包
      export/_style_fingerprint.json 语言指纹（口头禅/标点/emoji/连发）
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
OUT_S = os.path.join(SKILL_ROOT, "output", "_style_samples.txt")
OUT_F = os.path.join(SKILL_ROOT, "output", "_style_fingerprint.json")

PRICE_RE = re.compile(r"(?:¥|￥)|\d+(?:\.\d+)?\s*万|\d+\s*元")
NEG_RE = re.compile(r"(不行|不对|不是这样|烦|气死|投诉|骗子|坑|扯皮|违约|道歉|无语|服了| rejection|拒绝)")
REFUSE_RE = re.compile(r"(做不了|做不到|没法|不接|算了|不干|婉拒|不要|不买|不参与)")
GREET_RE = re.compile(r"(早安|早上好|晚安|在吗|好久不见|最近怎|咋样|新年好|中秋|端午|生日快)")
QUESTION_RE = re.compile(r"[？?]\s*$")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F\U0001F1E6-\U0001F1FF\u2600-\u27BF]")


def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def main():
    # ---- 全量自读一遍：缓存 self 消息 + 上下文窗口 ----
    # 为拿到上下文，逐行存 (t, chat, side, type, content, sender_name) 于滑动窗口
    window = collections.deque(maxlen=5)   # 最近 5 条（全会话）
    scenes = {k: [] for k in ["观点", "报价谈判", "提问", "冲突不满", "拒绝", "寒暄", "解答", "深夜"]}
    caps = {"观点": 45, "报价谈判": 45, "提问": 40, "冲突不满": 30,
            "拒绝": 30, "寒暄": 30, "解答": 40, "深夜": 25}

    # 指纹
    bigrams = collections.Counter()
    trigrams = collections.Counter()
    particles = collections.Counter()
    emojis = collections.Counter()
    lens = []
    bursts = []            # 每次连发的条数
    burst_now = 1
    prev_t = None
    prev_chat = None
    punct = collections.Counter()
    total_text = 0

    QA = []                # (question, my answer) 群内解答候选
    last_q = None

    t0 = time.time()
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = epoch(rec.get("create_time"))
            chat = rec.get("chat", "")
            side = rec.get("side")
            mtype = rec.get("type")
            c = rec.get("content") or ""
            if not isinstance(c, str):
                c = ""
            ctx = {"t": t, "chat": (rec.get("chat_name") or chat)[:14],
                   "side": side, "type": mtype,
                   "c": re.sub(r"\s+", " ", c.replace("\n", " "))[:150]}

            # ---- self 消息处理 ----
            if side == "self":
                is_text = (mtype == "文本" and c and not c.lstrip().startswith(("<", "{")))
                if is_text:
                    total_text += 1
                    text = c.strip()
                    lens.append(len(text))
                    # 连发
                    if prev_t is not None and prev_chat == chat and 0 <= t - prev_t <= 60:
                        burst_now += 1
                    else:
                        if burst_now > 1:
                            bursts.append(burst_now)
                        burst_now = 1
                    # 语气词/标点/emoji
                    for p in ["哈哈", "呢", "吧", "嘛", "哦", "嗯", "哈", "呀", "啦", "咯", "呗", "哎"]:
                        particles[p] += len(re.findall(re.escape(p), text))
                    for p in ["！", "？", "…", "~", "。"]:
                        punct[p] += text.count(p)
                    for e in EMOJI_RE.findall(text):
                        emojis[e] += 1
                    # n-gram（去标点，长度过滤）
                    clean = re.sub(r"[^\u4e00-\u9fff]", " ", text)
                    for seg in clean.split():
                        for i in range(len(seg) - 1):
                            bigrams[seg[i:i + 2]] += 1
                        for i in range(len(seg) - 2):
                            trigrams[seg[i:i + 3]] += 1
                    # 场景
                    d = datetime.datetime.fromtimestamp(t)
                    y = d.year
                    if not (2019 <= y <= 2026):
                        continue
                    def add(cat):
                        if len(scenes[cat]) < caps[cat]:
                            scenes[cat].append((t, list(window), ctx))
                    if len(text) >= 80:
                        add("观点")
                    if PRICE_RE.search(text) and len(text) >= 10:
                        add("报价谈判")
                    if QUESTION_RE.search(text) and 8 <= len(text) <= 100:
                        add("提问")
                    if NEG_RE.search(text):
                        add("冲突不满")
                    if REFUSE_RE.search(text) and 5 <= len(text) <= 100:
                        add("拒绝")
                    if GREET_RE.search(text) and len(text) <= 60:
                        add("寒暄")
                    if d.hour <= 5 and 10 <= len(text) <= 200:
                        add("深夜")
                # 群内解答（紧跟提问的实质回答）
                if last_q and last_q[1] == chat and 0 <= (t or 0) - last_q[0] <= 600 \
                        and is_text and 40 <= len(c) <= 400 and len(QA) < 60:
                    QA.append((last_q[2], c[:250]))
                    last_q = None
                prev_t, prev_chat = t, chat
            else:
                if mtype == "文本" and ("？" in c or "?" in c) and 8 <= len(c) <= 120:
                    last_q = (t, chat, c.strip()[:100])
                if prev_chat == chat and prev_t is not None and (t is None or t - prev_t > 60):
                    if burst_now > 1:
                        bursts.append(burst_now)
                    burst_now = 1
                prev_t, prev_chat = t, chat
            window.append(ctx)

    if burst_now > 1:
        bursts.append(burst_now)

    # ---- 写素材包 ----
    STOP_BI = {"这个", "那个", "一下", "没有", "就是", "还是", "可以", "什么", "怎么", "现在",
               "时候", "知道", "觉得", "可能", "应该", "一个", "我们", "你们", "他们", "自己",
               "已经", "所以", "但是", "因为", "如果", "需要", "里面", "问题", "明天", "今天"}
    with open(OUT_S, "w", encoding="utf-8") as f:
        f.write("沟通风格分析素材包（生成 %s）\n" % time.strftime("%Y-%m-%d %H:%M"))
        f.write("说明：【场景】标签 + 上下文（对方=TA，我=我），最后一行带 ◆ 的是我发的消息。\n\n")
        for cat, items in scenes.items():
            f.write("=" * 30 + " 场景：%s（%d 条） " % (cat, len(items)) + "=" * 30 + "\n")
            for t, win, cur in items:
                d = datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else "?"
                f.write("---- %s ｜ %s\n" % (d, cur["chat"]))
                for w in win[-4:]:
                    if w is cur:
                        continue
                    who = "我" if w["side"] == "self" else "TA"
                    f.write("  [%s] %s：%s\n" % (who, w["type"], w["c"][:110]))
                f.write("  ◆ [%s] %s：%s\n" % ("我", cur["type"], cur["c"][:200]))
            f.write("\n")
        f.write("=" * 30 + " 场景：群内解答（问→答，%d 对） " % len(QA) + "=" * 30 + "\n")
        for q, a in QA:
            f.write("  问：%s\n  ◆ 答：%s\n\n" % (q, a.replace("\n", " ")[:250]))

    # ---- 指纹 ----
    lens.sort()
    def pct(p):
        return lens[int(len(lens) * p)] if lens else 0
    fp = {
        "total_text_msgs": total_text,
        "len_median": pct(0.5), "len_p90": pct(0.9),
        "top_bigrams": [w for w, _ in bigrams.most_common(200) if w not in STOP_BI][:30],
        "top_trigrams": [w for w, _ in trigrams.most_common(60) if not any(s in w for s in STOP_BI)][:20],
        "particles": dict(particles.most_common(12)),
        "punct": dict(punct),
        "emoji_top": dict(emojis.most_common(12)),
        "burst_avg": round(sum(bursts) / len(bursts), 2) if bursts else 1.0,
        "burst_p90": sorted(bursts)[int(len(bursts) * 0.9)] if bursts else 1,
        "burst_count": len(bursts),
    }
    with open(OUT_F, "w", encoding="utf-8") as f:
        json.dump(fp, f, ensure_ascii=False, indent=1)

    n = sum(len(v) for v in scenes.values())
    print("抽样完成：场景消息 %d 条 + 解答对 %d；指纹：中位长度 %d，连发均值 %.1f" % (
        n, len(QA), fp["len_median"], fp["burst_avg"]))
    print("素材包: %s (%.0f KB)" % (OUT_S, os.path.getsize(OUT_S) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
