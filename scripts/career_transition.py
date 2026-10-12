#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""职业转型量化验证：从你 7.6 年的消息里量化「弱电工程 → 超级个体」的转型。

输出: export/career_report.md / career_charts.html
方法:
  1) 三套词典逐月计数（旧赛道=弱电/机电/音响工程；证书期=一建/造价/考证；新赛道=无人机/3D打印/AI自媒体）
  2) 季度迁移指数 new/(new+old)，连续 3 个季度 new>old 判定为转型拐点
  3) 新赛道关键词的【首次提及日期】——你什么时候第一次聊到无人机/大疆/3D打印…
  4) 报价行为: ¥/元/万 数字抽取（分年度+样例）
  5) 自我身份语句演变: 「我是做…/我们主营…/承接…」分三阶段采样
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
OUT_DIR = os.path.join(SKILL_ROOT, "output")

OLD_TERMS = ["综合布线","监控","摄像机","枪机","球机","门禁","道闸","楼宇对讲","可视对讲","报警","巡更",
             "背景音乐","公共广播","音箱","音响","话筒","麦克风","功放","调音台","均衡器","投影","LED屏",
             "显示屏","拼接屏","机房","桥架","穿线","放线","光纤","熔纤","弱电","智能化","停车场系统",
             "会议系统","中控","矩阵","舞台","KTV","包房","线管","PVC管","镀锌管","图纸","清单","预算",
             "广联达","BIM","CAD","深化设计","竣工","验收","招投标","投标","标书","工程量","签证","结算",
             "进度款","质保"]
CERT_TERMS = ["一建","二建","一级建造师","二级建造师","一造","二造","造价师","造价工程师","消防工程师",
              "备考","刷题","教材","押题","网课","精讲","习题班","实务","法规","管理","经济","案例分析",
              "准考证","考试","取证","注册","继续教育","报名费"]
NEW_TERMS = ["无人机","大疆","DJI","dji","飞控","桨叶","云台","图传","炸机","遥控器","电池","电调",
             "3D打印","打印机","喷头","热床","PLA","pla","耗材","切片","STL","stl","Fusion","fusion",
             "MakerWorld","拓竹","Bambu","闲鱼","淘宝","低空","维修","主板","焊接","焊台","万用表",
             "自媒体","公众号","引流","变现","流量","带货","短视频","抖音","小红书","B站","涨粉",
             "智能体","Coze","扣子","AI","GPT","gpt","大模型","提示词","Obsidian","知识库","副业",
             "超级个体","个人品牌","出海","接单"]
# 可选：从技能目录 config.json 覆盖赛道词典（定制你自己的三条线）
try:
    with open(os.path.join(SKILL_ROOT, "config.json"), encoding="utf-8") as _cf:
        _cfg = json.load(_cf)
    OLD_TERMS = _cfg.get("old_track_terms", OLD_TERMS)
    CERT_TERMS = _cfg.get("cert_track_terms", CERT_TERMS)
    NEW_TERMS = _cfg.get("new_track_terms", NEW_TERMS)
except Exception:
    pass


IDENTITY_RE = re.compile(
    r"(我是|本人是|我们是|我们是做|我是做|我做|我们主要|主营|专业做|专门做|承接|我们公司|我们厂)"
    r"[^。！？!?\n]{2,60}")
PRICE_RE = re.compile(r"(?:¥|￥)\s*[\d,，]+(?:\.\d+)?|\d+(?:,\d{3})+(?:\.\d+)?\s*元|\d+(?:\.\d+)?\s*万(?:元)?|\d+(?:,\d{3})*(?:\.\d+)?\s*元")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
ERAS = [("2019-2021", 2019, 2021), ("2022-2023", 2022, 2023), ("2024-2026", 2024, 2026)]


def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def quarter(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return "%dQ%d" % (y, (m - 1) // 3 + 1)


def main():
    monthly = collections.defaultdict(lambda: {"old": 0, "cert": 0, "new": 0, "total": 0})
    first_seen = {}                      # term -> (epoch, chat_name)
    price_year = collections.Counter()   # 你发消息含报价数字的条数(按年)
    price_samples = {n: [] for n, _, _ in ERAS}
    identity = {n: collections.OrderedDict() for n, _, _ in ERAS}  # text->first date

    t0 = time.time()
    with open(IN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("side") != "self":
                continue
            t = epoch(rec.get("create_time"))
            if t is None:
                continue
            d = datetime.datetime.fromtimestamp(t)
            if d.year < 2019 or d.year > 2026:
                continue
            ym = d.strftime("%Y-%m")
            mtype = rec.get("type")
            c = rec.get("content") or ""
            if not isinstance(c, str) or not c:
                continue
            if c.lstrip().startswith("<"):
                tm = TITLE_RE.search(c)
                c = tm.group(1) if tm else ""
                if not c:
                    continue
            scan = c[:600]
            hit_old = hit_cert = hit_new = False
            for w in OLD_TERMS:
                if w in scan:
                    hit_old = True
                    break
            for w in CERT_TERMS:
                if w in scan:
                    hit_cert = True
                    break
            for w in NEW_TERMS:
                if w in scan:
                    hit_new = True
                    if w not in first_seen:
                        first_seen[w] = (t, rec.get("chat_name") or rec.get("chat") or "")
            bucket = monthly[ym]
            bucket["total"] += 1
            if hit_old:
                bucket["old"] += 1
            if hit_cert:
                bucket["cert"] += 1
            if hit_new:
                bucket["new"] += 1
            y = d.year
            # 报价
            pm = PRICE_RE.search(scan)
            if pm:
                price_year[y] += 1
                for n, a, b in ERAS:
                    if a <= y <= b and len(price_samples[n]) < 60:
                        ctx = re.sub(r"\s+", " ", scan)[:120]
                        price_samples[n].append((
                            d.strftime("%Y-%m-%d"),
                            (rec.get("chat_name") or "")[:16], ctx))
                        break
            # 身份语句
            for im in IDENTITY_RE.finditer(scan):
                frag = im.group(0).strip()
                key = re.sub(r"\s+", "", frag)[:40]
                for n, a, b in ERAS:
                    if a <= y <= b:
                        if key not in identity[n]:
                            identity[n][key] = (d.strftime("%Y-%m-%d"), frag)
                        break

    years = list(range(2019, 2027))
    months = sorted(monthly.keys())
    quarters = sorted({quarter(m) for m in months})

    def qsum(key):
        out = []
        for q in quarters:
            s = sum(monthly[m][key] for m in months if quarter(m) == q)
            out.append(s)
        return out

    q_old, q_cert, q_new = qsum("old"), qsum("cert"), qsum("new")
    # 迁移指数（平滑：新旧均为 0 的季度记 None）
    idx = [round(n / (n + o), 3) if (n + o) > 0 else None
           for n, o in zip(q_new, q_old)]
    # 转型拐点：连续 3 季 new > old
    pivot = None
    for i in range(len(quarters) - 2):
        if all(idx[i + k] is not None and idx[i + k] > 0.5 for k in range(3)):
            pivot = quarters[i]
            break

    # ---------- Markdown ----------
    L = []
    L.append("# 职业转型量化验证报告\n")
    L.append("对象：你发送的消息（2019-01 ~ 2026-10）；生成于 %s\n" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("## 一、三条赛道的季度热度（命中你消息的条数）\n")
    L.append("| 季度 | 弱电工程 | 考证投资 | 新赛道(无人机/3D打印/AI) | 迁移指数 new/(new+old) |")
    L.append("|---|---|---|---|---|")
    for i, q in enumerate(quarters):
        L.append("| %s | %d | %d | %d | %s |" % (
            q, q_old[i], q_cert[i], q_new[i],
            ("%.2f" % idx[i]) if idx[i] is not None else "—"))
    L.append("")
    if pivot:
        L.append("**拐点判定**：自 **%s** 起连续 3 个季度新赛道热度超过弱电工程——这是数据意义上的转型拐点。\n" % pivot)
    else:
        L.append("**拐点判定**：尚未出现连续 3 季新赛道 > 弱电工程的稳定跨越。\n")

    L.append("## 二、新赛道关键词首现日期（你第一次聊到它是什么时候）\n")
    L.append("| 关键词 | 首次提及 | 场景 |")
    L.append("|---|---|---|")
    keys = ["无人机", "大疆", "DJI", "低空", "维修", "3D打印", "打印机", "Fusion", "拓竹",
            "闲鱼", "自媒体", "公众号", "抖音", "智能体", "Coze", "AI", "GPT", "副业", "超级个体", "变现"]
    rows = [(w, first_seen[w]) for w in keys if w in first_seen]
    rows.sort(key=lambda x: x[1][0])
    for w, (t, chat) in rows:
        L.append("| %s | %s | %s |" % (w, datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d"), chat[:20]))
    notseen = [w for w in keys if w not in first_seen]
    if notseen:
        L.append("\n未在你消息中出现过的关键词：%s\n" % "、".join(notseen))

    L.append("\n## 三、报价行为（含 ¥/元/万 数字的你发消息，按年）\n")
    L.append("| 年份 | 含报价消息条数 |")
    L.append("|---|---|")
    for y in years:
        L.append("| %d | %d |" % (y, price_year.get(y, 0)))
    for n, _, _ in ERAS:
        ex = price_samples[n]
        if ex:
            L.append("\n**%s 报价样例（前8）**：\n" % n)
            for dt, chat, ctx in ex[:8]:
                L.append("- `%s` %s：%s" % (dt, chat, ctx))

    L.append("\n## 四、自我身份语句演变（「我是做…」类陈述，各阶段抽样）\n")
    for n, _, _ in ERAS:
        L.append("**%s**：\n" % n)
        items = list(identity[n].values())[:25]
        if not items:
            L.append("-（该阶段未检出自我定义语句）\n")
        for dt, frag in items:
            L.append("- `%s` %s" % (dt, frag))
        L.append("")

    L.append("---\n*词典法固有误差：一词多义（如「维修」「建模」横跨新旧业务）会引入少量噪声，趋势结论仍稳健。*")
    with open(os.path.join(OUT_DIR, "career_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ---------- HTML ----------
    def dump(x):
        return json.dumps(x, ensure_ascii=False)
    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>职业转型量化验证</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f6f7fb;margin:0;padding:24px;color:#222}
.card{background:#fff;border-radius:14px;box-shadow:0 2px 10px #0001;padding:18px;margin:16px 0}
h2{font-size:17px;color:#1f6feb;margin:0 0 10px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
table{border-collapse:collapse;font-size:12px;width:100%}td,th{border:1px solid #e3e6ee;padding:4px 6px}</style></head>
<body><h1 style="font-size:22px">职业转型量化验证</h1>
<div class="card"><h2>三条赛道季度热度</h2><canvas id="c1" height="120"></canvas></div>
<div class="card"><h2>迁移指数 new/(new+old)（>0.5 = 新赛道占上风）</h2><canvas id="c2" height="90"></canvas></div>
<div class="card"><h2>新赛道关键词首现时间线</h2><div id="tl"></div></div>
<div class="card"><h2>含报价数字的你发消息（按年）</h2><canvas id="c3" height="90"></canvas></div>
<script>
const q=__Q__, oldv=__OLD__, certv=__CERT__, newv=__NEW__, idxv=__IDX__, price=__PRICE__, fs=__FS__;
new Chart(document.getElementById('c1'),{type:'line',data:{labels:q,datasets:[
 {label:'弱电工程',data:oldv,borderColor:'#e67e22',tension:.3},
 {label:'考证投资',data:certv,borderColor:'#8e44ad',tension:.3},
 {label:'新赛道',data:newv,borderColor:'#1f6feb',tension:.3}]}});
new Chart(document.getElementById('c2'),{type:'line',data:{labels:q,datasets:[
 {label:'迁移指数',data:idxv,borderColor:'#27ae60',tension:.3,spanGaps:true}]},
 options:{plugins:{legend:{display:false}}}});
let tl='<table><tr><th>关键词</th><th>首现日期</th><th>场景</th></tr>';
fs.forEach(r=>{tl+='<tr><td><b>'+r[0]+'</b></td><td>'+r[1]+'</td><td>'+r[2]+'</td></tr>';});
document.getElementById('tl').innerHTML=tl+'</table>';
new Chart(document.getElementById('c3'),{type:'bar',data:{labels:[2019,2020,2021,2022,2023,2024,2025,2026],
 datasets:[{label:'含报价条数',data:price,backgroundColor:'#1f6feb'}]},options:{plugins:{legend:{display:false}}}});
</script></body></html>"""
    fs_rows = [[w, datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d"), (c or "")[:14]]
               for w, (t, c) in sorted(first_seen.items(), key=lambda x: x[1][0])
               if w in keys]
    html = (html.replace("__Q__", dump(quarters))
                .replace("__OLD__", dump(q_old)).replace("__CERT__", dump(q_cert))
                .replace("__NEW__", dump(q_new)).replace("__IDX__", dump(idx))
                .replace("__PRICE__", dump([price_year.get(y, 0) for y in years]))
                .replace("__FS__", dump(fs_rows)))
    with open(os.path.join(OUT_DIR, "career_charts.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("转型分析完成，用时 %.1fs；拐点=%s" % (time.time() - t0, pivot or "未检出"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
