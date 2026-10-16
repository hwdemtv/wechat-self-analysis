#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared path + privacy helpers for wechat-self-analysis.

为什么需要它
------------
历史上各分析脚本零散地硬编码了三种不同的 messages.jsonl 位置：
  * SKILL_ROOT/output/messages.jsonl            （大多数脚本）
  * SKILL_ROOT/.wc_cache/export/messages.jsonl  （dump 默认导出，临时）
  * SKILL_ROOT/scripts/export/messages.jsonl    （3 个老脚本的写法）

本模块把这些位置收口成一个「定位器」，所有脚本统一调用
locate_messages_jsonl()，既消除不一致，也支撑「默认不把明文落在显眼目录」
的隐私策略：

  - dump_chats.py 默认把明文写到 .wc_cache/export/（已 gitignore，临时）；
  - 加 --export-raw 才落盘到 output/（显式保留、需确认）；
  - 分析脚本一律用 locate_messages_jsonl() 自动找到任意一处。

同时提供轻量日志脱敏 redact_log()，供 dump 等脚本在 stderr 中遮蔽账号标识
与本地绝对路径，避免把 wxid / 家目录路径写进日志或截图。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)            # scripts/ 的上一级

# 显式保留目录：用户主动 --export-raw 时的明文落盘处
EXPORT_DIR = os.path.join(SKILL_ROOT, "output")
# 默认临时目录：dump 默认导出处（已 gitignore，临时、易清理）
RAW_DIR = os.path.join(SKILL_ROOT, ".wc_cache", "export")
# 历史遗留目录：少数老脚本曾把明文写到这里
LEGACY_DIR = os.path.join(HERE, "export")

JSONL_NAME = "messages.jsonl"
MANIFEST_NAME = "manifest.json"


def output_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR


def raw_dir():
    os.makedirs(RAW_DIR, exist_ok=True)
    return RAW_DIR


def legacy_dir():
    os.makedirs(LEGACY_DIR, exist_ok=True)
    return LEGACY_DIR


def default_export_dir(export_raw):
    """dump_chats 的落盘目录：--export-raw 落到 output/，否则落到 .wc_cache/export/。"""
    return EXPORT_DIR if export_raw else RAW_DIR


def _candidates(prefer_raw):
    """返回待搜索的 messages.jsonl 路径列表（按优先级）。"""
    cands = [
        os.path.join(EXPORT_DIR, JSONL_NAME),
        os.path.join(RAW_DIR, JSONL_NAME),
        os.path.join(LEGACY_DIR, JSONL_NAME),
    ]
    if prefer_raw:
        cands = list(reversed(cands))
    return cands


def locate_messages_jsonl(prefer_raw=False):
    """找最近一次导出的 messages.jsonl。

    prefer_raw=False（分析脚本默认）：优先 output/，其次 .wc_cache/export/，再次 legacy scripts/export/
    prefer_raw=True（清理/诊断）：优先 .wc_cache/export/，其次 output/，再次 legacy
    找不到返回 None。
    """
    for p in _candidates(prefer_raw):
        if os.path.exists(p):
            return p
    return None


def manifest_path_for(jsonl_path):
    """给定 jsonl 路径，返回同目录下的 manifest.json 路径。"""
    return os.path.join(os.path.dirname(jsonl_path), MANIFEST_NAME)


def locate_manifest(prefer_raw=False):
    """找 manifest.json：优先与 locate_messages_jsonl 同目录，否则回退搜索各目录。"""
    j = locate_messages_jsonl(prefer_raw=prefer_raw)
    if j and os.path.exists(manifest_path_for(j)):
        return manifest_path_for(j)
    for base in (EXPORT_DIR, RAW_DIR, LEGACY_DIR):
        p = os.path.join(base, MANIFEST_NAME)
        if os.path.exists(p):
            return p
    return None


def redact_log(text):
    """对日志文本做轻量脱敏：遮蔽 wxid 账号标识与本地绝对路径。

    仅用于 stderr / 日志，不影响真实数据文件。重度内容脱敏请用 privacy_filter.py。
    """
    if not text:
        return text
    # 1) 遮蔽 wxid（wxid_ 开头，保留前缀+前3位，其余打码）
    import re
    text = re.sub(r"(wxid_[A-Za-z0-9]{0,3})[A-Za-z0-9]{4,}",
                  lambda m: m.group(1) + "****", text)
    # 2) 遮蔽常见本地绝对路径中的用户目录（如 C:\Users\xxx 或 /home/xxx）
    text = re.sub(r"[A-Za-z]:\\[Uu]sers\\[^\\]+", r"C:\\Users\\****", text)
    text = re.sub(r"/home/[^/]+", r"/home/****", text)
    return text
