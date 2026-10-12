# 微信聊天记录解密与自我行为分析 · WeChat 4.x Self-Analysis

> **本地解密 · 隐私优先 · 全离线** —— 把你自己微信 4.x 的本地加密数据库解密导出为明文，再跑一套行为分析报告。
> **Privacy-first, fully offline** WeChat 4.x chat export & self-behavior analytics.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-blue.svg)](https://github.com/hwdemtv/wechat-self-analysis)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org)
[![WeChat](https://img.shields.io/badge/WeChat-4.x-07C160.svg)](https://weixin.qq.com)
[![Agent Skill](https://img.shields.io/badge/agent--skill-WorkBuddy-ff69b4.svg)](https://www.workbuddy.cn)

---

## 这是什么 / What is this

一个 **WorkBuddy 技能（Agent Skill）**：在你**自己的 Windows 电脑**上，把你登录中的微信 4.x 本机加密聊天数据库（SQLCipher 4）解密导出为纯文本 `messages.jsonl`，再用十几个分析脚本生成多维度的「自我行为分析报告」——**全程不联网、不上传、不调用任何云端服务**。

A WorkBuddy agent skill that **locally** decrypts your own WeChat 4.x on-disk SQLCipher databases and produces multi-dimensional self-behavior analytics. **No network, no upload, no cloud.**

**核心关键词 / Keywords:** 微信聊天记录导出 · WeChat 4.x 解密 · SQLCipher · 聊天记录备份 · 自我分析 · 行为画像 · 隐私优先 · 本地离线 · 数字化转型复盘 · 关系资产盘点 · agent skill · WorkBuddy

---

## 为什么需要它 / Why

- 🔐 **密钥只活在微信进程内存**——这是整个方案的第一性原理。本技能用 `ctypes` 直接从 `Weixin.exe` 内存提取 SQLCipher 主密钥，再逐页 AES-256-CBC 解密，**不需要 root、不需要模拟器、不需要任何第三方账号**。
- 🧩 **解密核心已 vendored**——不再依赖 `wechatauto`，只需三个纯 PyPI 包（`cryptography` / `zstandard` / `jieba`）。
- 📊 **十层分析**：四维行为画像、年度演化、职业转型量化、人脉资产、知识资产、沟通风格、项目全周期漏斗、自我认知侧写、私域关系审计、单会话全文导出。
- 🛡️ **隐私红线内建**：拒绝分析他人账号；导出物与含真名文件禁止外传；对外内容输出前强制脱敏。

---

## 功能特性 / Features

| 维度 | 脚本 | 产出 |
|---|---|---|
| 解密导出 | `dump_chats.py` | `output/messages.jsonl` + `manifest.json`（流式，百万级消息单遍 14–180s） |
| 四维行为画像 | `analyze_chats.py` | 沟通主动性 / 情绪 / 时间精力 / 关系维护（Chart.js 图） |
| 年度演化 | `deep_analyze.py` | 关系×年度热力矩阵、作息热力、关键词三阶段演变 |
| 职业转型量化 | `career_transition.py` | 三赛道季度热度、迁移指数、转型拐点 |
| 人脉资产 | `network_assets.py` | 关系分级、行业标签、共群枢纽、群→私聊转化 |
| 知识资产 | `knowledge_assets.py` | 分享文件清单、观点库、高价值问答对 |
| 沟通风格 | `style_sampling.py` | 8 场景抽样 + 语言指纹（供 AI 撰写定性画像） |
| 项目漏斗 | `project_lifecycle.py` | 询价→回款会话级转化漏斗 |
| 自我认知 | `self_cognition_b.py` | 媒介迁移 / 撤回心理学 / 画饼 / 地理足迹 / 交付物演变 |
| 私域审计 | `private_domain_audit.py` | 关系半衰期 / 单向维系 / 群发回复率 / 死群 |
| 单会话全文 | `export_chat_transcript.py` | 任意会话完整时间线 md |
| md5 身份破解 | `identify_md5_chats.py` | 还原已退群/删除联系人的 md5 会话身份 |

---

## 实测数据 / Benchmarks

在作者本机（微信 4.x，约 **195 万条**消息）的真实跑测：

| 指标 | 数值 |
|---|---|
| 解密分片数 | 8 个消息分片 |
| 导出耗时 | 单遍流式 14–180 秒（取决于消息量） |
| 解密后端 | 内置 `scripts/_decrypt.py`（vendored，零 wechatauto 依赖） |
| 依赖体积 | 仅 `cryptography` + `zstandard` + `jieba` |
| 网络请求 | 0（完全离线） |

---

## 三种安装方式 / Install

### 方式一：一键脚本（推荐）

**Windows（PowerShell）：**
```powershell
irm https://github.com/hwdemtv/wechat-self-analysis/raw/main/install.ps1 | iex
```

**macOS / Linux（bash）：**
```bash
curl -fsSL https://github.com/hwdemtv/wechat-self-analysis/raw/main/install.sh | bash
```

### 方式二：手动克隆

```bash
git clone https://github.com/hwdemtv/wechat-self-analysis.git ~/.workbuddy/skills/wechat-self-analysis
```

### 方式三：下载干净版 zip

不想克隆仓库时，直接获取现成干净版即可：

- 到仓库 **Releases** 页下载 `wechat-self-analysis_clean.zip`（已剔除一切真实聊天数据，仅留占位说明）；
- 解压到你的 Agent 技能目录（如 `~/.workbuddy/skills/`），重启 Agent 即生效。

> 本技能是标准 `SKILL.md` 体系，**不绑定特定 Agent**，按你所用 Agent 的技能目录放置即可，无需为不同 Agent 各写一套安装步骤。

安装后，**先运行依赖引导**：
```bash
# Windows 直接双击
install_deps.cmd
# 或任意平台
python scripts/install_deps.py
```

---

## 快速开始 / Quick Start

> ⚠️ 前置：Windows + 微信 4.x（Weixin.exe）**已在本机桌面会话登录**。微信未运行时导出必然失败。

```bash
# 1) 解密导出
python scripts/dump_chats.py            # 或 --selftest 只验环境不碰微信

# 2) 四维行为分析
python scripts/analyze_chats.py

# 3) 进阶分析（任选）
python scripts/deep_analyze.py
python scripts/career_transition.py
python scripts/network_assets.py
python scripts/knowledge_assets.py
```

产物写入技能目录下的 `output/`。完整工作流见 [`SKILL.md`](SKILL.md)。

---

## 隐私与合规 / Privacy & Compliance

- ✅ 仅分析**用户本人**的设备与账号；明确拒绝分析他人。
- ✅ 解密与全部分析**在本地完成，零网络请求**。
- ✅ 对外分享内容（文章、样例）输出前必须脱敏（微信号、手机号、联系人真名、公司/学校名）。
- ✅ 本仓库**不含任何作者真实聊天数据**：`sample_reports/` 在发布时已替换为占位说明。
- ⚠️ 导出的 `messages.jsonl` 与含真名的分析文件**请勿上传网盘或公开分享**。

---

## 目录结构 / Structure

```
wechat-self-analysis/
├── SKILL.md                 # 技能本体（工作流 / 隐私红线）
├── README.md                # 本文件
├── LICENSE                  # MIT
├── config.json              # 分析词典（通用示例，可自定义）
├── requirements.txt         # cryptography / zstandard / jieba
├── install_deps.cmd         # Windows 双击安装依赖
├── install.sh / install.ps1 # 跨平台一键安装本技能
├── build_clean_dist.py      # 生成干净分发 zip
├── references/              # 密钥提取原理 / 坑位表
├── sample_reports/          # 占位（发布版无真实数据）
└── scripts/
    ├── _decrypt.py          # vendored 解密核心（SQLCipher 4）
    ├── dump_chats.py        # 解密导出
    ├── install_deps.py      # 依赖检查 + 安装引导
    ├── analyze_chats.py     # 四维画像
    ├── deep_analyze.py      # 年度演化
    ├── career_transition.py # 职业转型量化
    ├── network_assets.py    # 人脉资产
    ├── knowledge_assets.py  # 知识资产
    ├── style_sampling.py    # 沟通风格抽样
    ├── project_lifecycle.py # 项目漏斗
    ├── self_cognition_b.py  # 自我认知侧写
    ├── private_domain_audit.py # 私域审计
    ├── export_chat_transcript.py # 单会话全文
    └── identify_md5_chats.py    # md5 身份破解
```

---

## 常见问题 / FAQ

**Q：会被微信封号吗？**
A：本技能只读你本机已解密/可解密的本地数据库，不登录、不模拟、不发消息，**无封号风险**。但仍请仅用于分析本人数据。

**Q：支持 Mac / Linux 吗？**
A：解密步骤依赖 Windows 上的 `Weixin.exe` 进程内存，因此**导出仅限 Windows**。分析脚本（纯 Python）可在任意平台运行导出的 `messages.jsonl`。

**Q：微信没登录能导出吗？**
A：不能。SQLCipher 密钥只存在于已登录的微信进程内存，这是方案的第一性原理。

**Q：为什么不再需要 wechatauto？**
A：解密核心已被 vendored 为 `scripts/_decrypt.py`（仅用 `cryptography` + 懒加载 `zstandard` + 标准库 `ctypes`），彻底甩掉其原生依赖树。

---

## 关键词 / SEO Keywords

`微信聊天记录导出` `微信4.x解密` `WeChat 4.x decrypt` `SQLCipher` `聊天记录备份` `微信数据库解密` `自我行为分析` `行为画像` `微信数据可视化` `隐私优先` `本地离线分析` `agent skill` `WorkBuddy` `workbuddy skill` `微信复盘` `关系资产盘点` `职业转型分析` `人脉分析` `Python 微信` `微信自动化`

---

## License

[MIT](LICENSE) © 2026 hwdemtv
