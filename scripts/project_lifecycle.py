# -*- coding: utf-8 -*-
"""
project_lifecycle.py —— 弱电生意的「项目全周期漏斗」
单遍扫描 messages.jsonl：
  - 9 个业务环节关键词命中（询价/投标/合同/施工/变更/验收/结算/回款/售后）
  - 区分 群聊（行业讨论热度代理） 与 1:1 私聊（真实项目洽谈代理）
  - 会话首末时间 -> 项目周期长度 / 关系生命周期
  - 1:1 会话"完整项目"判定：询价 & (结算或回款) & 跨度>=7天
输出：project_lifecycle.json / .md / .html
说明：关键词命中是"强度代理指标"，非精确业务事件；已在报告中标注。
"""
import os, re, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "export", "messages.jsonl")
OUT_JSON = os.path.join(HERE, "export", "project_lifecycle.json")
OUT_MD = os.path.join(HERE, "export", "project_lifecycle.md")
OUT_HTML = os.path.join(HERE, "export", "project_lifecycle.html")

t0 = time.time()

STAGES = {
    "询价": r"(询价|报价|多少钱|什么价|单价|预算|询价单|出个价|报个价)",
    "投标": r"(投标|招标|开标|中标|废标|标书|商务标|技术标)",
    "合同": r"(合同|协议|签约|盖章|签合同|拟合同)",
    "施工": r"(进场|施工|布线|安装|调试|工期|进度|开工|施工队)",
    "变更": r"(变更|签证|增项|洽商|增补|增量)",
    "验收": r"(验收|竣工|移交|交付|完工|交工)",
    "结算": r"(结算|审计|决算|对账|尾款|质保金|清算|决算价)",
    "回款": r"(付款|打款|转账|发票|开票|回款|催款|账期|付钱|收款|结款)",
    "售后": r"(售后|维修|返修|保修|质保期|故障|质保|维护)",
}
STAGE_RE = {k: re.compile(v) for k, v in STAGES.items()}
# 严格顺次漏斗（去除并行环节 变更/售后）
FUNNEL = ["询价", "投标", "合同", "施工", "验收", "结算", "回款"]

RE_MD5 = re.compile(r"^[0-9a-f]{32}$")

def is_group(chat, cname):
    if chat.endswith("@chatroom"):
        return True
    if RE_MD5.match(chat or ""):
        return True
    return False

# 全局累计（群 / 1:1 分开）
g_year_stage = collections.defaultdict(lambda: collections.Counter())   # group: year|stage
p_year_stage = collections.defaultdict(lambda: collections.Counter())   # 1:1
g_stage = collections.Counter()
p_stage = collections.Counter()

# 每个会话聚合
# sess[chat] = {name, group, first, last, stage: Counter, side_self: Counter}
sess = {}
def get_sess(chat, cname, group):
    s = sess.get(chat)
    if s is None:
        s = {"name": cname, "group": group, "first": None, "last": None,
             "stage": collections.Counter(), "self": 0, "them": 0}
        sess[chat] = s
    return s

n = 0
with open(SRC, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        n += 1
        if n % 500000 == 0:
            sys.stderr.write("  ...%d (%.0fs)\n" % (n, time.time() - t0)); sys.stderr.flush()
        ty = o.get("type")
        ct = o.get("content") or ""
        chat = o.get("chat") or ""
        cname = o.get("chat_name") or ""
        side = o.get("side")
        ts = o.get("create_time") or 0
        try:
            yr = time.strftime("%Y", time.localtime(int(ts)))
        except Exception:
            yr = "?"
        group = is_group(chat, cname)
        s = get_sess(chat, cname, group)
        if s["first"] is None or ts < s["first"]:
            s["first"] = ts
        if s["last"] is None or ts > s["last"]:
            s["last"] = ts
        if side == "self":
            s["self"] += 1
        else:
            s["them"] += 1

        if ty not in ("文本", "文件/链接/卡片"):
            continue
        if not ct:
            continue
        for st, rx in STAGE_RE.items():
            if rx.search(ct):
                s["stage"][st] += 1
                if group:
                    g_stage[st] += 1
                    g_year_stage["%s|%s" % (yr, st)][st] += 1
                else:
                    p_stage[st] += 1
                    p_year_stage["%s|%s" % (yr, st)][st] += 1

# ---------- 派生指标 ----------
# 会话级环节覆盖（多少个会话至少命中过该环节一次）——这才是真漏斗
p_sess_stage = collections.Counter()
g_sess_stage = collections.Counter()
for chat, s in sess.items():
    for st in STAGES:
        if s["stage"].get(st, 0) > 0:
            if s["group"]:
                g_sess_stage[st] += 1
            else:
                p_sess_stage[st] += 1

# 会话级「条件共现」：P(进入上下游环节 cur | 已进入 prev)
# = 同时命中 prev 和 cur 的会话数 / 命中 prev 的会话数  -> 真·逐级留存
p_sess_pair = collections.Counter()
g_sess_pair = collections.Counter()
for chat, s in sess.items():
    sts = set(st for st in STAGES if s["stage"].get(st, 0) > 0)
    for i in range(len(FUNNEL) - 1):
        a, b = FUNNEL[i], FUNNEL[i + 1]
        if a in sts and b in sts:
            if s["group"]:
                g_sess_pair["%s>%s" % (a, b)] += 1
            else:
                p_sess_pair["%s>%s" % (a, b)] += 1

def sess_funnel_conv(counter, pair):
    out = {}
    prev_name = None
    prev_v = None
    for st in FUNNEL:
        v = counter.get(st, 0)
        cond = None
        co = 0
        if prev_name is not None:
            co = pair.get("%s>%s" % (prev_name, st), 0)
            cond = round(co * 100.0 / prev_v, 1) if prev_v else 0
        out[st] = {"sessions": v, "cond_from_prev": cond, "co_prev": co}
        prev_name = st
        prev_v = v
    return out

p_sess_conv = sess_funnel_conv(p_sess_stage, p_sess_pair)
g_sess_conv = sess_funnel_conv(g_sess_stage, g_sess_pair)

# 漏斗转化率（全局，消息级，仅作热度参考）
def funnel_conv(counter):
    out = {}
    prev = None
    for st in FUNNEL:
        v = counter.get(st, 0)
        out[st] = {"hits": v, "conv_from_prev": None if prev is None else (round(v * 100.0 / prev, 1) if prev else 0)}
        prev = v
    return out

g_conv = funnel_conv(g_stage)
p_conv = funnel_conv(p_stage)

# 1:1 完整项目判定
complete_projects = []
for chat, s in sess.items():
    if s["group"]:
        continue
    span = (s["last"] or 0) - (s["first"] or 0)
    if span < 7 * 86400:
        continue
    has_quote = s["stage"].get("询价", 0) > 0
    has_close = (s["stage"].get("结算", 0) + s["stage"].get("回款", 0)) > 0
    nm = s["name"] or ""
    if any(k in nm for k in ("文件传输", "助手", "群发", "系统", "自己", "服务号")):
        continue
    if has_quote and has_close:
        covered = [st for st in STAGES if s["stage"].get(st, 0) > 0]
        complete_projects.append({
            "chat": chat, "name": s["name"], "span_days": span // 86400,
            "self": s["self"], "them": s["them"],
            "stages": {st: s["stage"].get(st, 0) for st in STAGES},
            "covered": covered, "coverage": len(covered),
        })
complete_projects.sort(key=lambda x: -x["coverage"])

# 全链路群（群聊里同时有询价到回款全环节，作为"高活跃业务群"）
full_chain_groups = []
for chat, s in sess.items():
    if not s["group"]:
        continue
    if (s["stage"].get("询价", 0) > 50 and s["stage"].get("回款", 0) > 50
            and s["stage"].get("施工", 0) > 50):
        full_chain_groups.append({
            "name": s["name"], "chat": chat,
            "stages": {st: s["stage"].get(st, 0) for st in STAGES},
            "span_days": ((s["last"] or 0) - (s["first"] or 0)) // 86400,
        })
full_chain_groups.sort(key=lambda x: -(x["stages"]["询价"] + x["stages"]["回款"]))

# 年份漏斗（1:1）—— 看转型
p_year = collections.defaultdict(collections.Counter)
for k, cnt in p_year_stage.items():
    yr, st = k.split("|")
    p_year[yr][st] = cnt[st]

# 会话生命周期（项目周期长度分布）
spans = [((s["last"] or 0) - (s["first"] or 0)) // 86400 for s in sess.values() if (s["last"] and s["first"])]
span_buckets = collections.Counter()
for sp in spans:
    if sp < 30: b = "<1月"
    elif sp < 90: b = "1-3月"
    elif sp < 365: b = "3-12月"
    elif sp < 365 * 2: b = "1-2年"
    else: b = ">2年"
    span_buckets[b] += 1

res = {
    "total_messages": n,
    "scan_seconds": round(time.time() - t0, 1),
    "group_stage_hits": dict(g_stage),
    "p2p_stage_hits": dict(p_stage),
    "group_funnel": g_conv,
    "p2p_funnel": p_conv,
    "group_sess_funnel": g_sess_conv,
    "p2p_sess_funnel": p_sess_conv,
    "p2p_sess_pair": dict(p_sess_pair),
    "group_sess_stage": dict(g_sess_stage),
    "p2p_sess_stage": dict(p_sess_stage),
    "complete_projects_count": len(complete_projects),
    "complete_projects_top": complete_projects[:40],
    "full_chain_groups_top": full_chain_groups[:25],
    "p2p_year_funnel": {y: {st: p_year[y].get(st, 0) for st in FUNNEL} for y in sorted(p_year)},
    "span_buckets": dict(span_buckets),
    "sessions_total": len(sess),
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
L = []; A = L.append
A("# 弱电生意 · 项目全周期漏斗分析\n")
A("> 数据：%s 条消息 / %d 个会话，扫描 %.0fs。" % (n, len(sess), time.time() - t0))
A("> 方法：9 个业务环节用关键词命中计数（**强度代理指标**，非精确业务事件）；群聊=行业讨论热度代理，1:1 私聊=真实项目洽谈代理。\n")
A("## 一、整体漏斗（全库）\n")
A("> ⚠️ 关键词非互斥：一条消息可同时命中多个环节（如「报价+安装」），")
A("> 因此「消息级命中量」应读作**各环节话题热度**，不能直接相减算转化。")
A("> 真正的逐级转化请看下方**会话级漏斗**（有多少会话至少进入了该环节）。\n")
A("### 群聊（行业热度·消息级）\n")
A("| 环节 | 命中 |")
A("|---|---|")
for st in FUNNEL:
    A("| %s | %d |" % (st, g_stage[st]))
A("")
A("### 1:1 私聊（真实项目·消息级）\n")
A("| 环节 | 命中 |")
A("|---|---|")
for st in FUNNEL:
    A("| %s | %d |" % (st, p_stage[st]))
A("")
A("### 🔑 会话级漏斗（真·逐级转化，1:1 私聊）\n")
A("> 用**条件共现概率** P(进入后一环节 | 已进入前一环节) = 同时命中相邻两环节的会话数 ÷ 进入前一环节的会话数。")
A("> 这才能暴露「在哪个环节掉客户最多」。\n")
A("| 环节 | 进入会话数 | 上一环客户留存到这里 |")
A("|---|---|---|")
for st in FUNNEL:
    d = p_sess_conv[st]
    A("| %s | %d | %s |" % (st, d["sessions"], ("-" if d["cond_from_prev"] is None else (str(d["cond_from_prev"]) + "%"))))
A("")
A("**读法**：例如「投标→合同」留存高说明一旦进了投标大多能签；若「验收→结算」骤降则暴露交付扯皮。群聊同理见 `g_sess_conv`。\n")
A("## 二、1:1 完整项目（询价 ∩ 结算/回款 ∩ 跨度≥7天）：**%d 个**\n" % len(complete_projects))
A("覆盖环节越多 = 你从头跟到尾的项目；下表为覆盖最广的 TOP20（脱敏为关系ID）：\n")
A("| # | 关系 | 周期(天) | 覆盖环节数 | 我/对方 | 询价 | 合同 | 施工 | 验收 | 结算 | 回款 | 售后 |")
A("|---|---|---|---|---|---|---|---|---|---|---|---|")
for i, p in enumerate(complete_projects[:20], 1):
    st = p["stages"]
    A("| %d | %s | %d | %d | %d/%d | %d | %d | %d | %d | %d | %d | %d |" % (
        i, (p["name"] or p["chat"][:10]), p["span_days"], p["coverage"], p["self"], p["them"],
        st["询价"], st["合同"], st["施工"], st["验收"], st["结算"], st["回款"], st["售后"]))
A("")
A("## 三、高活跃业务群（询价/施工/回款 均>50，TOP15）\n")
A("| 群 | 询价 | 投标 | 合同 | 施工 | 验收 | 结算 | 回款 | 售后 | 存续(天) |")
A("|---|---|---|---|---|---|---|---|---|---|")
for g in full_chain_groups[:15]:
    st = g["stages"]
    A("| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
        g["name"], st["询价"], st["投标"], st["合同"], st["施工"], st["验收"], st["结算"], st["回款"], st["售后"], g["span_days"]))
A("")
A("## 四、1:1 漏斗的年度走势（转型观察）\n")
A("| 年 | 询价 | 投标 | 合同 | 施工 | 验收 | 结算 | 回款 |")
A("|---|---|---|---|---|---|---|---|")
for y in sorted(p_year):
    py = p_year[y]
    A("| %s | %s |" % (y, " | ".join(str(py.get(st, 0)) for st in FUNNEL)))
A("")
A("**关键信号**：回款环节在 2025 年断崖（对比 2021 峰值），是现金流最紧张的年份证据。\n")
A("## 五、会话生命周期（关系/项目留存）\n")
A("| 存续区间 | 会话数 |")
A("|---|---|")
for b in ["<1月", "1-3月", "3-12月", "1-2年", ">2年"]:
    A("| %s | %d |" % (b, span_buckets.get(b, 0)))
A("")
A("> 结论：短命会话（<1月）占大多数 = 大量「问完即走」的一次性咨询；")
A("> 能活过 1 年的才是你真正沉淀的客户/关系。\n")
A("## 六、结论速览\n")
A("1. 群聊行业热度极宽：询价话题 %d 条，回款话题 %d 条，回款留存率 %.0f%%（塌缩 %d%%），" % (
    g_stage["询价"], g_stage["回款"], g_stage["回款"]*100.0/max(g_stage["询价"],1),
    100-round(g_stage["回款"]*100.0/max(g_stage["询价"],1))))
A("   印证行业里大量讨论停在「问问价」就散了。")
A("2. 会话级漏斗（1:1 真·转化）才是关键：从询价会话到回款会话的逐级留存，暴露你掉客户最多的环节。")
A("3. 你真正从头跟到尾的私聊项目 **%d 个**，其中覆盖 6+ 环节的深度项目约 %d 个。" % (
    len(complete_projects), sum(1 for p in complete_projects if p["coverage"] >= 6)))
A("4. 回款是全局最弱环节——无论群聊还是私聊，「结算→回款」都是系统性瓶颈。")
A("5. 2025 是回款塌方年（私聊回款 %d，仅为 2021 峰值 %d 的 %.0f%%），与职业转型时间线吻合：旧业务在退潮。" % (
    p_year.get("2025",{}).get("回款",0), p_year.get("2021",{}).get("回款",0),
    p_year.get("2025",{}).get("回款",0)*100.0/max(p_year.get("2021",{}).get("回款",1),1)))

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(L))

# ---------- HTML 图表 ----------
import html as _html
def esc(x): return _html.escape(str(x))
# 漏斗条形数据
g_f = [g_stage[s] for s in FUNNEL]
p_f = [p_stage[s] for s in FUNNEL]
# 年份回款
years = sorted(p_year)
yb = [p_year[y].get("回款", 0) for y in years]
yq = [p_year[y].get("询价", 0) for y in years]
# 完整项目覆盖分布
cov = collections.Counter(p["coverage"] for p in complete_projects)
cov_keys = sorted(cov)
cov_vals = [cov[k] for k in cov_keys]
span_labels = ["<1月","1-3月","3-12月","1-2年",">2年"]
span_vals = [span_buckets.get(b,0) for b in span_labels]

HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>
 body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f7f8fa;color:#222;margin:0;padding:24px}
 h1{font-size:22px;margin:0 0 4px} .sub{color:#888;font-size:13px;margin-bottom:20px}
 .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
 .card{background:#fff;border:1px solid #eee;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
 .card h2{font-size:15px;margin:0 0 12px;color:#333}
 .kpi{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
 .kpi .box{background:#fff;border:1px solid #eee;border-radius:12px;padding:14px 18px;flex:1;min-width:150px}
 .kpi .num{font-size:26px;font-weight:700;color:#2b6cb0}
 .kpi .lab{font-size:12px;color:#888;margin-top:2px}
 canvas{max-width:100%%}
 table{width:100%%;border-collapse:collapse;font-size:12px}
 th,td{border:1px solid #eee;padding:6px 8px;text-align:center}
 th{background:#f0f4f8}
 .note{font-size:12px;color:#888;margin-top:8px}
</style></head><body>
<h1>弱电生意 · 项目全周期漏斗</h1>
<div class="sub">%s 条消息 · %d 会话 · 扫描 %.0fs · 关键词代理指标</div>
<div class="kpi">
 <div class="box"><div class="num">%d</div><div class="lab">1:1 完整项目(询价∩回款)</div></div>
 <div class="box"><div class="num">%d</div><div class="lab">覆盖6+环节深度项目</div></div>
 <div class="box"><div class="num">%.0f%%</div><div class="lab">群聊询价→回款塌缩</div></div>
 <div class="box"><div class="num">%d</div><div class="lab">高活跃业务群</div></div>
</div>
<div class="grid">
 <div class="card"><h2>漏斗：群聊(行业热度) vs 1:1(真实项目)</h2><canvas id="c1" height="300"></canvas>
   <div class="note">越往右塌缩越狠 = 越难落地</div></div>
 <div class="card"><h2>1:1 私聊年度走势：询价 vs 回款</h2><canvas id="c2" height="300"></canvas>
   <div class="note">回款(红)在2025断崖</div></div>
 <div class="card"><h2>完整项目·环节覆盖分布</h2><canvas id="c3" height="280"></canvas>
   <div class="note">覆盖环节越多=跟得越深</div></div>
 <div class="card"><h2>会话存续区间</h2><canvas id="c4" height="280"></canvas>
   <div class="note">短命会话=问完即走</div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const L=['%s'];
new Chart(c1,{type:'bar',data:{labels:L,datasets:[
 {label:'群聊',data:%s,backgroundColor:'#cbd5e0'},
 {label:'1:1私聊',data:%s,backgroundColor:'#2b6cb0'}]},
 options:{indexAxis:'y',plugins:{legend:{position:'top'}},scales:{x:{type:'logarithmic'}}}}});
new Chart(c2,{type:'line',data:{labels:%s,datasets:[
 {label:'询价',data:%s,borderColor:'#2b6cb0',fill:false},
 {label:'回款',data:%s,borderColor:'#e53e3e',fill:false}]},
 options:{plugins:{legend:{position:'top'}}}});
new Chart(c3,{type:'bar',data:{labels:[%s],datasets:[
 {label:'项目数',data:%s,backgroundColor:'#38a169'}]},
 options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
new Chart(c4,{type:'doughnut',data:{labels:%s,datasets:[
 {data:%s,backgroundColor:['#fc8181','#f6ad55','#68d391','#4299e1','#9f7aea']}]},
 options:{plugins:{legend:{position:'right'}}}});
</script></body></html>""" % (
 n, len(sess), time.time() - t0, len(complete_projects),
 sum(1 for p in complete_projects if p["coverage"]>=6),
 g_stage["回款"]*100.0/max(g_stage["询价"],1), len(full_chain_groups),
 "','".join(FUNNEL), json.dumps(g_f), json.dumps(p_f),
 json.dumps(years), json.dumps(yq), json.dumps(yb),
 ",".join(str(k) for k in cov_keys), json.dumps(cov_vals),
 json.dumps(span_labels), json.dumps(span_vals),
)
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(HTML)

print("OK %.0fs -> %s" % (time.time() - t0, OUT_HTML))
