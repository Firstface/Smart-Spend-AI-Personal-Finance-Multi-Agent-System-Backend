"""
Keyword / regex rules engine (Layer 2) — confidence = 0.85.

Applies regex matching on combined counterparty + goods_description text.
Higher priority than similarity matching and LLM, lower than merchant map.
"""
import re
from typing import Optional
from schemas.transaction import CategoryEnum

# Rule list: (compiled regex, category, evidence label)
# Order determines priority — first match wins
KEYWORD_RULES: list[tuple[re.Pattern, CategoryEnum, str]] = [
    # Food & Dining
    (re.compile(
        r"(外卖|堂食|餐厅|饭店|食堂|奶茶|咖啡|火锅|烧烤|面条|小面|面馆|米线|拉面|粥|寿司|"
        r"快餐|小吃|甜品|蛋糕|面包|饺子|汤圆|早餐|午餐|晚餐|宵夜|"
        r"restaurant|cafe|coffee|bakery|bubble tea|hotpot)",
        re.I
    ), CategoryEnum.FOOD, "keyword:food"),

    # Transport
    (re.compile(
        r"(出租车|打车|网约车|公交车|地铁票|机票|火车票|高铁票|船票|"
        r"过路费|停车费|加油|充电桩|汽车维修|保险|年检|驾照|"
        r"taxi|bus ticket|train ticket|flight|toll|parking|petrol|fuel)",
        re.I
    ), CategoryEnum.TRANSPORT, "keyword:transport"),

    # Housing
    (re.compile(
        r"(电费|水费|燃气费|煤气费|房租|物业费|暖气费|宽带|网费|"
        r"electricity|water bill|gas bill|rent|utilities|broadband|wifi)",
        re.I
    ), CategoryEnum.HOUSING, "keyword:housing"),

    # Daily Necessities
    (re.compile(
        r"(超市|便利店|日用品|洗衣液|洗洁精|纸巾|卫生纸|牙膏|牙刷|"
        r"沐浴露|洗发水|护肤品|化妆品|清洁|消毒|垃圾袋|保鲜膜|"
        r"supermarket|grocery|household|toiletries|detergent)",
        re.I
    ), CategoryEnum.DAILY_NECESSITIES, "keyword:daily"),

    # Entertainment & Leisure
    (re.compile(
        r"(电影|影院|KTV|游戏|门票|景区|游乐园|健身|游泳|羽毛球|"
        r"台球|棋牌|桌游|演唱会|音乐会|展览|博物馆|旅游|酒店|民宿|"
        r"cinema|movie|ticket|gym|fitness|concert|museum|hotel|resort)",
        re.I
    ), CategoryEnum.ENTERTAINMENT, "keyword:entertainment"),

    # Healthcare
    (re.compile(
        r"(药品|药店|医院|诊所|挂号|体检|化验|手术|医保|保健品|"
        r"维生素|口罩|体温计|血压计|眼镜|隐形眼镜|"
        r"pharmacy|clinic|hospital|medicine|prescription|health check)",
        re.I
    ), CategoryEnum.HEALTH, "keyword:health"),

    # Education
    (re.compile(
        r"(书籍|教材|课程|培训|学费|考试费|报名费|辅导|补课|"
        r"文具|练习册|网课|在线教育|学习资料|图书|"
        r"book|course|tuition|training|exam|tutorial|education)",
        re.I
    ), CategoryEnum.EDUCATION, "keyword:education"),

    # Subscriptions (supplements merchant map for uncovered cases)
    (re.compile(
        r"(月会员|年会员|会员费|订阅|自动续费|vip|premium|"
        r"subscription|membership|renewal|auto.?renew)",
        re.I
    ), CategoryEnum.SUBSCRIPTION, "keyword:subscription"),

    # Shopping (catch-all for e-commerce platforms)
    (re.compile(
        r"(网购|电商|购物|商城|旗舰店|专卖店|outlet|折扣|秒杀|"
        r"online shopping|e-commerce|mall|store)",
        re.I
    ), CategoryEnum.SHOPPING, "keyword:shopping"),
]


def match_keywords(
    counterparty: str, description: Optional[str]
) -> Optional[tuple[CategoryEnum, float, str]]:
    """
    Keyword rule matching.
    Returns (category, confidence=0.85, evidence string) or None.
    """
    if not counterparty:
        return None
    combined = f"{counterparty} {description or ''}".strip()
    for pattern, category, evidence_tag in KEYWORD_RULES:
        m = pattern.search(combined)
        if m:
            matched_word = m.group(0)
            return (category, 0.85, f"{evidence_tag}: matched '{matched_word}'")
    return None
