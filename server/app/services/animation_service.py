"""
AI 微动图生成服务（动态图书增强版）

功能:
1. 整页微动图（向后兼容）- 为教材插图生成 2-3 帧微动 GIF
2. 角色级微动图 - 为每个说话角色单独生成"说话"动画（嘴部+头部微动）
3. 背景持续微动图 - 生成持续循环的环境微动（风吹/云动/水波）

所有生成的 GIF 同时保存到本地 data/Tu/ 目录和上传 COS。
"""
import uuid
import json
import os
import logging
import httpx
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.textbook_models import TextbookPage
from app.services.ai_service import AIService
from app.utils.gif_composer import compose_gif
from app.utils.cos_uploader import upload_to_cos
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 本地 GIF 保存目录：优先使用配置 ANIMATION_LOCAL_DIR，否则默认 data/Tu/
_LOCAL_DIR = getattr(settings, "ANIMATION_LOCAL_DIR", "") or ""
if _LOCAL_DIR:
    LOCAL_GIF_DIR = _LOCAL_DIR
else:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    LOCAL_GIF_DIR = os.path.join(_PROJECT_ROOT, "data", "Tu")


class AnimationService:
    """AI 微动图生成服务：为教材插图生成角色级微动 GIF 和背景持续微动"""

    @staticmethod
    async def create_animation_task(
        db: AsyncSession,
        page_id: int,
        user_id: int = 0,
        enhanced: bool = True,
    ) -> dict:
        """创建微动图生成任务（增强版）

        增强流程:
        1. 获取页面插图和课文上下文
        2. AI 深度场景分析，识别角色和背景
        3. 生成角色级说话动画（每个角色单独 GIF）
        4. 生成背景持续微动动画
        5. 上传 COS / CDN
        6. 更新 page.background_anim_url + sentences_json.animation_url

        参数:
            db: 数据库会话
            page_id: 页面 ID
            user_id: 用户 ID
            enhanced: 是否启用增强模式（角色级+背景动画）
        """
        stmt = select(TextbookPage).where(TextbookPage.id == page_id)
        result = await db.execute(stmt)
        page = result.scalar_one_or_none()
        if not page:
            return {"task_id": "", "error": "页面不存在"}
        if not page.image_url:
            return {"task_id": "", "error": "页面无插图，无法生成微动图"}

        task_id = f"anim_{uuid.uuid4().hex[:12]}"

        # Setp 1: AI 深度场景分析
        scene_prompt = _build_enhanced_scene_prompt(page)
        try:
            scene_result = await AIService.chat_completion(
                db=db,
                messages=[
                    {"role": "system", "content": _ENHANCED_ANIMATION_SYSTEM_PROMPT},
                    {"role": "user", "content": scene_prompt},
                ],
                user_id=user_id,
                stream=False,
            )
            scene_analysis = _parse_enhanced_spec(scene_result)
        except Exception as e:
            logger.error("AI 场景分析失败: %s", e)
            return {"task_id": task_id, "status": "failed", "error": str(e)}

        # Step 2-6: 在后台执行（使用独立 DB session，避免 session 过期）
        import asyncio
        asyncio.ensure_future(
            _process_enhanced_animation_task(
                task_id=task_id,
                page_id=page.id,
                analysis=scene_analysis,
                enhanced=enhanced,
            )
        )

        return {
            "task_id": task_id,
            "status": "pending",
            "scene_analysis": scene_analysis,
            "message": "增强版微动图任务已创建，正在后台处理",
        }

    @staticmethod
    async def get_animation_status(task_id: str) -> dict:
        """查询微动图生成状态（含图片张数）"""
        try:
            from app.utils.redis_client import get_redis, RedisCache
            redis = await get_redis()
            cache = RedisCache(redis)
            status = await cache.get(f"anim:status:{task_id}")
            image_count = await cache.get(f"anim:count:{task_id}")
            result = {"task_id": task_id, "status": status or "pending"}
            if image_count is not None:
                result["image_count"] = int(image_count) if isinstance(image_count, str) else image_count
            return result
        except Exception:
            pass
        return {"task_id": task_id, "status": "pending"}


# ========== AI Prompt 构建（增强版）==========

_ENHANCED_ANIMATION_SYSTEM_PROMPT = """你是一个专业的儿童英语教材动画设计师。给定教材页面的课文内容和插图描述，请进行深度场景分析，输出三个部分：

## 1. 角色分析
识别插图中所有可能"说话"的角色（人物、动物等）：
- name: 角色英文名（小写，如 mike, amy, cat）
- description: 角色外观描述
- default_expression: 默认表情（smile, neutral）
- speaking_expression: 说话时表情变化（mouth_open, head_nod, blink）
- position: 在画面中的位置描述（left, center, right, top, bottom）

## 2. 角色说话动画
为每个角色生成2-3帧的"说话"动画规格：
- 每帧描述角色嘴部/头部/表情的微变化
- 保持背景和其他角色完全不变
- 每帧参数包含是否需要张嘴 (mouth_open: true/false)

## 3. 背景环境动画
识别插图背景中的自然元素，生成持续循环的微动动画：
- element: 元素名称（cloud, tree, grass, water, sun）
- action: 动效类型（drift, sway, ripple, twinkle）
- duration_sec: 循环周期（秒）
- params: 运动参数

请返回以下 JSON 格式（不要包含其他文字）：
{
  "scene_type": "对话/描述/综合",
  "description": "场景整体描述",
  "characters": [
    {
      "name": "mike",
      "description": "穿蓝色T恤的男孩",
      "default_expression": "smile",
      "speaking_expression": "嘴部微张+微笑点头",
      "position": "left",
      "speaking_prompt": "用于图生图的角色说话 prompt（描述角色说话时的样子）"
    }
  ],
  "background_elements": [
    {
      "element": "cloud",
      "action": "drift",
      "duration_sec": 3.0,
      "params": {"dx": 20, "dy": 0}
    }
  ],
  "background_prompt": "用于生成背景微动图的 prompt，仅描述背景环境效果",
  "full_animation_prompt": "用于生成整页微动图的 prompt（向后兼容）",
  "num_frames": 3,
  "num_character_frames": 2
}"""


def _build_enhanced_scene_prompt(page: TextbookPage) -> str:
    """构建增强版场景分析 Prompt"""
    text_excerpt = page.text_content[:500] if page.text_content else ""

    # 从 sentences_json 提取说话角色信息
    speakers_info = ""
    if page.sentences_json:
        speakers = set()
        for s in page.sentences_json:
            sp = s.get("speaker", "") if isinstance(s, dict) else ""
            if sp and sp != "narrator":
                speakers.add(sp)
        if speakers:
            speakers_info = f"课文中的说话角色: {', '.join(sorted(speakers))}"

    return f"""教材版本: {page.textbook_version}
年级: {page.grade}
单元: {page.unit_number}
页码: {page.page_number}

课文内容:
{text_excerpt}

{speakers_info}

图片URL: {page.image_url or '无'}

请进行深度场景分析，识别角色和背景元素，输出增强版动画规格。"""


def _parse_enhanced_spec(ai_response: str) -> dict:
    """解析增强版 AI 动画规格"""
    try:
        content = ai_response
        if isinstance(ai_response, dict):
            content = (
                ai_response.get("content", "")
                or ai_response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
        if isinstance(content, str):
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                content = content[start: end + 1]
            return json.loads(content)
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("解析增强动画规格失败: %s", e)
        return {
            "scene_type": "general",
            "description": "AI 分析结果",
            "characters": [],
            "background_elements": [],
            "background_prompt": "",
            "full_animation_prompt": "",
            "num_frames": 3,
            "num_character_frames": 2,
        }


# ========== 后台处理（增强版）==========


async def _process_enhanced_animation_task(
    task_id: str,
    page_id: int,
    analysis: dict,
    enhanced: bool = True,
):
    """增强版后台处理：角色动画 + 背景动画 + 整页动画

    使用独立 DB session，每页完成后立即提交，确保中断不丢数据。
    """
    from app.db.database import async_session as _async_session_factory

    try:
        await _set_task_status(task_id, "processing")

        characters = analysis.get("characters", [])
        background_elements = analysis.get("background_elements", [])
        full_prompt = analysis.get("full_animation_prompt", "")
        background_prompt = analysis.get("background_prompt", "")
        num_frames = analysis.get("num_frames", 3)
        num_char_frames = analysis.get("num_character_frames", 2)
        frame_duration = 800  # ms per frame

        cdn_base = getattr(settings, "CDN_BASE_URL", "")

        # ── 获取页面信息（提取后关闭session，后续只用提取的值）──
        async with _async_session_factory() as read_db:
            pg_stmt = select(TextbookPage).where(TextbookPage.id == page_id)
            pg_result = await read_db.execute(pg_stmt)
            pg = pg_result.scalar_one_or_none()
            if not pg:
                await _set_task_status(task_id, "failed")
                logger.error("页面不存在: page_id=%s", page_id)
                return
            # 提取所需字段，session 关闭后仍可用
            _p_version = pg.textbook_version
            _p_grade = pg.grade
            _p_unit = pg.unit_number
            _p_number = pg.page_number
            _p_sentences = pg.sentences_json

        # ── Step A: 生成角色级说话动画 ──
        character_animations = {}
        if enhanced and characters:
            for char in characters:
                char_name = char.get("name", "").lower()
                if not char_name:
                    continue
                speaking_prompt = char.get("speaking_prompt", "")
                if not speaking_prompt:
                    continue

                # 生成角色说话帧
                char_frames = await _generate_character_frames(
                    character_name=char_name,
                    speaking_prompt=speaking_prompt,
                    frame_count=num_char_frames,
                )
                if char_frames:
                    # 合成角色 GIF
                    gif_bytes = compose_gif(
                        frame_bytes_list=char_frames,
                        duration=frame_duration,
                        loop=0,
                        max_size_bytes=256 * 1024,  # 角色动画小一点
                    )
                    # 本地保存到 data/Tu/
                    local_name = f"{_p_version}_{_p_grade}_{_p_unit}_char_{char_name}_p{_p_number}.gif"
                    _save_gif_local(gif_bytes, local_name)
                    # 上传 COS
                    cos_key = (
                        f"textbook/{_p_version}/{_p_grade}/"
                        f"{_p_unit}/char_{char_name}_p{_p_number}.gif"
                    )
                    cdn_url = await _upload_gif_to_cdn(gif_bytes, cos_key)
                    character_animations[char_name] = cdn_url
                    logger.info(
                        "角色微动图生成成功: page_id=%s, char=%s, url=%s",
                        page_id, char_name, cdn_url,
                    )

        # ── Step B: 生成背景持续微动图 ──
        background_anim_url = ""
        if enhanced and (background_prompt or background_elements):
            bg_prompt = background_prompt or f"背景微动: 持续循环，{analysis.get('description', '微风拂过')}"
            bg_frames = await _generate_background_frames(
                prompt=bg_prompt,
                elements=background_elements,
                frame_count=num_frames,
            )
            if bg_frames:
                gif_bytes = compose_gif(
                    frame_bytes_list=bg_frames,
                    duration=frame_duration,
                    loop=0,
                    max_size_bytes=384 * 1024,  # 背景微动图适中大小
                )
                # 本地保存到 data/Tu/
                local_name = f"{_p_version}_{_p_grade}_{_p_unit}_bg_p{_p_number}.gif"
                _save_gif_local(gif_bytes, local_name)
                cos_key = (
                    f"textbook/{_p_version}/{_p_grade}/"
                    f"{_p_unit}/bg_p{_p_number}.gif"
                )
                background_anim_url = await _upload_gif_to_cdn(gif_bytes, cos_key)
                logger.info(
                    "背景微动图生成成功: page_id=%s, url=%s",
                    page_id, background_anim_url,
                )

        # ── Step C: 生成整页微动图（向后兼容） ──
        page_animation_url = ""
        if full_prompt:
            full_frames = await _generate_frame_images(
                prompt_base=full_prompt,
                frames_spec=[],
                frame_count=num_frames,
            )
            if full_frames:
                gif_bytes = compose_gif(
                    frame_bytes_list=full_frames,
                    duration=frame_duration,
                    loop=0,
                    max_size_bytes=512 * 1024,
                )
                # 本地保存到 data/Tu/
                local_name = f"{_p_version}_{_p_grade}_{_p_unit}_anim_p{_p_number}.gif"
                _save_gif_local(gif_bytes, local_name)
                cos_key = (
                    f"textbook/{_p_version}/{_p_grade}/"
                    f"{_p_unit}/anim_{_p_number}.gif"
                )
                page_animation_url = await _upload_gif_to_cdn(gif_bytes, cos_key)
                logger.info(
                    "整页微动图生成成功: page_id=%s, url=%s",
                    page_id, page_animation_url,
                )
        else:
            # 无 full_prompt 但可能有角色/背景图，用第一帧背景或角色图作为整页GIF
            page_animation_url = background_anim_url or (
                next(iter(character_animations.values())) if character_animations else ""
            )

        # ── Step D: 更新数据库（独立 session，立即提交）──
        async with _async_session_factory() as save_db:
            # 更新整页动画
            update_values = {}
            if page_animation_url:
                update_values["animation_url"] = page_animation_url
            if background_anim_url:
                update_values["background_anim_url"] = background_anim_url

            if update_values:
                stmt_upd = (
                    update(TextbookPage)
                    .where(TextbookPage.id == page_id)
                    .values(**update_values)
                )
                await save_db.execute(stmt_upd)

            # 更新 sentences_json 中的 animation_url（角色级动画映射）
            if character_animations and _p_sentences:
                sentences = list(_p_sentences)
                updated = False
                for s in sentences:
                    if isinstance(s, dict):
                        speaker = s.get("speaker", "")
                        if speaker in character_animations:
                            s["animation_url"] = character_animations[speaker]
                            updated = True
                if updated:
                    stmt_sent = (
                        update(TextbookPage)
                        .where(TextbookPage.id == page_id)
                        .values(sentences_json=sentences)
                    )
                    await save_db.execute(stmt_sent)

            await save_db.commit()
            logger.info("微动图数据已保存: page_id=%s", page_id)

        # ── 统计实际生成的动图张数 ──
        image_count = (
            len(character_animations)
            + (1 if background_anim_url else 0)
            + (1 if page_animation_url and full_prompt else 0)
        )
        await _set_task_image_count(task_id, image_count)
        await _set_task_status(task_id, "completed")
        logger.info(
            "增强微动图任务完成: page_id=%s, characters=%s, bg=%s, images=%s",
            page_id,
            list(character_animations.keys()),
            bool(background_anim_url),
            image_count,
        )

    except Exception as e:
        logger.error("增强微动图生成失败: task_id=%s, page_id=%s, error=%s",
                     task_id, page_id, e, exc_info=True)
        await _set_task_status(task_id, "failed")


# ========== 帧生成函数 ==========


async def _generate_frame_images(
    prompt_base: str,
    frames_spec: list[dict],
    frame_count: int = 3,
) -> list[bytes]:
    """调用图片生成模型逐帧生成图片（通用）

    参数:
        prompt_base: 基础场景 prompt
        frames_spec: 各帧动作描述 [{element, action, params}]
        frame_count: 生成帧数

    返回:
        list[bytes]: 各帧图片二进制数据
    """
    if not frames_spec:
        frames_spec = [{"action": f"frame_{i+1}"} for i in range(frame_count)]

    model = settings.ANIMATION_MODEL
    api_key = settings.ANIMATION_API_KEY
    api_base = settings.ANIMATION_API_BASE

    if not api_key:
        raise ValueError("未配置 ANIMATION_API_KEY")

    frames = []
    async with httpx.AsyncClient(timeout=120) as client:
        for i, frame in enumerate(frames_spec[:frame_count]):
            action_desc = frame.get("action", f"frame_{i+1}")
            params = frame.get("params", {})
            prompt = prompt_base
            if action_desc:
                prompt += f", {action_desc}"
            for k, v in params.items():
                prompt += f", {k}={v}"

            resp = await client.post(
                f"{api_base}/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "prompt": prompt,
                    "image_size": "1024x1024",
                },
            )

            if resp.status_code != 200:
                raise ValueError(
                    f"图片帧生成失败: status={resp.status_code}, "
                    f"body={resp.text[:300]}"
                )

            data = resp.json()
            img_url = data["images"][0]["url"]
            img_resp = await client.get(img_url, timeout=60)
            if img_resp.status_code != 200:
                raise ValueError(f"图片下载失败: {img_url}")
            frames.append(img_resp.content)

    return frames


async def _generate_character_frames(
    character_name: str,
    speaking_prompt: str,
    frame_count: int = 2,
) -> list[bytes]:
    """为指定角色生成"说话"动画的逐帧图片

    生成 2 帧：
      帧 0: 角色闭嘴/默认表情
      帧 1: 角色张嘴/说话表情

    两帧保持背景完全一致，仅修改角色嘴部/表情。
    """
    model = settings.ANIMATION_MODEL
    api_key = settings.ANIMATION_API_KEY
    api_base = settings.ANIMATION_API_BASE

    if not api_key:
        raise ValueError("未配置 ANIMATION_API_KEY")

    frames = []
    async with httpx.AsyncClient(timeout=120) as client:
        for i in range(frame_count):
            # 第 0 帧闭嘴，第 1 帧张嘴
            if i == 0:
                frame_prompt = (
                    f"{speaking_prompt}, 角色闭嘴，默认表情，"
                    f"保持背景不变，仅角色嘴部闭合"
                )
            else:
                frame_prompt = (
                    f"{speaking_prompt}, 角色张嘴说话，表情自然，"
                    f"保持背景完全一致，仅角色嘴部张开"
                )

            resp = await client.post(
                f"{api_base}/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "prompt": frame_prompt,
                    "image_size": "1024x1024",
                },
            )

            if resp.status_code != 200:
                raise ValueError(
                    f"角色帧生成失败: status={resp.status_code}, "
                    f"body={resp.text[:300]}"
                )

            data = resp.json()
            img_url = data["images"][0]["url"]
            img_resp = await client.get(img_url, timeout=60)
            if img_resp.status_code != 200:
                raise ValueError(f"图片下载失败: {img_url}")
            frames.append(img_resp.content)

    return frames


async def _generate_background_frames(
    prompt: str,
    elements: list[dict],
    frame_count: int = 3,
) -> list[bytes]:
    """生成背景持续微动动画的逐帧图片

    针对背景环境元素生成持续循环的自然动效
    """
    if not elements:
        return await _generate_frame_images(
            prompt_base=prompt,
            frames_spec=[],
            frame_count=frame_count,
        )

    model = settings.ANIMATION_MODEL
    api_key = settings.ANIMATION_API_KEY
    api_base = settings.ANIMATION_API_BASE

    if not api_key:
        raise ValueError("未配置 ANIMATION_API_KEY")

    frames = []
    async with httpx.AsyncClient(timeout=120) as client:
        for i in range(frame_count):
            # 构建背景帧 prompt
            frame_actions = []
            for elem in elements:
                element_name = elem.get("element", "")
                action = elem.get("action", "")
                params = elem.get("params", {})
                dx = params.get("dx", 0)
                dy = params.get("dy", 0)
                frame_actions.append(f"{element_name} {action} 相位{i}/{frame_count} 偏移({dx * i / frame_count:.1f}, {dy * i / frame_count:.1f})")

            actions_str = "; ".join(frame_actions)
            frame_prompt = (
                f"{prompt}, 持续循环的背景环境动效, "
                f"不包含任何角色或人物, 帧{i+1}/{frame_count}: {actions_str}"
            )

            resp = await client.post(
                f"{api_base}/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "prompt": frame_prompt,
                    "image_size": "1024x1024",
                },
            )

            if resp.status_code != 200:
                raise ValueError(
                    f"背景帧生成失败: status={resp.status_code}, "
                    f"body={resp.text[:300]}"
                )

            data = resp.json()
            img_url = data["images"][0]["url"]
            img_resp = await client.get(img_url, timeout=60)
            if img_resp.status_code != 200:
                raise ValueError(f"图片下载失败: {img_url}")
            frames.append(img_resp.content)

    return frames


# ========== 本地保存 ==========


def _save_gif_local(gif_bytes: bytes, local_filename: str) -> str:
    """将 GIF 二进制数据保存到 data/Tu/ 目录

    参数:
        gif_bytes: GIF 二进制数据
        local_filename: 本地文件名（如 PEP_3_Unit1_char_mike_p2.gif）

    返回:
        str: 本地文件完整路径，失败返回空字符串
    """
    try:
        os.makedirs(LOCAL_GIF_DIR, exist_ok=True)
        local_path = os.path.join(LOCAL_GIF_DIR, local_filename)
        with open(local_path, "wb") as f:
            f.write(gif_bytes)
        logger.info("GIF 已保存到本地: %s (%s KB)", local_path, len(gif_bytes) // 1024)
        return local_path
    except Exception as e:
        logger.warning("本地保存 GIF 失败: %s, error=%s", local_filename, e)
        return ""


# ========== 上传与状态管理 ==========


async def _upload_gif_to_cdn(gif_bytes: bytes, cos_key: str) -> str:
    """上传 GIF 到 COS 并返回 CDN URL"""
    try:
        cos_url = await upload_to_cos(
            data=gif_bytes,
            key=cos_key,
            content_type="image/gif",
        )
        return cos_url
    except ImportError:
        logger.warning("cos-python-sdk-v5 未安装，返回 mock URL")
        return f"{settings.CDN_BASE_URL}/{cos_key}"
    except Exception as e:
        logger.error("COS 上传失败: %s", e)
        raise


async def _set_task_status(task_id: str, status: str):
    """在 Redis 中更新任务状态"""
    try:
        from app.utils.redis_client import get_redis, RedisCache
        redis = await get_redis()
        cache = RedisCache(redis)
        await cache.set(f"anim:status:{task_id}", status, ex=3600)
    except Exception as e:
        logger.warning("更新任务状态失败: %s", e)


async def _set_task_image_count(task_id: str, count: int):
    """在 Redis 中记录该任务实际生成的动图张数"""
    try:
        from app.utils.redis_client import get_redis, RedisCache
        redis = await get_redis()
        cache = RedisCache(redis)
        await cache.set(f"anim:count:{task_id}", str(count), ex=3600)
    except Exception as e:
        logger.warning("存储动图张数失败: %s", e)
