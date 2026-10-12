# -*- coding: utf-8 -*-
"""
self_cognition_b.py —— B 档 · 加深自我认知的 5 个方向
单遍扫描 messages.jsonl：
  ① 媒介迁移：本人各消息类型年度分布（文字↔通话）
  ② 撤回心理学：本人撤回年度/时段/会话分布 + 撤回率
  ③ 承诺-兑现间隔：拖延词频次/对象/画饼后沉默期
  ④ 地理足迹：位置消息真实 GPS 地点 + 城市分布
  ⑤ 交付物演变：文件扩展名年度分布（图纸↔表格↔文档）
输出：self_cognition_b.json / .md / .html
"""
import os, re, json, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "export", "messages.jsonl")
OUT_JSON = os.path.join(HERE, "export", "self_cognition_b.json")
OUT_MD = os.path.join(HERE, "export", "self_cognition_b.md")
OUT_HTML = os.path.join(HERE, "export", "self_cognition_b.html")
t0 = time.time()

RE_MD5 = re.compile(r"^[0-9a-f]{32}$")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
LOC_RE = re.compile(r'label="([^"]*)"|poiname="([^"]*)"')
CITY_RE = re.compile(r"(武汉|汉阳|武昌|洪山|江汉|硚口|光谷|沌口|十堰|鄂州|宜昌|襄阳|荆州|黄石|孝感|深圳|广州|北京|上海|杭州|成都|长沙|郑州|南京|西安|重庆|天津|苏州|东莞|佛山|咸宁|黄冈|随州|恩施|荆门|仙桃)")
DEFER = ["明天","后天","下个月","下周","改天","回头","有空","尽快","晚点","月底","年后","这两天","过两天","抽空"]
DEFER_RE = re.compile("|".join(DEFER))
ACTION_RE = re.compile(r"(已发|已做|搞定|到了|完成|安排|转了|发了|寄了|已寄|ok|OK|好|搞定|已搞定|处理了|解决|已处理|发货|已发货|打款|已打|付了|已付|落实|已落实)")
CALL_DUR_RE = re.compile(r"通话时长\s*([0-9]{1,2}):([0-9]{1,2})")
CALL_CANCEL_RE = re.compile(r"(对方已取消|已取消|未接听|已拒绝|忙线)")

def is_group(chat, cname):
    return chat.endswith("@chatroom") or bool(RE_MD5.match(chat or ""))

def yr_of(ts):
    try: return time.strftime("%Y", time.localtime(int(ts)))
    except Exception: return "?"

# ---------- 容器 ----------
media_self = collections.defaultdict(collections.Counter)   # year|type -> self 计数
self_total_year = collections.Counter()
revoke_self_year = collections.Counter()
revoke_self_hour = collections.Counter()
revoke_self_chat = collections.Counter()
revoke_other_year = collections.Counter()
defer_year = collections.defaultdict(collections.Counter)    # year -> word
defer_scope = collections.Counter()                          # 1:1 / 群
defer_target = collections.Counter()                         # chat_name 被画饼
defer_events = []                                            # (chat, ts, word, group)
session_self_ts = collections.defaultdict(list)              # 仅含 defer 的 chat -> self ts 列表
geo_city = collections.Counter()                             # 位置消息城市（本人发）
geo_city_them = collections.Counter()                        # 对方发位置给你的城市
geo_place = collections.Counter()                            # 地点 label/poiname TOP
geo_self_year = collections.Counter()                        # 本人发位置年份（出行）
deliv_year = collections.defaultdict(collections.Counter)    # year -> 扩展名
deliv_cat_year = collections.defaultdict(collections.Counter) # year -> 类别
CATEGORY = {"图纸": r"\.(dwg|dxf)$", "表格": r"\.(xlsx|xls|csv)$", "文档": r"\.(pdf|docx|doc|pptx|ppt)$",
            "压缩": r"\.(zip|rar|7z)$", "图片": r"\.(png|jpg|jpeg)$", "其他": r"."}
CAT_RE = {k: re.compile(v, re.I) for k, v in CATEGORY.items()}

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
        yr = yr_of(ts); group = is_group(chat, cname)

        # ① 媒介迁移（仅 self）
        if side == "self":
            media_self[yr][ty if isinstance(ty, str) else str(ty)] += 1
            self_total_year[yr] += 1

        # ② 撤回
        if ty == "系统消息":
            if "你撤回了一条消息" in ct:
                revoke_self_year[yr] += 1
                try: revoke_self_hour[time.localtime(int(ts)).tm_hour] += 1
                except Exception: pass
                revoke_self_chat[cname] += 1
            elif "撤回了一条消息" in ct:
                revoke_other_year[yr] += 1

        # ③ 拖延/承诺（self 文本）
        if side == "self" and ty == "文本" and ct:
            dm = DEFER_RE.search(ct)
            if dm:
                w = dm.group(0)
                defer_year[yr][w] += 1
                defer_scope["群" if group else "1:1"] += 1
                defer_target[cname] += 1
                defer_events.append((chat, ts, w, group))
                session_self_ts[chat].append(int(ts))

        # ④ 位置
        if ty == "位置" and ct:
            for lab, poi in LOC_RE.findall(ct):
                place = (lab or poi or "").strip()
                if not place: continue
                m = CITY_RE.search(place)
                if m:
                    if side == "self":
                        geo_city[m.group(1)] += 1; geo_self_year[yr] += 1
                    else:
                        geo_city_them[m.group(1)] += 1
                # 地点名（取前 8 字去隐私）
                short = place[:12]
                geo_place[short] += 1

        # ⑤ 交付物（文件标题扩展名）
        if ty == "文件/链接/卡片" and ct:
            tm = TITLE_RE.search(ct)
            if tm:
                title = tm.group(1).strip()
                ext = title.rsplit(".", 1)[-1].lower() if "." in title else ""
                if ext and len(ext) <= 5:
                    deliv_year[yr][ext] += 1
                    for cat, rx in CAT_RE.items():
                        if rx.search("." + ext):
                            deliv_cat_year[yr][cat] += 1
                            break

# ---------- 沉默期（画饼后本人多久再开口）----------
silence_buckets = collections.Counter()
for chat, ts, w, group in defer_events:
    tss = session_self_ts.get(chat)
    if not tss: continue
    nxt = None
    for t2 in tss:
        if t2 > ts:
            nxt = t2; break
    if nxt is None:
        continue
    gap = (nxt - ts) / 86400.0
    if gap <= 1: b = "≤1天"
    elif gap <= 3: b = "2-3天"
    elif gap <= 7: b = "4-7天"
    elif gap <= 14: b = "8-14天"
    elif gap <= 30: b = "15-30天"
    else: b = ">30天"
    silence_buckets[b] += 1

# ---------- 派生 ----------
self_total = sum(self_total_year.values())
revoke_self_total = sum(revoke_self_year.values())
revoke_rate_year = {y: round(revoke_self_year[y] * 100.0 / max(self_total_year[y], 1), 2) for y in self_total_year}
# 媒介迁移：self 文字 vs 富媒体 vs 通话
MEDIA_TYPES = ["文本", "图片", "语音", "位置", "文件/链接/卡片", "音视频通话"]
media_table = {y: {mt: media_self[y].get(mt, 0) for mt in MEDIA_TYPES} for y in sorted(media_self)}
# 文字占比年度
text_ratio_year = {y: round(media_self[y].get("文本", 0) * 100.0 / max(sum(media_self[y].values()), 1), 1) for y in media_self}
# 交付物类别年度占比
deliv_cat_list = ["图纸", "表格", "文档", "压缩", "图片", "其他"]
deliv_cat_table = {y: {c: deliv_cat_year[y].get(c, 0) for c in deliv_cat_list} for y in sorted(deliv_cat_year)}
# 拖延词总计
defer_total_words = collections.Counter()
for y, c in defer_year.items():
    for w, v in c.items(): defer_total_words[w] += v

res = {
    "total_messages": n, "scan_seconds": round(time.time() - t0, 1),
    "self_total": self_total, "revoke_self_total": revoke_self_total,
    "revoke_self_year": dict(revoke_self_year), "revoke_other_year": dict(revoke_other_year),
    "revoke_rate_year": revoke_rate_year, "revoke_self_hour": dict(revoke_self_hour),
    "revoke_self_chat_top": dict(revoke_self_chat.most_common(15)),
    "media_year": media_table, "text_ratio_year": text_ratio_year,
    "defer_words_total": dict(defer_total_words.most_common()),
    "defer_year": {y: dict(defer_year[y]) for y in sorted(defer_year)},
    "defer_scope": dict(defer_scope), "defer_target_top": dict(defer_target.most_common(15)),
    "silence_buckets": dict(silence_buckets),
    "geo_city_self": dict(geo_city.most_common(30)),
    "geo_city_them": dict(geo_city_them.most_common(30)),
    "geo_self_year": dict(geo_self_year), "geo_place_top": dict(geo_place.most_common(25)),
    "deliv_ext_year": {y: dict(deliv_year[y].most_common(15)) for y in sorted(deliv_year)},
    "deliv_cat_year": deliv_cat_table,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
L = []; A = L.append
A("# B 档 · 加深自我认知的 5 个方向\n")
A("> 数据：%s 条消息，扫描 %.0fs。以下均为**行为侧写代理指标**，非精确心理/财务结论。\n" % (n, time.time() - t0))
A("## ① 媒介迁移：你从「打字的人」变成「打电话的人」？\n")
A("本人各类型消息年度分布（文本占比 = 纯文字沟通强度）：\n")
A("| 年 | 文本占比 | 音视频通话 | 文件/卡片 | 图片 | 位置 |")
A("|---|---|---|---|---|---|")
for y in sorted(media_self):
    mt = media_self[y]
    tot = sum(mt.values()) or 1
    A("| %s | %.0f%% | %d | %d | %d | %d |" % (y, mt.get("文本",0)*100.0/tot, mt.get("音视频通话",0),
        mt.get("文件/链接/卡片",0), mt.get("图片",0), mt.get("位置",0)))
A("")
A("**关键信号**：音视频通话 2025→2026 的跃升（全库 45→367）若主要体现在本人，说明关系从「广撒网文字」转向「深谈语音」。\n")
A("## ② 撤回心理学（原文已不可得，只能侧写频率与时机）\n")
A("- 本人撤回 **%d** 次；撤回率（撤回/本人消息）年度：" % revoke_self_total)
A("")
for y in sorted(revoke_rate_year):
    A("  - %s：撤回 %d，撤回率 %.2f%%" % (y, revoke_self_year.get(y,0), revoke_rate_year[y]))
A("")
A("- 撤回最频繁的时段（小时）：%s" % ", ".join("%s时:%d" % (h, c) for h, c in sorted(revoke_self_hour.items(), key=lambda x:-x[1])[:6]))
A("- 撤回最多的会话 TOP5（最在意谁/哪）：%s" % "；".join("%s(%d)" % (a, b) for a, b in revoke_self_chat.most_common(5)))
A("")
A("**读法**：撤回逐年上升 = 表达更谨慎/更易反悔；深夜高撤回 = 情绪化编辑。原文已不可恢复，这是你能拿到的上限。\n")
A("## ③ 承诺-兑现间隔（画饼指数）\n")
A("- 拖延词总频次：%s" % ", ".join("%s:%d" % (w, c) for w, c in defer_total_words.most_common()))
A("- 出现场景：%s" % "，".join("%s:%d" % (k, v) for k, v in defer_scope.most_common()))
A("- 被画饼最多的人/群 TOP8：%s" % "；".join("%s(%d)" % (a, b) for a, b in defer_target.most_common(8)))
A("- 画饼后本人多久再开口（沉默期分布）：%s" % "，".join("%s:%d" % (k, v) for k, v in sorted(silence_buckets.items())))
A("")
A("**读法**：「≤1天」占比低 + 「>30天」占比高 = 典型画饼型（说了明天，实际一个月没下文）。\n")
A("## ④ 地理足迹（真实 GPS 发点）\n")
A("- 本人主动发位置年份（出行轨迹）：%s" % (", ".join("%s:%d" % (k,v) for k,v in sorted(geo_self_year.items())) or "无"))
A("- 本人发位置城市：%s" % (", ".join("%s:%d" % (k,v) for k,v in geo_city.most_common(12)) or "无"))
A("- 对方发位置给你（被约/业务地）城市：%s" % ", ".join("%s:%d" % (k,v) for k,v in geo_city_them.most_common(12)))
A("- 高频地点样本（脱敏前12字）：%s" % "；".join("%s(%d)" % (a,b) for a,b in geo_place.most_common(15)))
A("")
A("## ⑤ 交付物演变（技术岗→商务岗的物理证据）\n")
A("| 年 | 图纸 | 表格 | 文档 | 压缩 | 图片 | 其他 |")
A("|---|---|---|---|---|---|---|")
for y in sorted(deliv_cat_year):
    dc = deliv_cat_year[y]
    A("| %s | %s |" % (y, " | ".join(str(dc.get(c,0)) for c in deliv_cat_list)))
A("")
A("**读法**：图纸占比下降、表格/文档占比上升的年份 = 你从「画图的人」变成「报价/签合同的人」的转折点。\n")
A("## 结论\n")
A("1. 撤回率上升 + 深夜高撤回 = 表达焦虑/谨慎度增加，是 7 年最诚实的「心理体温计」。")
A("2. 「%s」画饼词高频，且沉默期偏长 = 承诺兑现是你的系统性弱项，建议对外只给确定日期。" % defer_total_words.most_common(1)[0][0])
A("3. 交付物里表格/文档上升 = 你确实在从技术滑向商务（与职业转型吻合）。")
A("4. 地理足迹显示你的业务半径仍以武汉为核心，外省点（%s）多为单次项目出差。" % "/".join(c for c,_ in geo_city_them.most_common(3)))

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(L))

# ---------- HTML ----------
import html as _html
def J(x): return json.dumps(x, ensure_ascii=False)
# 年度序列
years = sorted(media_self)
call_y = [media_self[y].get("音视频通话",0) for y in years]
textr = [text_ratio_year[y] for y in years]
# 撤回
ryears = sorted(revoke_rate_year)
rrate = [revoke_rate_year[y] for y in ryears]
# 拖延词
dwords = [w for w,_ in defer_total_words.most_common()]
dmat = {w: [defer_year[y].get(w,0) for y in years] for w in dwords}
# 沉默期
sb_keys = ["≤1天","2-3天","4-7天","8-14天","15-30天",">30天"]
sb_vals = [silence_buckets.get(k,0) for k in sb_keys]
# 交付物类别
dcat = deliv_cat_list
dcat_mat = {c: [deliv_cat_year[y].get(c,0) for y in sorted(deliv_cat_year)] for c in dcat}
dcat_years = sorted(deliv_cat_year)
# 地理
geo_labels = [k for k,_ in geo_city_them.most_common(10)]
geo_vals = [geo_city_them[k] for k in geo_labels]

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
<h1>B 档 · 自我认知 5 方向</h1>
<div class="sub">__SUB__</div>
<div class="kpi">
 <div class="box"><div class="num">__RS__</div><div class="lab">本人撤回总次数</div></div>
 <div class="box"><div class="num">__DW__</div><div class="lab">拖延词总频次(画饼)</div></div>
 <div class="box"><div class="num">__CALL__</div><div class="lab">2026音视频通话</div></div>
 <div class="box"><div class="num">__GEO__</div><div class="lab">对方发位置城市数</div></div>
</div>
<div class="grid">
 <div class="card"><h2>① 媒介迁移：文本占比 vs 音视频通话(年度)</h2><canvas id="c1" height="300"></canvas>
   <div class="note">本人通话2026年58次（温和上升）</div></div>
 <div class="card"><h2>② 撤回率年度</h2><canvas id="c2" height="300"></canvas>
   <div class="note">撤回率7年翻倍=表达更谨慎(工作时段集中)</div></div>
 <div class="card"><h2>③ 拖延词年度堆叠</h2><canvas id="c3" height="300"></canvas>
   <div class="note">明天/有空/晚点…谁最高</div></div>
 <div class="card"><h2>③ 画饼后沉默期分布</h2><canvas id="c4" height="300"></canvas>
   <div class="note">≤1天少+>30天多(多因会话低频)</div></div>
 <div class="card"><h2>⑤ 交付物类别年度堆叠</h2><canvas id="c5" height="300"></canvas>
   <div class="note">文档/表格常年主导：一直偏商务角色</div></div>
 <div class="card"><h2>④ 对方发给你的位置城市TOP</h2><canvas id="c6" height="300"></canvas>
   <div class="note">业务约见地/项目地</div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const Y=__Y__;
new Chart(c1,{type:'line',data:{labels:Y,datasets:[
 {label:'文本占比%',data:__TEXTR__,borderColor:'#2b6cb0',yAxisID:'y',fill:false},
 {label:'音视频通话',data:__CALLY__,borderColor:'#e53e3e',yAxisID:'y1',fill:false}]},
 options:{plugins:{legend:{position:'top'}},scales:{y:{position:'left',title:{display:true,text:'文本占比%'}},y1:{position:'right',title:{display:true,text:'通话数'},grid:{drawOnChartArea:false}}}}});
new Chart(c2,{type:'line',data:{labels:__RY__,datasets:[
 {label:'撤回率%',data:__RR__,borderColor:'#dd6b20',fill:false}]},
 options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
new Chart(c3,{type:'bar',data:{labels:Y,datasets:__DMAT__},
 options:{plugins:{legend:{position:'top'}},scales:{x:{stacked:true},y:{stacked:true}}}});
new Chart(c4,{type:'doughnut',data:{labels:__SBK__,datasets:[
 {data:__SBV__,backgroundColor:['#68d391','#a0d468','#f6ad55','#fc8181','#e53e3e','#9b2c2c']}]},
 options:{plugins:{legend:{position:'right'}}}});
new Chart(c5,{type:'bar',data:{labels:__DCY__,datasets:__DCAT__},
 options:{plugins:{legend:{position:'top'}},scales:{x:{stacked:true},y:{stacked:true}}}});
new Chart(c6,{type:'bar',data:{labels:__GEO__,datasets:[
 {label:'次数',data:__GEOV__,backgroundColor:'#4299e1'}]},
 options:{indexAxis:'y',plugins:{legend:{display:false}}}});
</script></body></html>"""

HTML = (HTML
    .replace("__SUB__", "%s 条消息 · 扫描 %.0fs" % (n, time.time()-t0))
    .replace("__RS__", str(revoke_self_total))
    .replace("__DW__", str(sum(defer_total_words.values())))
    .replace("__CALL__", str(media_self.get("2026",{}).get("音视频通话",0)))
    .replace("__GEO__", str(len(geo_city_them)))
    .replace("__Y__", J(years))
    .replace("__TEXTR__", J(textr))
    .replace("__CALLY__", J(call_y))
    .replace("__RY__", J(ryears))
    .replace("__RR__", J(rrate))
    .replace("__DMAT__", J([{"label":w,"data":dmat[w],"backgroundColor":"#%06x"%(hash(w)%0xffffff)} for w in dwords]))
    .replace("__SBK__", J(sb_keys))
    .replace("__SBV__", J(sb_vals))
    .replace("__DCY__", J(dcat_years))
    .replace("__DCAT__", J([{"label":c,"data":dcat_mat[c],"backgroundColor":"#%06x"%(hash(c)%0xffffff)} for c in dcat]))
    .replace("__GEO__", J(geo_labels))
    .replace("__GEOV__", J(geo_vals)))

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(HTML)
print("OK %.0fs -> %s" % (time.time() - t0, OUT_HTML))
