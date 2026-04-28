"""
parser.py 单元测试。
运行：cd backend && python -m pytest tests/test_parser.py -v
"""
import os
import pytest

# 将 backend/ 加入 sys.path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.categorization.parser import parse_file
from schemas.transaction import DirectionEnum


# ── 微信账单测试（使用仓库根目录的真实账单文件）─────────────────────────────────
WECHAT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "微信支付账单流水文件(20250301-20260301)_20260330112907.xlsx"
)

def test_parse_wechat_real_file():
    if not os.path.exists(WECHAT_FILE):
        pytest.skip("微信账单文件不存在，跳过")
    with open(WECHAT_FILE, "rb") as f:
        content = f.read()
    txns = parse_file("wechat.xlsx", content)
    assert len(txns) > 0
    # 所有记录都有 counterparty 和 amount
    for t in txns:
        assert t.counterparty
        assert t.amount >= 0
        assert t.direction in list(DirectionEnum)
    print(f"微信账单解析：{len(txns)} 条，首条: {txns[0].counterparty} ¥{txns[0].amount}")


# ── 支付宝账单测试 ─────────────────────────────────────────────────────────────
ALIPAY_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "支付宝交易明细(20250330-20260329).csv"
)

def test_parse_alipay_real_file():
    if not os.path.exists(ALIPAY_FILE):
        pytest.skip("支付宝账单文件不存在，跳过")
    with open(ALIPAY_FILE, "rb") as f:
        content = f.read()
    txns = parse_file("alipay.csv", content)
    assert len(txns) > 0
    for t in txns:
        assert t.counterparty
        assert t.amount >= 0
    print(f"支付宝账单解析：{len(txns)} 条，首条: {txns[0].counterparty} ¥{txns[0].amount}")


# ── 不支持的格式 ───────────────────────────────────────────────────────────────
def test_unsupported_format():
    from agents.categorization.parser import parse_file
    with pytest.raises(ValueError, match="Unsupported file format"):
        parse_file("bill.pdf", b"dummy content")
