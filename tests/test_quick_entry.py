"""
quick_entry.py 单元测试（仅测正则层，无需 LLM 调用）。
运行：cd backend && python -m pytest tests/test_quick_entry.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from agents.categorization.quick_entry import try_regex_parse


@pytest.mark.parametrize("message,expected_merchant,expected_amount", [
    ("Grab $12.80",            "Grab",      12.80),
    ("星巴克 ¥38",              "星巴克",    38.0),
    ("FairPrice $45.60",       "FairPrice",  45.60),
    ("午饭 35元",               "午饭",       35.0),
    ("咖啡 18.5",               "咖啡",       18.5),
    ("地铁 2.1",                "地铁",        2.1),
    ("Netflix subscription $15.99", "Netflix", 15.99),
    ("美团外卖 52元",            "美团外卖",  52.0),
])
def test_regex_parse_success(message, expected_merchant, expected_amount):
    result = try_regex_parse(message)
    assert result is not None, f"应解析成功: '{message}'"
    assert result.success
    assert result.transaction is not None
    assert result.transaction.counterparty == expected_merchant
    assert abs(result.transaction.amount - expected_amount) < 0.01


@pytest.mark.parametrize("message", [
    "什么是50-30-20法则？",
    "帮我分析一下我的消费",
    "你好",
    "今天天气不错",
])
def test_regex_parse_non_transaction(message):
    result = try_regex_parse(message)
    assert result is None, f"非记账消息不应被解析: '{message}'"


def test_regex_parse_zero_amount():
    result = try_regex_parse("某商家 $0")
    assert result is None, "金额为0不应解析成功"
