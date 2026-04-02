"""
商家映射字典（Layer 1）— confidence = 1.0。

课程对应：确定性规则优先于LLM —— 反模式 "Don't rush to use agentic AI for everything"。
精确命中商家关键词，直接返回分类，零LLM成本。
"""
from typing import Optional
from schemas.transaction import CategoryEnum

# 商家名关键词 → 分类
# 键为小写，匹配时对 counterparty 做 lower() 处理
MERCHANT_MAP: dict[str, CategoryEnum] = {
    # ── 餐饮美食 ──────────────────────────────────────────────────────────────
    "美团": CategoryEnum.FOOD,
    "饿了么": CategoryEnum.FOOD,
    "肯德基": CategoryEnum.FOOD,
    "kfc": CategoryEnum.FOOD,
    "麦当劳": CategoryEnum.FOOD,
    "mcdonald": CategoryEnum.FOOD,
    "星巴克": CategoryEnum.FOOD,
    "starbucks": CategoryEnum.FOOD,
    "瑞幸": CategoryEnum.FOOD,
    "luckin": CategoryEnum.FOOD,
    "茶百道": CategoryEnum.FOOD,
    "霸王茶姬": CategoryEnum.FOOD,
    "喜茶": CategoryEnum.FOOD,
    "奈雪": CategoryEnum.FOOD,
    "海底捞": CategoryEnum.FOOD,
    "必胜客": CategoryEnum.FOOD,
    "pizza hut": CategoryEnum.FOOD,
    "汉堡王": CategoryEnum.FOOD,
    "burger king": CategoryEnum.FOOD,
    "subway": CategoryEnum.FOOD,
    "麻辣烫": CategoryEnum.FOOD,
    "沙县": CategoryEnum.FOOD,
    "兰州拉面": CategoryEnum.FOOD,
    "老乡鸡": CategoryEnum.FOOD,
    "真功夫": CategoryEnum.FOOD,
    "华莱士": CategoryEnum.FOOD,
    "dicos": CategoryEnum.FOOD,
    "德克士": CategoryEnum.FOOD,
    "foodpanda": CategoryEnum.FOOD,
    "grab food": CategoryEnum.FOOD,
    "grabfood": CategoryEnum.FOOD,

    # ── 交通出行 ──────────────────────────────────────────────────────────────
    "滴滴": CategoryEnum.TRANSPORT,
    "高德打车": CategoryEnum.TRANSPORT,
    "曹操出行": CategoryEnum.TRANSPORT,
    "神州专车": CategoryEnum.TRANSPORT,
    "t3出行": CategoryEnum.TRANSPORT,
    "中国铁路": CategoryEnum.TRANSPORT,
    "铁路12306": CategoryEnum.TRANSPORT,
    "12306": CategoryEnum.TRANSPORT,
    "smrt": CategoryEnum.TRANSPORT,
    "sbs transit": CategoryEnum.TRANSPORT,
    "ez-link": CategoryEnum.TRANSPORT,
    "grab": CategoryEnum.TRANSPORT,
    "gojek": CategoryEnum.TRANSPORT,
    "comfort taxi": CategoryEnum.TRANSPORT,
    "uber": CategoryEnum.TRANSPORT,
    "lyft": CategoryEnum.TRANSPORT,
    "地铁": CategoryEnum.TRANSPORT,
    "mrt": CategoryEnum.TRANSPORT,
    "公交": CategoryEnum.TRANSPORT,
    "高铁": CategoryEnum.TRANSPORT,
    "动车": CategoryEnum.TRANSPORT,
    "停车": CategoryEnum.TRANSPORT,
    "加油站": CategoryEnum.TRANSPORT,
    "中国石化": CategoryEnum.TRANSPORT,
    "中国石油": CategoryEnum.TRANSPORT,
    "壳牌": CategoryEnum.TRANSPORT,
    "shell": CategoryEnum.TRANSPORT,
    "esso": CategoryEnum.TRANSPORT,
    "easybook": CategoryEnum.TRANSPORT,
    "busonlineticket": CategoryEnum.TRANSPORT,

    # ── 居住 ─────────────────────────────────────────────────────────────────
    "国家电网": CategoryEnum.HOUSING,
    "南方电网": CategoryEnum.HOUSING,
    "水务": CategoryEnum.HOUSING,
    "自来水": CategoryEnum.HOUSING,
    "燃气": CategoryEnum.HOUSING,
    "天然气": CategoryEnum.HOUSING,
    "物业": CategoryEnum.HOUSING,
    "房租": CategoryEnum.HOUSING,
    "链家": CategoryEnum.HOUSING,
    "贝壳": CategoryEnum.HOUSING,
    "爱彼迎": CategoryEnum.HOUSING,
    "airbnb": CategoryEnum.HOUSING,

    # ── 订阅服务 ──────────────────────────────────────────────────────────────
    "netflix": CategoryEnum.SUBSCRIPTION,
    "spotify": CategoryEnum.SUBSCRIPTION,
    "apple music": CategoryEnum.SUBSCRIPTION,
    "youtube premium": CategoryEnum.SUBSCRIPTION,
    "disney+": CategoryEnum.SUBSCRIPTION,
    "disney plus": CategoryEnum.SUBSCRIPTION,
    "hbo": CategoryEnum.SUBSCRIPTION,
    "amazon prime": CategoryEnum.SUBSCRIPTION,
    "爱奇艺": CategoryEnum.SUBSCRIPTION,
    "腾讯视频": CategoryEnum.SUBSCRIPTION,
    "优酷": CategoryEnum.SUBSCRIPTION,
    "芒果tv": CategoryEnum.SUBSCRIPTION,
    "bilibili": CategoryEnum.SUBSCRIPTION,
    "b站大会员": CategoryEnum.SUBSCRIPTION,
    "网易云音乐": CategoryEnum.SUBSCRIPTION,
    "qq音乐": CategoryEnum.SUBSCRIPTION,
    "酷狗": CategoryEnum.SUBSCRIPTION,
    "microsoft 365": CategoryEnum.SUBSCRIPTION,
    "office 365": CategoryEnum.SUBSCRIPTION,
    "adobe": CategoryEnum.SUBSCRIPTION,
    "dropbox": CategoryEnum.SUBSCRIPTION,
    "notion": CategoryEnum.SUBSCRIPTION,
    "chatgpt": CategoryEnum.SUBSCRIPTION,
    "openai": CategoryEnum.SUBSCRIPTION,
    "claude": CategoryEnum.SUBSCRIPTION,

    # ── 购物 ─────────────────────────────────────────────────────────────────
    "拼多多": CategoryEnum.SHOPPING,
    "京东": CategoryEnum.SHOPPING,
    "淘宝": CategoryEnum.SHOPPING,
    "天猫": CategoryEnum.SHOPPING,
    "苏宁": CategoryEnum.SHOPPING,
    "国美": CategoryEnum.SHOPPING,
    "amazon": CategoryEnum.SHOPPING,
    "shopee": CategoryEnum.SHOPPING,
    "lazada": CategoryEnum.SHOPPING,
    "taobao": CategoryEnum.SHOPPING,
    "jd.com": CategoryEnum.SHOPPING,
    "zara": CategoryEnum.SHOPPING,
    "h&m": CategoryEnum.SHOPPING,
    "uniqlo": CategoryEnum.SHOPPING,
    "优衣库": CategoryEnum.SHOPPING,
    "nike": CategoryEnum.SHOPPING,
    "adidas": CategoryEnum.SHOPPING,
    "muji": CategoryEnum.SHOPPING,
    "无印良品": CategoryEnum.SHOPPING,

    # ── 医疗健康 ──────────────────────────────────────────────────────────────
    "药房": CategoryEnum.HEALTH,
    "大药房": CategoryEnum.HEALTH,
    "医院": CategoryEnum.HEALTH,
    "诊所": CategoryEnum.HEALTH,
    "体检": CategoryEnum.HEALTH,
    "guardian": CategoryEnum.HEALTH,
    "watson": CategoryEnum.HEALTH,
    "watsons": CategoryEnum.HEALTH,
    "屈臣氏": CategoryEnum.HEALTH,
    "健康元": CategoryEnum.HEALTH,

    # ── 日用百货 ──────────────────────────────────────────────────────────────
    "walmart": CategoryEnum.DAILY_NECESSITIES,
    "沃尔玛": CategoryEnum.DAILY_NECESSITIES,
    "家乐福": CategoryEnum.DAILY_NECESSITIES,
    "carrefour": CategoryEnum.DAILY_NECESSITIES,
    "大润发": CategoryEnum.DAILY_NECESSITIES,
    "永辉": CategoryEnum.DAILY_NECESSITIES,
    "盒马": CategoryEnum.DAILY_NECESSITIES,
    "seven-eleven": CategoryEnum.DAILY_NECESSITIES,
    "7-eleven": CategoryEnum.DAILY_NECESSITIES,
    "7eleven": CategoryEnum.DAILY_NECESSITIES,
    "全家": CategoryEnum.DAILY_NECESSITIES,
    "familymart": CategoryEnum.DAILY_NECESSITIES,
    "罗森": CategoryEnum.DAILY_NECESSITIES,
    "lawson": CategoryEnum.DAILY_NECESSITIES,
    "fairprice": CategoryEnum.DAILY_NECESSITIES,
    "ntuc": CategoryEnum.DAILY_NECESSITIES,
    "cold storage": CategoryEnum.DAILY_NECESSITIES,
    "giant": CategoryEnum.DAILY_NECESSITIES,
    "ikea": CategoryEnum.DAILY_NECESSITIES,
    "宜家": CategoryEnum.DAILY_NECESSITIES,

    # ── 娱乐休闲 ──────────────────────────────────────────────────────────────
    "万达影城": CategoryEnum.ENTERTAINMENT,
    "cgv": CategoryEnum.ENTERTAINMENT,
    "大地影院": CategoryEnum.ENTERTAINMENT,
    "猫眼": CategoryEnum.ENTERTAINMENT,
    "淘票票": CategoryEnum.ENTERTAINMENT,
    "大麦": CategoryEnum.ENTERTAINMENT,
    "秀动": CategoryEnum.ENTERTAINMENT,
    "ktv": CategoryEnum.ENTERTAINMENT,
    "唱吧": CategoryEnum.ENTERTAINMENT,
    "steam": CategoryEnum.ENTERTAINMENT,
    "epic games": CategoryEnum.ENTERTAINMENT,
    "playstation": CategoryEnum.ENTERTAINMENT,
    "xbox": CategoryEnum.ENTERTAINMENT,
    "nintendo": CategoryEnum.ENTERTAINMENT,

    # ── 教育 ─────────────────────────────────────────────────────────────────
    "新东方": CategoryEnum.EDUCATION,
    "好未来": CategoryEnum.EDUCATION,
    "学而思": CategoryEnum.EDUCATION,
    "coursera": CategoryEnum.EDUCATION,
    "udemy": CategoryEnum.EDUCATION,
    "duolingo": CategoryEnum.EDUCATION,
    "多邻国": CategoryEnum.EDUCATION,
}


def match_merchant(counterparty: str) -> Optional[tuple[CategoryEnum, float, str]]:
    """
    精确商家映射匹配。
    返回 (类别, 置信度=1.0, 证据字符串) 或 None。
    """
    if not counterparty:
        return None
    normalized = counterparty.lower().strip()
    for keyword, category in MERCHANT_MAP.items():
        if keyword in normalized:
            return (category, 1.0, f"商家映射命中: '{keyword}' → {category.value}")
    return None
