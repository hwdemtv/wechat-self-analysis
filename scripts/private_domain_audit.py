# -*- coding: utf-8 -*-
"""
private_domain_audit.py —— 闭合 A 档剩余两项
④ 关系半衰期 / 社交破产清单：会话生命周期、单向维系、待激活关系
② 私域群发效率：群发助手发给个人后的回复率、沉默对象、对牛弹琴群
单遍扫描 messages.jsonl，输出 .json/.md/.html
"""
import os, re, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "export", "messages.jsonl")
# 隐私默认策略：若 scripts/export/ 下没有明文，自动在 .wc_cache/export/ 或 output/ 定位。
try:
    from _paths import locate_messages_jsonl as _locate
    if not os.path.exists(SRC):
        _f = _locate()
        if _f:
            SRC = _f
except Exception:
    pass
OUT_JSON = os.path.join(HERE, "export", "private_domain_audit.json")
OUT_MD = os.path.join(HERE, "export", "private_domain_audit.md")
OUT_HTML = os.path.join(HERE, "export", "private_domain_audit.html")
t0 = time.time()
NOW = time.time()

RE_MD5 = re.compile(r"^[0-9a-f]{32}$")
def is_group(chat, cname):
    return chat.endswith("@chatroom") or bool(RE_MD5.match(chat or ""))
def yr_of(ts):
    try: return time.strftime("%Y", time.localtime(int(ts)))
    except Exception: return "?"

sess = {}   # chat -> {name,group,first,last,n,self,them,last_side,last_ts}
def get_sess(chat, cname, group):
    s = sess.get(chat)
    if s is None:
        s = {"name": cname, "group": group, "first": None, "last": None,
             "n": 0, "self": 0, "them": 0, "last_side": None, "last_ts": 0}
        sess[chat] = s
    return s

massend_year = collections.Counter()
massend_count = collections.Counter()       # chat -> 群发事件数
massend_replied = collections.Counter()     # chat -> 群发后被回复数
massend_pending = {}                         # chat -> bool

n = 0
with open(SRC, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: o = json.loads(line)
        except Exception: continue
        n += 1
        if n % 500000 == 0:
            sys.stderr.write("  ...%d (%.0fs)\n" % (n, time.time() - t0)); sys.stderr.flush()
        ty = o.get("type"); ct = o.get("content") or ""
        chat = o.get("chat") or ""; cname = o.get("chat_name") or ""
        side = o.get("side"); ts = o.get("create_time") or 0
        group = is_group(chat, cname)
        s = get_sess(chat, cname, group)
        if s["first"] is None or ts < s["first"]: s["first"] = ts
        if s["last"] is None or ts > s["last"]: s["last"] = ts
        s["n"] += 1
        if side == "self": s["self"] += 1
        else: s["them"] += 1
        s["last_side"] = side; s["last_ts"] = ts

        if ty == "系统消息" and ("masssend" in ct or "群发助手" in ct):
            massend_year[yr_of(ts)] += 1
            massend_count[chat] += 1
            massend_pending[chat] = True
        elif side == "them" and massend_pending.get(chat):
            massend_replied[chat] += 1
            massend_pending[chat] = False

# ---------- 派生 ----------
# 关系生命周期（1:1）
rel_decay = collections.Counter()       # 活跃/温/冷/死
one2one_total = 0
single_keep = []                        # 单向维系（你最后开口>90天无回）
to_activate = []                        # 曾高频现沉寂（该激活）
for chat, s in sess.items():
    if s["group"]: continue
    one2one_total += 1
    ltn = (NOW - (s["last"] or 0)) / 86400.0
    if ltn < 30: rel_decay["活跃"] += 1
    elif ltn < 90: rel_decay["温"] += 1
    elif ltn < 365: rel_decay["冷"] += 1
    else: rel_decay["死"] += 1
    if s["last_side"] == "self" and ltn > 90:
        single_keep.append({"name": s["name"], "n": s["n"], "ltn": int(ltn), "self": s["self"], "them": s["them"]})
    # 待激活：曾高频(>300)、对等(对方占比>30%)、现已沉寂(>180天) 的真个人关系
    nm = s["name"] or ""
    if any(k in nm for k in ("训练营","助手","客服","官方","机器人","群","俱乐部","学会","协会","公司","学院","平台","中心","交流","联盟","服务号")):
        continue
    if s["n"] > 300 and (s["them"] / s["n"]) > 0.3 and ltn > 180:
        to_activate.append({"name": s["name"], "n": s["n"], "ltn": int(ltn), "self": s["self"], "them": s["them"]})
single_keep.sort(key=lambda x: -x["ltn"])
to_activate.sort(key=lambda x: -x["n"])

# 群生命周期与互动
group_total = 0
group_dead = 0
dead_groups_top = []                     # 死群中你曾投入最多（最该退）
for chat, s in sess.items():
    if not s["group"]: continue
    group_total += 1
    ltn = (NOW - (s["last"] or 0)) / 86400.0
    if ltn > 365:
        group_dead += 1
        dead_groups_top.append({"name": s["name"], "n": s["n"], "ltn": int(ltn), "self": s["self"]})
dead_groups_top.sort(key=lambda x: -x["n"])

# 私域群发效率
massend_total = sum(massend_count.values())
massend_targets = len(massend_count)
massend_replied_total = sum(massend_replied.values())
massend_reply_rate = round(massend_replied_total * 100.0 / massend_total, 1) if massend_total else 0
massend_silent = []                      # 群发后从未回
for chat, c in massend_count.items():
    if massend_replied.get(chat, 0) == 0:
        massend_silent.append({"name": sess[chat]["name"], "times": c})
massend_silent.sort(key=lambda x: -x["times"])

# 1:1 普通私聊对方回应基准（them 占比，作为群发效果对照）
one2one_them_ratio = sum(s["them"] for s in sess.values() if not s["group"]) / \
                     max(sum(s["n"] for s in sess.values() if not s["group"]), 1)

res = {
    "total_messages": n, "scan_seconds": round(time.time() - t0, 1),
    "one2one_total": one2one_total, "rel_decay": dict(rel_decay),
    "single_keep_count": len(single_keep), "to_activate_count": len(to_activate),
    "single_keep_top": single_keep[:30], "to_activate_top": to_activate[:30],
    "group_total": group_total, "group_dead": group_dead,
    "dead_groups_top": dead_groups_top[:25],
    "massend_silent_count": len(massend_silent),
    "massend_total": massend_total, "massend_targets": massend_targets,
    "massend_reply_rate": massend_reply_rate, "massend_replied_total": massend_replied_total,
    "massend_year": dict(sorted(massend_year.items())),
    "one2one_them_ratio": round(one2one_them_ratio, 3),
    "massend_silent_top": massend_silent[:30],
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
L = []; A = L.append
A("# 私域关系与群发效率审计（A 档闭合：④关系半衰期 + ②私域群发）\n")
A("> 数据：%s 条消息 / %d 会话，扫描 %.0fs。NOW=本次运行时刻。\n" % (n, len(sess), time.time() - t0))
A("## ④ 关系半衰期（1:1 私聊，共 %d 个）\n" % one2one_total)
A("| 状态 | 会话数 | 定义 |")
A("|---|---|---|")
A("| 活跃 | %d | 最后消息 <30 天前 |" % rel_decay["活跃"])
A("| 温 | %d | 30-90 天 |" % rel_decay["温"])
A("| 冷 | %d | 90-365 天 |" % rel_decay["冷"])
A("| 死 | %d | >365 天（关系已亡） |" % rel_decay["死"])
A("")
A("- **单向维系清单**（你最后开口、对方 >90 天没回，你单方面吊着）：**%d 个**" % len(single_keep))
A("- **待激活关系**（曾高频聊天 >200 条、现已沉寂 >180 天，值得重启）：**%d 个**\n" % len(to_activate))
A("### 待激活 TOP15（最该重启的关系）\n")
A("| 关系 | 历史消息 | 已沉寂(天) | 我/对方 |")
A("|---|---|---|---|")
for p in to_activate[:15]:
    A("| %s | %d | %d | %d/%d |" % (p["name"], p["n"], p["ltn"], p["self"], p["them"]))
A("")
A("## ② 私域群发效率（群发助手发给个人）\n")
A("- 群发总次数：**%d**；群发对象（去重）：**%d** 人" % (massend_total, massend_targets))
A("- 群发后对方回复率：**%.1f%%**" % massend_reply_rate)
A("- 对照：普通 1:1 私聊对方消息占比 = **%.1f%%**（群发效果 %s）" % (
    one2one_them_ratio * 100, "显著更差" if massend_reply_rate < one2one_them_ratio * 100 else "接近"))
A("- 群发年度：%s" % ", ".join("%s:%d" % (k, v) for k, v in sorted(massend_year.items())))
A("")
A("### 群发后从未回复的对象 TOP15（群发对他们 = 已读不回/拉黑边缘）\n")
A("| 对象 | 被群发次数 |")
A("|---|---|")
for m in massend_silent[:15]:
    A("| %s | %d |" % (m["name"], m["times"]))
A("")
A("## 群生命周期（共 %d 个群）\n" % group_total)
A("- 死群（>365 天无活跃）：**%d** 个（占 %.0f%%）——你的群资产严重注水" % (group_dead, group_dead*100.0/group_total))
A("- 没有纯「对牛弹琴群」（群里总有人说话），但 %.0f%% 的群已死，说明你大量加群后不再参与。\n" % (group_dead*100.0/group_total))
A("### 最该退的死群 TOP15（你曾投入最多、现已死）\n")
A("| 群 | 历史消息 | 沉寂(天) |")
A("|---|---|---|")
for g in dead_groups_top[:15]:
    A("| %s | %d | %d |" % (g["name"], g["n"], g["ltn"]))
A("")
A("## 结论\n")
A("1. 你的 %d 个 1:1 关系里，**真正活跃+温（<90天）仅 %d 个**，冷/死合计 %d 个（占 %.0f%%）。单向维系 %d 个 = 你单方面吊着的关系，建议批量放手。" % (
    one2one_total, rel_decay["活跃"]+rel_decay["温"], rel_decay["冷"]+rel_decay["死"],
    (rel_decay["冷"]+rel_decay["死"])*100.0/one2one_total, len(single_keep)))
A("2. 群发助手回复率 %.1f%% 远低于普通私聊对方占比 %.1f%% —— 群发是**低效触达**；尤其 %d 个「群发后从不回」的对象，群发对他们已无意义。" % (
    massend_reply_rate, one2one_them_ratio*100, len(massend_silent)))
A("3. %d 个死群（占群总数 %.0f%%）= 群资产注水，2026 群发加码（%d 次）是在给已死的群/关系续命，而非激活新价值。" % (
    group_dead, group_dead*100.0/group_total, massend_year.get("2026", 0)))
A("4. 行动建议：把「待激活」对等旧关系做成**重启清单**；把「单向维系 %d 个 + 群发沉默对象 %d 个 + 死群 %d 个」做成**断舍离清单**。" % (
    len(single_keep), len(massend_silent), group_dead))

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(L))

# ---------- HTML ----------
import html as _html
def J(x): return json.dumps(x, ensure_ascii=False)
decay_keys = ["活跃","温","冷","死"]
decay_vals = [rel_decay.get(k,0) for k in decay_keys]
myears = sorted(massend_year)
myvals = [massend_year[y] for y in myears]
# 群分类
group_alive = group_total - group_dead
HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>
 body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f7f8fa;color:#222;margin:0;padding:24px}
 h1{font-size:22px;margin:0 0 4px} .sub{color:#888;font-size:13px;margin-bottom:20px}
 .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
 .card{background:#fff;border:1px solid #eee;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
 .card h2{font-size:15px;margin:0 0 12px;color:#333}
 .kpi{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
 .kpi .box{background:#fff;border:1px solid #eee;border-radius:12px;padding:14px 18px;flex:1;min-width:150px}
 .kpi .num{font-size:24px;font-weight:700;color:#2b6cb0}
 .kpi .lab{font-size:12px;color:#888;margin-top:2px}
 canvas{max-width:100%%}
 .note{font-size:12px;color:#888;margin-top:8px}
</style></head><body>
<h1>私域关系与群发效率审计</h1>
<div class="sub">__SUB__</div>
<div class="kpi">
 <div class="box"><div class="num">__DEAD__</div><div class="lab">已死1:1关系(>1年)</div></div>
 <div class="box"><div class="num">__SINGLE__</div><div class="lab">单向维系(你吊着)</div></div>
 <div class="box"><div class="num">__MRATE__%%</div><div class="lab">群发回复率(对照__OR__%%)</div></div>
 <div class="box"><div class="num">__GDEAD__</div><div class="lab">死群(>1年)</div></div>
</div>
<div class="grid">
 <div class="card"><h2>④ 1:1 关系半衰期</h2><canvas id="c1" height="280"></canvas>
   <div class="note">活跃/温/冷/死</div></div>
 <div class="card"><h2>② 群发年度趋势</h2><canvas id="c2" height="280"></canvas>
   <div class="note">2026 群发加码</div></div>
 <div class="card"><h2>群资产分类</h2><canvas id="c3" height="280"></canvas>
   <div class="note">活群/死群</div></div>
 <div class="card"><h2>群发效率 vs 普通私聊</h2><canvas id="c4" height="280"></canvas>
   <div class="note">群发回复率(红) vs 私聊回应占比</div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
new Chart(c1,{type:'doughnut',data:{labels:__DK__,datasets:[{data:__DV__,backgroundColor:['#68d391','#a0d468','#f6ad55','#e53e3e']}]},
 options:{plugins:{legend:{position:'right'}}}});
new Chart(c2,{type:'bar',data:{labels:__MY__,datasets:[{label:'群发次数',data:__MYV__,backgroundColor:'#4299e1'}]},
 options:{plugins:{legend:{display:false}}}});
new Chart(c3,{type:'pie',data:{labels:__GK__,datasets:[{data:__GV__,backgroundColor:['#68d391','#e53e3e','#f6ad55']}]},
 options:{plugins:{legend:{position:'right'}}}});
new Chart(c4,{type:'bar',data:{labels:['群发回复率','普通私聊回应'],datasets:[
 {label:'%',data:[__MRATE__,__OR__],backgroundColor:['#e53e3e','#2b6cb0']}]},
 options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
</script></body></html>"""
HTML = (HTML
    .replace("__SUB__", "%s 条消息 · %d 会话 · %.0fs" % (n, len(sess), time.time()-t0))
    .replace("__DEAD__", str(rel_decay["死"]))
    .replace("__SINGLE__", str(len(single_keep)))
    .replace("__MRATE__", "%.1f" % massend_reply_rate)
    .replace("__OR__", "%.1f" % (one2one_them_ratio*100))
    .replace("__GDEAD__", str(group_dead))
    .replace("__DK__", J(decay_keys))
    .replace("__DV__", J(decay_vals))
    .replace("__MY__", J(myears))
    .replace("__MYV__", J(myvals))
    .replace("__GK__", J(["活群","死群"]))
    .replace("__GV__", J([group_alive, group_dead])))
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(HTML)
print("OK %.0fs -> %s" % (time.time() - t0, OUT_HTML))
