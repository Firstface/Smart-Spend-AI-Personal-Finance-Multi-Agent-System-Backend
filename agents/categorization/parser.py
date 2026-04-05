"""
文件解析器：微信支付Excel + 支付宝CSV。

微信账单结构：
  前17行为说明头，第18行为列头，第19行起为数据。
  列：交易时间|交易类型|交易对方|商品|收/支|金额(元)|支付方式|当前状态|交易单号|商户单号|备注

支付宝账单结构：
  前若干行为说明头，找到以"交易时间,"开头的行作为列头，之后为数据。
  编码：GBK。
  列：交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注
"""
import openpyxl
import csv
import io
import logging
from datetime import datetime
from typing import List

from schemas.transaction import TransactionRaw, DirectionEnum

logger = logging.getLogger("categorization.parser")


# ── 微信支付 Excel ──────────────────────────────────────────────────────────────
def parse_wechat_excel(content: bytes) -> List[TransactionRaw]:
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    transactions = []

    direction_map = {
        "支出": DirectionEnum.EXPENSE,
        "收入": DirectionEnum.INCOME,
    }

    for row in ws.iter_rows(min_row=19, values_only=True):
        if row[0] is None:
            break

        txn_type = str(row[1] or "").strip()
        direction_raw = str(row[4] or "").strip()
        direction = direction_map.get(direction_raw, DirectionEnum.NEUTRAL)

        # 退款类交易标记为 neutral
        if "退款" in txn_type:
            direction = DirectionEnum.NEUTRAL

        # 解析金额：去掉可能存在的 ¥ 符号
        raw_amount = str(row[5] or "0").replace("¥", "").replace(",", "").strip()
        try:
            amount = abs(float(raw_amount))
        except ValueError:
            logger.warning(f"微信账单金额解析失败: {row[5]}，跳过该行")
            continue

        # 解析时间
        if isinstance(row[0], datetime):
            txn_time = row[0]
        else:
            try:
                txn_time = datetime.strptime(str(row[0]).strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"微信账单时间解析失败: {row[0]}，跳过该行")
                continue

        txn = TransactionRaw(
            source="wechat",
            transaction_time=txn_time,
            transaction_type=txn_type,
            counterparty=str(row[2] or "").strip(),
            goods_description=str(row[3] or "").strip() or None,
            direction=direction,
            amount=amount,
            payment_method=str(row[6] or "").strip() or None,
            status=str(row[7] or "").strip() or None,
            order_id=str(row[8] or "").strip() or None,
            merchant_order_id=str(row[9] or "").strip() or None,
            remark=str(row[10] or "").strip() if row[10] and str(row[10]).strip() != "/" else None,
            original_category=None,  # 微信无自带分类
        )
        transactions.append(txn)

    logger.info(f"微信账单解析完成，共 {len(transactions)} 条记录")
    return transactions


# ── 支付宝 CSV ─────────────────────────────────────────────────────────────────
def parse_alipay_csv(content: bytes) -> List[TransactionRaw]:
    # 支付宝账单编码为 GBK
    try:
        text = content.decode("gbk")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    lines = text.strip().split("\n")

    # 找到列头行（以"交易时间,"开头）
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("交易时间,") or line.startswith("交易时间，"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("无法识别支付宝CSV格式：找不到列头行（应以'交易时间,'开头）")

    # 过滤末尾汇总行（支付宝CSV末尾有"---"分隔的汇总）
    data_lines = []
    for line in lines[header_idx:]:
        if line.startswith("---") or line.strip() == "":
            break
        data_lines.append(line)

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    transactions = []

    direction_map = {
        "支出": DirectionEnum.EXPENSE,
        "收入": DirectionEnum.INCOME,
        "不计收支": DirectionEnum.NEUTRAL,
    }

    for row in reader:
        time_str = row.get("交易时间", "").strip()
        if not time_str:
            continue

        try:
            txn_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"支付宝账单时间解析失败: {time_str}，跳过该行")
            continue

        direction_str = row.get("收/支", "").strip()
        direction = direction_map.get(direction_str, DirectionEnum.NEUTRAL)

        category_raw = row.get("交易分类", "").strip()
        if category_raw == "退款":
            direction = DirectionEnum.NEUTRAL

        raw_amount = row.get("金额", "0").strip().replace(",", "")
        try:
            amount = abs(float(raw_amount))
        except ValueError:
            logger.warning(f"支付宝账单金额解析失败: {row.get('金额')}，跳过该行")
            continue

        txn = TransactionRaw(
            source="alipay",
            transaction_time=txn_time,
            transaction_type=category_raw or None,
            counterparty=row.get("交易对方", "").strip(),
            counterparty_account=row.get("对方账号", "").strip() or None,
            goods_description=row.get("商品说明", "").strip() or None,
            direction=direction,
            amount=amount,
            payment_method=row.get("收/付款方式", "").strip() or None,
            status=row.get("交易状态", "").strip() or None,
            order_id=row.get("交易订单号", "").strip() or None,
            merchant_order_id=row.get("商家订单号", "").strip() or None,
            original_category=category_raw if category_raw and category_raw != "退款" else None,
            remark=row.get("备注", "").strip() or None,
        )
        transactions.append(txn)

    logger.info(f"支付宝账单解析完成，共 {len(transactions)} 条记录")
    return transactions


# ── 统一入口 ───────────────────────────────────────────────────────────────────
def parse_file(filename: str, content: bytes) -> List[TransactionRaw]:
    """根据文件扩展名分发到对应解析器"""
    name_lower = filename.lower()
    if name_lower.endswith(".xlsx") or name_lower.endswith(".xls"):
        return parse_wechat_excel(content)
    elif name_lower.endswith(".csv"):
        return parse_alipay_csv(content)
    else:
        raise ValueError(f"不支持的文件格式: {filename}，请上传 .xlsx 或 .csv 文件")
