#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy_filter 单元测试：验证强/弱 PII 脱敏均生效。

运行：  python tests/test_redaction.py
（也可被 pytest 收集：每个 test_* 函数独立）
"""
import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)
import privacy_filter as pf  # noqa: E402


def test_phone():
    out, c = pf.redact_text("手机13800138000")
    assert "<PHONE>" in out and "13800138000" not in out


def test_idcard():
    out, c = pf.redact_text("身份证420100199001011234")
    assert "<IDCARD>" in out and "420100199001011234" not in out


def test_bank():
    out, c = pf.redact_text("卡6222021234567890123")
    assert "<BANK>" in out and "6222021234567890123" not in out


def test_email():
    out, c = pf.redact_text("邮箱a@b.com")
    assert "<EMAIL>" in out and "a@b.com" not in out


def test_wxid():
    out, c = pf.redact_text("wxid_abcde12345")
    assert "<WXID>" in out and "wxid_abcde12345" not in out


def test_qq_labeled():
    out, c = pf.redact_text("qq 123456789")
    assert "<QQ>" in out and "123456789" not in out


def test_qq_unlabeled_not_greedy():
    # 普通数字不应被误判为 QQ
    out, c = pf.redact_text("数量 12345 个")
    assert "<QQ>" not in out


def test_url():
    out, c = pf.redact_text("见 http://fake.example.com/x")
    assert "<URL>" in out and "fake.example.com" not in out


def test_names_weak():
    out, c = pf.redact_text("张三 你好", names=["张三"])
    assert "<NAME>" in out and "张三" not in out


def test_record():
    rec = {"content": "手机13800138000", "chat_name": "张三"}
    r, c = pf.redact_record(rec, names=["张三"])
    assert "<PHONE>" in r["content"]
    assert "<NAME>" in r["chat_name"]


def test_example_file():
    """对 examples/sample_messages.jsonl 跑一遍，确认各类 PII 都被脱敏。"""
    ex = os.path.join(REPO, "examples", "sample_messages.jsonl")
    assert os.path.exists(ex), "示例文件缺失"
    with open(ex, "r", encoding="utf-8") as f:
        blob = f.read()
    # 示例里出现的真实形态应当全部被清掉
    for leak in ("13800138000", "420100199001011234", "6222021234567890123",
                 "fake.user@example.com", "wxid_abcde12345",
                 "http://fake-company.example.com"):
        assert leak in blob, "示例文件缺少预期样例: %s" % leak
    out, _ = pf.redact_text(blob, names=["张三", "武汉假科技有限公司"])
    for leak in ("13800138000", "420100199001011234", "6222021234567890123",
                 "fake.user@example.com", "wxid_abcde12345",
                 "http://fake-company.example.com", "张三",
                 "武汉假科技有限公司"):
        assert leak not in out, "脱敏遗漏: %s" % leak


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("ALL PASS (%d tests)" % len(fns))
