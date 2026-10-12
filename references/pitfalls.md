# 踩坑位表（11 条，按出现顺序排列）

每条含：症状 → 根因 → 解法。导出或分析报错时逐项对照。

## 坑 1：弱密钥扫描器提取 0 个密钥
- 症状：自研/复用的扫描器扫完全部内存，密钥数为 0
- 根因：WechatVibe 自带的 `native-reader/wr/discovery.scan_key_candidates` 只认 `x'<hex>'` 字面量密钥，微信 4.1.x 已不用该形式
- 解法：一律用 `wechatauto.db.WeChatDB`（`com.Tencent.WCDB.Config.Cipher` 内存锚点），不要复用 wr.discovery

## 坑 2：PyWxDump 不支持 4.x
- 症状：偏移表覆盖 3.2.1.154~3.9.12.55，4.x 直接失效
- 解法：放弃 PyWxDump，用 wechatauto

## 坑 3：微信未运行
- 症状：`RuntimeError: 未检测到 Weixin.exe，请先登录微信再运行`
- 根因：`_find_weixin_pids` 用 `tasklist /FI "IMAGENAME eq Weixin.exe"` 精确匹配；微信没开就是找不到
- 解法：启动微信并登录，保持窗口打开（可最小化）。若微信以管理员运行，脚本也需管理员

## 坑 4：GUI 共用缓存 → WinError 5
- 症状：`PermissionError: [WinError 5] 拒绝访问: '...contact__contact.db.tmp' -> '...db'`
- 根因：WechatVibe GUI 还开着，与本脚本共用 `%TEMP%\wechatauto_db\<账号>\` 缓存并持有解密库连接；`os.replace` 替换被占用文件被 Windows 拒绝
- 解法：`WeChatDB(workdir=<独立目录>)`；配合对 `_open` 的 PermissionError 退避重试（3 次退避 + 清缓存兜底）

## 坑 5：多开导出窗口互相截断
- 症状：`messages.jsonl` 行数远小于 manifest 的 total_messages（如 6.5 万 vs 195 万）
- 根因：两个导出进程都用 `open(path, "w")`，后者启动时把前者的完整输出截断
- 解法：①单实例锁（`.dump.lock`，O_CREAT|O_EXCL，10 分钟过期接管）；②写 `messages_<pid>.part` 临时文件，全部成功后 `os.replace` 原子转正

## 坑 6：跨分片乱序 → 负回复时延
- 症状：回复时延均值 -88 万秒
- 根因：同一会话的消息分布在多个 message_N.db 分片，按 sort_seq 合并后 create_time 回跳
- 解法：只对 `t >= last_t` 的相邻对计算时延/线程；乱序消息跳过；`last_t` 永远取最大时间

## 坑 7：幽灵群混进 1:1 关系表
- 症状：32 位 md5 名的"联系人"霸榜关系第一名
- 根因：已退出/解散/被踢的群，微信删除 chat_room 表资料但保留 Msg_<md5> 消息表；导出反查不到名字
- 解法：md5 名 + 消息正文「≥3 个不同 `xxx:` 发言前缀」或「移出群聊/解散」系统消息 → 重分类为群

## 坑 8：单向推送号污染回复率
- 症状：大量"你占比 0%、回复率 0%"的联系人
- 根因：公众号/服务号推送全部计入对方发言
- 解法：关系入表门槛 = 总量 ≥20 且本人发言 ≥5 条

## 坑 9：JSON 快扫失配
- 症状：`line.find('"chat":"')` 永远返回 -1
- 根因：`json.dumps` 默认分隔符带空格（`"chat": "..."`）
- 解法：逐行解析统一用 `json.loads`，不做字符串快扫

## 坑 10：卡片标题噪声
- 症状：「微信转账」「邀请你加入群聊」「<![CDATA[...]]>」混进知识资产代表作
- 解法：剥 CDATA → 噪声子串过滤（不支持展示该内容/转账/邀请入群/聊天记录转发）→ 微信内部域名单独剔除

## 坑 11：词典子串误伤
- 症状：「AI人脸摄像机」厂商规格书被归入新赛道主题
- 解法：强信号词（STRONG_NEW）单独命中即可归类；弱词（AI/GPT）需 ≥2 个新词共现才归类

## 附：价格抽取的固有噪声
「400万」是像素不是金额、「6W」上下文不明——报价分析只做计数与人工复核样例，不做自动汇总金额。
