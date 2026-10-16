#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检：依赖 / 微信进程 / 数据目录。不提取密钥、不写任何文件、不安装。

用法：
    python scripts/setup_check.py            # 完整自检
    python scripts/setup_check.py --dry-run  # 同上（本工具本就不写/不装，--dry-run 仅显式声明不改动）
"""
import sys, os, subprocess, argparse


def main():
    ap = argparse.ArgumentParser(description="环境自检（--dry-run 仅声明不改动）")
    ap.add_argument("--dry-run", action="store_true",
                   help="显式声明：本工具只检查、绝不写文件或安装（kill switch 提示）")
    args = ap.parse_args()
    dry_run = args.dry_run

    ok = True
    # 1. 依赖（解密核心已是自带模块 scripts/_decrypt.py，只需 cryptography；
    #    psutil 不再需要——解密用 ctypes 直接读内存；wechatauto 仅为可选回退）
    for mod in ("cryptography", "_decrypt"):
        try:
            __import__(mod)
            print("[OK] 依赖 %s" % mod)
        except ImportError as e:
            print("[FAIL] 依赖 %s 未安装（%s）" % (mod, e))
            ok = False
    try:
        import jieba  # noqa
        print("[OK] 依赖 jieba（deep_analyze 需要）")
    except ImportError:
        print("[WARN] jieba 未安装，deep_analyze.py 将不可用（其余脚本不受影响）")

    # 2. 微信进程
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="gbk", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        found = "Weixin.exe" in (r.stdout or "")
        if found:
            print("[OK] 微信进程 Weixin.exe 运行中")
        else:
            print("[FAIL] 未检测到 Weixin.exe —— 请先启动微信并登录")
            ok = False
    except OSError as e:
        print("[WARN] 无法检查进程（%s），跳过" % e)

    # 3. 数据目录
    try:
        from _decrypt import auto_detect_db_dir
        d = auto_detect_db_dir()
        if d:
            print("[OK] 微信数据目录: %s" % d)
        else:
            print("[FAIL] 未定位到微信 4.x 数据目录（确认安装的是 4.x 且登录过）")
            ok = False
    except Exception:
        pass  # 依赖缺失时上面已报

    print("\n结论：%s" % ("环境就绪，可运行 scripts/dump_chats.py" if ok else "存在问题，先按上面提示处理"))
    if dry_run:
        print("[dry-run] 本工具只做检查，未提取密钥、未写文件、未安装任何东西。")
        print("          若需安装缺失依赖且不放心，可先预览：")
        print("            python scripts/install_deps.py --dry-run")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
