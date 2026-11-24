"""
STT 语音识别服务

使用 SiliconFlow 托管的 Whisper API（兼容 OpenAI 格式）将音频转为文本。
Audio 文件通过 HTTP multipart/form-data 上传后调用该服务的 transcribe() 方法。
"""
import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# SiliconFlow Whisper 兼容端点
WHISPER_API_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
WHISPER_MODEL = "FunAudioLLM/SenseVoiceSmall"  # 或 "whisper-large-v3"


class STTService:
    """语音识别服务 — 使用 SiliconFlow Whisper 兼容 API"""

    @staticmethod
    async def transcribe(
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: str = "en",
    ) -> str:
        """将音频字节流转换为文本

        参数:
            audio_bytes: 原始音频字节数据（支持 wav / mp3 / m4a 等格式）
            filename:   上传时的文件名（扩展名决定 API 识别的格式）
            language:   语言提示（en / zh / auto）

        返回:
            str: 识别出的文本
        """
        api_key = getattr(settings, "MULTIMODAL_API_KEY", "") or getattr(settings, "LLM_API_KEY", "")
        if not api_key:
            raise ValueError("未配置 MULTIMODAL_API_KEY，请在 .env 中填写 SiliconFlow API Key")

        # 构造 multipart/form-data 请求
        files = {
            "file": (filename, audio_bytes, "audio/wav"),
        }
        data = {
            "model": WHISPER_MODEL,
            "language": language,
            "response_format": "json",
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        logger.info("STT 请求: model=%s, language=%s, size=%d bytes", WHISPER_MODEL, language, len(audio_bytes))

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(WHISPER_API_URL, headers=headers, files=files, data=data)

        if resp.status_code != 200:
            logger.error("STT 调用失败: status=%s, body=%s", resp.status_code, resp.text[:500])
            raise ValueError(f"语音识别失败: HTTP {resp.status_code}")

        result = resp.json()
        text = result.get("text", "").strip()
        logger.info("STT 结果: text='%s'", text[:100])
        return text if text else ""
