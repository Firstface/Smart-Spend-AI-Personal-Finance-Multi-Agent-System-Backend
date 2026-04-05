"""
共用依赖注入：从 Authorization Header 提取 user_id。
无 token 时降级为 "demo-user"（方便开发调试）。
"""
from fastapi import Header
from typing import Optional
from api.auth import get_current_user_id


def get_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """
    从 'Authorization: Bearer <token>' 提取 user_id。
    无 token 时返回 'demo-user'，兼容前端未登录状态。
    """
    if not authorization or not authorization.startswith("Bearer "):
        return "demo-user"
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return get_current_user_id(token)
    except Exception:
        return "demo-user"
