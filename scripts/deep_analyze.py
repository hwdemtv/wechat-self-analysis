#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度分析：在四维报告之上的进阶洞察。

输入: export/messages.jsonl
输出: export/deep_report.md      深度报告
      export/deep_charts.html    可视化（年度轨迹/热力图/关键词）

分析项:
  1) 年度演化: 每年总消息/你发送/1:1与群占比/活跃天数/深夜占比/新会话数
  2) 核心关系×年度热力矩阵(Top 1:1): 谁在哪些年重要、谁在衰减
  3) 时段×星期热力图: 你的作息指纹
  4) 关键词演变(三阶段 jieba 分词): 关注焦点迁移
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
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
OUT_DIR = os.path.join(SKILL_ROOT, "output")

try:
    import jieba
    jieba.setLogLevel(60)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

STOP = set("""的了是在我有和就不人这中大为上个国我们你们他们她说要地到以以及就是没有还是但是因为所以如果那么这些那些自己什么怎么可以现在时候知道已经一个一些这个那个也是都是不是觉得可能应该或者而且然后其他下面上面左右多少非常真的假的哈哈嘻嘻嗯哦呃呀吧呢嘛啊吗啦咯呗哈嘿昂喔好滴行哦收到谢谢不客气没事没关系不好意思麻烦一下然后转发图片语音视频红包表情文件链接名片小程序音乐动画""".split())

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

YEAR_MIN, YEAR_MAX = 2019, 2026
ERAS = [("2019-2021", 2019, 2021), ("2022-2023", 2022, 2023), ("2024-2026", 2024, 2026)]
YEARS = list(range(YEAR_MIN, YEAR_MAX + 1))

def main():
    if not os.path.exists(IN_PATH):
        print("找不到输入文件", IN_PATH)
        return 2

    yearly = {y: {"total": 0, "self": 0, "self_1to1": 0, "self_group": 0,
                  "days": set(), "deep_night": 0} for y in YEARS}
    heat = [[0] * 24 for _ in range(7)]              # dow x hour (self)
    kw_counter = {name: collections.Counter() for name, _, _ in ERAS}
    chat_self = collections.Counter()
    chat_is_group = {}
    chat_name = {}
    first_year = {}
    chat_prefixes = collections.defaultdict(set)
    chat_grp_sig = set()
    chat_year_self = collections.defaultdict(collections.Counter)

    t0 = time.time()
    # ---- 第一遍：年度/热力/关键词/会话统计 ----
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = epoch(rec.get("create_time"))
            if t is None:
                continue
            d = datetime.datetime.fromtimestamp(t)
            y = d.year
            chat = rec.get("chat", "")
            side = rec.get("side")
            if chat not in chat_is_group:
                chat_is_group[chat] = chat.endswith("@chatroom") or chat.startswith("@@")
                chat_name[chat] = rec.get("chat_name") or chat
                first_year[chat] = y
            elif y < first_year.get(chat, 9999):
                first_year[chat] = y
            if side == "self":
                chat_self[chat] += 1
                if y in yearly:
                    yearly[y]["self"] += 1
                    yearly[y]["days"].add(d.strftime("%Y-%m-%d"))
                    chat_year_self[chat][y] += 1
                    if d.hour <= 5:
                        yearly[y]["deep_night"] += 1
                    heat[d.weekday()][d.hour] += 1
                if not HAS_JIEBA:
                    continue
                c = rec.get("content")
                if rec.get("type") == "文本" and isinstance(c, str) and c \
                        and not c.lstrip().startswith(("<", "{")):
                    for w in jieba.lcut(c):
                        if len(w) >= 2 and not w.isdigit() and w not in STOP:
                            for name, a, b in ERAS:
                                if a <= y <= b:
                                    kw_counter[name][w] += 1
                                    break
            else:
                if MD5_NAME_RE.match(chat) and isinstance(rec.get("content"), str):
                    m2 = PREFIX_RE.match(rec["content"])
                    if m2:
                        chat_prefixes[chat].add(m2.group(1))
                    if GROUP_SIG_RE.search(rec["content"][:120]):
                        chat_grp_sig.add(chat)
            if y in yearly:
                yearly[y]["total"] += 1

    # 退群/解散群重分类
    reclassified = 0
    for c in chat_is_group:
        if MD5_NAME_RE.match(c) and (len(chat_prefixes.get(c, ())) >= 3 or c in chat_grp_sig):
            chat_is_group[c] = True
            chat_name[c] = "已退群_" + c[:8]
            reclassified += 1
    # 年度群/1:1 拆分（重分类后计算才准确）
    for c, yc in chat_year_self.items():
        g = chat_is_group.get(c)
        for y, n in yc.items():
            if y in yearly:
                if g:
                    yearly[y]["self_group"] += n
                else:
                    yearly[y]["self_1to1"] += n

    new_chats_year = collections.Counter(first_year.values())

    # ---- 第二遍：核心 1:1 关系 × 年度矩阵 ----
    top_1to1 = [(chat, n) for chat, n in chat_self.most_common(300)
                if not chat_is_group.get(chat)][:12]
    targets = set(c for c, _ in top_1to1)
    rel_matrix = {c: collections.Counter() for c in targets}
    rel_first = {c: None for c in targets}
    rel_last = {c: None for c in targets}
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            chat = rec.get("chat", "")
            if chat not in targets or rec.get("side") != "self":
                continue
            t = epoch(rec.get("create_time"))
            if t is None:
                continue
            d = datetime.datetime.fromtimestamp(t)
            if YEAR_MIN <= d.year <= YEAR_MAX:
                rel_matrix[chat][d.year] += 1
            if rel_first[chat] is None or t < rel_first[chat]:
                rel_first[chat] = t
            if rel_last[chat] is None or t > rel_last[chat]:
                rel_last[chat] = t

    now = time.time()

    def status(last_t):
        days = (now - last_t) / 86400.0
        if days < 30: return "活跃"
        if days < 180: return "低频"
        if days < 730: return "沉默"
        return "断联"

    # ---------- Markdown ----------
    L = []
    L.append("# 微信行为深度分析（进阶版）\n")
    L.append("数据：2019-02 ~ 2026-10，共 %s 条；生成于 %s\n" % (
        format(sum(yearly[y]["total"] for y in YEARS), ","),
        time.strftime("%Y-%m-%d %H:%M")))

    L.append("## 一、年度演化轨迹\n")
    L.append("| 年份 | 总消息 | 你发 | 1:1你发 | 群你发 | 活跃天数 | 深夜(0-5点) | 深夜占比 | 当年新会话 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for y in YEARS:
        d = yearly[y]
        L.append("| %d | %s | %s | %s | %s | %d | %d | %.1f%% | %d |" % (
            y, format(d["total"], ","), format(d["self"], ","),
            format(d["self_1to1"], ","), format(d["self_group"], ","),
            len(d["days"]), d["deep_night"],
            100.0 * d["deep_night"] / max(1, d["self"]), new_chats_year.get(y, 0)))
    L.append("")

    L.append("## 二、核心 1:1 关系 × 年度热力（你发送条数）\n")
    L.append("| 关系 | " + " | ".join(str(y) for y in YEARS) + " | 峰值年 | 最近互动 | 状态 |")
    L.append("|---|" + "---|" * len(YEARS) + "---|---|---|")
    for chat, _n in top_1to1:
        name = chat_name.get(chat, chat)
        cells = [rel_matrix[chat].get(y, 0) for y in YEARS]
        peak = YEARS[cells.index(max(cells))] if max(cells) > 0 else "-"
        last = rel_last[chat]
        L.append("| %s | " % name + " | ".join(str(c) if c else "·" for c in cells) +
                 " | %s | %s | %s |" % (
                     peak,
                     datetime.datetime.fromtimestamp(last).strftime("%Y-%m-%d") if last else "-",
                     status(last) if last else "-"))
    L.append("")

    L.append("## 三、作息指纹（你发送消息 时段×星期）\n")
    L.append("行=星期(一~日)，列=0~23 点。\n")
    dows = ["一", "二", "三", "四", "五", "六", "日"]
    L.append("| 时 | " + " | ".join(str(h) for h in range(24)) + " |")
    L.append("|---|" + "---|" * 24)
    for di in range(7):
        cells = [str(heat[di][h]) if heat[di][h] else "·" for h in range(24)]
        L.append("| %s | " % dows[di] + " | ".join(cells) + " |")
    L.append("")

    L.append("## 四、关键词演变（jieba 分词，你发送的文本，各阶段 Top30）\n")
    for name, _, _ in ERAS:
        top = [w for w, _c in kw_counter[name].most_common(30)]
        L.append("**%s**：%s\n" % (name, "、".join(top) if top else "（无）"))
    L.append("")
    L.append("---\n*关键词已过滤常用停用词与纯数字；XML/系统消息不计入。*")

    with open(os.path.join(OUT_DIR, "deep_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ---------- HTML ----------
    years_js = json.dumps(YEARS)
    rel_js = json.dumps([
        {"name": chat_name.get(c, c), "values": [rel_matrix[c].get(y, 0) for y in YEARS]}
        for c, _ in top_1to1], ensure_ascii=False)
    kw_js = json.dumps({name: [w for w, _ in kw_counter[name].most_common(25)]
                        for name, _, _ in ERAS}, ensure_ascii=False)

    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>微信行为深度分析</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f6f7fb;margin:0;padding:24px;color:#222}
.card{background:#fff;border-radius:14px;box-shadow:0 2px 10px #0001;padding:18px;margin:16px 0}
h2{font-size:17px;color:#1f6feb;margin:0 0 10px}.grid{display:grid;grid-template-columns:1fr;gap:14px}
.kw{display:flex;flex-wrap:wrap;gap:6px}.kw span{background:#eef3ff;border-radius:14px;padding:3px 10px;font-size:13px}
table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #e3e6ee;padding:3px 6px;text-align:center;min-width:26px}</style></head>
<body>
<h1 style="font-size:22px">微信行为深度分析</h1>
<div class="card"><h2>年度轨迹（你发送）</h2><canvas id="y1" height="100"></canvas>
<div class="grid"><div><canvas id="y2" height="100"></canvas></div>
<div><canvas id="y3" height="100"></canvas></div></div></div>
<div class="card"><h2>核心 1:1 关系 × 年度（你发送条数，堆叠）</h2><canvas id="rel" height="140"></canvas></div>
<div class="card"><h2>作息指纹（时段×星期，颜色=消息量）</h2><div id="heat"></div></div>
<div class="card"><h2>关键词演变（三阶段 Top25）</h2><div class="grid" id="kw"></div></div>
<script>
const years=__YEARS__, heat=__HEAT__, rel=__REL__, kw=__KW__;
const sself=__SELF__, s1=__S1__, sg=__SG__, newc=__NEWC__;
new Chart(document.getElementById('y1'),{type:'line',data:{labels:years,datasets:[{label:'你发送总数',data:sself,borderColor:'#1f6feb',tension:.3}]},options:{plugins:{legend:{display:false}}}});
new Chart(document.getElementById('y2'),{type:'bar',data:{labels:years,datasets:[{label:'1:1你发',data:s1,backgroundColor:'#1f6feb'},{label:'群你发',data:sg,backgroundColor:'#e67e22'}]}});
new Chart(document.getElementById('y3'),{type:'bar',data:{labels:years,datasets:[{label:'当年新会话数',data:newc,backgroundColor:'#27ae60'}]},options:{plugins:{legend:{display:false}}}});
new Chart(document.getElementById('rel'),{type:'bar',data:{labels:years,datasets:rel.map((r,i)=>({label:r.name,data:r.values,backgroundColor:['#1f6feb','#e67e22','#27ae60','#8e44ad','#c0392b','#16a085','#f39c12','#2c3e50','#d35400','#7f8c8d','#2980b9','#27363b'][i%12]}))},options:{scales:{x:{stacked:true},y:{stacked:true}}}});
const dows=['一','二','三','四','五','六','日'];
const mx=Math.max(...heat.flat())||1;
let h='<table><tr><th>时\\\\星期</th>'+dows.map(d=>'<th>'+d+'</th>').join('')+'</tr>';
for(let hh=0;hh<24;hh++){h+='<tr><th>'+hh+'</th>';
for(let di=0;di<7;di++){const v=heat[di][hh];const a=v/mx;
h+='<td style="background:rgba(31,111,235,'+(a*0.85+0.03).toFixed(2)+');color:'+(a>0.5?'#fff':'#333')+'">'+(v||'·')+'</td>';}
h+='</tr>';}
document.getElementById('heat').innerHTML=h+'</table>';
const colors=['#1f6feb','#e67e22','#27ae60'];
let kh='';
Object.keys(kw).forEach((k,i)=>{kh+='<div><b style="color:'+colors[i]+'">'+k+'</b><div class="kw">'+kw[k].map(w=>'<span>'+w+'</span>').join('')+'</div></div>';});
document.getElementById('kw').innerHTML=kh;
</script></body></html>"""
    html = (html.replace("__YEARS__", years_js).replace("__HEAT__", json.dumps(heat))
            .replace("__REL__", rel_js).replace("__KW__", kw_js)
            .replace("__SELF__", json.dumps([yearly[y]["self"] for y in YEARS]))
            .replace("__S1__", json.dumps([yearly[y]["self_1to1"] for y in YEARS]))
            .replace("__SG__", json.dumps([yearly[y]["self_group"] for y in YEARS]))
            .replace("__NEWC__", json.dumps([new_chats_year.get(y, 0) for y in YEARS])))
    with open(os.path.join(OUT_DIR, "deep_charts.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("深度分析完成: deep_report.md / deep_charts.html, 用时 %.1fs" % (time.time() - t0))
    return 0

if __name__ == "__main__":
    sys.exit(main())
