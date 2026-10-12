#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键安装 wechat-self-analysis 所需的 Python 依赖，并做环境检查与引导。

用法：
    python scripts/install_deps.py
或直接双击技能根目录的 install_deps.cmd（Windows）。

它会：
  1. 确认 Python >= 3.11；
  2. 检查/安装 cryptography、zstandard、jieba（仅这 3 个纯 PyPI 包）；
  3. 确认自带解密模块 scripts/_decrypt.py 可导入（无需 wechatauto / WechatVibe）；
  4. 打印后续步骤与引导。
"""
import sys
import os
import subprocess

MIN_PY = (3, 11)
DEPS = ["cryptography", "zstandard", "jieba"]


def have(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def pip_install(pkg):
    print("  -> 正在 pip install %s ..." % pkg)
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
    return rc == 0


def main():
    print("=== wechat-self-analysis 环境安装与检查 ===")
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
    for pkg in DEPS:
        if have(pkg):
            print("  [OK] %s 已安装" % pkg)
        else:
            print("  [缺失] %s" % pkg)
            if pip_install(pkg) and have(pkg):
                print("  [OK] %s 安装成功" % pkg)
            else:
                print("  [FAIL] %s 安装失败（可能离线或 pip 不可用）" % pkg)
                ok = False

    # 3. 自带解密模块（依赖 cryptography）
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
