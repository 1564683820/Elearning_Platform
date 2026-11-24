"""
TTS 语音合成服务

使用火山引擎 v3 豆包大模型 API（WebSocket 双向流式），含双层缓存：
  1. 永久文件缓存（本地磁盘，同文本永不重复调用 API）
  2. Redis 临时缓存（TTL 24h，加速存取）

Resource-Id: seed-tts-2.0（豆包语音合成大模型2.0）
API: wss://openspeech.bytedance.com/api/v3/tts/bidirection
"""
import json as json_module
import time
import uuid
import os
import hashlib
import base64
import logging
import httpx
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.paths import UPLOADS_DIR
from app.utils.redis_client import get_redis, RedisCache

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis 缓存 TTL（24 小时）
TTS_CACHE_TTL = 86400

# 火山引擎 v3 TTS HTTP 地址（单向流式合成，推荐）
# 文档: https://www.volcengine.com/docs/6561/79823
VOLC_TTS_HTTP_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

# v3 Resource-Id：官方预置音色 2.0
VOLC_TTS_RESOURCE_ID = "seed-tts-2.0"


def _get_persist_dir() -> str:
    """获取 TTS 永久缓存目录

    优先级:
      1. 配置 TTS_PERSIST_DIR（绝对路径）
      2. 服务端上传目录下的 textbook/tts/
    """
    if settings.TTS_PERSIST_DIR:
        return settings.TTS_PERSIST_DIR
    return str(UPLOADS_DIR / "textbook" / "tts")


def _get_persist_path(speaker: str, text: str) -> str:
    """获取 TTS 永久文件的绝对路径"""
    text_md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
    persist_dir = _get_persist_dir()
    return os.path.join(persist_dir, speaker, f"{text_md5}.mp3")


def _get_persist_url(speaker: str, text: str) -> str:
    """获取 TTS 永久文件的可访问 URL"""
    text_md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"/uploads/textbook/tts/{speaker}/{text_md5}.mp3"


# seed-tts-2.0 音色映射（角色类型 -> Speaker ID）
# 示例代码中确认可用的音色: zh_female_gaolengyujie_uranus_bigtts
# 其他音色需要登录控制台 > 音色库查看
CHARACTER_VOICE_MAP_V2 = {
    "cat_teacher": "zh_female_gaolengyujie_uranus_bigtts",
    "emma": "zh_female_gaolengyujie_uranus_bigtts",
    "vv": "zh_female_vv_uranus_bigtts",
    "gaolengyujie": "zh_female_gaolengyujie_uranus_bigtts",
}

VOICE_MAP_V2 = {
    "zh_female_gaolengyujie_uranus_bigtts": "zh_female_gaolengyujie_uranus_bigtts",
    "zh_female_vv_uranus_bigtts": "zh_female_vv_uranus_bigtts",
}


def _resolve_volc_speaker(voice_id: str) -> str:
    """解析为 seed-tts-2.0 兼容的 Speaker ID

    支持三种输入:
      1. 角色别名（如 cat_teacher, emma）→ 查 CHARACTER_VOICE_MAP_V2
      2. 完整 Speaker ID（如 zh_female_gaolengyujie_uranus_bigtts）→ 直接返回
      3. 未知 → 返回示例中确认可用的默认音色
    """
    if voice_id in CHARACTER_VOICE_MAP_V2:
        return CHARACTER_VOICE_MAP_V2[voice_id]
    if voice_id in VOICE_MAP_V2:
        return VOICE_MAP_V2[voice_id]
    # 默认使用示例代码中确认可用的音色
    return "zh_female_vv_uranus_bigtts"


async def _call_volc_v3_tts(text: str, speaker: str) -> bytes:
    """调用火山引擎 v3 TTS API（HTTP 单向流式合成），返回 MP3 音频字节

    使用 httpx 发送 HTTP POST 请求，从 NDJSON 响应中逐行解析 base64 音频块。
    文档: https://www.volcengine.com/docs/6561/79823
    """
    api_key = getattr(settings, "TTS_API_KEY", "") or ""
    if not api_key:
        raise ValueError("未配置 TTS_API_KEY，请在 .env 中填入")

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": VOLC_TTS_RESOURCE_ID,
        "Content-Type": "application/json",
    }

    body = {
        "user": {"uid": "elearning_user"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
            },
        },
    }

    # 中英双语音色（zh_female_vv_uranus_bigtts）通过 explicit_language 指定输出语种
    # 检测文本语言：如果大部分字符是 ASCII，强制输出英文
    ascii_chars = sum(1 for c in text if ord(c) < 256)
    if ascii_chars > len(text) * 0.6:
        body["req_params"]["audio_params"]["explicit_language"] = "en"
    else:
        body["req_params"]["audio_params"]["explicit_language"] = "zh-cn"

    logger.debug("TTS HTTP 请求: speaker=%s, text_len=%s", speaker, len(text))

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.post(VOLC_TTS_HTTP_URL, json=body, headers=headers)

    if resp.status_code != 200:
        raise ValueError(
            f"TTS 调用失败: status={resp.status_code}, body={resp.text[:500]}"
        )

    # 解析 NDJSON 响应：逐行读取，提取 base64 音频块
    audio_chunks: list[bytes] = []
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json_module.loads(line)
        except json_module.JSONDecodeError:
            continue
        code = chunk.get("code", -1)
        raw_data = chunk.get("data")
        if code == 0 and raw_data:
            audio_chunks.append(base64.b64decode(raw_data))
        elif code == 20000000:
            break
        elif code != 0:
            # Log the full chunk for debugging before raising
            logger.warning("TTS NDJSON 错误块: %s", chunk)
            raise ValueError(
                f"TTS 服务错误: code={code}, message={chunk.get('message', '')}"
            )

    if not audio_chunks:
        # Log the raw response for diagnosis
        logger.warning("TTS 无音频数据，原始响应前 500 字符: %s", resp.text[:500])
        raise ValueError("TTS 返回空音频数据")

    logger.debug("TTS HTTP 完成: %d 个块, 总计 %d bytes",
                 len(audio_chunks), sum(len(c) for c in audio_chunks))
    return b"".join(audio_chunks)


class TTSService:
    """TTS 语音合成服务（火山引擎 v3 豆包大模型 API）"""

    @staticmethod
    async def synthesize(
        text: str,
        voice_type: str = "zh_female_vv_uranus_bigtts",
        save_path: Optional[str] = None,
        use_cache: bool = True,
    ) -> bytes:
        """调用火山引擎 v3 TTS API（seed-tts-2.0）生成语音

        参数:
            text: 待合成文本
            voice_type: Speaker ID（默认 zh_female_vv_uranus_bigtts，你账号可用的中文女声）
            save_path: 若指定，将音频写入本地文件
            use_cache: 是否使用缓存（Redis + 本地文件）

        返回:
            bytes: MP3 音频二进制数据
        """
        if not text.strip():
            raise ValueError("TTS 文本不能为空")

        # 解析为 v3 Speaker ID
        speaker = _resolve_volc_speaker(voice_type)

        text_md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
        cache_key = f"tts:{speaker}:{text_md5}"
        persist_path = _get_persist_path(speaker, text)

        # ── 第 1 层缓存：本地永久文件 ──
        if use_cache and os.path.isfile(persist_path):
            with open(persist_path, "rb") as f:
                audio_bytes = f.read()
            logger.debug("TTS 本地文件缓存命中: %s", persist_path)
            if save_path:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(audio_bytes)
            return audio_bytes

        # ── 第 2 层缓存：Redis ──
        if use_cache:
            redis = await get_redis()
            cache = RedisCache(redis)
            cached = await cache.get(cache_key)
            if cached is not None:
                audio_bytes = base64.b64decode(cached)
                logger.debug("TTS Redis 缓存命中: speaker=%s, text_len=%s", speaker, len(text))
                os.makedirs(os.path.dirname(persist_path), exist_ok=True)
                with open(persist_path, "wb") as f:
                    f.write(audio_bytes)
                if save_path:
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(audio_bytes)
                return audio_bytes

        # ── 第 3 层：调用火山引擎 TTS API（X-Api-Key 鉴权）────
        audio_bytes = await _call_volc_v3_tts(text=text, speaker=speaker)

        # ── 写入缓存 ──
        os.makedirs(os.path.dirname(persist_path), exist_ok=True)
        with open(persist_path, "wb") as f:
            f.write(audio_bytes)
        logger.info("TTS 已写入永久缓存: %s (%d bytes)", persist_path, len(audio_bytes))

        if use_cache and audio_bytes:
            await cache.set(cache_key, base64.b64encode(audio_bytes).decode(), ex=TTS_CACHE_TTL)

        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(audio_bytes)

        logger.info("TTS 合成成功: voice=%s, text_len=%s, bytes=%s",
                    speaker, len(text), len(audio_bytes))
        return audio_bytes

    @staticmethod
    async def synthesize_for_page(
        db: AsyncSession,
        page_id: int,
        sentence_index: int = -1,
    ) -> dict:
        """为教材页面合成音频，返回可直接播放的 audio_url

        参数:
            db: 数据库会话
            page_id: 教材页面 ID
            sentence_index: -1 合成整页全文用于全文朗读;
                            >=0 合成指定句子的音频用于点读

        返回:
            dict: {audio_url, text, voice_type, cached}
                  audio_url 可直接返回前端播放
                  cached=true 表示从缓存读取（未消耗 API 费用）
        """
        from app.services.textbook_service import TextbookService

        cdn_base = getattr(settings, "CDN_BASE_URL", "")
        detail = await TextbookService.get_page_detail(db, page_id, cdn_base)
        if not detail:
            return {"audio_url": "", "error": "页面不存在"}

        # 确定合成文本和音色
        sentences = detail.get("sentences", [])
        if sentence_index >= 0 and sentence_index < len(sentences):
            sentence = sentences[sentence_index]
            text = sentence.get("en") or sentence.get("text", "")
        else:
            text = detail.get("text_content", "")

        if not text.strip():
            return {"audio_url": "", "error": "无文本内容"}

        # 确定 Speaker ID（seed-tts-2.0 音色）
        speaker = _resolve_volc_speaker(
            getattr(settings, "TTS_VOICE", "zh_female_vv_uranus_bigtts")
        )

        # 检查永久文件缓存是否存在
        persist_path = _get_persist_path(speaker, text)
        cached = os.path.isfile(persist_path)

        if cached:
            audio_url = _get_persist_url(speaker, text)
            logger.debug("TTS 缓存命中: page_id=%s, sentence=%s, url=%s",
                         page_id, sentence_index, audio_url)
        else:
            # 调用合成 API（v3）
            try:
                await TTSService.synthesize(
                    text=text,
                    voice_type=speaker,
                    use_cache=True,
                )
            except Exception as e:
                logger.error("TTS 合成失败: page_id=%s, error=%s", page_id, e)
                return {"audio_url": "", "error": str(e)}

            audio_url = _get_persist_url(speaker, text)
            logger.info("TTS 合成成功: page_id=%s, sentence=%s, url=%s",
                        page_id, sentence_index, audio_url)

        # 拼装完整 URL（如果配置了 CDN）
        if cdn_base:
            audio_url = f"{cdn_base.rstrip('/')}/{audio_url.lstrip('/')}"

        return {
            "audio_url": audio_url,
            "text": text,
            "text_len": len(text),
            "speaker": speaker,
            "voice_type": speaker,
            "cached": cached,
        }

    @staticmethod
    async def create_tts_task(
        db: AsyncSession,
        page_id: int,
        sentence_index: int = -1,
        user_id: int = 0,
    ) -> dict:
        """为教材页面创建 TTS 朗读任务（兼容旧调用方）

        现在使用 synthesize_for_page 替代，返回 audio_url
        """
        result = await TTSService.synthesize_for_page(db, page_id, sentence_index)
        task_id = f"tts_{uuid.uuid4().hex[:12]}"
        return {
            "task_id": task_id,
            "status": "completed" if result.get("audio_url") else "failed",
            "audio_url": result.get("audio_url", ""),
            "audio_path": result.get("audio_url", ""),
            "text_len": result.get("text_len", 0),
            "error": result.get("error", ""),
            "cached": result.get("cached", False),
        }


# 便捷函数：兼容 textbook router 和 video_ai_service 中的调用
async def synthesize_speech(
    text: str,
    voice_type: str = "zh_female_vv_uranus_bigtts",
    save_path: Optional[str] = None,
) -> bytes:
    """TTS 语音合成便捷函数（seed-tts-2.0）

    参数:
        text: 待合成文本
        voice_type: Speaker ID（默认 zh_female_vv_uranus_bigtts）
        save_path: 可选本地保存路径
    """
    return await TTSService.synthesize(text, voice_type, save_path)
