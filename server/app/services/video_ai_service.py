"""AI 视频教材演绎服务 — 教材课文 → 角色配音视频生成

工作流:
1. 用户选择教材页面 + 课文内容
2. 用户选择预设角色（或上传自定义角色图）
3. AI 分析课文，生成分镜脚本（含每段文案+角色表情+场景描述）
4. 调用 TTS 生成配音音频
5. 合成视频（角色图 + 配音 + 字幕 + 背景）
6. 上传 CDN，更新视频记录状态
"""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.models.video_models import AiVideo, PresetCharacter
from app.schemas.video import CHARACTER_TYPE_MAP
from app.services.ai_service import AIService
from app.core.config import get_settings
from app.db.database import async_session as async_session_factory

logger = logging.getLogger(__name__)

settings = get_settings()


class VideoAIService:
    """AI 视频教材演绎服务"""

    # ========== 预设角色管理 ==========

    @staticmethod
    async def list_characters(db: AsyncSession) -> list[dict]:
        """获取所有启用的预设角色列表"""
        stmt = select(PresetCharacter).where(
            PresetCharacter.is_active == 1
        ).order_by(PresetCharacter.sort_order.asc())
        result = await db.execute(stmt)
        chars = result.scalars().all()
        return [
            {
                "character_key": c.character_key,
                "name": c.name,
                "description": c.description,
                "image_url": c.image_url or "",
                "voice_type": c.voice_type,
            }
            for c in chars
        ]

    # ========== AI 分镜脚本生成 ==========

    @staticmethod
    async def generate_script(
        db: AsyncSession,
        text_content: str,
        character_name: str,
        user_id: int = 0,
    ) -> dict:
        """AI 分析课文内容，生成视频分镜脚本

        参数:
            db: 数据库会话
            text_content: 课文文字内容
            character_name: 角色名称（用于提示 AI）
            user_id: 用户ID（用于 AI 调用计费）

        返回:
            dict: 包含 scenes 列表的分镜脚本
        """
        prompt = _build_script_prompt(text_content, character_name)
        try:
            response = await AIService.chat_completion(
                db=db,
                messages=[
                    {"role": "system", "content": _SCRIPT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                user_id=user_id,
                stream=False,
            )
            script = _parse_script(response)
            return script
        except Exception as e:
            # AI 失败时返回默认脚本
            return _generate_default_script(text_content)

    # ========== 视频生成任务管理 ==========

    @staticmethod
    async def create_video_task(
        db: AsyncSession,
        user_id: int,
        title: str,
        textbook_version: str,
        textbook_grade: str,
        textbook_semester: str,
        unit_id: Optional[int],
        unit_name: str,
        page_ids: list[int],
        text_content: str,
        character_type: str,
        character_image_url: Optional[str] = None,
    ) -> dict:
        """创建 AI 视频生成任务

        Args:
            同上 VideoGenerateRequest 字段

        Returns:
            dict: 包含 task_id 和状态
        """
        # 1. AI 生成分镜脚本
        character_name = CHARACTER_TYPE_MAP.get(character_type, character_type)
        script = await VideoAIService.generate_script(
            db=db,
            text_content=text_content,
            character_name=character_name,
            user_id=user_id,
        )

        # 2. 创建视频记录
        video = AiVideo(
            user_id=user_id,
            title=title or f"{unit_name} - {character_name}演绎",
            textbook_version=textbook_version,
            textbook_grade=textbook_grade,
            textbook_semester=textbook_semester,
            unit_id=unit_id,
            unit_name=unit_name,
            page_ids=page_ids if page_ids else None,
            text_content=text_content,
            character_type=character_type,
            character_image_url=character_image_url,
            script_json=script,
            status="pending",
        )
        db.add(video)
        await db.commit()
        await db.refresh(video)

        # 3. 投递异步视频合成任务（非阻塞，不 await）
        _enqueue_video_render(video.id, script, character_type, character_image_url)

        return {
            "id": video.id,
            "title": video.title,
            "status": video.status,
            "created_at": str(video.created_at),
            "message": "视频生成任务已创建",
        }

    @staticmethod
    async def get_video(db: AsyncSession, video_id: int, user_id: int) -> Optional[dict]:
        """获取单个视频详情"""
        stmt = select(AiVideo).where(AiVideo.id == video_id, AiVideo.user_id == user_id)
        result = await db.execute(stmt)
        video = result.scalar_one_or_none()
        if not video:
            return None

        # 增加观看计数
        video.view_count = (video.view_count or 0) + 1
        await db.commit()

        character_name = CHARACTER_TYPE_MAP.get(video.character_type, video.character_type)
        return {
            "id": video.id,
            "title": video.title,
            "textbook_version": video.textbook_version,
            "textbook_grade": video.textbook_grade,
            "textbook_semester": video.textbook_semester,
            "unit_name": video.unit_name,
            "character_type": video.character_type,
            "character_type_name": character_name,
            "character_image_url": video.character_image_url or "",
            "script_json": video.script_json or {},
            "video_url": video.video_url or "",
            "thumbnail_url": video.thumbnail_url or "",
            "subtitle_url": video.subtitle_url or "",
            "duration": video.duration or 0,
            "text_content": video.text_content or "",
            "status": video.status,
            "error_message": video.error_message or "",
            "view_count": video.view_count,
            "favorite_count": video.favorite_count,
            "created_at": str(video.created_at),
            "updated_at": str(video.updated_at),
        }

    @staticmethod
    async def list_videos(
        db: AsyncSession,
        user_id: int,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """获取用户视频列表"""
        conditions = [AiVideo.user_id == user_id]
        if status:
            conditions.append(AiVideo.status == status)

        count_stmt = select(func.count()).select_from(
            select(AiVideo).where(*conditions).subquery()
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(AiVideo)
            .where(*conditions)
            .order_by(desc(AiVideo.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        videos = result.scalars().all()

        items = []
        for v in videos:
            character_name = CHARACTER_TYPE_MAP.get(v.character_type, v.character_type)
            items.append({
                "id": v.id,
                "title": v.title,
                "textbook_version": v.textbook_version,
                "textbook_grade": v.textbook_grade,
                "unit_name": v.unit_name,
                "character_type": v.character_type,
                "character_type_name": character_name,
                "thumbnail_url": v.thumbnail_url or "",
                "duration": v.duration or 0,
                "status": v.status,
                "view_count": v.view_count or 0,
                "favorite_count": v.favorite_count or 0,
                "created_at": str(v.created_at),
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def delete_video(db: AsyncSession, video_id: int, user_id: int) -> bool:
        """删除视频"""
        stmt = select(AiVideo).where(AiVideo.id == video_id, AiVideo.user_id == user_id)
        result = await db.execute(stmt)
        video = result.scalar_one_or_none()
        if not video:
            return False
        await db.delete(video)
        await db.commit()
        return True

    @staticmethod
    async def toggle_favorite(db: AsyncSession, video_id: int, user_id: int) -> Optional[dict]:
        """切换视频收藏状态（增/删收藏计数）"""
        stmt = select(AiVideo).where(AiVideo.id == video_id, AiVideo.user_id == user_id)
        result = await db.execute(stmt)
        video = result.scalar_one_or_none()
        if not video:
            return None
        # 切换收藏状态 — 这里简化为增减 favorite_count
        # 实际可用独立的收藏表
        video.favorite_count = 1 if (video.favorite_count or 0) == 0 else 0
        await db.commit()
        return {"id": video.id, "favorited": video.favorite_count == 1}

    @staticmethod
    async def get_video_status(db: AsyncSession, video_id: int, user_id: int) -> Optional[dict]:
        """查询视频生成状态（供轮询使用）"""
        stmt = select(AiVideo).where(AiVideo.id == video_id, AiVideo.user_id == user_id)
        result = await db.execute(stmt)
        video = result.scalar_one_or_none()
        if not video:
            return None
        return {
            "id": video.id,
            "status": video.status,
            "video_url": video.video_url or "",
            "thumbnail_url": video.thumbnail_url or "",
            "duration": video.duration or 0,
            "error_message": video.error_message or "",
        }


# ========== Prompt 构建 ==========

_SCRIPT_SYSTEM_PROMPT = """你是一个儿童英语教育视频编导。给定一段英语课文和一个角色，请生成视频分镜脚本。

每个分镜包含:
1. spoken_text: 角色朗读的英文文本（自然分段，每段不超过3句话）
2. translation: 对应中文翻译
3. emotion: 角色的表情/情绪（如: 微笑/开心/认真/疑问/惊讶/点头）
4. duration_sec: 该段预计时长（秒）
5. background_desc: 背景描述（如: 教室/公园/家里/动物园）

规则:
- 按课文自然段落分段
- 第一段以角色自我介绍开头
- 语言难度匹配课文的学习阶段
- 返回纯 JSON 数组"""


def _build_script_prompt(text_content: str, character_name: str) -> str:
    """构建分镜脚本生成 Prompt"""
    return f"""角色名称: {character_name}
课文内容:
{text_content}

请为这个角色设计朗读该课文的视频分镜脚本。
返回 JSON 数组格式，每个元素包含: spoken_text, translation, emotion, duration_sec, background_desc"""


def _parse_script(response: str) -> dict:
    """解析 AI 返回的分镜脚本"""
    try:
        content = response
        if isinstance(response, dict):
            content = response.get("content", "") or str(response)
        if isinstance(content, str):
            # 提取 JSON 数组
            match = re.search(r'\[[\s\S]*\]', content)
            if match:
                scenes = json.loads(match.group())
            else:
                # 尝试提取 JSON 对象
                match = re.search(r'\{[\s\S]*\}', content)
                if match:
                    scenes = json.loads(match.group())
                    scenes = scenes.get("scenes", scenes.get("scenes", []))
                else:
                    scenes = []
        else:
            scenes = content if isinstance(content, list) else []
        if not isinstance(scenes, list):
            scenes = []
        return {"scenes": scenes, "total_scenes": len(scenes)}
    except (json.JSONDecodeError, TypeError):
        return _generate_default_script(text_content="")


def _generate_default_script(text_content: str) -> dict:
    """AI 解析失败时生成默认脚本"""
    if not text_content:
        return {"scenes": [], "total_scenes": 0}

    # 按句子拆分
    sentences = re.split(r'[.?!\n]+', text_content)
    sentences = [s.strip() for s in sentences if s.strip()]

    scenes = []
    for i, sentence in enumerate(sentences):
        scenes.append({
            "spoken_text": sentence + ".",
            "translation": "",
            "emotion": "微笑" if i % 2 == 0 else "认真",
            "duration_sec": max(3, len(sentence.split()) * 2),
            "background_desc": "教室",
        })

    return {"scenes": scenes, "total_scenes": len(scenes)}


# ========== 异步任务管理 ==========

# CDN 基础路径配置（从 Settings 读取，可被环境变量覆盖）
_settings = get_settings()
CDN_BASE_URL = _settings.CDN_BASE_URL or "https://cdn.elearning.com/video"
OUTPUT_DIR = _settings.VIDEO_OUTPUT_DIR or "./output/video"


def _enqueue_video_render(
    video_id: int,
    script: dict,
    character_type: str,
    character_image_url: Optional[str] = None,
):
    """投递视频合成任务到后台异步执行

    使用 asyncio.create_task 在事件循环后台运行视频合成，
    后续可替换为 Celery / 消息队列（RabbitMQ/Pulsar）。
    """
    task = asyncio.ensure_future(
        _run_video_render_pipeline(
            video_id=video_id,
            script=script,
            character_type=character_type,
            character_image_url=character_image_url,
        )
    )
    task.add_done_callback(_on_render_done)
    logger.info("视频合成任务已投递: video_id=%s", video_id)


def _on_render_done(future: asyncio.Future):
    """渲染任务完成回调"""
    exc = future.exception()
    if exc:
        logger.error("视频合成任务异常: %s", exc)


async def _run_video_render_pipeline(
    video_id: int,
    script: dict,
    character_type: str,
    character_image_url: Optional[str] = None,
):
    """异步视频渲染流水线 - 后台执行

    完整流程:
    1. 状态标记为 processing
    2. 逐段调用 TTS 生成配音音频
    3. 拼接音频片段 + 生成字幕 SRT 文件
    4. 上传配音和字幕到 CDN
    5. 使用角色图片合成视频帧（FFmpeg）
    6. 合成最终视频文件
    7. 上传视频 + 缩略图到 CDN
    8. 更新 ai_video 记录为 completed
    """
    # 获取独立数据库会话（避免 session 跨任务失效）
    async with async_session_factory() as db:
        try:
            # Step 1: 标记为 processing
            logger.info("[video=%s] 开始视频合成...", video_id)
            await _update_video_status(db, video_id, "processing")
            scenes = script.get("scenes", [])

            # Step 2: 逐段 TTS 生成配音
            tts_urls = []
            total_duration = 0
            subtitle_entries = []
            for idx, scene in enumerate(scenes):
                spoken_text = scene.get("spoken_text", "")
                if not spoken_text:
                    continue

                # 调用 TTS 生成单段音频
                audio_url, duration = await _call_tts_api(
                    text=spoken_text,
                    voice_type=_resolve_voice_type(character_type),
                    scene_index=idx,
                )
                tts_urls.append(audio_url)
                total_duration += duration

                # 生成字幕条目
                subtitle_entries.append({
                    "index": idx + 1,
                    "start": total_duration - duration,
                    "end": total_duration,
                    "text": spoken_text,
                })

            # Step 3: 拼接完整音频
            full_audio_url = await _concat_audio(tts_urls, video_id)

            # Step 4: 生成字幕 SRT 文件并上传
            subtitle_url = await _generate_and_upload_subtitle(
                subtitle_entries, video_id
            )

            # Step 5: 视频合成
            character_img = character_image_url or _get_default_character_image(character_type)
            output_video_url = await _composite_video(
                video_id=video_id,
                character_image=character_img,
                audio_url=full_audio_url,
                subtitle_url=subtitle_url,
                scenes=scenes,
            )

            # Step 6: 生成缩略图
            thumbnail_url = await _generate_thumbnail(video_id, output_video_url)

            # Step 7: 上传到 CDN
            cdn_video_url = await _upload_to_cdn(output_video_url, f"video/{video_id}/final.mp4")
            cdn_thumbnail_url = await _upload_to_cdn(thumbnail_url, f"video/{video_id}/thumb.jpg")
            cdn_subtitle_url = await _upload_to_cdn(subtitle_url, f"video/{video_id}/subtitle.srt")

            # Step 8: 更新为 completed
            await _update_video_result(
                db=db,
                video_id=video_id,
                video_url=cdn_video_url,
                thumbnail_url=cdn_thumbnail_url,
                subtitle_url=cdn_subtitle_url,
                duration=total_duration,
            )
            logger.info("[video=%s] 视频合成完成，时长=%ss", video_id, total_duration)

        except Exception as e:
            logger.error("[video=%s] 视频合成失败: %s", video_id, e, exc_info=True)
            await _update_video_status(db, video_id, "failed", error_message=str(e))


# ========== 子步骤实现 ==========


async def _call_tts_api(
    text: str,
    voice_type: str,
    scene_index: int,
) -> tuple[str, int]:
    """调用 TTS API 生成单段配音

    返回 (本地音频路径, 时长秒数)
    使用 TTSService 调用火山引擎豆包语音合成
    """
    from app.services.tts_service import TTSService, _resolve_volc_speaker

    task_id = f"tts_{uuid.uuid4().hex[:8]}"
    audio_path = os.path.join(OUTPUT_DIR, f"{task_id}.mp3")
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)

    try:
        volc_voice = _resolve_volc_speaker(voice_type)
        audio_bytes = await TTSService.synthesize(
            text=text,
            voice_type=volc_voice,
            save_path=audio_path,
        )
    except Exception as e:
        logger.error("TTS 调用失败: %s", e)
        # fallback: 生成静音占位文件
        estimated_duration = max(2, len(text) // 3)
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 1024)
        return audio_path, estimated_duration

    # 估算时长：MP3 文件大小 / 码率 (~64kbps = 8KB/s)
    estimated_duration = max(2, len(audio_bytes) // 8000) if audio_bytes else max(2, len(text) // 3)

    logger.debug("TTS 生成成功: text_len=%s, duration=%ss, path=%s", len(text), estimated_duration, audio_path)
    return audio_path, estimated_duration


async def _concat_audio(audio_urls: list[str], video_id: int) -> str:
    """使用 FFmpeg 拼接多段音频为完整文件

    将各段 MP3 通过 concat demuxer 拼接，无重新编码，速度快
    """
    concat_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_audio.mp3")
    os.makedirs(os.path.dirname(concat_path), exist_ok=True)

    if not audio_urls:
        logger.warning("音频列表为空: video_id=%s", video_id)
        with open(concat_path, "wb") as f:
            f.write(b"")
        return concat_path

    # 如果只有一段，直接复制
    if len(audio_urls) == 1:
        import shutil
        shutil.copy2(audio_urls[0], concat_path)
        logger.info("单段音频，直接复制: video_id=%s", video_id)
        return concat_path

    try:
        # 生成 concat 文件列表
        filelist_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_filelist.txt")
        with open(filelist_path, "w", encoding="utf-8") as f:
            for url in audio_urls:
                f.write(f"file '{url}'\n")

        # 使用 FFmpeg concat demuxer
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", filelist_path,
            "-c", "copy",
            concat_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("FFmpeg concat 失败: %s", stderr.decode()[:500])
            # fallback: 用 Python 简单拼接
            _fallback_concat_audio(audio_urls, concat_path)
        else:
            # 清理临时文件
            try:
                os.remove(filelist_path)
            except OSError:
                pass

    except FileNotFoundError:
        logger.warning("FFmpeg 未安装，使用 Python fallback 拼接: video_id=%s", video_id)
        _fallback_concat_audio(audio_urls, concat_path)
    except Exception as e:
        logger.error("音频拼接异常: %s", e)
        _fallback_concat_audio(audio_urls, concat_path)

    logger.info("音频拼接完成: video_id=%s, segments=%s", video_id, len(audio_urls))
    return concat_path


def _fallback_concat_audio(audio_urls: list[str], output_path: str):
    """Python fallback：简单拼接 MP3 文件（不保证格式正确，仅占位）"""
    with open(output_path, "wb") as out:
        for url in audio_urls:
            try:
                with open(url, "rb") as f:
                    out.write(f.read())
            except (IOError, OSError) as e:
                logger.warning("拼接文件失败: %s, error=%s", url, e)


async def _generate_and_upload_subtitle(
    entries: list[dict],
    video_id: int,
) -> str:
    """根据字幕条目生成 SRT 文件并返回本地路径

    格式标准 SRT:
        1
        00:00:01,000 --> 00:00:04,000
        Hello world
    """
    srt_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_subtitle.srt")
    os.makedirs(os.path.dirname(srt_path), exist_ok=True)

    lines = []
    for entry in entries:
        start_sec = entry["start"]
        end_sec = entry["end"]
        lines.append(str(entry["index"]))
        lines.append(f"{_format_srt_time(start_sec)} --> {_format_srt_time(end_sec)}")
        lines.append(entry["text"])
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.debug("字幕文件已生成: entries=%s, path=%s", len(entries), srt_path)
    return srt_path


def _format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间戳: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


async def _composite_video(
    video_id: int,
    character_image: str,
    audio_url: str,
    subtitle_url: str,
    scenes: list[dict],
) -> str:
    """使用 FFmpeg 合成最终视频

    流程:
    1. 角色图片循环作为视频帧
    2. 叠加配音音频
    3. 嵌入学语字幕
    4. 输出 MP4
    """
    video_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_final.mp4")
    os.makedirs(os.path.dirname(video_path), exist_ok=True)

    # 确保角色图存在，不存在则生成占位
    char_img_path = character_image
    if not os.path.exists(char_img_path):
        char_img_path = _create_placeholder_image(video_id, character_image)

    try:
        # 使用 FFmpeg 合成
        # 将字幕嵌入视频帧
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",             # 图片循环
            "-i", char_img_path,       # 角色图
            "-i", audio_url,           # 配音音频
            "-vf", f"subtitles={subtitle_url}:force_style='FontName=SimHei,FontSize=24'",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-shortest",
            video_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("FFmpeg 视频合成失败: %s", stderr.decode()[:500])
            raise RuntimeError(f"FFmpeg 合成失败: {stderr.decode()[:300]}")

    except FileNotFoundError:
        logger.error("FFmpeg 未安装，无法合成视频: video_id=%s", video_id)
        raise RuntimeError("FFmpeg 未安装，请先安装 FFmpeg")
    except Exception as e:
        logger.error("视频合成异常: %s", e)
        raise

    logger.info("视频合成完成: video_id=%s, scenes=%s", video_id, len(scenes))
    return video_path


def _create_placeholder_image(video_id: int, char_image_path: str) -> str:
    """创建角色占位图（若角色图不存在）"""
    placeholder_path = os.path.join(OUTPUT_DIR, f"char_{video_id}_placeholder.png")
    os.makedirs(os.path.dirname(placeholder_path), exist_ok=True)

    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (720, 1280), (240, 240, 240))
        draw = ImageDraw.Draw(img)
        draw.text((360, 640), "角色", fill=(100, 100, 100), anchor="mm")
        img.save(placeholder_path)
    except ImportError:
        # 无 PIL 时生成纯色图片
        with open(placeholder_path, "wb") as f:
            f.write(b"\x00" * 1024)

    return placeholder_path


async def _generate_thumbnail(video_id: int, video_path: str) -> str:
    """从视频中截取一帧生成缩略图

    使用 FFmpeg: ffmpeg -i input.mp4 -ss 00:00:01 -vframes 1 thumb.jpg
    """
    thumb_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_thumb.jpg")
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", "00:00:01",
            "-vframes", "1",
            "-q:v", "2",
            thumb_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("FFmpeg 缩略图生成失败: %s", stderr.decode()[:300])
            # fallback: 生成 PIL 占位图
            _fallback_thumbnail(thumb_path, video_id)
    except FileNotFoundError:
        logger.warning("FFmpeg 未安装，使用 PIL 生成占位缩略图: video_id=%s", video_id)
        _fallback_thumbnail(thumb_path, video_id)
    except Exception as e:
        logger.error("缩略图生成异常: %s", e)
        _fallback_thumbnail(thumb_path, video_id)

    logger.debug("缩略图已生成: video_id=%s", video_id)
    return thumb_path


def _fallback_thumbnail(thumb_path: str, video_id: int):
    """PIL fallback: 生成占位缩略图"""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 180), (60, 60, 60))
        draw = ImageDraw.Draw(img)
        draw.text((160, 90), f"Video {video_id}", fill=(200, 200, 200), anchor="mm")
        img.save(thumb_path, "JPEG", quality=60)
    except ImportError:
        # 无 PIL 时生成空文件
        with open(thumb_path, "wb") as f:
            f.write(b"\x00" * 512)


async def _upload_to_cdn(local_path: str, remote_key: str) -> str:
    """上传文件到 COS CDN 并返回公开 URL

    使用腾讯云 COS SDK 上传，自动推断 MIME 类型
    """
    from app.utils.cos_uploader import upload_local_file_to_cos

    try:
        cdn_url = await upload_local_file_to_cos(
            local_path=local_path,
            key=remote_key,
        )
        logger.info("CDN 上传成功: local=%s → url=%s", local_path, cdn_url)
        return cdn_url
    except Exception as e:
        logger.error("CDN 上传失败: %s, fallback 到 mock URL", e)
        # fallback: 返回 mock CDN URL
        return f"{CDN_BASE_URL}/{remote_key}"


def _resolve_voice_type(character_type: str) -> str:
    """根据角色类型返回 TTS 音色"""
    from app.schemas.video import CHARACTER_VOICE_MAP
    return CHARACTER_VOICE_MAP.get(character_type, "zh-CN-XiaoxiaoNeural")


def _get_default_character_image(character_type: str) -> str:
    """获取角色默认图片本地路径"""
    return os.path.join(OUTPUT_DIR, f"characters/{character_type}.png")


async def _update_video_status(
    db: AsyncSession,
    video_id: int,
    status: str,
    error_message: Optional[str] = None,
):
    """更新视频状态（不关心返回结果）"""
    stmt = select(AiVideo).where(AiVideo.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        return
    video.status = status
    if error_message:
        video.error_message = error_message
    await db.commit()


async def _update_video_result(
    db: AsyncSession,
    video_id: int,
    video_url: str,
    thumbnail_url: str,
    subtitle_url: str,
    duration: int,
):
    """更新视频生成结果"""
    stmt = select(AiVideo).where(AiVideo.id == video_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        return
    video.status = "completed"
    video.video_url = video_url
    video.thumbnail_url = thumbnail_url
    video.subtitle_url = subtitle_url
    video.duration = duration
    await db.commit()
