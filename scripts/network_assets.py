#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人脉资产盘点（创业前尽调）。

输出: export/network_assets.md   打分卡+标签+枢纽+转化路径
      export/network_graph.html  交互式人脉图谱(vis-network)

方法:
  Pass A(messages.jsonl 流式):
    - 群成员: 每个 @chatroom 里发言过的 sender_name → 成员(昵称)
    - 1:1 统计: 与 analyze_chats 同口径(量/回复率/字数/寒暄/静默) + 每关系文本样本
  Pass B(contact.db):
    - user→nick / nick→user 双向映射(跨群身份归一)
  计算: 共群枢纽 / 关系分级 / 行业标签 / 群→私聊转化
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
from wechatauto.db import WeChatDB

IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
OUT_MD = os.path.join(SKILL_ROOT, "output", "network_assets.md")
OUT_HTML = os.path.join(SKILL_ROOT, "output", "network_graph.html")

GREET_RE = re.compile(r"(早安|早上好|晚安|在吗|最近怎|咋样|好久不见|注意身体|休息)")
TAG_RULES = [
    ("无人机/低空", ["无人机", "大疆", "低空", "飞行", "航拍"]),
    ("自媒体/AI", ["自媒体", "AI", "智能体", "公众号", "工作流", "淘金", "一人公司", "coze", "Coze", "流量"]),
    ("考证/培训", ["一建", "二建", "建造师", "造价", "优路", "培训", "教育", "考证", "注册"]),
    ("音响/灯光", ["音响", "灯光", "音频", "扩声", "话筒", "舞台", "迪士普", "DSPPA", "锐丰", "音王", "嘉声"]),
    ("弱电/智能化", ["弱电", "智能化", "安防", "监控", "门禁", "布线", "楼控", "消防", "机电", "安装",
                    "智控", "信息", "网络", "科技", "集成", "智能"]),
    ("政企/事业单位", ["学校", "医院", "学院", "局", "委员会", "研究院", "设计院", "中心", "政府", "小学", "中学"]),
    ("房地产/物业", ["物业", "业主", "置业", "地产", "万科", "金地", "蜜城"]),
]

# 可选：从技能目录 config.json 覆盖行业标签词典（格式：[["标签名", ["关键词"...]], ...]）
try:
    with open(os.path.join(SKILL_ROOT, "config.json"), encoding="utf-8") as _cf:
        _cfg = json.load(_cf)
    if _cfg.get("industry_tags"):
        TAG_RULES = [(str(n), list(k)) for n, k in _cfg["industry_tags"]]
except Exception:
    pass
OTHERS_TAG = "其他"
# 退群/解散群识别（chat 名只剩 md5）
MD5_NAME_RE = re.compile(r"^[0-9a-f]{32}$")
PREFIX_RE = re.compile(r"^([A-Za-z0-9_@.\-]{3,45}):")
GROUP_SIG_RE = re.compile(r"(移出群聊|移出了群聊|解散|不是微信朋友关系|已被群主|群主已将|你已退出群聊)")


def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def tag_of(text):
    for name, kws in TAG_RULES:
        if any(k in text for k in kws):
            return name
    return OTHERS_TAG


def main():
    # ---------- Pass A ----------
    group_members = collections.defaultdict(set)   # group -> set(identity)
    member_groups = collections.defaultdict(set)   # identity -> set(group)
    member_msgs = collections.Counter()            # identity -> msgs in my groups
    md5_pending = {}                               # md5名会话 -> 群特征候选
    chats = {}                                     # 1:1 统计
    now = time.time()

    def get_chat(chat, name):
        if chat not in chats:
            chats[chat] = {"name": name, "n_self": 0, "n_them": 0,
                           "words_self": 0, "first": None, "last": None,
                           "lat_n": 0, "lat_sum": 0.0,
                           "thr_them": 0, "thr_ignored": 0, "greet": 0,
                           "samples": []}
        return chats[chat]

    cur = None; last_t = None; last_side = None
    thr_init = None; thr_replied = False

    def close_thr(r):
        nonlocal thr_init, thr_replied
        if thr_init == "them" and not thr_replied:
            r["thr_ignored"] += 1
        thr_init = None; thr_replied = False

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
            c = rec.get("content") or ""
            # md5 名会话：候选"已退群"，先暂存特征与成员，Pass A 结束后统一判定
            if MD5_NAME_RE.match(chat):
                p = md5_pending.setdefault(
                    chat, {"members": set(), "msgs": collections.Counter(),
                           "prefixes": set(), "sig": False})
                who = rec.get("sender_name") or ""
                if side != "self" and who and who != "我":
                    p["members"].add(who)
                    p["msgs"][who] += 1
                    if isinstance(c, str) and c:
                        m2 = PREFIX_RE.match(c)
                        if m2:
                            p["prefixes"].add(m2.group(1))
                        if GROUP_SIG_RE.search(c[:120]):
                            p["sig"] = True
                continue
            is_group = chat.endswith("@chatroom") or chat.startswith("@@")
            if is_group:
                who = rec.get("sender_name") or ""
                if who and side != "self" and who != "我":
                    group_members[chat].add(who)
                    member_groups[who].add(chat)
                    member_msgs[who] += 1
                continue
            # 1:1
            r = get_chat(chat, rec.get("chat_name") or chat)
            if chat != cur:
                if cur is not None and cur in chats:
                    close_thr(chats[cur])
                cur = chat; last_t = None; last_side = None
                thr_init = None; thr_replied = False
            c = rec.get("content") or ""
            if side == "self":
                r["n_self"] += 1
                if rec.get("type") == "文本" and isinstance(c, str):
                    r["words_self"] += len(c)
                    if GREET_RE.search(c):
                        r["greet"] += 1
            else:
                r["n_them"] += 1
                if rec.get("type") == "文本" and isinstance(c, str) and len(c) <= 150:
                    if len(r["samples"]) < 5:
                        r["samples"].append(c[:100])
            if t:
                if r["first"] is None or t < r["first"]:
                    r["first"] = t
                if r["last"] is None or t > r["last"]:
                    r["last"] = t
            if t is not None:
                if last_t is None:
                    thr_init = side; thr_replied = (side == "self")
                    if side == "them":
                        r["thr_them"] += 1
                elif t >= last_t:
                    gap = t - last_t
                    if gap > 6 * 3600:
                        close_thr(r)
                        thr_init = side; thr_replied = (side == "self")
                        if side == "them":
                            r["thr_them"] += 1
                    elif side == "self" and last_side == "them":
                        thr_replied = True
                        r["lat_n"] += 1; r["lat_sum"] += gap
                last_t = t; last_side = side
    if cur is not None and cur in chats:
        close_thr(chats[cur])

    # md5 候选群判定：多发言人前缀(≥3) 或退群系统消息 → 归入群网络
    reclassified = 0
    for chat, p in md5_pending.items():
        if len(p["prefixes"]) >= 3 or p["sig"]:
            group_members[chat] |= p["members"]
            for who in p["members"]:
                member_groups[who].add(chat)
                member_msgs[who] += p["msgs"][who]
            reclassified += 1
    print("Pass A 完成: 群 %d 个(+md5 判定 %d), 群成员(昵称) %d 人, 1:1 会话 %d 个, %.0fs" % (
        len(group_members), reclassified, len(member_groups), len(chats), time.time() - t0))

    # ---------- Pass B: contact.db 映射 ----------
    user2nick, nick2user = {}, {}
    db = WeChatDB(workdir=os.path.join(SKILL_ROOT, ".wc_cache", "dump"))
    for rel, path, _ in db._db_files:
        if os.path.basename(path) != "contact.db":
            continue
        conn = db._open(rel)
        try:
            for u, n, rk in conn.execute(
                    "SELECT username, nick_name, remark FROM contact"):
                disp = rk or n or ""
                if u and disp:
                    user2nick[u] = disp
                    nick2user.setdefault(disp, u)
                    nick2user.setdefault(n or disp, u)
        finally:
            conn.close()
        break

    # ---------- 计算 ----------
    def disp(user):
        return user2nick.get(user, user)

    # 身份归一：群成员昵称 -> username（能对上的）
    identity_groups = collections.defaultdict(set)
    identity_msgs = collections.Counter()
    for nick, gs in member_groups.items():
        ident = nick2user.get(nick, nick)
        identity_groups[ident] |= gs
        identity_msgs[ident] += member_msgs[nick]

    # 1:1 关系打分卡
    rels = []
    for chat, r in chats.items():
        total = r["n_self"] + r["n_them"]
        if total < 20 or r["n_self"] < 5:
            continue
        reply_rate = None
        if r["thr_them"]:
            reply_rate = 1.0 - r["thr_ignored"] / r["thr_them"]
        silence = (now - r["last"]) / 86400.0 if r["last"] else None
        mean_lat = r["lat_sum"] / r["lat_n"] if r["lat_n"] else None
        origin = "群认识" if chat in identity_groups else "直接添加"
        text_tag = " ".join(r["samples"])
        tag = tag_of(r["name"]) if tag_of(r["name"]) != OTHERS_TAG else tag_of(text_tag)
        if silence is not None and reply_rate is not None:
            if reply_rate >= 0.75 and total >= 200 and silence <= 60:
                tier = "核心挚友"
            elif silence <= 60 and total >= 50:
                tier = "活跃关系"
            elif total >= 150 and silence > 365:
                tier = "沉睡资产"
            elif 60 < silence <= 365 and total >= 50:
                tier = "待激活"
            else:
                tier = "一般联系人"
        else:
            tier = "一般联系人"
        rels.append({
            "chat": chat, "name": r["name"], "total": total,
            "n_self": r["n_self"], "n_them": r["n_them"],
            "words_self": r["words_self"], "first": r["first"],
            "reply_rate": reply_rate, "mean_lat": mean_lat,
            "greet": r["greet"], "silence": silence,
            "origin": origin, "tag": tag, "tier": tier,
        })
    rels.sort(key=lambda x: -x["total"])

    # 群→私聊转化（按首联年份）
    conv_by_year = collections.defaultdict(lambda: [0, 0])
    for x in rels:
        fy = datetime.datetime.fromtimestamp(x["first"]).year if x["first"] else None
        if fy and 2019 <= fy <= 2026:
            conv_by_year[fy][1] += 1
            if x["origin"] == "群认识":
                conv_by_year[fy][0] += 1

    # 共群枢纽（与我共享群数 Top）——排除 1:1 对端以外也要统计，但含对端更有意义
    hubs = sorted(identity_groups.items(), key=lambda x: -len(x[1]))[:40]
    top_persons = [ident for ident, _ in hubs]
    # 行业标签分布（1:1 核心关系）
    tag_dist = collections.Counter(x["tag"] for x in rels)

    # 图: 我 + Top35 枢纽/关系；边=共群数 或 1:1
    graph_persons = []
    seen = set()
    for x in rels[:35]:
        ident = nick2user.get(x["name"], x["name"])
        if ident not in seen:
            seen.add(ident)
            graph_persons.append(ident)
    for ident in top_persons:
        if len(graph_persons) >= 45:
            break
        if ident not in seen:
            seen.add(ident)
            graph_persons.append(ident)
    edges = []
    for i, a in enumerate(graph_persons):
        ga = identity_groups.get(a, set())
        w1to1 = 0
        # 1:1 边权：用消息总量
        rel_map = {nick2user.get(x["name"], x["name"]): x for x in rels}
        w = len(ga) * 2
        if a in rel_map:
            w += 15 + min(rel_map[a]["total"], 300) / 20.0
        edges.append({"from": "ME", "to": a, "value": round(w, 1),
                      "title": "1:1:%s / 共群:%d" % (
                          rel_map[a]["name"] if a in rel_map else "-", len(ga))})
        for b in graph_persons[i + 1:]:
            inter = len(ga & identity_groups.get(b, set()))
            if inter >= 2:
                edges.append({"from": a, "to": b, "value": inter,
                              "title": "共群 %d" % inter})
    nodes = [{"id": "ME", "label": "我", "group": "ME", "value": 30}]
    for a in graph_persons:
        if a == "ME":
            continue
        t = None
        for x in rels:
            if nick2user.get(x["name"], x["name"]) == a:
                t = x["tag"]; break
        if t is None:
            t = tag_of(a) if tag_of(a) != OTHERS_TAG else OTHERS_TAG
        nodes.append({"id": a, "label": disp(a)[:14], "group": t, "value": 8})

    # ---------- Markdown ----------
    L = ["# 人脉资产盘点报告\n"]
    L.append("生成：%s\n" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("## 一、总览\n")
    L.append("- 核心统计口径的 1:1 关系（≥20 条且你发过 ≥5 条）：**%d** 个" % len(rels))
    L.append("- 有过发言的群：**%d** 个，覆盖群成员（发言者）**%d** 人" % (
        len(group_members), len(member_groups)))
    tier_cnt = collections.Counter(x["tier"] for x in rels)
    L.append("- 关系分级：%s" % "，".join("%s **%d**" % (k, v)
                                          for k, v in tier_cnt.most_common()))
    origin_cnt = collections.Counter(x["origin"] for x in rels)
    L.append("- 来源构成：%s" % "，".join("%s **%d**（%.0f%%）" % (k, v, 100.0 * v / len(rels))
                                          for k, v in origin_cnt.most_common()))
    L.append("- 行业标签分布：%s\n" % "，".join("%s **%d**" % (k, v)
                                                for k, v in tag_dist.most_common()))

    L.append("## 二、关系打分卡 Top40\n")
    L.append("| 关系 | 总量 | 你占比 | 回复率 | 平均回复 | 寒暄 | 静默天 | 来源 | 标签 | 分级 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    def fmt_lat(x):
        if x["mean_lat"] is None: return "—"
        s = x["mean_lat"]
        return "%.0f秒" % s if s < 60 else ("%.1f分" % (s / 60) if s < 3600 else "%.1f时" % (s / 3600))
    for x in rels[:40]:
        L.append("| %s | %d | %.0f%% | %s | %s | %d | %.0f | %s | %s | **%s** |" % (
            x["name"][:14], x["total"], 100.0 * x["n_self"] / max(1, x["total"]),
            ("%.0f%%" % (x["reply_rate"] * 100)) if x["reply_rate"] is not None else "—",
            fmt_lat(x), x["greet"],
            x["silence"] if x["silence"] is not None else -1,
            x["origin"], x["tag"], x["tier"]))
    L.append("")

    for tier in ["核心挚友", "活跃关系", "待激活", "沉睡资产"]:
        items = [x for x in rels if x["tier"] == tier]
        if not items:
            continue
        L.append("### %s（%d 人，按总量取前 12）\n" % (tier, len(items)))
        for x in items[:12]:
            L.append("- **%s**（%d 条，静默 %.0f 天，%s）" % (
                x["name"], x["total"], x["silence"] or -1, x["tag"]))
        L.append("")

    L.append("## 三、共群枢纽 Top30（与你在最多群里共存的人）\n")
    L.append("| 人 | 共享群数 | 群内发言 | 标签 |")
    L.append("|---|---|---|---|")
    for ident, gs in hubs[:30]:
        L.append("| %s | %d | %d | %s |" % (
            disp(ident)[:14], len(gs), identity_msgs[ident],
            tag_of(disp(ident)) if tag_of(disp(ident)) != OTHERS_TAG else OTHERS_TAG))
    L.append("")

    L.append("## 四、群→私聊转化路径（你的关系从哪来）\n")
    L.append("| 首联年份 | 新增核心关系 | 其中群认识 | 转化率 |")
    L.append("|---|---|---|---|")
    for y in sorted(conv_by_year):
        a, b = conv_by_year[y]
        L.append("| %d | %d | %d | %.0f%% |" % (y, b, a, 100.0 * a / max(1, b)))
    L.append("\n*口径：该 1:1 对端曾在你的任一群里发过言，即记为「群认识」。*\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ---------- HTML 图谱 ----------
    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>人脉网络图谱</title>
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.3.0/dist/vis-network.min.js"></script>
<style>body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;padding:16px;background:#f6f7fb}
#net{width:100%;height:92vh;background:#fff;border-radius:14px;box-shadow:0 2px 10px #0001}
.legend{font-size:13px;margin:8px 4px}.legend span{display:inline-block;padding:2px 10px;border-radius:10px;margin-right:8px;color:#fff}</style>
</head><body>
<div class="legend">人脉核心圈（Top 节点；边宽=共群数/1:1 强度）
<span style="background:#e67e22">弱电/智能化</span><span style="background:#16a085">音响/灯光</span>
<span style="background:#8e44ad">考证/培训</span><span style="background:#1f6feb">自媒体/AI</span>
<span style="background:#c0392b">无人机/低空</span><span style="background:#2c3e50">政企</span>
<span style="background:#7f8c8d">其他</span></div>
<div id="net"></div>
<script>
const nodes=__NODES__, edges=__EDGES__;
const colors={"ME":"#111111","弱电/智能化":"#e67e22","音响/灯光":"#16a085","考证/培训":"#8e44ad",
"自媒体/AI":"#1f6feb","无人机/低空":"#c0392b","政企/事业单位":"#2c3e50","房地产/物业":"#d35400","其他":"#7f8c8d"};
nodes.forEach(n=>{n.color=colors[n.group]||"#7f8c8d";n.font={size:14};n.shape="dot";});
const net=new vis.Network(document.getElementById('net'),
 {nodes:new vis.DataSet(nodes),edges:new vis.DataSet(edges)},
 {edges:{scaling:{min:1,max:12}},physics:{barnesHut:{gravitationalConstant:-8000}},interaction:{hover:true}});
</script></body></html>"""
    html = (html.replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
                .replace("__EDGES__", json.dumps(edges, ensure_ascii=False)))
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print("人脉盘点完成，用时 %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
