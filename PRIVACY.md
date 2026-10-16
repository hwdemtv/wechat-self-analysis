# 数据安全指南 · Privacy & Data Safety (for users)

> 配套技能：`wechat-self-analysis`（微信 4.x 本地聊天记录解密 + 自我行为分析）
> 本文件是**给使用者的操作指南**，讲清楚「数据在哪、怎么才会泄露、怎么保护自己」。
> 给开发者/维护者的安全清单见 [`SECURITY.md`](SECURITY.md)。

---

## 1. 它到底动了什么 / What it touches

- 只读你**本机、已登录**的微信本地加密数据库（SQLCipher 4 密文）。
- 密钥**只存在于微信进程内存**，本工具用 `ctypes` 从 `Weixin.exe` 内存提取，**不修改、不写入**微信数据库。
- 解密与全部分析都在**你本机**完成，**零网络请求**（唯一的例外是可选的安装依赖，那是从 PyPI 拉公开纯包）。

一句话：**它不会把你的聊天记录发到任何地方——除非你自己把它发出去。**

---

## 2. 明文落在哪 / Where the plaintext goes

解密后的明文 `messages.jsonl` 是**最敏感**的产物，因为它包含你与他人的大量个人信息。

| 你执行的方式 | 明文落盘位置 | 是否进 git | 风险 |
|---|---|---|---|
| `python scripts/dump_chats.py`（默认） | `.wc_cache/export/messages.jsonl` | ❌ 已 gitignore | 低（临时、不显眼、易清理） |
| `python scripts/dump_chats.py --export-raw`（需二次确认） | `output/messages.jsonl` | ❌ 已 gitignore | 中（长期明文副本，需自管） |

分析脚本会自动在以上两处（及历史 `scripts/export/`）定位明文，**你不用关心具体路径**。

> 默认策略：明文默认落在 `.wc_cache/export/`（临时、gitignore）。只有你**显式**加 `--export-raw` 并确认，才会保留一份到 `output/` 供分享/分析。

---

## 3. 怎样才会泄露 / How leaks actually happen

解密与分析全程离线、零上传、不调用任何云端服务（仅首次安装依赖需联网拉取纯 PyPI 包，且支持 `--dry-run` 预检）；泄露几乎都来自**使用者的后续操作**：

1. ❌ 把 `messages.jsonl`、`manifest.json`、含真名的分析文件**上传网盘 / GitHub / 发给别人**。
2. ❌ 把**原文**直接贴进 ChatGPT / 文心 / 通义等**第三方 AI / API**。
3. ❌ 在文章、视频里**截图原始聊天**（露微信号、头像、昵称、手机号）。
4. ❌ 把可识别第三方（客户、家人、同事）的对话**公开**，熟人可重识别。
5. ❌ 帮别人导出 / 读别人的微信 / 用本工具做**监控**——这既违法也违背本工具定位。

---

## 4. 保护自己：三步走 / Protect yourself

### ① 导出后及时清理
- 默认在 `.wc_cache/export/` 的产物，分析完可直接删除该目录。
- 若用过 `--export-raw`，用完请删除 `output/messages.jsonl` 与 `output/manifest.json`，或移入加密盘。

### ② 对外前先脱敏（强烈推荐）
```bash
# 把明文 jsonl 脱敏成新文件，并打印命中统计
python scripts/privacy_filter.py messages.jsonl -o messages_redacted.jsonl --summary

# 额外点名替换姓名/公司/地址（每行一个词）
python scripts/privacy_filter.py messages.jsonl -o out.jsonl --names my_names.txt
```
它会自动替换：📱 手机号 · 🪪 身份证 · 💳 银行卡 · ✉️ 邮箱 · `wxid_` · QQ · 网址；
姓名/公司/地址等「弱 PII」用 `--names` 词表**点名**替换（避免误伤）。

### ③ 喂 AI 只给脱敏样本
正确流向：**本地解密 → 本地统计 → 本地脱敏 → 只抽必要样本 → 再给 AI 定性**。
不要把 195 万条原文丢给模型；把「【对方】：询问项目交付时间…」这种脱敏片段交给 AI 即可。

---

## 5. 安装时别中招 / Safe install

- ✅ **推荐**：到 Releases 下载 `wechat-self-analysis_clean.zip`，解压前**比对 SHA-256**。
- ⚠️ **不推荐** `irm ... | iex` / `curl ... | bash` 直跑远程脚本——对会碰聊天数据的工具，供应链风险过高。
- 🔍 不放心安装会做什么？先预览：`python scripts/install_deps.py --dry-run`，它只打印将要执行的 `pip` 命令，**绝不真装**。

---

## 6. 一句话红线 / The one-line red line

**只分析你自己的账号；明文不出本机；对外必脱敏；绝不监控他人。**

违反以上任何一条，不仅违背本工具定位，也可能触碰《个人信息保护法》第十条/第二十五条。
