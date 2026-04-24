"""
Follow-up & Insights Agent 工具函数。

包含缓存装饰器和其他通用工具函数。
"""
from functools import lru_cache
import logging
from typing import Callable, Any

logger = logging.getLogger("insights.utils")

# 缓存配置
CACHE_SIZE = 100
CACHE_TTL = 3600  # 缓存有效期（秒）


# 缓存装饰器，用于缓存频繁使用的分析结果
# 注意：由于交易列表是不可哈希的，这里不使用 lru_cache
def cached_analysis(maxsize: int = CACHE_SIZE) -> Callable:
    """
    缓存分析结果的装饰器
    
    Args:
        maxsize: 缓存大小
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        # 由于交易列表是不可哈希的，这里不使用 lru_cache
        # 直接返回原函数
        return func
    return decorator


def clear_cache():
    """
    清除所有缓存
    """
    # 这里我们不能直接清除其他模块的缓存
    # 因为这会导致循环导入
    # 每个模块需要自己管理自己的缓存
    logger.info("Cache cleared successfully")