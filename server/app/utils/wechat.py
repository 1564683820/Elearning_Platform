import httpx
from app.core.config import get_settings

settings = get_settings()

# 微信 code2session 接口
WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


async def code2session(code: str) -> dict:
    """
    用微信 login code 换取 openid 和 session_key
    返回: {"openid": "...", "session_key": "...", "unionid": "..."} 或 {"errcode": ..., "errmsg": ...}
    """
    params = {
        "appid": settings.WX_APPID,
        "secret": settings.WX_APP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(WX_CODE2SESSION_URL, params=params)
        resp.raise_for_status()
        return resp.json()
