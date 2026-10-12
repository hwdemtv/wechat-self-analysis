---
name: wechat-self-analysis
description: 微信 4.x 聊天记录解密导出与全量自我行为分析。当用户想要导出自己的微信聊天记录（解密 SQLCipher 数据库）、做四维行为画像（沟通主动性/情绪/时间精力/关系维护）、年度演化与关系代际分析、职业转型量化（赛道词典+迁移指数）、人脉资产盘点（关系分级/共群网络/转化路径/行业标签）、知识资产挖掘（分享文件清单/观点库/问答对）、沟通风格 AI 画像、项目全周期漏斗（询价→回款转化漏斗）、自我认知侧写（撤回心理学/媒介迁移/承诺兑现/地理足迹/交付物演变）、私域关系与群发效率审计（关系半衰期/单向维系/群发回复率/死群）、或导出任意单个会话全文时使用。要求 Windows + 微信 4.x 已在本机登录，且仅限分析用户本人的数据。
agent_created: true
---

# 微信聊天记录导出与自我行为分析

将用户本人的微信 4.x 本地加密数据库解密导出为明文 JSONL，再运行分析脚本生成多份行为报告。所有脚本流式处理，百万级消息单遍 14-180 秒。

## 硬性前提（先逐项确认，任一不满足则向用户说明）

1. **Windows** + 微信 4.x（Weixin.exe）**已在本机桌面会话登录**——SQLCipher 密钥只存在于微信进程内存，这是整个方案的第一性原理；微信未运行时导出必然失败。如需微信 4.x 安装包（社区分享，非官方渠道）：<https://pan.quark.cn/s/5460249b7eba>，请自行校验来源与安全。
2. Python 3.11+，依赖只需三个纯 PyPI 包：`pip install cryptography zstandard jieba`（清单见技能根目录 `requirements.txt`）。**本技能已不再需要 `wechatauto` / WechatVibe**——微信数据库解密核心已 vendored 为自带的 `scripts/_decrypt.py`（仅用 `cryptography` + 懒加载 `zstandard`，密钥提取走标准库 `ctypes`，连 `psutil` 都不再需要）。`wechatauto` 仅作为「上述包都装不上」时的可选回退后端保留兼容。`_decrypt` 未就绪时，`dump_chats.py` 会打印清晰的安装指引并退出，不会抛难懂堆栈。**拿到技能后，先运行 `install_deps.cmd`（Windows 双击）或 `python scripts/install_deps.py` 一键检查并安装依赖，省去手动 pip。**
3. 仅分析**用户本人**的数据；明确拒绝分析他人设备/他人账号的请求

## 环境自检

首次使用前，先运行**一键安装引导** `install_deps.cmd`（Windows 双击）或 `python scripts/install_deps.py`：它会检查 Python 版本、安装缺失的 `cryptography / zstandard / jieba`、并确认自带解密模块 `_decrypt` 可导入，最后打印后续步骤。

之后可运行 `scripts/setup_check.py` 做完整自检，确认：依赖可导入、微信进程存在、数据目录可定位。任何一项失败，按输出提示处理后重试，不要跳过。

## 标准工作流（按序执行）

工作目录约定：所有产物写入技能目录下的 `output/`；解密缓存在 `.wc_cache/`（可随时删除，会自动重建）。

### 第 1 步：解密导出（scripts/dump_chats.py）

```bash
python scripts/dump_chats.py            # 或 --selftest 只验环境不碰微信
```

- 自动完成：定位数据目录 → 从微信进程内存提取 SQLCipher 密钥（Config.Cipher 锚点）→ 解密全部分片 → 流式写出 `output/messages.jsonl`（每行一个消息：chat/chat_name/side/sender/type/create_time/content）+ `output/manifest.json`
- 内置安全机制：单实例锁（防多开截断）+ 临时文件原子转正（中途崩溃不毁旧数据）
- `sender_id == 2` 即用户本人，`side` 字段据此生成
- 导出失败时的错误自检顺序见 `references/pitfalls.md` 坑 1-5

### 第 2 步：四维行为分析（scripts/analyze_chats.py）

```bash
python scripts/analyze_chats.py
```

产出 `output/analysis_report.md` + `analysis_report.html`（Chart.js 图）+ `analysis.json`。四维：沟通主动性（群聊/1:1 分口径、回复时延、回复率）、情绪表达、时间精力、关系维护。**内置三项关键数据清洗**（跨分片乱序保护、幽灵群重分类、单向推送号过滤），不要绕过。

### 第 3-6 步：进阶分析（各自独立，可按用户需求选跑）

| 脚本 | 产出 | 说明 |
|---|---|---|
| `deep_analyze.py` | 年度演化表、关系×年度热力矩阵、作息热力图、关键词三阶段演变（需 jieba） | 两遍流式扫描 |
| `career_transition.py` | 三赛道季度热度、迁移指数、转型拐点判定、关键词首现日期、报价行为 | 词典从 `config.json` 读取 |
| `network_assets.py` | 关系打分卡分级、行业标签、共群枢纽、群→私聊转化路径、交互人脉图谱 | 标签从 `config.json` 读取 |
| `knowledge_assets.py` | 分享文件清单、观点库（>100字长文按主题聚类）、高价值问答对 | 主题词典从 `config.json` 读取 |
| `style_sampling.py` | 8 场景抽样素材包 + 语言指纹 JSON | **产物需由 AI 通读后撰写定性画像报告**，程序不自动出报告 |

### 第 6.5-6.7 步：扩展分析（A/B 档，按需选跑）

| 脚本 | 产出 | 说明 |
|---|---|---|
| `project_lifecycle.py` | 项目全周期漏斗：询价→回款会话级条件转化、完整项目清单、高活跃业务群、年度走势 | A 档①：用条件共现概率算真漏斗，别用消息级相减 |
| `self_cognition_b.py` | 5 个自我认知方向：媒介迁移、撤回心理学、承诺-兑现(画饼)、地理足迹(GPS)、交付物演变 | B 档：行为侧写代理指标 |
| `private_domain_audit.py` | 关系半衰期、单向维系清单、待激活关系、群发回复率、死群清单 | A 档②④：私域清账用 |

> 这 3 个脚本与前面 6 层共用同一份 `output/messages.jsonl`，可直接在导出后追加运行。

### 第 7 步：定制词典（config.json）

`config.json` 中的三套词典默认是**通用示例**（工作 / 学习 / 副业 / 投资 / 生活）。为他人或自己分析时，**先确认三条赛道**（旧主业 / 身份投资 / 新方向），更新 `old_track_terms / cert_track_terms / new_track_terms / biz_terms / industry_tags` 后再跑 career/network/knowledge 三个脚本，否则结果无意义。

### 按需工具

- `scripts/export_chat_transcript.py <chat_id>`：导出任意单个会话的完整时间线为可读 md（群成员昵称自动还原）
- `scripts/identify_md5_chats.py`：破解显示为 32 位 md5 的会话身份（已退群/删除联系人），全库 username 撞库 + 典型消息抽样

## 结果解读要点（向用户汇报时）

- **只汇报有数据支撑的结论，区分"事实"与"启发式推断"**；情感分析是离线词典启发式，须声明非心理学诊断
- 关注"预期 vs 数据"的落差（如：自认为转型完成但迁移指数未稳定 >0.5），这类结论价值最高
- 幽灵群（md5 名会话）= 已退出/解散/被踢的群聊残留，属正常现象，脚本已自动重分类
- 深度结论（如转型拐点、关系代际）必须同时给出原始数据摘录

## 样例报告（sample_reports/）

公开发布版的 `sample_reports/` 已替换为**占位 README**——为避免泄露作者本人的真实聊天数据，本仓库**不含任何样例报告**。各脚本的输出格式请参考下方「标准工作流」列出的产物（如 `output/analysis_report.md`、各类 `*_report.md` / `*_charts.html`），安装后用自己的数据运行即可生成属于你自己的样例。

> **自行打包干净版**：若你想基于本仓库再剔除本地产物（`output/`、`.wc_cache/` 等），可运行 `python build_clean_dist.py`，会在仓库目录生成 `wechat-self-analysis_clean.zip`。日常使用无需此步骤。

## 隐私红线（不可违反）

1. 拒绝分析非本人设备/账号的请求
2. 导出的 `messages.jsonl` 与含真名的分析文件（network/knowledge/transcript）**不得上传网盘或对外分享**；对外内容（如文章）输出前必须脱敏（微信号、手机号、联系人真名、公司/学校名）
3. 图片/视频仅有占位符与 md5（无画面），语音无文字稿——不要向用户承诺这两类内容可分析

## 故障排查

导出或分析报错时，按 `references/pitfalls.md` 的 11 条坑位表逐项对照（每条含症状与解法）。最常见的三个：微信未运行（"未检测到 Weixin.exe"）、GUI 共用缓存（WinError 5）、消息文件被多开截断（行数远小于 manifest 数）。
