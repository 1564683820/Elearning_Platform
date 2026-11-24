"""JSON 序列化工具 — 处理 SSE 等场景下的大整数安全转换"""
import json

# JS 安全整数上限：超出此范围的 int 在 JSON 中转为字符串，防止前端 JSON.parse 精度丢失
_JS_MAX_SAFE_INT = 2 ** 53


def _convert_bigint(obj):
    """递归将超出 JS 安全整数范围的 int 转为字符串"""
    if isinstance(obj, dict):
        return {k: _convert_bigint(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_bigint(v) for v in obj]
    if isinstance(obj, int) and (obj > _JS_MAX_SAFE_INT or obj < -_JS_MAX_SAFE_INT):
        return str(obj)
    return obj


def safe_json_dumps(obj, **kwargs) -> str:
    """将对象中的大整数转为字符串后再 JSON 序列化（用于 SSE 等非 FastAPI 标准响应）"""
    converted = _convert_bigint(obj)
    return json.dumps(converted, **kwargs)
