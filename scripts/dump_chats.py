#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump decrypted WeChat 4.x messages to plaintext JSONL for self-behavior analysis.

MUST run in the interactive desktop session where WeChat is logged in — the SQLCipher
key lives only in the WeChat process memory. We reuse WechatVibe's bundled `wechatauto`
library, which is exactly what the WechatVibe GUI itself uses for WeChat 4.x:

  * WeChatDB()            auto-detects the data dir AND extracts the per-account
                          SQLCipher key from live WeChat memory via the
                          `com.Tencent.WCDB.Config.Cipher` memory anchor (the path
                          that actually works on 4.1.x — unlike the weak hex-literal
                          scanner).
  * _message_dbs()        enumerates every message shard (.db).
  * _build_md5_index()    maps Msg_<md5> table -> username.
  * _sender_id_index()    maps real_sender_id -> username (group members etc.).
  * _export_row()         friendly-decodes message_content (utf-8 / zstd / blob).
  * _resolve_sender()     resolves a sender_id to a display name; sender_id == 2 == me.

Output (in ./export):
  messages.jsonl   one message per line:
                     {chat, chat_name, side("self"|"them"), sender_id, sender_name,
                      type, create_time, content, local_id, sort_seq}
  manifest.json     {wxid, nick_name, total_chats, total_messages, first_time,
                     last_time, exported_at, top_chats:[{username,name,count}]}

Run:  dump-chats.cmd   (double-click in your own session, WeChat running & logged in)
Self-test (no WeChat needed):  python _dump_chats.py --selftest
"""
import sys, os, re, json, time, sqlite3, argparse, atexit

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)   # 技能根目录(scripts/ 的上一级)

# 解密后端（优先自带、零 wechatauto 依赖）：
#   首选 scripts/_decrypt.py —— 已从 wechatauto/db.py vendored 的解密核心，
#   仅依赖 cryptography + zstandard，替换了唯一的 wechatauto.logger 依赖。
#   若它无法导入（如 cryptography 缺失），再回退到上游 wechatauto.db（需 WechatVibe 环境）。
try:
    from _decrypt import WeChatDB, MSG_TYPE_NAMES
    _BACKEND = "builtin"
except ImportError:
    try:
        from wechatauto.db import WeChatDB, MSG_TYPE_NAMES
        _BACKEND = "wechatauto"
    except ImportError:
        WeChatDB = None          # type: ignore
        MSG_TYPE_NAMES = {}      # type: ignore
        _BACKEND = None


def _ensure_backend():
    """Return True if a decryption backend is available; otherwise print a clear,
    copy-pasteable fix and return False (caller should then exit non-zero)."""
    if _BACKEND is not None:
        return True
    sys.stderr.write(
        """
[dump] 未能导入解密引擎（需要 cryptography + zstandard + jieba）。
       本技能的解密模块 scripts/_decrypt.py 仅依赖上述纯 PyPI 包，无需 wechatauto / WechatVibe。

       最省事：双击技能根目录的 install_deps.cmd（Windows），或运行
         python scripts/install_deps.py
       它会自动检查并安装缺失的依赖。

       手动安装也行：
         pip install cryptography zstandard jieba
       安装到“将要运行本技能脚本的那个 Python”里，然后重新运行即可。

  （仅当上述 pip 都不可用（如完全离线）时，才考虑克隆 WechatVibe 项目、
   在其 .venv 里运行本技能作为兜底；正常环境用内置 _decrypt 即可。）
"""
    )
    return False


def selftest():
    """Validate the environment without needing a running WeChat (no key scan)."""
    if not _ensure_backend():
        return 2
    problems = []
    try:
        import cryptography  # noqa: F401
        from cryptography.hazmat.primitives.ciphers import algorithms  # noqa: F401
    except Exception as e:  # pragma: no cover
        problems.append("cryptography 未安装: %s" % e)
    try:
        import psutil  # noqa: F401
    except Exception:
        problems.append("psutil 未安装（内存扫描需要）")
    if not callable(getattr(WeChatDB, "export_history", None)):
        problems.append("WeChatDB.export_history 不存在")
    print("decrypt backend=%s, WeChatDB=%r" % (_BACKEND, WeChatDB))
    print("MSG_TYPE_NAMES entries=%d" % len(MSG_TYPE_NAMES))
    if problems:
        print("SELFTEST FAIL:")
        for p in problems:
            print("  - " + p)
        return 1
    print("SELFTEST OK (venv/crypto/psutil ready). 现在请在已登录微信的桌面会话双击 dump-chats.cmd 运行真实导出。")
    return 0


def _to_epoch_seconds(v):
    """WeChat create_time is normally Unix epoch seconds; guard against ms values."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v > 1e11:      # > year 5138 -> treat as milliseconds
        v = v / 1000.0
    return v


def _open_with_retry(db, rel, attempts=3):
    """打开解密库；PermissionError（缓存文件被占用/杀软扫描锁）时退避重试，
    最后清掉该库的缓存文件再试一次。仍失败则抛出。"""
    last = None
    for i in range(attempts):
        try:
            return db._open(rel)
        except PermissionError as e:
            last = e
            sys.stderr.write("[dump]  缓存被占用(%s)，第 %d/%d 次重试...\n"
                             % (rel, i + 1, attempts))
            time.sleep(1.5 * (i + 1))
    # 兜底：清掉该 rel 的缓存产物后重建
    base = os.path.join(db.workdir, rel.replace(os.sep, "__"))
    for suf in ("", ".tmp", ".stamp", ".wal"):
        try:
            p = base + suf
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
    try:
        return db._open(rel)
    except Exception:
        raise last


def _call_with_retry(fn, *a, **k):
    """库内部批量打开多份库的调用（_build_md5_index 等）做整体重试。"""
    last = None
    for i in range(3):
        try:
            return fn(*a, **k)
        except PermissionError as e:
            last = e
            sys.stderr.write("[dump]  缓存被占用，第 %d/3 次重试...\n" % (i + 1))
            time.sleep(1.5 * (i + 1))
    raise last


def main():
    if not _ensure_backend():
        return 2
    export_dir = os.path.join(SKILL_ROOT, "output")
    os.makedirs(export_dir, exist_ok=True)
    jsonl_path = os.path.join(export_dir, "messages.jsonl")
    manifest_path = os.path.join(export_dir, "manifest.json")

    # ---- 单实例锁：防止多开窗口互相截断输出 ----
    lock_path = os.path.join(export_dir, ".dump.lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode())
    except FileExistsError:
        try:
            age = time.time() - os.path.getmtime(lock_path)
        except OSError:
            age = 9999
        if age < 600:
            sys.stderr.write(
                "[dump] 检测到可能有另一个导出进程正在运行（export/.dump.lock，%.0f 秒前创建）。\n"
                "       请先关闭其它导出窗口再试；若确认没有，手动删除该锁文件后重试。\n" % age
            )
            return 4
        try:
            os.remove(lock_path)
        except OSError:
            pass
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode())

    def _release_lock():
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            os.remove(lock_path)
        except OSError:
            pass

    atexit.register(_release_lock)

    # ---- 写入临时文件，全部成功后才原子改名，中途死掉不毁旧数据 ----
    for n in os.listdir(export_dir):
        if n.startswith("messages_") and n.endswith(".part"):
            try:
                os.remove(os.path.join(export_dir, n))
            except OSError:
                pass
    part_path = os.path.join(export_dir, "messages_%d.part" % os.getpid())

    t0 = time.time()
    sys.stderr.write("[dump] 初始化 WeChatDB（自动定位目录 + 从微信内存提取密钥）...\n")

    # 关键：用项目内独立缓存目录，避免与 WechatVibe GUI（Electron）共用
    # Temp\wechatauto_db 缓存——GUI 若开着会持有解密库连接，导致
    # os.replace 报 WinError 5（拒绝访问）。
    workdir = os.path.join(SKILL_ROOT, ".wc_cache", "dump")

    try:
        db = WeChatDB(workdir=workdir)  # auto-detect + live memory key extraction
    except Exception as e:
        sys.stderr.write(
            "\n[dump] 无法初始化微信数据库：%s\n"
            "       请确认：① 微信已启动并已登录；② 在本机桌面会话（非远程/沙箱）运行；\n"
            "       ③ 当前微信版本受支持（4.x）。\n" % e
        )
        return 2

    self_info = db.get_self_info()
    wxid = self_info.get("username") or getattr(db, "wxid", "")
    self_nick = self_info.get("nick_name") or "我"
    sys.stderr.write("[dump] 当前账号: %s (昵称: %s)\n" % (wxid, self_nick))

    idx = _call_with_retry(db._build_md5_index)
    nicks = _call_with_retry(db._nickname_index)
    sender_index = _call_with_retry(db._sender_id_index)

    # Enumerate every Msg_<md5> table across all message shards.
    buckets = {}
    all_conns = []
    for rel in db._message_dbs():
        try:
            conn = _open_with_retry(db, rel)
        except Exception as e:
            sys.stderr.write("[dump]  跳过无法解密的库 %s: %s\n" % (rel, e))
            continue
        all_conns.append(conn)
        for (t,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
        ).fetchall():
            buckets.setdefault(t[4:], []).append((conn, t))

    if not buckets:
        sys.stderr.write("[dump] 未找到任何消息表，导出中止。\n")
        for c in all_conns:
            try: c.close()
            except Exception: pass
        return 3

    total = 0
    chat_counts = []
    times = []
    order = sorted(buckets.keys())
    n_chats = len(order)
    sys.stderr.write("[dump] 发现 %d 个会话，开始解密导出...\n" % n_chats)

    with open(part_path, "w", encoding="utf-8") as f:
        for i, md5 in enumerate(order):
            user = idx.get(md5, md5)
            name = nicks.get(user, user)
            rows = []
            for conn, table in buckets[md5]:
                try:
                    rows += conn.execute(
                        "SELECT local_id, local_type, server_id, real_sender_id, "
                        "create_time, message_content, packed_info_data, sort_seq "
                        "FROM %s ORDER BY sort_seq ASC, local_id ASC" % table
                    ).fetchall()
                except sqlite3.DatabaseError:
                    continue
            if not rows:
                continue
            cnt = 0
            for r in rows:
                m = db._export_row(r, MSG_TYPE_NAMES)
                sid = r["real_sender_id"]
                side = "self" if str(sid) in ("2", 2) else "them"
                sender_name = db._resolve_sender(sid, sender_index, nicks, self_nick)
                ct = m.get("create_time")
                ep = _to_epoch_seconds(ct)
                if ep:
                    times.append(ep)
                rec = {
                    "chat": user,
                    "chat_name": name,
                    "side": side,
                    "sender_id": m.get("sender_id"),
                    "sender_name": sender_name,
                    "type": m.get("type"),
                    "create_time": ct,
                    "content": m.get("content"),
                    "local_id": m.get("local_id"),
                    "sort_seq": m.get("sort_seq"),
                }
                f.write(json.dumps(rec, ensure_ascii=False))
                f.write("\n")
                cnt += 1
            total += cnt
            chat_counts.append((user, name, cnt))
            if (i + 1) % 50 == 0 or (i + 1) == n_chats:
                sys.stderr.write("[dump]  进度 %d/%d 会话, %d 条消息\n" % (i + 1, n_chats, total))

    # 全部写完才把临时文件转正为 messages.jsonl（原子替换）
    os.replace(part_path, jsonl_path)
    sys.stderr.write("[dump] 输出已转正: %s\n" % jsonl_path)

    for c in all_conns:
        try: c.close()
        except Exception: pass

    chat_counts.sort(key=lambda x: -x[2])
    first_time = min(times) if times else None
    last_time = max(times) if times else None

    manifest = {
        "wxid": wxid,
        "nick_name": self_nick,
        "total_chats": len(chat_counts),
        "total_messages": total,
        "first_time": first_time,
        "last_time": last_time,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "top_chats": [
            {"username": u, "name": n, "count": c}
            for (u, n, c) in chat_counts[:50]
        ],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    dt = time.time() - t0
    sys.stderr.write(
        "[dump] 完成：%d 个会话, %d 条消息, 用时 %.1fs\n" % (len(chat_counts), total, dt)
    )
    sys.stderr.write("[dump] 输出: %s\n" % jsonl_path)
    sys.stderr.write("[dump] 清单: %s\n" % manifest_path)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="仅校验环境，不接触微信")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    sys.exit(main())
