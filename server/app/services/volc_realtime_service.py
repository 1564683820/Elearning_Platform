"""
火山引擎豆包端到端实时语音大模型 Realtime API 服务

协议: WebSocket + 自定义二进制帧
文档: https://www.volcengine.com/docs/6561/1594356
WebSocket: wss://openspeech.bytedance.com/api/v3/realtime/dialogue

支持的客户端事件:
  1      StartConnection      声明确认连接 (通常握手后自动完成)
  2      FinishConnection     断开 WebSocket 连接
  100    StartSession         启动一个会话（核心事件，带人设/场景配置）
  102    FinishSession        结束当前会话（可复用连接）
  200    TaskRequest          上传音频二进制 (Message Type = 0b0010)
  300    SayHello             客户端提交打招呼文本
  500    ChatTTSText          指定文本请求音频合成

服务端事件:
  50     ConnectionStarted    连接建立成功
  150    SessionStarted       会话启动成功，返回 dialog_id
  350    TTSSentenceStart     合成音频起始，含 tts_type 和 text
  352    TTSResponse          返回音频二进制 (Message Type = 0b1011)
  359    TTSEnded             TTS 结束
  450    ASRInfo              识别出音频流首字
  451    ASRResponse          用户说话的文本内容
  459    ASREnded             模型认为用户说话结束
  550    ChatResponse         模型回复的文本内容
  559    ChatEnded            模型回复文本结束
"""

import asyncio
import json
import struct
import uuid
import logging
from typing import Optional, Callable, Awaitable
from enum import IntEnum

try:
    from websockets.exceptions import ConnectionClosed as WebSocketClosed
except ImportError:
    WebSocketClosed = Exception  # fallback

logger = logging.getLogger(__name__)

# ─── 二进制协议常量 ───────────────────────────────────
# Byte 0
PROTOCOL_VERSION = 0b0001  # 高 4 位
HEADER_SIZE = 0b0001       # 低 4 位（表示基本头长度为 1*4=4 字节）
HEADER_BYTE0 = (PROTOCOL_VERSION << 4) | HEADER_SIZE  # 0x11

# Byte 1 - Message Type (高 4 位)
class MessageType(IntEnum):
    CLIENT_TEXT    = 0b0001  # 客户端文本事件
    AUDIO_ONLY     = 0b0010  # 客户端音频数据
    SERVER_TEXT    = 0b1001  # 服务端文本事件
    AUDIO_RESPONSE = 0b1011  # 服务端音频数据
    ERROR          = 0b1111  # 错误信息

# Byte 1 - Specific Flags (低 4 位)
# 官方协议: https://www.volcengine.com/docs/6561/1594356#f3f2449c
#   bit0-1: SEQUENCE 模式 (0b00=无, 0b01=正数序号, 0b10=末包无序号, 0b11=末包负数)
#   bit2:   EVENT    (0b0100=携带event_id)
#   bit3:   reserved (Error帧时为0b1111)
# 注意: connect_id/session_id 不出现在 flags 中，而是由事件类型决定
class FlagBits(IntEnum):
    SEQUENCE    = 0b0001  # bit0: 普通序号（正数递增）
    EVENT       = 0b0100  # bit2: 携带 event_id

# Byte 2 - 序列化方式
class Serialization(IntEnum):
    RAW  = 0b0000  # 裸音频
    JSON = 0b0001  # JSON 文本

# Byte 2 - 压缩方式
class Compression(IntEnum):
    NONE = 0b0000
    GZIP = 0b0001

# 事件 ID
class EventId(IntEnum):
    # 客户端事件
    START_CONNECTION    = 1
    FINISH_CONNECTION   = 2
    START_SESSION       = 100
    FINISH_SESSION      = 102
    TASK_REQUEST        = 200
    SAY_HELLO           = 300
    CHAT_TTS_TEXT       = 500
    # 服务端事件
    CONNECTION_STARTED  = 50
    SESSION_STARTED     = 150
    TTS_SENTENCE_START  = 350
    TTS_RESPONSE        = 352
    TTS_ENDED           = 359
    ASR_INFO            = 450
    ASR_RESPONSE        = 451
    ASR_ENDED           = 459
    CHAT_RESPONSE       = 550
    CHAT_ENDED          = 559

# 固定认证参数
VOLC_REALTIME_RESOURCE_ID = "volc.speech.dialog"
VOLC_REALTIME_APP_KEY = "PlgvMymc7f3tQnJ6"
VOLC_REALTIME_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"

# ─── 协议编码/解码工具 ───────────────────────────────

def _build_header(
    msg_type: int,
    flags: int = 0,
    serialization: int = Serialization.RAW,
    compression: int = Compression.NONE,
) -> bytes:
    """构建 4 字节基本头部"""
    return struct.pack(
        "BBBB",
        HEADER_BYTE0,
        (msg_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,  # reserved
    )


def _build_optional_fields(
    flags: int,
    event_id: Optional[int] = None,
    connect_id: Optional[str] = None,
    session_id: Optional[str] = None,
    sequence: Optional[int] = None,
) -> bytes:
    """构建可选字段（顺序固定：sequence? → event → connect_id/session_id?）

    官方协议: https://www.volcengine.com/docs/6561/1594356#a1bdc86f
    - sequence:   4 字节有符号大端（flags bit0 控制）
    - event:      4 字节无符号大端（flags bit2=0x04 控制）
    - connect_id: 仅 Connect 类事件(1,2)携带，4B长度前缀 + UTF-8字符串
    - session_id: 仅 Session 类事件(100,102,300…)携带，4B长度前缀 + UTF-8字符串

    connect_id/session_id 的携带不由 flags 控制，而是由事件类型决定。
    调用方传入哪个就编码哪个。
    """
    parts = []
    if flags & FlagBits.SEQUENCE and sequence is not None:
        parts.append(struct.pack("!i", sequence))
    if flags & FlagBits.EVENT and event_id is not None:
        parts.append(struct.pack("!I", event_id))
    # connect_id / session_id 始终编码（不受 flags 控制）
    if connect_id:
        cid_bytes = connect_id.encode("utf-8")
        parts.append(struct.pack("!I", len(cid_bytes)))
        parts.append(cid_bytes)
    if session_id:
        sid_bytes = session_id.encode("utf-8")
        parts.append(struct.pack("!I", len(sid_bytes)))
        parts.append(sid_bytes)
    return b"".join(parts)


def build_text_frame(event_id: int, payload: dict,
                     connect_id: Optional[str] = None,
                     session_id: Optional[str] = None) -> bytes:
    """构建客户端文本事件的完整二进制帧

    官方协议帧结构:
      [header 4B] [event 4B] [session_id/connect_id] [payload_size 4B] [payload]

    - 所有 Full-client 文本帧都携带 EVENT 标志 (0x04)
    - Connect 事件(1,2): 携带 connect_id（4B长度 + UTF-8字符串）
    - Session 事件(100,102,300…): 携带 session_id（4B长度 + UUID字符串）

    Args:
        event_id: 事件 ID
        payload:  JSON payload
        connect_id: 连接 UUID（仅 Connect 事件）
        session_id: 会话 UUID（仅 Session 事件）

    Returns:
        完整的二进制帧
    """
    flags = FlagBits.EVENT  # 文本帧必须携带 event (0x04)
    header = _build_header(
        MessageType.CLIENT_TEXT,
        flags=flags,
        serialization=Serialization.JSON,
    )
    optional = _build_optional_fields(
        flags, event_id=event_id,
        connect_id=connect_id, session_id=session_id,
    )
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    payload_size = struct.pack("!I", len(payload_bytes))
    return header + optional + payload_size + payload_bytes


def build_audio_frame(audio_data: bytes, session_id: str) -> bytes:
    """构建音频数据的二进制帧

    V3 协议音频帧结构（TaskRequest 事件）:
      [header 4B] [event 4B=200] [session_id_len 4B] [session_id N] [audio_size 4B] [audio_data]

    - Message type = AUDIO_ONLY (0b0010)
    - Flags = EVENT (0b0100)，携带 event_id=TaskRequest(200)
    - Serialization = RAW (0b0000)，音频数据不序列化
    - 包含 session_id（Session 类事件必须携带）
    - 不携带 SEQUENCE，序列号由服务端自动分配

    Args:
        audio_data: PCM 音频数据
        session_id: 当前会话 ID

    Returns:
        完整的二进制帧
    """
    flags = FlagBits.EVENT
    header = _build_header(
        MessageType.AUDIO_ONLY,
        flags=flags,
        serialization=Serialization.RAW,
    )
    optional = _build_optional_fields(
        flags,
        event_id=EventId.TASK_REQUEST,
        session_id=session_id,
    )
    payload_size = struct.pack("!I", len(audio_data))

    return header + optional + payload_size + audio_data


def parse_server_frame(data: bytes) -> dict:
    """解析服务端返回的二进制帧

    官方协议服务端帧结构:
      正常帧: [header 4B] [event 4B] [session_id_len 4B] [session_id N] [payload_size 4B] [payload]
      错误帧: [header 4B] [error_code 4B] [payload_size 4B] [payload]  (无 session_id)

    注意: session_id 在服务端帧中始终紧随 event 出现，不受 flags 控制。

    Returns:
        {
            "message_type": int,
            "event_id": int or None,
            "connect_id": str or None,
            "session_id": str or None,
            "payload": bytes or str,
        }
    """
    if len(data) < 4:
        raise ValueError(f"帧数据过短: {len(data)} bytes")

    byte0, byte1, byte2, byte3 = struct.unpack("BBBB", data[:4])

    msg_type = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F
    serialization = (byte2 >> 4) & 0x0F
    compression = byte2 & 0x0F
    is_error = (msg_type == MessageType.ERROR)

    offset = 4
    result: dict = {"message_type": msg_type, "event_id": None,
                    "connect_id": None, "session_id": None}

    # 服务端帧: header 后固定 4 字节 event_id（或错误码）
    if len(data) < offset + 4:
        return result
    result["event_id"] = struct.unpack("!I", data[offset:offset+4])[0]
    offset += 4

    # 非错误帧: event 后固定携带 session_id (4B长度 + N字节UUID字符串)
    if not is_error and offset + 4 <= len(data):
        sid_size = struct.unpack("!I", data[offset:offset+4])[0]
        offset += 4
        if sid_size > 0 and offset + sid_size <= len(data):
            try:
                result["session_id"] = data[offset:offset+sid_size].decode("utf-8")
            except UnicodeDecodeError:
                result["session_id"] = data[offset:offset+sid_size].hex()
            offset += sid_size

    # 解析 payload 大小和内容
    if len(data) < offset + 4:
        return result
    payload_size = struct.unpack("!I", data[offset:offset+4])[0]
    offset += 4

    if len(data) < offset + payload_size:
        logger.warning("payload 不完整: need=%d, have=%d", payload_size, len(data) - offset)
        return result

    payload_raw = data[offset:offset+payload_size]

    if compression == Compression.GZIP:
        import gzip
        payload_raw = gzip.decompress(payload_raw)

    if serialization == Serialization.JSON:
        try:
            result["json"] = json.loads(payload_raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("JSON 解析失败: %s", e)
            result["text"] = payload_raw.decode("utf-8", errors="replace")
    else:
        result["payload"] = payload_raw

    return result


# ─── Realtime 对话管理器 ─────────────────────────────

class RealtimeDialogueSession:
    """管理一个 Volcengine Realtime API 会话

    使用方式:
        session = RealtimeDialogueSession(app_id, access_key)
        async with session:
            # await session.start_session(...)
            # await session.send_audio(chunk)
            # async for event in session.receive_events():
            #     ...
    """

    def __init__(
        self,
        app_id: str,
        access_key: str,
        connect_id: Optional[str] = None,
    ):
        self.app_id = app_id
        self.access_key = access_key
        self.connect_id = connect_id or str(uuid.uuid4())
        self.session_id: Optional[str] = None
        self._ws = None  # websockets.WebSocketClientProtocol
        self._seq = 0
        self._recv_buffer = bytearray()
        self._closed = False  # 标记 volc 连接是否已断开

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    @property
    def is_connected(self) -> bool:
        """检查火山引擎 WebSocket 连接是否活跃"""
        return (
            self._ws is not None
            and not self._closed
            and self._ws.close_code is None
        )

    async def connect(self):
        """建立 WebSocket 连接到火山引擎

        V3 协议流程:
          1. WebSocket 握手（携带 HTTP 认证头）
          2. 客户端发送 StartConnection (event_id=1)，声明 connect_id
          3. 服务端返回 ConnectionStarted (event_id=50)，确认连接就绪
          4. 之后才可发送 StartSession (event_id=100) 启动会话

        若跳过步骤 2-3 直接发送 StartSession，服务端状态机错位，
        会导致后续 JSON 解析异常 (错误码 45000001)。
        """
        import websockets

        headers = [
            ("X-Api-App-ID", self.app_id),
            ("X-Api-Access-Key", self.access_key),
            ("X-Api-Resource-Id", VOLC_REALTIME_RESOURCE_ID),
            ("X-Api-App-Key", VOLC_REALTIME_APP_KEY),
            ("X-Api-Connect-Id", self.connect_id),
        ]

        logger.info("[Realtime] 正在连接: app_id=%s, connect_id=%s", self.app_id, self.connect_id)
        self._ws = await websockets.connect(
            VOLC_REALTIME_URL,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10MB
        )
        self._closed = False
        self._seq = 0  # 重连时重置序列号，避免与服务端 autoAssignedSequence 不匹配
        self._recv_buffer = bytearray()
        logger.info("[Realtime] WebSocket 握手成功，开始发送 StartConnection")

        # V3 协议: 握手后必须先发送 StartConnection，等待 ConnectionStarted
        await self._start_connection()

    async def _start_connection(self):
        """发送 StartConnection 事件并等待 ConnectionStarted 响应

        StartConnection (event_id=1) 用于确认连接。
        注意: connect_id 已通过 HTTP header (X-Api-Connect-Id) 传递，
        帧内不再重复携带，否则服务端会将 connect_id_len 误认为 payload_size，
        导致 "declared body size does not match actual body size" 错误。
        """
        # connect_id 不在帧内携带（已通过 HTTP header 传递）
        frame = build_text_frame(
            EventId.START_CONNECTION,
            {},  # 空 payload
        )
        logger.info("[Realtime] 发送 StartConnection: connect_id=%s, frame_len=%d",
                     self.connect_id, len(frame))
        await self._ws.send(frame)

        # 等待服务端返回 ConnectionStarted (event_id=50)
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("[Realtime] 等待 ConnectionStarted 超时 (10s)")
                raise TimeoutError("等待 ConnectionStarted 超时")
            except WebSocketClosed as e:
                logger.error("[Realtime] 等待 ConnectionStarted 时连接关闭: code=%s, reason=%s",
                             e.code, e.reason)
                raise

            if not isinstance(raw, bytes):
                logger.error("[Realtime] 连接阶段收到非二进制数据: %s", type(raw).__name__)
                raise RuntimeError(f"连接阶段收到非二进制数据: {type(raw).__name__}")

            logger.info("[Realtime] 连接阶段收到 %d bytes [前32字节: %s]",
                        len(raw), raw[:32].hex()[:64])
            events = self._parse_server_stream(raw)
            for evt in events:
                eid = evt.get("event_id")
                mt = evt.get("message_type")
                logger.info("[Realtime] 连接阶段事件: event_id=%s, msg_type=%s", eid, mt)

                if mt == MessageType.ERROR:
                    js = evt.get("json", {})
                    err_msg = js.get("error", js.get("message", "未知错误"))
                    logger.error("[Realtime] StartConnection 失败: %s",
                                 json.dumps(js, ensure_ascii=False)[:500])
                    raise RuntimeError(f"StartConnection 失败: {err_msg}")

                if eid == EventId.CONNECTION_STARTED:
                    # StartConnection 占用了 seq=1，同步本地计数器
                    self._seq = 1
                    logger.info("[Realtime] 收到 ConnectionStarted，连接已确认 (seq=%d)", self._seq)
                    return

        logger.info("[Realtime] 连接已确认，可以开始 StartSession")

    async def start_session(self, system_role: str = "",
                            bot_name: str = "AI Tutor",
                            speaking_style: str = "",
                            dialog_id: str = "",
                            strict_audit: bool = False,
                            audit_response: str = "",
                            model: str = "1.2.1.1",
                            speaker: str = "en_female_dacey_uranus_bigtts"):
        """启动对话会话

        Args:
            system_role:   场景人设/ system prompt（英语学习场景描述）
            bot_name:      AI 角色名
            speaking_style: 对话风格描述
            dialog_id:     加载历史对话 ID（空=新对话）
            strict_audit:  安全审核等级
            audit_response: 命中审核后的自定义回复
            model:         端到端模型版本，1.2.1.1=O2.0, 2.2.0.0=SC2.0
            speaker:       TTS 发音人（英语美式女声）
        """
        extra = {
            "strict_audit": strict_audit,
            "model": model,
            # keep_alive: 麦克风静音时保持连接不超时，服务端通过 VAD 自动检测用户说话
            "input_mod": "keep_alive",
        }
        if audit_response:
            extra["audit_response"] = audit_response
        payload = {
            "dialog": {
                "bot_name": bot_name,
                "system_role": system_role,
                "speaking_style": speaking_style,
                "dialog_id": dialog_id,
                "extra": extra,
            },
            "asr": {
                "extra": {
                    "end_smooth_window_ms": 1000,  # 用户停止说话后 1s 判定为结束
                }
            },
            "tts": {
                "speaker": speaker,
                "audio_config": {
                    "format": "pcm_s16le",  # PCM 16bit 小端序
                    "sample_rate": 24000,
                    "channel": 1,
                }
            }
        }
        # 每次启动新会话时递增序列号（StartConnection 已占用 seq=1）
        # StartSession 是无序列号的文本帧 → 服务端自动分配 seq=2
        self._seq += 1
        self.session_id = str(uuid.uuid4())
        # 预先序列化 payload 以获取精确大小用于日志
        payload_json = json.dumps(payload, ensure_ascii=False)
        logger.info("[Realtime] StartSession payload: %d chars, system_role=%d chars, speaking_style=%d chars",
                     len(payload_json), len(system_role), len(speaking_style))
        frame = build_text_frame(
            EventId.START_SESSION, payload,
            session_id=self.session_id,
        )
        logger.info("[Realtime] 发送 StartSession: session_id=%s, frame_len=%d",
                     self.session_id, len(frame))
        logger.debug("[Realtime] StartSession hex (%d bytes): %s", len(frame), frame[:60].hex())
        await self._ws.send(frame)
        logger.info("[Realtime] 已发送 StartSession (服务端自动分配 seq=%d)", self._seq)

    async def send_audio(self, pcm_data: bytes):
        """发送 PCM 音频数据

        V3 协议: 音频帧使用 EVENT flag (TaskRequest=200) + session_id，
        不携带 SEQUENCE，序列号由服务端自动分配。

        Args:
            pcm_data: PCM 16KHz 单声道 int16 小端序
        """
        if not self.session_id:
            logger.warning("[Realtime] send_audio: session_id 为空，跳过")
            return
        frame = build_audio_frame(pcm_data, self.session_id)
        await self._ws.send(frame)

    async def finish_session(self):
        """结束当前会话（连接可复用）

        根据火山引擎 V3 协议，必须设置 audio_flag=1 告诉服务端用户语音流已结束，
        否则服务端会持续等待音频，不会触发 ASR 最终识别和 Chat 回复。
        """
        payload = {}
        if self.session_id:
            payload["extra"] = {"audio_flag": 1}
        # FinishSession (102)是Session事件 → 只携带 session_id
        frame = build_text_frame(
            EventId.FINISH_SESSION, payload,
            session_id=self.session_id,
        )
        await self._ws.send(frame)
        logger.info("[Realtime] 已发送 FinishSession")

    async def say_hello(self, text: str = ""):
        """发送打招呼文本，触发 AI 主动回复（SayHello 事件）

        SayHello 模拟用户说了一句文本，AI 大模型收到后会解析并生成回复。
        用于开场时让 AI 主动发起对话。

        注意: SayHello 是无序列号的文本帧，服务端会在统一命名空间中自动分配序号。
        这里递增 _seq 以与服务端 autoAssignedSequence 保持同步。

        Args:
            text: 打招呼文本，如 "Hello! I'd like to order a coffee."
        """
        # 注意：文档要求 payload 字段名为 "content" 而非 "text"
        payload = {"content": text} if text else {"content": ""}
        # SayHello (300)是Session事件 → 只携带 session_id
        frame = build_text_frame(
            EventId.SAY_HELLO, payload,
            session_id=self.session_id,
        )
        await self._ws.send(frame)
        # SayHello 无显式序列号，服务端自动分配 seq，这里同步计数
        self._seq += 1
        logger.info("[Realtime] 已发送 SayHello: %s (服务端自动分配 seq=%d)", text[:60], self._seq)

    async def close(self):
        """关闭 WebSocket 连接"""
        self._closed = True
        if self._ws and self._ws.close_code is None:
            try:
                # FinishConnection(2)是Connect事件 → connect_id 已通过 HTTP header 传递
                frame = build_text_frame(
                    EventId.FINISH_CONNECTION, {},
                )
                await self._ws.send(frame)
            except Exception:
                pass
            try:
                await self._ws.close()
            except Exception:
                pass
            logger.info("[Realtime] 连接已关闭")

    async def receive_events(self):
        """接收并解析服务端事件（异步生成器）

        注意：每次调用此生成器时，会先尝试从内部缓存 _recv_buffer 中提取完整帧，
        然后再从 WebSocket 读取新数据。这样可以避免多个消费者之间的数据丢失。

        Yields:
            dict: 解析后的事件字典
        """
        logger.debug("[Realtime] receive_events 开始迭代, _recv_buffer=%d, _ws.close_code=%s",
                     len(self._recv_buffer), self._ws.close_code if self._ws else "NO_WS")
        while self._ws and self._ws.close_code is None:
            # 先尝试从已有缓存提取完整帧
            if self._recv_buffer:
                events = self._parse_server_stream(b"")
                for evt in events:
                    yield evt

            # 再从 WebSocket 读取新数据
            try:
                raw = await self._ws.recv()
            except WebSocketClosed as e:
                logger.info("[Realtime] 服务端连接已关闭: code=%s, reason=%s", e.code, e.reason)
                break
            except asyncio.IncompleteReadError as e:
                logger.info("[Realtime] 连接意外断开 (IncompleteRead): %s", e)
                break
            except Exception as e:
                logger.info("[Realtime] 接收结束: type=%s, msg=%s", type(e).__name__, e)
                break

            if isinstance(raw, bytes):
                logger.info("[Realtime] 收到 %d bytes [前32字节 hex: %s]",
                            len(raw), raw[:32].hex()[:64])
                events = self._parse_server_stream(raw)
                logger.info("[Realtime] _parse_server_stream 返回 %d 个事件", len(events))
                for evt in events:
                    logger.info("[Realtime] yield 事件: event_id=%s, msg_type=%s",
                                evt.get("event_id"), evt.get("message_type"))
                    yield evt
            elif raw is None:
                logger.info("[Realtime] 收到 EOF, 服务端已关闭连接")
                break
            else:
                logger.info("[Realtime] 收到非二进制数据: type=%s, 内容: %s",
                            type(raw).__name__, str(raw)[:200])
                # 收到非 bytes 数据通常表示协议异常，退出循环
                break
        exit_reason = ""
        if self._ws is None:
            exit_reason = "self._ws=None (连接已置空)"
        elif self._ws.close_code is not None:
            exit_reason = f"close_code={self._ws.close_code}, close_reason={self._ws.close_reason}"
        logger.info("[Realtime] receive_events 退出迭代, 原因: %s", exit_reason)
        self._closed = True

    def _parse_server_stream(self, data: bytes) -> list[dict]:
        """从字节流中解析出完整的帧列表

        服务端帧格式:
          正常帧: [4B header][4B event][4B sid_len][N sid][4B payload_size][payload]
          错误帧: [4B header][4B error_code][4B payload_size][payload]  (无 session_id)

        parse_server_frame 负责内容解析；本方法负责从缓存中切出完整帧。
        """
        self._recv_buffer.extend(data)
        events = []

        while True:
            buf = self._recv_buffer
            if len(buf) < 4:
                break

            byte1 = buf[1]
            flags = byte1 & 0x0F
            msg_type = (byte1 >> 4) & 0x0F
            is_error = (msg_type == MessageType.ERROR)

            # header(4) + event/error_code(4)
            offset = 8
            if len(buf) < offset:
                break

            # 非错误帧: 读取 session_id
            if not is_error:
                if len(buf) < offset + 4:
                    break
                sid_size = struct.unpack("!I", buf[offset:offset+4])[0]
                offset += 4 + sid_size

            # payload_size(4) + payload
            if len(buf) < offset + 4:
                break
            payload_size = struct.unpack("!I", buf[offset:offset+4])[0]
            frame_total = offset + 4 + payload_size

            if len(buf) < frame_total:
                break  # 等待更多数据

            frame_bytes = bytes(buf[:frame_total])
            del self._recv_buffer[:frame_total]

            evt = parse_server_frame(frame_bytes)
            events.append(evt)

            # 更新 session_id
            if evt.get("session_id"):
                self.session_id = evt["session_id"]

            # 记录关键事件日志
            self._log_event(evt)

        return events

    def _log_event(self, evt: dict):
        """记录关键事件的日志"""
        eid = evt.get("event_id")
        if eid == EventId.CONNECTION_STARTED:
            logger.info("[Realtime] 连接已确认")
        elif eid == EventId.SESSION_STARTED:
            sid = evt.get("json", {}).get("dialog_id", "")
            logger.info("[Realtime] 会话已启动: dialog_id=%s", sid)
        elif eid == EventId.ASR_RESPONSE:
            results = evt.get("json", {}).get("results", [])
            text = results[0].get("text", "") if results else ""
            logger.info("[Realtime] ASR: %s", text[:80])
        elif eid == EventId.CHAT_RESPONSE:
            text = evt.get("json", {}).get("content", "")
            logger.info("[Realtime] Chat: %s", text[:80])
        elif eid == EventId.ASR_ENDED:
            logger.info("[Realtime] ASR 结束")
        elif eid == EventId.CHAT_ENDED:
            logger.info("[Realtime] Chat 结束")
        elif eid == EventId.TTS_ENDED:
            logger.info("[Realtime] TTS 结束")
        elif evt.get("message_type") == MessageType.ERROR:
            evt_json = evt.get("json") or evt.get("text", "")
            logger.warning("[Realtime] ⚠️ 错误事件 | event_id=%s | JSON=%s | raw_payload_hex=%s",
                           evt.get("event_id"),
                           json.dumps(evt_json, ensure_ascii=False)[:500] if isinstance(evt_json, dict) else str(evt_json)[:500],
                           evt.get("payload", b"")[:128].hex() if isinstance(evt.get("payload"), bytes) else "N/A")


# ─── 便捷调用函数 ────────────────────────────────────

async def realtime_voice_chat(
    pcm_audio: bytes,
    system_prompt: str = "",
    bot_name: str = "AI Tutor",
    speaking_style: str = "",
    app_id: str = "",
    access_key: str = "",
    timeout: float = 30.0,
) -> dict:
    """一次完整的端到端语音对话调用

    Args:
        pcm_audio:      PCM 16KHz 单声道 int16 小端序音频
        system_prompt:  场景人设/System Prompt
        bot_name:       AI 角色名
        speaking_style: 说话风格
        app_id:         火山引擎 APP ID
        access_key:     火山引擎 Access Key
        timeout:        超时秒数

    Returns:
        {
            "asr_text": str,          # 语音识别文本
            "chat_texts": [str],      # AI 回复文本（可能有多个片段）
            "audio_chunks": [bytes],  # TTS 音频块列表（OGG/Opus）
            "dialog_id": str,         # 对话 ID
        }
    """
    result: dict = {
        "asr_text": "",
        "chat_texts": [],
        "audio_chunks": [],
        "dialog_id": "",
    }

    session = RealtimeDialogueSession(app_id, access_key)
    try:
        await session.connect()
    except Exception as e:
        raise ConnectionError(f"连接火山引擎 Realtime API 失败: {e}") from e

    try:
        # 1. 启动会话（设置场景）
        await session.start_session(
            system_role=system_prompt,
            bot_name=bot_name,
            speaking_style=speaking_style,
            model="1.2.1.1",
            speaker="en_female_dacey_uranus_bigtts",
        )

        # 2. 等待 SessionStarted
        try:
            async for evt in session.receive_events():
                if evt.get("event_id") == EventId.SESSION_STARTED:
                    result["dialog_id"] = evt.get("json", {}).get("dialog_id", "")
                    break
        except Exception as e:
            logger.warning("[Realtime] 接收 SessionStarted 异常: %s", e)

        # 3. 发送音频（按 4KB 分块发送，模拟流式）
        chunk_size = 4096
        for i in range(0, len(pcm_audio), chunk_size):
            await session.send_audio(pcm_audio[i:i+chunk_size])

        # 4. 发送 FinishSession 表示用户说完
        await session.finish_session()

        # 5. 收集服务端响应
        async def collect():
            async for evt in session.receive_events():
                eid = evt.get("event_id")
                js = evt.get("json") or {}

                if eid == EventId.ASR_RESPONSE:
                    results = js.get("results", [])
                    result["asr_text"] += results[0].get("text", "") if results else ""
                elif eid == EventId.CHAT_RESPONSE:
                    result["chat_texts"].append(js.get("content", ""))
                elif evt.get("message_type") == MessageType.AUDIO_RESPONSE:
                    payload = evt.get("payload")
                    if payload:
                        result["audio_chunks"].append(payload)
                elif eid == EventId.CHAT_ENDED:
                    break

        await asyncio.wait_for(collect(), timeout=timeout)

    except asyncio.TimeoutError:
        logger.warning("[Realtime] 等待响应超时")
    except Exception as e:
        logger.error("[Realtime] 对话出错: %s", e)
        raise
    finally:
        await session.close()

    result["chat_text"] = "".join(result["chat_texts"])
    return result
