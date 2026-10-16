#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键安装 wechat-self-analysis 所需的 Python 依赖，并做环境检查与引导。

用法：
    python scripts/install_deps.py            # 检查并安装缺失依赖
    python scripts/install_deps.py --dry-run  # 仅预览将执行的 pip 命令，绝不安装（kill switch）
或直接双击技能根目录的 install_deps.cmd（Windows）。

它会：
  1. 确认 Python >= 3.11；
  2. 检查/安装 cryptography、zstandard、jieba（仅这 3 个纯 PyPI 包）；
  3. 确认自带解密模块 scripts/_decrypt.py 可导入（无需 wechatauto / WechatVibe）；
  4. 打印后续步骤与引导。

安全说明：本脚本只装上述 3 个公开 PyPI 纯包，不会访问网络下载脚本、不会执行
远程代码、不会改动微信或系统其它部分。加 --dry-run 可先行预览，确认无误再实装。
"""
import sys
import os
import argparse
import subprocess

MIN_PY = (3, 11)
DEPS = ["cryptography", "zstandard", "jieba"]


def have(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def pip_install(pkg, dry_run=False):
    if dry_run:
        print("  -> [dry-run] 将执行: %s -m pip install %s" % (sys.executable, pkg))
        return True
    print("  -> 正在 pip install %s ..." % pkg)
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
    return rc == 0


def main():
    ap = argparse.ArgumentParser(description="安装 wechat-self-analysis 依赖（--dry-run 仅预览）")
    ap.add_argument("--dry-run", action="store_true",
                   help="只打印将执行的 pip 命令，不真正安装任何东西（kill switch）")
    args = ap.parse_args()
    dry_run = args.dry_run

    print("=== wechat-self-analysis 环境安装与检查 ===%s" %
          ("  [DRY-RUN 仅预览]" if dry_run else ""))
    print("")

    # 1. Python 版本
    vi = sys.version_info
    print("Python 版本: %d.%d.%d" % (vi[0], vi[1], vi[2]))
    if (vi[0], vi[1]) < MIN_PY:
        print("  [FAIL] 需要 Python >= 3.11，请先安装或切换到 3.11+。")
        return 1
    print("  [OK] Python 版本满足要求")

    # 2. 依赖
    ok = True
    missing = []
    for pkg in DEPS:
        if have(pkg):
            print("  [OK] %s 已安装" % pkg)
        else:
            print("  [缺失] %s" % pkg)
            missing.append(pkg)
            if pip_install(pkg, dry_run=dry_run) and have(pkg):
                print("  [OK] %s 安装成功" % pkg)
            else:
                if not dry_run:
                    print("  [FAIL] %s 安装失败（可能离线或 pip 不可用）" % pkg)
                    ok = False

    if dry_run and missing:
        print("")
        print("[dry-run] 实际将执行的安装命令：")
        print("  %s -m pip install %s" % (sys.executable, " ".join(missing)))

    # 3. 自带解密模块（依赖 cryptography）
    if not dry_run or have("cryptography"):
        try:
            if have("cryptography"):
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                import importlib
                importlib.import_module("_decrypt")
                print("  [OK] 自带解密模块 _decrypt 可导入（无需 wechatauto）")
            else:
                print("  [FAIL] cryptography 缺失，_decrypt 无法导入")
                ok = False
        except Exception as e:
            print("  [FAIL] _decrypt 导入异常: %s" % e)
            ok = False

    print("")
    if dry_run:
        print("[dry-run] 未做任何改动。确认无误后去掉 --dry-run 重新运行即可安装。")
        return 0
    if ok:
        print("环境就绪。后续步骤：")
        print("  1) 确认微信 4.x 已启动并登录本机；")
        print("  2) 运行  python scripts/setup_check.py  做完整自检；")
        print("  3) 运行  python scripts/dump_chats.py  导出聊天记录。")
    else:
        print("有依赖未能就绪。请手动执行：")
        print("  %s -m pip install cryptography zstandard jieba" % sys.executable)
        print("（权限不足可加 --user；离线环境需先备好这三个 wheel。）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
