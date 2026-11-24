"""
语音对话 API 路由 — STT + AI 对话 + TTS 一体化端点 + WebSocket 实时对话

流程:
  REST:  接收用户上传的音频 → STT → AI 对话 → TTS → 返回结果
  WS:    客户端 WebSocket 连接 → 后端代理到火山引擎 Realtime API（端到端语音对话）
"""
import json
import os
import hashlib
import base64
import asyncio
import logging
import struct
from fastapi import APIRouter, Depends, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.ai_service import AIService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.scenario_prompts import build_scenario_system_prompt
from app.schemas.common import ResponseData
from app.core.config import get_settings
from app.core.paths import UPLOADS_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["语音对话"])

# 场景预设 — 复用 ai_chat 的场景列表
try:
    from app.services.scenario_prompts import SCENARIO_PRESETS
except ImportError:
    SCENARIO_PRESETS = []

# 音频缓存目录
settings_voice = get_settings()
AUDIO_CACHE_DIR = str(UPLOADS_DIR / "voice_chat")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)


class TTSRequest(BaseModel):
    """通用 TTS 合成请求"""
    text: str
    voice_type: str = "zh_female_vv_uranus_bigtts"


@router.post("/voice-chat", response_model=ResponseData)
async def voice_chat(
    file: UploadFile = File(...),
    scenario_id: str = Form(""),
    level: str = Form("intermediate"),
    conversation_history: str = Form("[]"),   # JSON string of previous messages
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """语音对话：接收音频 → STT → AI 对话 + 纠错 → TTS → 返回结果

    参数:
        file:                音频文件 (wav/mp3/m4a)
        scenario_id:         场景 ID（如 coffee, restaurant）
        level:               难度 (beginner/intermediate/advanced)
        conversation_history: 之前对话历史的 JSON 字符串

    返回:
        { transcription, ai_content, analysis, audio_url, audio_bytes (base64) }
    """
    # 1. 读取音频（纯内存处理，不持久化到磁盘）
    audio_bytes = await file.read()
    if not audio_bytes:
        return ResponseData(code=1, message="音频内容为空")

    # 2. STT 转文本
    try:
        transcription = await STTService.transcribe(audio_bytes, filename=file.filename or "audio.wav", language="en")
    except Exception as e:
        logger.error("STT 失败: %s", e)
        return ResponseData(code=1, message=f"语音识别失败: {str(e)}")

    if not transcription.strip():
        return ResponseData(code=1, message="未能识别到语音内容，请重试")

    # 3. 构造 AI 对话消息
    history = []
    try:
        history = json.loads(conversation_history)
        if not isinstance(history, list):
            history = []
    except (json.JSONDecodeError, TypeError):
        history = []

    # 构建 system prompt（含纠错指令）
    system_prompt = _build_voice_scenario_prompt(scenario_id, level)

    # 过滤掉历史中的 system 消息，用新的 system prompt
    filtered_history = [m for m in history if m.get("role") != "system"]
    messages = [{"role": "system", "content": system_prompt}] + filtered_history
    # 追加用户语音转写的文本
    messages.append({"role": "user", "content": transcription})

    # 4. 调用 LLM
    try:
        ai_response = await AIService.chat_completion(
            db, messages, user_id,
            timeout_seconds=60.0,
        )
    except Exception as e:
        logger.error("AI 对话失败: %s", e)
        return ResponseData(code=1, message=f"AI 回复失败: {str(e)}")

    # 5. 解析 AI 回复中的纠错分析（如果存在 ---PRONUNCIATION_ANALYSIS--- 分隔）
    ai_content = ai_response
    analysis = ""
    separator = "---PRONUNCIATION_ANALYSIS---"
    if separator in ai_response:
        parts = ai_response.split(separator, 1)
        ai_content = parts[0].strip()
        analysis = parts[1].strip()

    # 6. TTS 合成 AI 回答的音频（只合成纯英文回答部分，不合成中文分析）
    tts_text = _extract_english_for_tts(ai_content)
    audio_bytes_tts = b""
    audio_url = ""
    if tts_text.strip():
        try:
            audio_bytes_tts = await TTSService.synthesize(
                text=tts_text,
                voice_type="zh_female_vv_uranus_bigtts",
                use_cache=True,
            )
            # 不持久化到磁盘，直接通过 base64 返回给客户端
            audio_url = ""
        except Exception as e:
            logger.warning("TTS 合成失败: %s", e)

    import base64
    return ResponseData(data={
        "transcription": transcription,
        "ai_content": ai_content,
        "analysis": analysis,
        "audio_url": audio_url,
        "audio_base64": base64.b64encode(audio_bytes_tts).decode() if audio_bytes_tts else "",
    })


# ═══════════════════════════════════════════════════════
# 对话评分（在用户结束对话后调用，对整个会话进行评分）
# ═══════════════════════════════════════════════════════

class VoiceEvaluateRequest(BaseModel):
    """对话评分请求"""
    scenario_id: str = ""
    level: str = "intermediate"
    conversation_history: list = []  # [{role, content}, ...]


@router.post("/voice-evaluate", response_model=ResponseData)
async def voice_evaluate(
    body: VoiceEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """对整个对话进行 AI 综合评分

    分析用户的语法、词汇、流利度、互动质量等维度，
    返回分数和改进建议。
    """
    scene_name = _get_scene_name(body.scenario_id) or "英语口语练习"

    # 收集用户发言和AI发言
    user_turns = [m.get("content", "") for m in body.conversation_history if m.get("role") == "user"]
    total_turns = len(user_turns)

    if total_turns == 0:
        return ResponseData(code=1, message="对话轮次不足，无法评分")

    # 构建评分 system prompt — 增加发音准确度和停顿管理维度
    eval_prompt = (
        "You are an expert English speaking assessment evaluator. "
        f"Evaluate the following conversation in the scenario '{scene_name}' (level: {body.level}).\n\n"
        "Score each dimension out of its max, then compute the total:\n"
        "1. Pronunciation Accuracy (0-20): phonetic clarity, word stress, intonation, 'th'/'r'/'l' sounds\n"
        "2. Pause & Fluency Management (0-20): natural pacing, avoiding excessive 'uh/um' fillers, "
        "smooth between phrases, appropriate pausing\n"
        "3. Grammar Accuracy (0-20): correct sentence structure, tenses, articles, prepositions\n"
        "4. Vocabulary & Expression (0-20): word choice, variety, idiomatic usage relevant to the scene\n"
        "5. Interaction & Engagement (0-20): responsiveness, asking questions, staying on topic\n\n"
        "Total: sum of all dimensions (max 100)\n\n"
        "Respond in JSON format ONLY, no preamble:\n"
        "{\n"
        '  "score": <total 0-100>,\n'
        '  "dimensions": {\n'
        '    "pronunciation": <0-20>,\n'
        '    "pause_fluency": <0-20>,\n'
        '    "grammar": <0-20>,\n'
        '    "vocabulary": <0-20>,\n'
        '    "interaction": <0-20>\n'
        '  },\n'
        '  "feedback": "<2-3 sentence overall feedback in Chinese>",\n'
        '  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],\n'
        '  "improvements": ["<improvement 1>", "<improvement 2>"]\n'
        "}\n\n"
        "Conversation to evaluate:"
    )

    history_msgs = [{"role": "system", "content": eval_prompt}]
    for m in body.conversation_history:
        role = m.get("role", "user")
        if role == "ai":
            role = "assistant"
        history_msgs.append({"role": role, "content": m.get("content", "")})

    # ── 带重试的 AI 评分调用（deepseek-v4-flash 偶有空响应） ──
    ai_response = ""
    MAX_RETRIES = 2
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ai_response = await AIService.chat_completion(
                db, history_msgs, user_id,
                timeout_seconds=60.0,
                max_tokens=2048,
            )
        except Exception as e:
            logger.warning("评分 AI 调用失败(第%d次): %s", attempt, e)
            ai_response = ""
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.0)
            continue

        # 检查是否为空响应（deepseek-v4-flash 偶有返回 HTTP 200 但 content 为空）
        if ai_response is None or ai_response.strip() == "":
            logger.warning("评分 AI 返回空内容(第%d次)，即将重试…", attempt)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.0)
            continue

        # 非空，退出重试循环
        break

    # ── 所有重试后仍为空 → 降级为默认评分 ──
    if ai_response is None or ai_response.strip() == "":
        logger.error("评分 AI 在所有 %d 次尝试后均返回空内容，使用默认评分兜底", MAX_RETRIES)
        result = {
            "score": 60,
            "dimensions": {
                "pronunciation": 12,
                "pause_fluency": 12,
                "grammar": 12,
                "vocabulary": 12,
                "interaction": 12,
            },
            "feedback": "AI 评分暂时不可用，请稍后重试或查看详情。",
            "strengths": ["参与了对话练习"],
            "improvements": ["建议重新评分获取详细分析"],
        }
        return ResponseData(data=result)

    # ── 解析 JSON ──
    logger.info("评分原始响应(前500字符): %s", ai_response[:500])
    text = ai_response.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        else:
            text = parts[1] if len(parts) > 1 else text
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("not a dict")
    except (json.JSONDecodeError, ValueError):
        # 若 LLM 未严格返回 JSON，尝试用平衡括号算法提取（兜底）
        brace_depth = 0
        start = -1
        json_str = ""
        for i, ch in enumerate(ai_response):
            if ch == '{':
                if start == -1:
                    start = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and start >= 0:
                    json_str = ai_response[start:i+1]
                    break
        if json_str:
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning("评分JSON解析失败，原始响应: %s", ai_response[:300])
                # 降级返回默认评分
                result = _fallback_evaluation()
                return ResponseData(data=result)
        else:
            logger.warning("评分未找到JSON，原始响应: %s", ai_response[:300])
            # 降级返回默认评分
            result = _fallback_evaluation()
            return ResponseData(data=result)

    # 规范化
    result.setdefault("score", 0)
    result.setdefault("dimensions", {})
    result.setdefault("feedback", "")
    result.setdefault("strengths", [])
    result.setdefault("improvements", [])
    # 确保各维度缺省值
    dims = result["dimensions"]
    dims.setdefault("pronunciation", 0)
    dims.setdefault("pause_fluency", 0)
    dims.setdefault("grammar", 0)
    dims.setdefault("vocabulary", 0)
    dims.setdefault("interaction", 0)

    return ResponseData(data=result)


@router.post("/tts", response_model=ResponseData)
async def text_to_speech(
    body: TTSRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """通用 TTS 合成 — 将文本转为 MP3 音频

    返回: { audio_url, audio_base64 }
    """
    if not body.text.strip():
        return ResponseData(code=1, message="文本不能为空")

    try:
        audio_bytes = await TTSService.synthesize(
            text=body.text,
            voice_type=body.voice_type,
            use_cache=True,
        )
    except Exception as e:
        logger.error("TTS 合成失败: %s", e)
        return ResponseData(code=1, message=f"TTS 合成失败: {str(e)}")

    import base64
    tts_filename = f"tts_{hashlib.md5(body.text.encode()).hexdigest()}.mp3"
    return ResponseData(data={
        "audio_url": f"/uploads/voice_chat/{tts_filename}",
        "audio_base64": base64.b64encode(audio_bytes).decode(),
    })


@router.get("/voice-chat/audio/{filename}", response_class=FileResponse)
async def get_voice_audio(filename: str):
    """获取缓存的语音对话音频文件"""
    file_path = os.path.join(AUDIO_CACHE_DIR, filename)
    if not os.path.isfile(file_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(file_path, media_type="audio/mpeg")


def _build_voice_scenario_prompt(scenario_id: str, level: str = "intermediate") -> str:
    """构建语音场景对话的 system prompt，含语音纠错分析指令"""
    scene_desc = ""
    user_role = ""

    if scenario_id:
        for s in SCENARIO_PRESETS:
            if s["id"] == scenario_id:
                scene_desc = s.get("scene_desc", "")
                user_role = s.get("user_role", "")
                break

    if not scene_desc:
        # 简洁英语口语陪练 prompt（避免过长/特殊字符导致服务端 JSON 解析异常）
        scenario_prompt = (
            "You are a professional English speaking tutor. "
            "Talk to the user in English and help them practice. "
            "Be encouraging, correct grammar mistakes gently, and keep conversations natural."
        )
        return scenario_prompt

    scenario_prompt = (
        f"You are an English speaking tutor in a roleplay scenario. "
        f"Scene: {scene_desc}. Your role: {user_role}. "
        f"Speak only in English. Be natural and helpful."
    )
    return scenario_prompt


def _extract_english_for_tts(text: str) -> str:
    """从 AI 回复中提取英文部分用于 TTS 合成

    取 ---PRONUNCIATION_ANALYSIS--- 之前的内容（情景对话部分），
    过滤掉非英文段落，保留纯英文段落
    """
    # 取分析分隔之前的内容
    separator = "---PRONUNCIATION_ANALYSIS---"
    if separator in text:
        text = text.split(separator, 1)[0].strip()

    return text


# ═══════════════════════════════════════════════════════
# WebSocket 实时语音对话（火山引擎端到端 Realtime API）
# ═══════════════════════════════════════════════════════

@router.websocket("/voice-chat/ws")
async def voice_chat_websocket(websocket: WebSocket):
    """实时语音对话 WebSocket 端点

    建立连接后自动代理到火山引擎端到端实时语音大模型 API。

    客户端查询参数:
      - scenario_id: 场景 ID（如 coffee, restaurant）
      - level:       难度 (beginner / intermediate / advanced)
      - token:       用户 JWT token

    客户端 → 服务端:
      - 二进制消息: PCM 16KHz 单声道 int16 小端序音频块
      - JSON 文本:  {type: "finish_session"} 结束本轮会话

    服务端 → 客户端（JSON 文本）:
      - {type: "session_started", dialog_id: "..."}
      - {type: "asr", text: "..."}
      - {type: "chat", text: "..."}
      - {type: "audio", data: "<base64 ogg/opus>"}   (TTS 音频块)
      - {type: "asr_ended"}
      - {type: "chat_ended"}
      - {type: "tts_ended"}
      - {type: "error", message: "..."}
      - {type: "full_result"} — 最终结果摘要
    """
    await websocket.accept()

    # 读取查询参数
    scenario_id = websocket.query_params.get("scenario_id", "")
    level = websocket.query_params.get("level", "intermediate")

    # 验证 token (从 query param 获取)
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.send_json({"type": "error", "message": "缺少 token"})
        await websocket.close(code=4001)
        return

    # 解析 user_id (简易验证)
    try:
        from app.api.deps import get_current_user_id_ws
        user_id = await get_current_user_id_ws(token)
    except Exception as e:
        logger.warning("WebSocket token 验证失败: %s", e)
        await websocket.send_json({"type": "error", "message": "token 验证失败"})
        await websocket.close(code=4001)
        return

    # 获取火山引擎配置
    settings_voice = get_settings()
    app_id = settings_voice.VOLC_REALTIME_APP_ID or settings_voice.VOLC_APP_ID
    access_key = settings_voice.VOLC_REALTIME_ACCESS_KEY or settings_voice.VOLC_TTS_ACCESS_KEY

    if not app_id or not access_key:
        err_msg = "未配置火山引擎 Realtime API 凭证"
        logger.error(err_msg)
        await websocket.send_json({"type": "error", "message": err_msg})
        await websocket.close(code=4001)
        return

    # 构建场景 system prompt
    system_prompt = _build_voice_scenario_prompt(scenario_id, level)
    if scenario_id:
        scene_name = _get_scene_name(scenario_id)
        bot_name = f"{scene_name} Assistant" if scene_name else "AI Tutor"
    else:
        bot_name = "AI Tutor"

    # ── 连接火山引擎 Realtime API ──
    from app.services.volc_realtime_service import RealtimeDialogueSession, EventId, MessageType
    session = RealtimeDialogueSession(app_id, access_key)

    try:
        await session.connect()
    except Exception as e:
        logger.error("连接火山引擎 Realtime API 失败: %s", e)
        await websocket.send_json({"type": "error", "message": f"连接语音服务失败: {str(e)}"})
        await websocket.close(code=1011)
        return

    # 收集结果
    result = {"asr_text": "", "chat_texts": [], "audio_chunks": []}
    volc_task = None  # 确保 finally 块可访问

    # ── 事件处理函数：从火山引擎接收事件并转发给客户端 ──
    async def handle_volc_events(volc_stream):
        """从火山引擎接收事件并转发给客户端"""
        logger.info("[WS] handle_volc_events 任务已启动")
        try:
            async for evt in volc_stream:
                eid = evt.get("event_id")
                js = evt.get("json") or {}
                mt = evt.get("message_type")

                if eid == EventId.ASR_INFO:
                    pass  # 首个字识别到

                elif eid == EventId.ASR_RESPONSE:
                    results = js.get("results", [])
                    text = results[0].get("text", "") if results else ""
                    result["asr_text"] += text
                    await websocket.send_json({"type": "asr", "text": text})

                elif eid == EventId.ASR_ENDED:
                    await websocket.send_json({"type": "asr_ended"})

                elif eid == EventId.CHAT_RESPONSE:
                    text = js.get("content", "")
                    result["chat_texts"].append(text)
                    await websocket.send_json({"type": "chat", "text": text})

                elif eid == EventId.CHAT_ENDED:
                    await websocket.send_json({"type": "chat_ended"})

                elif eid == EventId.TTS_SENTENCE_START:
                    tts_text = js.get("text", "")
                    await websocket.send_json({"type": "tts_start", "text": tts_text})

                elif mt == MessageType.AUDIO_RESPONSE:
                    payload = evt.get("payload")
                    if payload:
                        result["audio_chunks"].append(payload)
                        await websocket.send_json({
                            "type": "audio",
                            "data": base64.b64encode(payload).decode(),
                        })

                elif eid == EventId.TTS_ENDED:
                    await websocket.send_json({"type": "tts_ended"})

                elif mt == MessageType.ERROR:
                    err_code = evt.get("event_id", "N/A")
                    err_msg = js.get("error", js.get("message", "未知错误"))
                    logger.warning("[WS] ⚠️ 火山引擎错误: event_id=%s, %s",
                                   err_code, json.dumps(js, ensure_ascii=False)[:500])
                    await websocket.send_json({
                        "type": "error",
                        "message": f"火山引擎错误 (code={err_code}): {err_msg}",
                        "detail": js,
                    })
        except Exception as e:
            logger.warning("[WS] handle_volc_events 异常退出: %s", e)

    try:
        # 1. 启动会话 (input_mod="keep_alive" 已在 start_session 中设置)
        await session.start_session(
            system_role=system_prompt,
            bot_name=bot_name,
            speaking_style="Speak clearly in standard English. Be patient and encouraging.",
            model="1.2.1.1",
            speaker="en_female_dacey_uranus_bigtts",
        )
        logger.info("[WS] StartSession 已发送")

        # 2. 等待 SessionStarted（同步等待，确保会话就绪）
        volc_stream = session.receive_events()
        session_ready = False
        try:
            async for evt in volc_stream:
                eid = evt.get("event_id")
                mt = evt.get("message_type")
                js = evt.get("json") or {}

                if mt == MessageType.ERROR:
                    err_code = evt.get("event_id", "N/A")
                    err_msg = js.get("error", js.get("message", "未知错误"))
                    logger.error("[WS] StartSession 失败: %s", json.dumps(js, ensure_ascii=False)[:500])
                    await websocket.send_json({
                        "type": "error",
                        "message": f"会话启动失败 (code={err_code}): {err_msg}",
                    })
                    await session.close()
                    await websocket.close()
                    return

                if eid == EventId.SESSION_STARTED:
                    dialog_id = js.get("dialog_id", "")
                    await websocket.send_json({
                        "type": "session_started",
                        "dialog_id": dialog_id,
                    })
                    logger.info("[WS] 会话已创建: dialog_id=%s", dialog_id)
                    session_ready = True
                    break

                logger.debug("[WS] SessionStarted 前收到事件: event_id=%s, msg_type=%s", eid, mt)
        except asyncio.TimeoutError:
            logger.error("[WS] 等待 SessionStarted 超时")

        if not session_ready:
            await websocket.send_json({"type": "error", "message": "会话启动超时"})
            await session.close()
            await websocket.close()
            return

        # 3. 发送 SayHello，让 AI 主动发起对话
        greeting_text = _build_scene_greeting(scenario_id)
        await session.say_hello(greeting_text)
        logger.info("[WS] 已发送 SayHello: %s", greeting_text[:60])

        # 4. 启动后台事件处理任务
        #    keep_alive 模式下连接不会超时，后台任务将持续处理服务端事件
        volc_task = asyncio.create_task(handle_volc_events(volc_stream))

        # 5. 主循环：接收客户端音频并转发给火山引擎（支持多轮连续对话）
        session_active = True  # 标记当前 session 是否活跃（仅用于防重复 finish）
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive(), timeout=300)
            except asyncio.TimeoutError:
                logger.info("[WS] 客户端超时（5分钟无数据）")
                break

            if raw.get("type") == "websocket.disconnect":
                break

            if raw.get("type") == "websocket.receive":
                msg = raw["bytes"] if "bytes" in raw else raw.get("text")

                if isinstance(msg, bytes):
                    if not session.is_connected:
                        logger.warning("[WS] Volc 连接已断开，丢弃 %d bytes 音频", len(msg))
                        await websocket.send_json({
                            "type": "error",
                            "message": "语音服务连接已断开，请重新连接",
                        })
                        break
                    # 连续对话：每轮 finish_session 后 session_active 会重置，
                    # 下一轮音频到来时直接转发，火山引擎会自动处理
                    logger.info("[WS] 收到客户端音频: %d bytes (seq=%d)", len(msg), getattr(session, '_seq', 0))
                    try:
                        await session.send_audio(msg)
                        logger.info("[WS] 已转发到火山引擎: %d bytes", len(msg))
                    except Exception as send_err:
                        logger.warning("[WS] 发送音频失败: %s", send_err)
                        await websocket.send_json({
                            "type": "error",
                            "message": f"音频发送失败: {str(send_err)}。请重新连接。",
                        })
                        break

                elif isinstance(msg, str):
                    try:
                        cmd = json.loads(msg)
                        cmd_type = cmd.get("type", "")
                        if cmd_type == "finish_session":
                            if not session_active:
                                logger.info("[WS] 已标记结束，忽略重复的 finish_session")
                                continue
                            await session.finish_session()
                            session_active = False
                            logger.info("[WS] 客户端请求结束会话")
                        elif cmd_type == "reset_session":
                            # 连续对话：进入下一轮，重置 session 活跃标记
                            session_active = True
                            logger.info("[WS] 客户端请求开始新一轮对话")
                        elif cmd_type == "close":
                            break
                    except json.JSONDecodeError:
                        pass

        # 6. 发送 FinishSession（通知服务端正常结束）
        try:
            await session.finish_session()
            logger.info("[WS] FinishSession 已发送")
        except Exception:
            pass

        # 7. 等待 volc 事件处理任务完成（最多 10s）
        try:
            await asyncio.wait_for(volc_task, timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            volc_task.cancel()
            try:
                await volc_task
            except (asyncio.CancelledError, Exception):
                pass

        # 8. 发送最终结果摘要（连接可能已关闭，需要保护）
        try:
            await websocket.send_json({
                "type": "full_result",
                "asr_text": result["asr_text"],
                "chat_text": "".join(result["chat_texts"]),
                "audio_size": sum(len(c) for c in result["audio_chunks"]),
            })
        except Exception:
            logger.warning("[WS] 发送 full_result 失败，连接可能已关闭")

    except WebSocketDisconnect:
        logger.info("[WS] 客户端断开连接")
    except Exception as e:
        logger.error("[WS] 处理异常: %s", e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # 确保资源释放
        if volc_task is not None and not volc_task.done():
            volc_task.cancel()
        await session.close()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("[WS] 实时语音对话结束")


def _fallback_evaluation() -> dict:
    """降级默认评分 — 当 LLM 连续返回空内容时使用"""
    return {
        "score": 60,
        "dimensions": {
            "pronunciation": 12,
            "pause_fluency": 12,
            "grammar": 12,
            "vocabulary": 12,
            "interaction": 12,
        },
        "feedback": "AI 评分暂时不可用，请稍后重试或查看详情。",
        "strengths": ["参与了对话练习"],
        "improvements": ["建议重新评分获取详细分析"],
    }


def _get_scene_name(scenario_id: str) -> str:
    """根据场景 ID 获取中文名称"""
    for s in SCENARIO_PRESETS:
        if s["id"] == scenario_id:
            return s["name"]
    return ""


def _build_scene_greeting(scenario_id: str) -> str:
    """根据场景生成用户的初始打招呼文本，SayHello 时触发 AI 主动开口"""
    greetings = {
        "coffee": "Hello! I'd like to have a cup of coffee. What do you recommend?",
        "restaurant": "Hi! I'd like to see the menu, please.",
        "shopping": "Hello! I'm just looking around. Could you show me some T-shirts?",
        "travel": "Excuse me, could you tell me how to get to the nearest museum?",
        "hotel": "Hi, I have a reservation. I'd like to check in, please.",
        "airport": "Hello, where is the check-in counter for international flights?",
        "interview": "Good morning, thank you for giving me this opportunity. I'm ready for the interview.",
        "hospital": "Hello doctor, I'm not feeling well. Could you help me?",
        "library": "Hello, I'd like to borrow a book. How does it work?",
        "friends": "Hi there! Nice to meet you. My name is Alex.",
    }
    return greetings.get(scenario_id, "Hello! I'm ready to start the conversation.")
