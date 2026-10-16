# 安全整改清单 V1.0 · Security Hardening Checklist

> 配套技能：`wechat-self-analysis`（微信 4.x 本地聊天记录解密 + 自我行为分析）
> 本文档面向**开源发布**场景，定义本项目的安装安全、数据生命周期、脱敏层、AI 调用边界与发布前检查项。
> 定位说明：本项目不是「微信破解工具」，而是 **Local-first Personal Data Audit（本地优先的个人数据审计工具）**——核心卖点是「聊天记录不上传、统计在本地、AI 只处理脱敏后的结果」。

---

## 0. 风险评级（来自安全评审）

| 维度 | 评级 | 说明 |
|---|---|---|
| 技术可行性 | 🟢 8.5/10 | 已真实跑通 195 万条 / 3871 会话 / 65 秒，并处理跨分片、幽灵群、多开覆盖 |
| 数据处理设计 | 🟡 6/10 | 流式处理、单实例锁、原子转正良好；但默认产生完整 `messages.jsonl` 偏激进 |
| Agent 安全 | 🟠 4/10 | Agent 与微信同处一个系统用户/会话，天然具备读取进程内存的权限 |
| 安装供应链 | 🔴 3/10 | `irm | iex` 一键远程脚本对「碰聊天数据」的工具风险过高（已降级） |
| 隐私设计 | 🟡 5/10 | 已有隐私意识，但应进一步做到「原始数据默认不落盘、不上传、不进 AI」 |
| 法律风险 | 🟡 自用可控 / 对外服务显著升高 | 自己设备自用 vs 帮别人导出，风险等级完全不同 |

**结论**：技术路线可以继续；**安全架构必须升级**；公开传播可以做，但绝对不要包装成「微信破解工具」。

---

## 1. 核心原则（不可妥协）

1. **Local-first**：解密、统计、分析全部在本机完成，零网络请求（除可选的依赖安装）。
2. **原始数据最小化**：原始聊天明文只在内存中经过，不长期落盘、不上传、不进任何云端 AI。
3. **本人数据边界**：只处理用户**自己合法持有、且有权分析**的数据；不用于访问、获取、监控或分析他人微信账号与设备。
4. **第三方 PII 责任**：聊天记录来自本人账号，但其中包含大量第三方个人信息；使用者对导出、分析、保存、公开行为负责。「只读自己账号」≠「没有他人隐私风险」。

---

## 2. 威胁模型（Threat Model）

| 威胁 | 来源 | 影响 | 缓解 |
|---|---|---|---|
| 供应链投毒 | 仓库/账号被攻陷、CDN/DNS 劫持、依赖污染 | 远程脚本/依赖被替换为恶意代码，可读取微信进程与聊天数据并外传 | 不推荐 `irm\|iex`；提供 Release zip + SHA-256；只从官方仓库安装 |
| Agent 越权 | 不可信 Agent / 技能 / 脚本在本地执行 | 借助同用户同会话权限读取微信内存 | 只从可信来源装技能；只在本机自己账号下运行；不交不可信环境 |
| 原始数据泄露 | `messages.jsonl` 落盘后被上传/窃取 | 全量明文（含第三方 PII）外泄 | 分析后删除或加密存储；Phase-2 改为默认不导出原始 JSONL |
| 公开再识别 | 公开统计含「H君+行业+城市+时间」组合 | 熟人可重识别第三方 | 案例泛化到月级/去身份；只公开脱敏后统计 |
| 误用为监控 | 用于伴侣/员工/他人监控 | 违法 + 伦理问题 | 使用边界声明；拒绝分析他人账号 |

---

## 3. 安装与供应链安全

- ✅ **推荐**：到 Releases 下载 `wechat-self-analysis_clean.zip` → 自行解压到技能目录 → 运行 `install_deps` / `setup_check`。
- ✅ **校验完整性**：每个 Release 附 zip 的 **SHA-256**，解压前比对。
- ⚠️ **不推荐**：`irm .../install.ps1 | iex` 或 `curl ... | bash` 直跑远程脚本——对会读取微信内存与聊天数据的工具，一旦上游被篡改或网络被劫持，风险远高于普通工具。保留该命令但**不再标记为推荐**。
- ✅ 安装脚本（`install.sh` / `install.ps1`）仅做「下载仓库 / 放到技能目录」，不包含任何采集、回传逻辑；脚本本身也应可审计（纯文本、无混淆）。
- ✅ 依赖仅 `cryptography` / `zstandard` / `jieba` 三个纯 PyPI 包，无原生依赖树，降低 supply-chain 面。

---

## 4. 数据生命周期（Data Lifecycle）

实际落地架构（v1.1 起）：

```
微信本地 DB(已登录本机)
      │  ctypes 读 Weixin.exe 进程内存提取 SQLCipher 密钥（PROCESS_VM_READ 最小权限）
      ▼
本地解密（SQLCipher 4 / AES-256-CBC）
      │
      ▼
dump_chats.py
      ├─ 默认：明文写到 .wc_cache/export/messages.jsonl（gitignore、临时、不显眼）★推荐默认
      └─ --export-raw（需二次确认）：明文持久化到 output/messages.jsonl（显式保留）
      │
      ▼
分析脚本（统一用 _paths.locate_messages_jsonl() 自动定位任意一处）
      │
      ├─ 本地统计/指标 → metrics / 报告（全部本地、零联网）
      └─ 对外前：privacy_filter.py 脱敏 → 再分享/进 AI
```

- 默认行为：`dump_chats.py` 默认把明文写到 **`.wc_cache/export/`**（已 gitignore，临时、不显眼），而非显眼的 `output/`。分析脚本通过 `_paths.locate_messages_jsonl()` 自动定位，端到端仍可用。
- `--export-raw`：用户显式加该开关并二次确认（交互 y/N；非交互环境需 `--yes`）后，才把明文持久化到 `output/` 供分析/分享。
- 任何含真名/手机号/地址的分析产物，输出前用 `privacy_filter.py` 强制脱敏（见 `scripts/privacy_filter.py` 与 `tests/test_redaction.py`）。

---

## 5. 脱敏层与 AI 调用边界

- 正确流向：**本地解密 → 本地统计 → 本地脱敏 → 只抽必要样本 → 再给 AI 定性**，绝不把 195 万条原文丢给模型。
- AI 输入示例：发送「【对方】：询问项目交付时间……」而非「张三：你上次那个项目什么时候能给我？我公司杭州余杭区……」。
- 至少做到：联系人匿名化（A/B/C）、地点/公司/项目脱敏、只保留无法识别个人的必要语义。
- `style_sampling.py` 已设计为「抽样素材包 + 语言指纹」，产物交给用户本地 AI 通读，而非上传原文。

---

## 6. 权限与 Agent 信任边界

- 运行本技能的 Agent 与微信**同处一个系统用户/会话**，天然拥有 `OpenProcess(PROCESS_VM_READ)` 读取微信进程内存的权限——这是方案可行的前提，也是最大安全隐患。
- 因此：**只从可信来源安装技能；只在本机自己账号下运行；绝不要把技能/脚本交给不可信环境或他人执行。**
- 技能只读、不写微信数据库；不修改、不注入、不模拟微信客户端行为。

---

## 7. 隐私与法律红线

依据《个人信息保护法》：第十条（禁止非法收集/使用/加工/传输/买卖/提供/公开他人个人信息）、第二十五条（处理者不得公开其处理的个人信息，除非取得单独同意）、以及「合法、正当、必要、最小影响」原则。

| 行为 | 判断 |
|---|---|
| 自己电脑分析自己微信 | 🟢 相对低风险 |
| 本地统计 / 本地生成报告 | 🟢 |
| 原始聊天存加密硬盘 | 🟡 |
| 原始聊天交本地 AI | 🟡 |
| 脱敏后抽样交 AI | 🟢/🟡 |
| 原始聊天上传 ChatGPT / 第三方 API / 网盘 / GitHub | 🔴 不推荐 |
| 公开联系人聊天内容 | 🔴 |
| 帮别人导出 / 读别人微信 / 监控他人 | 🔴 |

---

## 7.1 数据分级（L0–L4）

| 级别 | 数据 | 落盘默认 | 处理要求 |
|---|---|---|---|
| L0 | 代码、文档、依赖清单、示例假数据 | 入库 | 公开安全 |
| L1 | 本地统计指标 / 聚合报告（无可识别个人） | 可保留 | 去身份后可分享 |
| L2 | 脱敏样本（手机/身份证/银行卡/邮箱/wxid/QQ/网址已替换；姓名需显式词表） | 谨慎保留 | 经 `privacy_filter.py` 处理后 |
| L3 | 明文 `messages.jsonl` / `manifest.json`（含本人与第三方 PII） | **默认不落显眼目录、gitignore** | 仅本机、用完即删或加密 |
| L4 | 原始微信数据库（SQLCipher 密文 + 内存密钥） | 不复制、不导出 | 绝不离开本机 |

→ `dump_chats` 默认产出落在 **L3 临时区（`.wc_cache/export`）**；`--export-raw` 才升为显式保留的 L3 副本。

## 7.2 硬性红线（Red Lines · 发布阻塞）

任何一项触发，本次发布 / 改动 **一律拒绝**：

| 红线 | 说明 |
|---|---|
| 原始聊天明文进 AI / 第三方 API / 网盘 / GitHub | 绝不把 L3 明文上传 |
| 导出 / 读取他人微信账号、监控他人 | 仅限本人合法持有账号 |
| 公开可识别第三方的对话内容 | 熟人重识别风险 |
| 包装为「微信破解工具」对外传播 | 定位必须是 Local-first Personal Data Audit |
| 推荐 `irm\|iex` / `curl\|bash` 直跑远程脚本 | 供应链风险过高（已降级） |
| 仓库提交任何真实聊天数据 / 真实 PII | `output/` `.wc_cache/` `scripts/export/` 不入库 |
| 关闭最小权限 / 引入联网回传 | 违反 Local-first 与最小权限原则 |

## 7.3 Definition of Done（各优先级验收标准）

- **P0（验收）**：无真实 PII 入库；脚本零联网；进程访问为最小权限（`PROCESS_VM_READ | PROCESS_QUERY_INFORMATION`，非 `ALL_ACCESS`）；原始明文默认落到 gitignored 临时区；依赖锁定（`requirements-lock.txt`）；脱敏脚本可用且有测试。
- **P1（验收）**：`--export-raw` 默认关闭且需二次确认；分析脚本统一经 `_paths.locate_messages_jsonl()` 定位；`privacy_filter.py` 覆盖手机/身份证/银行卡/邮箱/wxid/QQ/网址；README/文章已降级 `irm\|iex` 并附 SHA-256。
- **P2（验收）**：`install_deps.py` / `setup_check.py` 具 `--dry-run` kill switch；SQL 表名白名单校验；日志不泄露 wxid / 家目录路径；对外服务合规模板（规划中）。

---

## 8. GitHub 发布前检查项（Pre-publish Checklist）

- [ ] 仓库**不含任何作者真实聊天数据**（`sample_reports/` 为占位说明，`output/` / `.wc_cache/` 不提交）
- [ ] `config.json` 已中性化（赛道词典为通用示例，无作者行业/身份词）
- [ ] PII 扫描：全文 0 个真实微信号 / 手机号 / 身份证 / 银行卡 / 住址 / 真实姓名
- [ ] `requirements.txt` 仅含可 pip 的纯 PyPI 包
- [ ] 发布前生成 `wechat-self-analysis_clean.zip`（剔除真实数据）
- [ ] Releases 附该 zip 的 **SHA-256**
- [ ] README 安装说明已**降级 `irm|iex`**、标注供应链风险、推荐 zip + 校验
- [ ] 隐私/安全章节（含「这不是破解微信」边界 + 第三方 PII 责任）已就位
- [ ] 顶部标识为「Local-first Personal Data Audit」，避免「破解」措辞
- [ ] `LICENSE` / `topics` 完整
- [ ] `scripts/privacy_filter.py` 与 `tests/test_redaction.py` 存在，且 `python tests/test_redaction.py` 通过
- [ ] `install_deps.py` / `setup_check.py` 支持 `--dry-run`（kill switch，不真正安装）
- [ ] `dump_chats.py` 默认落到 `.wc_cache/export/`，`--export-raw` 需二次确认
- [ ] `_paths.locate_messages_jsonl()` 已统一各分析脚本的明文定位（含 legacy `scripts/export/`）
- [ ] 数据分级 L0–L4（§7.1）与硬性红线（§7.2）已写入本文件
- [ ] 全文 grep 确认零网络调用（socket/requests/urllib/httpx/aiohttp/urlopen）

---

## 9. 整改优先级（Roadmap）

- **P0（已完成 ✅）**：隐私/法律边界章节；弱化绝对化技术表述；`sender_id==2` 校验提示；回复时延口径；97.9%→「离线词典正向命中率」；AI「非心理诊断」；日期泛化到月级；Release zip 不含真实数据；`requirements` 纯 PyPI；**零联网（已验证无 socket/requests 等调用）**；**最小进程权限（`PROCESS_VM_READ | PROCESS_QUERY_INFORMATION`，非 `ALL_ACCESS`）**；**`.gitignore` 覆盖 `output/` `.wc_cache/` `scripts/export/`**；**`requirements-lock.txt` 精确锁定 cryptography/zstandard/jieba**。
- **P1（已完成 ✅）**：README 与文章降级 `irm|iex` + SHA-256 校验；**`--export-raw` 默认关闭且需二次确认（dump_chats）**；**分析脚本统一经 `_paths.locate_messages_jsonl()` 定位（修复 `scripts/export` 与 `output` 不一致）**；**`privacy_filter.py` 脱敏脚本 + 测试（`tests/test_redaction.py`）**；Agent 信任边界说明上架。
- **P2（部分完成 ✅/⏳）**：**`install_deps.py` / `setup_check.py` `--dry-run` kill switch**；**SQL 表名白名单校验（P2-01）**；**日志脱敏（wxid / 家目录，P2-03/04）**；原始明文默认不落盘的内存流式管线 ⏳（当前默认落 `.wc_cache/export` 临时区，已是务实折中）；脱敏层自动化模板 ⏳；对外服务合规模板（规划中）⏳。

---

*本清单随评审意见持续迭代。任何涉及「读取他人数据 / 外传原始聊天 / 包装为破解工具」的改动都会被拒绝。*
