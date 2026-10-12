#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识资产挖掘：把你 7.6 年的微信输出整理成可进 Obsidian 的素材库。

输出: export/knowledge_assets.md
  1) 知识分发总览（年度曲线/渠道 Top/最常分享的资料）
  2) 文件与链接分享清单（13000+ 张卡片的标题，按年归档，去重计数）
  3) 观点库（>100 字的长消息，按主题聚类，去重）
  4) 高价值问答对（群内：别人提问 → 你的实质回答）
"""
import sys, os, re, json, time, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)
IN_PATH = os.path.join(SKILL_ROOT, "output", "messages.jsonl")
OUT_MD = os.path.join(SKILL_ROOT, "output", "knowledge_assets.md")

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
URL_RE = re.compile(r"https?://([A-Za-z0-9.\-]+)")
NOISE_SUBSTR = {"不支持展示该内容", "邀请你加入群聊", "微信转账", "微信红包",
                "收到一笔转账", "群聊的聊天记录", "共1个内容", "大家都在玩的手游"}

WECHAT_NOISE_DOM = {"support.weixin.qq.com", "wx.qlogo.cn", "u.weixin.qq.com",
                    "mmbiz.qpic.cn", "wxapp.tc.qq.com", "dldir1v6.qq.com",
                    "mmbiz.qlogo.cn", "res.wx.qq.com", "www.qq.com"}

OLD_TERMS = ["综合布线","监控","摄像机","门禁","道闸","对讲","报警","广播","音箱","音响","话筒","功放",
             "调音台","投影","LED屏","显示屏","拼接屏","机房","桥架","光纤","弱电","智能化","会议系统",
             "中控","舞台","KTV","图纸","清单","预算","广联达","BIM","CAD","深化","竣工","验收","投标",
             "标书","工程量","签证","结算","进度款","停车场","交换机","POE"," poe"]
CERT_TERMS = ["一建","二建","一造","二造","造价师","消防工程师","备考","刷题","教材","押题","网课","精讲",
              "实务","法规","准考证","取证","注册","考试"]
NEW_TERMS = ["无人机","大疆","DJI","dji","飞控","桨叶","云台","图传","炸机","3D打印","打印机","喷头","PLA",
             "耗材","切片","STL","stl","Fusion","fusion","MakerWorld","拓竹","Bambu","闲鱼","淘宝","低空",
             "维修","主板","焊接","焊台","自媒体","公众号","引流","变现","流量","带货","短视频","抖音",
             "小红书","智能体","Coze","扣子","AI","GPT","gpt","大模型","提示词","Obsidian","知识库","副业",
             "超级个体","个人品牌","接单","工作流","DSL"]
BIZ_TERMS = ["工资","面试","招聘","离职","老板","同事","加班","职场","社保","公积金","合同","欠款","垫资"]
# 可选：从技能目录 config.json 覆盖主题词典
try:
    with open(os.path.join(SKILL_ROOT, "config.json"), encoding="utf-8") as _cf:
        _cfg = json.load(_cf)
    OLD_TERMS = _cfg.get("old_track_terms", OLD_TERMS)
    CERT_TERMS = _cfg.get("cert_track_terms", CERT_TERMS)
    NEW_TERMS = _cfg.get("new_track_terms", NEW_TERMS)
    BIZ_TERMS = _cfg.get("biz_terms", BIZ_TERMS)
except Exception:
    pass



def epoch(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


STRONG_NEW = {"无人机", "大疆", "DJI", "3D打印", "打印机", "Fusion", "拓竹", "Bambu", "闲鱼",
              "低空", "智能体", "Coze", "扣子", "Obsidian", "副业", "超级个体", "公众号",
              "自媒体", "变现", "工作流", "DSL", "小红书", "抖音"}


def classify(text):
    if any(w in text for w in STRONG_NEW):
        return "新赛道"
    checks = [("弱电工程", OLD_TERMS), ("考证经验", CERT_TERMS), ("职场商务", BIZ_TERMS)]
    for name, terms in checks:
        if any(w in text for w in terms):
            return name
    # 弱 "AI"/"GPT" 单独出现不足以定新赛道，需与其它新词共现
    new_hits = sum(1 for w in NEW_TERMS if w in text)
    if new_hits >= 2:
        return "新赛道"
    return "其他观点"


def main():
    # files[(title, year)] = count; file_first[(title)] = (date, chat)
    files = {}
    long_msgs = []           # (date, chat, is_group, theme, text)
    qa = []                  # (date, chat, q, a)
    domains = collections.Counter()
    long_by_year = collections.Counter()
    last_q = None            # (t, chat, excerpt)
    seen_files = set()
    t0 = time.time()

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
            if d.year < 2019 or d.year > 2026:
                continue
            chat = rec.get("chat", "")
            chat_name = (rec.get("chat_name") or chat)[:16]
            side = rec.get("side")
            mtype = rec.get("type")
            c = rec.get("content") or ""
            if not isinstance(c, str):
                continue

            if side == "self" and mtype in ("文件/链接/卡片",):
                tm = TITLE_RE.search(c)
                title = tm.group(1).strip() if tm else ""
                title = re.sub(r"<!\[CDATA\[|\]\]>", "", title)
                title = re.sub(r"\s+", " ", title)[:80]
                if title and not any(nz in title for nz in NOISE_SUBSTR) \
                        and not title.startswith(("<?xml", "<msg")):
                    y = d.year
                    key = (title, y)
                    files.setdefault(key, [0, None])
                    files[key][0] += 1
                    if files[key][1] is None:
                        files[key][1] = (d.strftime("%Y-%m-%d"), chat_name)
                for dm in URL_RE.finditer(c):
                    dl = dm.group(1).lower()
                    if dl not in WECHAT_NOISE_DOM:
                        domains[dl] += 1

            if side == "self" and mtype == "文本":
                text = c.strip()
                # 问答对：紧跟别人提问的实质回答
                if last_q and last_q[1] == chat and 0 <= t - last_q[0] <= 600 \
                        and len(text) >= 30 and len(qa) < 500:
                    qa.append((d.strftime("%Y-%m-%d"), chat_name,
                               last_q[2][:80], text[:200]))
                    last_q = None
                elif "?" in text or "？" in text:
                    last_q = None  # 自己也在提问，打断链
                # 观点库
                if len(text) >= 100 and not text.lstrip().startswith(("<", "{")):
                    norm = re.sub(r"\s+", "", text)[:40]
                    if norm not in seen_files:
                        seen_files.add(norm)
                    else:
                        continue  # 群发模板去重（如「欢迎入局」话术）
                    long_by_year[d.year] += 1
                    long_msgs.append((d.strftime("%Y-%m-%d"), chat_name,
                                      chat.endswith("@chatroom"), classify(text), text[:600]))
            elif side == "them" and mtype == "文本":
                if ("？" in c or "?" in c) and len(c) >= 8 and len(c) <= 120:
                    last_q = (t, chat, c)

    # ---------- 输出 ----------
    L = ["# 知识资产库（微信 7.6 年输出沉淀）\n"]
    L.append("生成：%s ｜ 输入：%s 条消息\n" % (time.strftime("%Y-%m-%d"), "1,952,120"))

    L.append("## 一、知识分发总览\n")
    L.append("- 分享文件/链接卡片：%d 张（按标题+年份去重后 %d 份独立资料）" % (
        sum(v[0] for v in files.values()), len(files)))
    L.append("- 观点长文（>100字）：%d 条，年度分布：%s" % (
        len(long_msgs), "，".join("%d:%d" % (y, long_by_year.get(y, 0)) for y in range(2019, 2027))))
    top_dom = domains.most_common(15)
    L.append("- 链接域名 Top15：%s" % "，".join("%s(%d)" % (d, n) for d, n in top_dom))
    theme_cnt = collections.Counter(x[3] for x in long_msgs)
    L.append("- 观点主题分布：%s\n" % "，".join("%s %d" % (k, v) for k, v in theme_cnt.most_common()))

    L.append("## 二、最常分享的资料 Top30（你反复分发的东西 = 你的代表作）\n")
    L.append("| 份数 | 首发 | 场景 | 标题 |")
    L.append("|---|---|---|---|")
    top_files = sorted(files.items(), key=lambda x: -x[1][0])[:30]
    for (title, y), (cnt, first) in top_files:
        L.append("| %d | %s | %s | %s |" % (cnt, first[0], first[1], title))
    L.append("")

    L.append("## 三、文件与链接分享清单（按年，独立资料）\n")
    by_year = collections.defaultdict(list)
    for (title, y), (cnt, first) in files.items():
        by_year[y].append((first[0], first[1], cnt, title))
    for y in sorted(by_year):
        L.append("### %d 年（%d 份）\n" % (y, len(by_year[y])))
        for dt, chat, cnt, title in sorted(by_year[y]):
            L.append("- `%s` %s%s%s" % (dt, title,
                                        (" ×%d" % cnt) if cnt > 1 else "",
                                        (" ｜" + chat) if cnt == 1 else ""))
        L.append("")

    L.append("## 四、观点库（按主题）\n")
    themes = ["新赛道", "弱电工程", "考证经验", "职场商务", "其他观点"]
    for th in themes:
        items = [x for x in long_msgs if x[3] == th]
        if not items:
            continue
        L.append("### %s（%d 条）\n" % (th, len(items)))
        for dt, chat, is_grp, _t, text in sorted(items):
            text1 = text.replace("\n", " ").strip()
            L.append("- `%s`%s%s：%s" % (dt, "｜" + chat if chat else "",
                                         "｜群" if is_grp else "", text1))
        L.append("")

    L.append("## 五、高价值问答对（别人问 → 你答，前 %d 对）\n" % min(300, len(qa)))
    for dt, chat, q, a in qa[:300]:
        L.append("- `%s` %s\n  - **问**：%s\n  - **答**：%s" % (dt, chat, q.replace("\n", " "), a.replace("\n", " ")))

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("完成：文件卡片 %d 张(独立 %d) / 观点长文 %d 条 / 问答对 %d 个，用时 %.1fs" % (
        sum(v[0] for v in files.values()), len(files), len(long_msgs), len(qa), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
