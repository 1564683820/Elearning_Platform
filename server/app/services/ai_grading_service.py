"""
多模态 AI 批卷服务
使用多模态大模型（视觉语言模型）对答题卡照片进行答案识别，替代传统 OpenCV OMR 扫描

数据流：
  答题卡照片 + 试卷配置 → 多模态模型 → 结构化 JSON → 与标准答案对比批改

输出 JSON 完全兼容原有 scan_answer_sheet() 的返回格式，下游批改逻辑无需改动
"""

import asyncio
import json
import logging
import re
import time
import base64
import os
import traceback
import random

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 重试配置
MAX_RETRIES = 3                  # 最大重试次数
RETRY_BASE_DELAY = 2.0           # 基础重试间隔（秒）
RETRY_BACKOFF_FACTOR = 2.0       # 退避倍增因子
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 图片大小上限 5MB（超过则压缩）
IMAGE_QUALITY = 75               # 压缩质量 75/100

# 全局信号量：限制多模态API并发调用数，避免超过API服务商的并发限制
# 月之暗面官方API支持并发，设3个并发槽位，兼顾速度与稳定性
MULTIMODAL_SEMAPHORE = asyncio.Semaphore(50)


class MultiModalGradingService:
    """多模态答题卡识别服务 —— 用视觉大模型直接理解答题卡照片"""

    @staticmethod
    async def recognize_answer_sheet(
        image_path: str,
        questions: list[dict],
        exam_title: str = "",
        grade: str = "",
    ) -> dict:
        """
        使用多模态模型识别答题卡照片，提取考生答案

        参数：
            image_path — 答题卡照片文件路径
            questions  — 试卷题目列表 (TeacherExam.questions JSON)
            exam_title — 试卷名称（用于提示词上下文）
            grade      — 年级（用于提示词上下文）

        返回：与 scan_answer_sheet() 格式完全兼容的 dict
            {
                "success": True/False,
                "exam_number": "考号数字",
                "student_name": "",
                "answers": [{question_number, student_answer, confidence}, ...],
                "recognized_count": int,
                "confidence_overall": float,
                "detail_summary": "识别摘要",
                "duration_ms": int,
            }
        """
        start_time = time.time()

        # 构建提示词
        prompt = MultiModalGradingService._build_prompt(questions, exam_title, grade)

        # 读取图片并转 base64（带大小检查和压缩）
        try:
            image_base64, mime_type = MultiModalGradingService._load_and_optimize_image(image_path)
        except FileNotFoundError:
            return MultiModalGradingService._error_result("答题卡图片未找到", start_time)
        except Exception as e:
            logger.error("读取图片异常 | path=%s | type=%s | msg=%s",
                         os.path.basename(image_path), type(e).__name__, str(e))
            return MultiModalGradingService._error_result(
                f"读取答题卡图片失败: {type(e).__name__} — {e}", start_time)

        image_data_url = f"data:image/{mime_type};base64,{image_base64}"

        # API 配置
        api_key = settings.MULTIMODAL_API_KEY
        api_base = settings.MULTIMODAL_API_BASE.rstrip("/")
        model = settings.MULTIMODAL_MODEL

        if not api_key:
            return MultiModalGradingService._error_result(
                "未配置多模态 API Key，请在 .env 中设置 MULTIMODAL_API_KEY", start_time
            )
        if not model:
            return MultiModalGradingService._error_result(
                "未配置多模态模型名称，请在 .env 中设置 MULTIMODAL_MODEL", start_time
            )

        data_url_len = len(image_data_url)
        logger.info("多模态批卷 | model=%s api_base=%s 题目数=%d 图片=%s size=%dKB",
                     model, api_base, len(questions),
                     os.path.basename(image_path), data_url_len // 1024)

        # 带重试的模型调用（信号量限制并发=1，避免外部API限流）
        try:
            async with MULTIMODAL_SEMAPHORE:
                logger.info("多模态API获取信号量，开始调用模型 | model=%s", model)
                raw_result = await MultiModalGradingService._call_with_retry(
                    api_key=api_key,
                    api_base=api_base,
                    model=model,
                    image_data_url=image_data_url,
                    prompt=prompt,
                )
        except Exception as e:
            exc_type = type(e).__name__
            exc_msg = str(e) or "(无详细错误信息)"
            logger.error("多模态模型调用彻底失败（已重试%d次）| type=%s msg=%s\n%s",
                         MAX_RETRIES, exc_type, exc_msg, traceback.format_exc())
            return MultiModalGradingService._error_result(
                f"多模态模型调用失败（{exc_type}）: {exc_msg}", start_time)

        # 解析模型输出
        parsed = MultiModalGradingService._parse_model_output(raw_result, questions)

        # 附加耗时
        parsed["duration_ms"] = int((time.time() - start_time) * 1000)

        if parsed["success"]:
            logger.info("多模态识别成功 | 考号=%s 识别%d题/%d题 耗时=%dms",
                        parsed.get("exam_number", ""),
                        parsed.get("recognized_count", 0),
                        len(questions),
                        parsed["duration_ms"])
        else:
            logger.warning("多模态识别失败 | 原因=%s 耗时=%dms",
                           parsed.get("error", "未知"), parsed["duration_ms"])

        return parsed

    # ==================== 图片处理 ====================

    @staticmethod
    def _load_and_optimize_image(image_path: str) -> tuple[str, str]:
        """
        加载图片文件并转为base64，必要时压缩

        返回: (base64字符串, mime类型)
        """
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp", ".bmp": "bmp"}
        mime_type = mime_map.get(ext, "jpeg")

        # 检查文件大小
        file_size = os.path.getsize(image_path)

        with open(image_path, "rb") as f:
            raw_data = f.read()

        # 始终对图片进行缩放+压缩以提升识别速度（答题卡仅需~2048px分辨率）
        if file_size > MAX_IMAGE_SIZE_BYTES:
            logger.info("图片过大(%dKB)，压缩到 %dKB 以内",
                        file_size // 1024, MAX_IMAGE_SIZE_BYTES // 1024)
        try:
            raw_data = MultiModalGradingService._compress_image(
                raw_data, mime_type, MAX_IMAGE_SIZE_BYTES
            )
            logger.info("图片优化完成 | 原始=%dKB → 优化=%dKB",
                        file_size // 1024, len(raw_data) // 1024)
        except Exception as e:
            logger.warning("图片压缩失败(%s)，使用原图（可能影响请求速度）", e)

        image_base64 = base64.b64encode(raw_data).decode("utf-8")
        return image_base64, mime_type

    @staticmethod
    def _compress_image(raw_data: bytes, mime_type: str, max_size: int) -> bytes:
        """
        压缩图片到 max_size 以下

        策略：逐步降低质量直到满足大小要求
        """
        try:
            from PIL import Image as PILImage
            from io import BytesIO

            pil_mime_map = {
                "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP"
            }
            pil_fmt = pil_mime_map.get(mime_type, "JPEG")

            img = PILImage.open(BytesIO(raw_data))

            # 如果图片尺寸过大，先缩放到合理尺寸
            max_dim = 2048
            if max(img.size) > max_dim:
                ratio = max_dim / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, PILImage.Resampling.LANCZOS)
                logger.info("图片缩放 | %s → %s", img.size, new_size)

            # 转为 RGB（RGBA 无法保存为 JPEG）
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # 二分法查找合适质量
            quality = IMAGE_QUALITY
            lo, hi = 10, 95
            for _ in range(6):
                buf = BytesIO()
                img.save(buf, format="JPEG" if pil_fmt in ("JPEG", "BMP") else pil_fmt,
                         quality=quality, optimize=True)
                size = buf.tell()
                if size <= max_size:
                    return buf.getvalue()
                hi = quality - 1
                quality = (lo + hi) // 2
                if quality < lo:
                    break

            # 最终尝试最低质量
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=lo, optimize=True)
            return buf.getvalue()

        except ImportError:
            logger.warning("PIL(Pillow) 未安装，跳过图片压缩")
            return raw_data
        except Exception:
            raise

    # ==================== 模型调用（带重试） ====================

    @staticmethod
    async def _call_with_retry(
        api_key: str,
        api_base: str,
        model: str,
        image_data_url: str,
        prompt: str,
    ) -> str:
        """带指数退避重试的模型调用"""
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await MultiModalGradingService._call_vision_model(
                    api_key=api_key,
                    api_base=api_base,
                    model=model,
                    image_data_url=image_data_url,
                    prompt=prompt,
                    attempt=attempt + 1,
                )
            except NotRetryableError:
                # 不可重试的错误（如认证失败、内容违规）直接抛出
                raise
            except Exception as e:
                last_error = e
                exc_type = type(e).__name__
                exc_msg = str(e) or "(无详细错误信息)"

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
                    jitter = random.uniform(0, 1.0)
                    delay += jitter
                    logger.warning(
                        "多模态调用失败，将在 %.1fs 后重试 (第%d/%d次) | type=%s msg=%s",
                        delay, attempt + 1, MAX_RETRIES, exc_type, exc_msg
                    )
                    await _async_sleep(delay)
                else:
                    logger.error(
                        "多模态调用已重试%d次全部失败 | 最后一次 type=%s msg=%s",
                        MAX_RETRIES, exc_type, exc_msg
                    )

        raise last_error  # type: ignore

    @staticmethod
    async def _call_vision_model(
        api_key: str,
        api_base: str,
        model: str,
        image_data_url: str,
        prompt: str,
        attempt: int = 1,
    ) -> str:
        """调用多模态视觉模型 API（OpenAI 兼容格式）"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # 确保 image url 格式正确
        image_url_field = image_data_url
        if not image_url_field.startswith("data:image"):
            logger.warning("image_data_url 格式异常，尝试修复: %s...", image_url_field[:80])
            image_url_field = f"data:image/jpeg;base64,{image_data_url}"

        # 视觉模型消息格式：content 为数组，包含 image_url 和 text
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url_field},
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            "temperature": 1,         # Kimi-K2.6官方API仅支持temperature=1
            "max_tokens": 2048,    # 答题卡识别结果约1KB，2048足够
        }

        # 超时设置（首次90s，重试60s，图片压缩后模型响应会更快）
        timeout_seconds = 90.0 if attempt == 1 else 60.0
        timeout = httpx.Timeout(timeout_seconds, connect=20.0, read=timeout_seconds)

        logger.info("多模态 API 请求 | attempt=%d model=%s timeout=%ds",
                     attempt, model, int(timeout_seconds))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                elapsed = resp.elapsed.total_seconds()
                logger.info("多模态模型响应 | status=%d | elapsed=%.1fs",
                            resp.status_code, elapsed)

            # 处理 HTTP 错误
            if resp.status_code != 200:
                error_body = resp.text[:500] if resp.text else "(空响应体)"
                logger.error("多模态模型 HTTP 错误 | status=%d body=%s",
                             resp.status_code, error_body)

                # 分类错误类型
                if resp.status_code == 401:
                    raise NotRetryableError(
                        f"API Key 无效或已过期 (HTTP 401)"
                    )
                elif resp.status_code == 403:
                    raise NotRetryableError(
                        f"API 访问被拒绝 (HTTP 403)，请检查 API Key 权限: {error_body}"
                    )
                elif resp.status_code == 429:
                    raise ValueError(
                        f"API 请求频率超限 (HTTP 429)，请稍后重试: {error_body}"
                    )
                elif resp.status_code == 413:
                    raise NotRetryableError(
                        f"图片过大 (HTTP 413)，请使用更小的图片或降低分辨率: {error_body}"
                    )
                elif resp.status_code == 422:
                    raise NotRetryableError(
                        f"模型不支持该请求格式 (HTTP 422)，可能是模型名'{model}'不支持视觉输入: {error_body}"
                    )
                elif 500 <= resp.status_code < 600:
                    raise ValueError(
                        f"API 服务器错误 (HTTP {resp.status_code}): {error_body}"
                    )
                else:
                    raise ValueError(
                        f"API 返回异常状态码 HTTP {resp.status_code}: {error_body}"
                    )

            # 解析响应 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                raw_text = resp.text[:500] if resp.text else "(空)"
                logger.error("多模态模型返回非JSON | raw=%s", raw_text)
                raise ValueError(f"API 返回了非 JSON 格式的内容: {raw_text[:200]}")

            if not data.get("choices"):
                logger.error("多模态模型响应无choices | keys=%s",
                             list(data.keys()) if isinstance(data, dict) else type(data))
                finish_reason = "unknown"
                # 检查是否有错误信息
                if isinstance(data, dict) and data.get("error"):
                    err_info = data["error"]
                    err_msg = err_info.get("message", str(err_info))
                    raise ValueError(f"API 返回错误: {err_msg}")
                raise ValueError("API 返回了空的 choices 列表，可能模型不支持此请求")

            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "unknown")
            content = choice.get("message", {}).get("content", "")

            if not content or not content.strip():
                logger.warning("多模态模型返回空内容 | finish_reason=%s | full_data_keys=%s",
                               finish_reason,
                               list(data.keys()) if isinstance(data, dict) else "N/A")
                if finish_reason == "length":
                    raise ValueError("模型输出被截断（finish_reason=length），可能需要增加 max_tokens")
                elif finish_reason == "content_filter":
                    raise NotRetryableError(
                        "模型输出被内容过滤器拦截（finish_reason=content_filter），请检查图片内容"
                    )
                else:
                    raise ValueError(
                        f"多模态模型返回了空内容 (finish_reason={finish_reason})，请检查图片质量和 API 配置"
                    )

            logger.debug("模型原始输出（前500字符）: %s", content[:500])
            return content

        except NotRetryableError:
            raise
        except ValueError:
            raise
        except httpx.ConnectTimeout:
            raise ValueError(
                f"连接 API 服务器超时 (connect_timeout={timeout_seconds}s)，请检查网络和 API 地址"
            )
        except httpx.ReadTimeout:
            raise ValueError(
                f"API 响应超时 (read_timeout={timeout_seconds}s)，图片可能太大或模型处理太慢"
            )
        except httpx.WriteTimeout:
            raise ValueError(
                f"上传图片超时 (write_timeout={timeout_seconds}s)，请压缩图片后重试"
            )
        except httpx.PoolTimeout:
            raise ValueError("API 连接池超时，请稍后重试")
        except httpx.RemoteProtocolError as e:
            raise ValueError(
                f"API 服务器连接异常 (RemoteProtocolError): {e}"
            )
        except httpx.NetworkError as e:
            raise ValueError(
                f"网络错误 ({type(e).__name__}): {e}"
            )
        except Exception:
            # 未知异常，记录完整堆栈后重新抛出
            logger.error("多模态模型调用抛出未预期异常:\n%s", traceback.format_exc())
            raise

    # ==================== 提示词构建 ====================

    @staticmethod
    def _build_prompt(
        questions: list[dict],
        exam_title: str,
        grade: str,
    ) -> str:
        """构建发送给多模态模型的提示词（含布局+分数信息）"""
        total = len(questions)

        # 统计各题选项数、每题分数，构造题号-分值对照表
        question_lines = []
        score_map_entries = []
        score_total = 0
        for i, q in enumerate(questions):
            qnum = q.get("question_number", i + 1)
            q_type = q.get("type", "choice")
            options = q.get("options", [])
            opt_cnt = len(options) if isinstance(options, list) else 4
            opt_labels = "、".join(chr(65 + j) for j in range(min(opt_cnt, 8)))
            q_score = q.get("score", 0)
            score_total += q_score
            type_label = "选择题" if q_type == "choice" else "填空题" if q_type == "fill" else q_type
            question_lines.append(
                f"  第{qnum}题（{type_label}，{q_score}分）: 选项 {opt_labels}"
            )
            # 构造题号-分值JSON条目
            correct_answer = q.get("correct_answer", "")
            score_map_entries.append(
                f'    {{"question_number": {qnum}, "score": {q_score}, "type": "{q_type}", '
                f'"correct_answer": "{correct_answer}"}}'
            )

        # 构造题号-分值-正确答案对照JSON（供模型参考评分）
        score_map_json = "[\n" + ",\n".join(score_map_entries) + "\n  ]"

        # 考号填涂区详细布局说明（模型需要足够空间信息才能定位网格）
        layout_hint = (
            "答题卡布局说明：\n"
            "1. **考号填涂区** = 一个独立的矩形网格区域，与下面题目的答题区明显分开。\n"
            "   通常位于答题卡**左上角**或**顶部居中**，区域上方标注「考号」「学号」「准考证号」。\n"
            "2. **网格结构**：每个纵列代表考号的一位（第1列=考号第1位，第2列=考号第2位），共6~9列。\n"
            "   每列内从上到下排列10个小框，分别印有数字0,1,2,...,9（有时数字在框旁边）。\n"
            "3. **填涂识别**：学生用铅笔将对应数字的小框涂黑。已填涂的框呈现**深黑色**，\n"
            "   与周围未填涂的白色/浅色框形成鲜明对比。在每列中找出颜色最深的那个框，\n"
            "   它所在行对应的数字就是该位的值。\n"
            "4. **前导0**：如实保留所有前导0，如7位考号0012345不能写成12345。"
        )

        prompt = f"""你是一个专业的答题卡识别助手。请仔细观察这张答题卡照片，识别填涂的答案，并以JSON格式返回。

## 试卷信息
- 试卷名称：{exam_title or "未知试卷"}
- 适用年级：{grade or "未知"}
- 总题数：{total} 题
- 总分：{score_total} 分

## 题目配置（含每题分值）
{chr(10).join(question_lines)}

## 题号-分值-正确答案对照表（JSON）
```json
{score_map_json}
```
**说明**：上表中 correct_answer 为空表示该题答案尚未设置（如翻译题/填空题），
此时模型只需识别学生填写内容，不进行正误判断。若 correct_answer 有值，
则在识别学生答案后，与正确答案比对，正确则得分，错误则得0分。

## 答题卡布局参考
{layout_hint}

## 识别任务
1. **考号识别**（重要！请仔细执行）：
   a. 先在整个答题卡图片中寻找标有「考号」「学号」标签的网格区域
   b. 从左到右逐列扫描，每列代表考号的一位数字
   c. 在每列内部从上到下找：10个位置中哪个被涂黑了（深色框 = 该位数字）
   d. 按列顺序拼接所有位数字得到完整考号，保留前导0
2. **答案识别**：选择题找最深填涂框对应的字母（A/B/C/D），填空题/翻译题识别书写内容

## 输出格式（严格JSON，不要任何其他文字）
```json
{{
  "success": true,
  "exam_number": "识别出的完整考号数字（含前导0，若看不清则为空字符串）",
  "student_name": "",
  "answers": [
    {{"question_number": 1, "student_answer": "A", "is_correct": true, "score": 5, "confidence": 0.95}},
    {{"question_number": 2, "student_answer": "C", "is_correct": false, "score": 0, "confidence": 0.88}},
    {{"question_number": 3, "student_answer": "sun", "is_correct": null, "score": null, "confidence": 0.90}}
  ],
  "recognized_count": 有答案的题目数量,
  "total_score": 学生实际得分（整数，各题score之和）,
  "max_score": 试卷满分,
  "confidence_overall": 0.0到1.0之间的浮点数,
  "detail_summary": "简要识别与评分情况说明"
}}
```

**字段说明**：
- answers[].is_correct: correct_answer有值时填 true/false，无值时填 null（表示不判分）
- answers[].score: 该题学生实际得分（正确=该题满分，错误=0，不判分=null）
- total_score: 所有有判分题目的 score 之和
- max_score: 试卷满分（=总分）

## 注意事项
- 只输出JSON，不要任何额外文字
- 必须覆盖所有{total}道题，按question_number升序排列
- confidence: 清晰=0.85~1.0，模糊=0.5~0.7，未填涂/无法判断=student_answer=""、is_correct=false、score=0
- 选择题返回字母（如"A"），填空题返回文字内容
- 考号看不清时 exam_number 设为 ""
- 图片无法识别为答题卡时 success=false
- 评分：学生答案与correct_answer比对（忽略大小写和首尾空格），一致=该题满分，不一致=0分。correct_answer为空则不判分（is_correct=null, score=null）。
- 总分 = 有判分题score之和，满分 = {score_total}分
"""
        return prompt

    # ==================== 输出解析 ====================

    @staticmethod
    def _parse_model_output(raw_text: str, questions: list[dict]) -> dict:
        """
        解析多模态模型返回的文本，提取结构化 JSON

        处理模型可能返回的各种噪声：
        1. 直接 JSON
        2. ```json ... ``` 代码块包裹
        3. 前后有额外的解释文字
        """
        # 清洗文本
        text = raw_text.strip()

        # 尝试 1: 直接解析
        parsed = MultiModalGradingService._try_parse_json(text)
        if parsed:
            return MultiModalGradingService._validate_and_fix(parsed, questions)

        # 尝试 2: 提取 ```json ... ``` 代码块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            parsed = MultiModalGradingService._try_parse_json(json_match.group(1).strip())
            if parsed:
                return MultiModalGradingService._validate_and_fix(parsed, questions)

        # 尝试 3: 提取第一个 { 到最后一个 }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            json_str = text[first_brace:last_brace + 1]
            parsed = MultiModalGradingService._try_parse_json(json_str)
            if parsed:
                return MultiModalGradingService._validate_and_fix(parsed, questions)

        # 完全无法解析
        logger.error("无法从模型输出中提取JSON: %s", text[:300])
        return {
            "success": False,
            "error": f"无法解析模型输出: {text[:200]}",
            "exam_number": "",
            "answers": [],
            "recognized_count": 0,
            "total_score": 0,
            "max_score": 0,
            "confidence_overall": 0.0,
            "detail_summary": "模型输出格式异常",
            "duration_ms": 0,
        }

    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        """尝试解析 JSON 字符串，失败返回 None"""
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
            return None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _validate_and_fix(result: dict, questions: list[dict]) -> dict:
        """
        验证并修正模型输出的 JSON

        确保：
        1. 必要字段存在
        2. answers 覆盖所有题目（缺失题补充空答案）
        3. question_number 使用 int 类型
        """
        # 确保基本字段
        result.setdefault("success", True)
        result.setdefault("exam_number", "")
        result.setdefault("student_name", "")
        result.setdefault("confidence_overall", 0.0)
        result.setdefault("detail_summary", "")
        result.setdefault("duration_ms", 0)
        # 分值相关字段默认值
        result.setdefault("total_score", 0)
        result.setdefault("max_score", 0)

        raw_answers = result.get("answers", [])
        if not isinstance(raw_answers, list):
            raw_answers = []
            result["answers"] = raw_answers

        # 规范化每题答案：统一 question_number 为 int，确保必要字段存在
        normalized = {}
        for a in raw_answers:
            if not isinstance(a, dict):
                continue
            qnum = a.get("question_number", 0)
            try:
                qnum = int(qnum)
            except (ValueError, TypeError):
                continue
            # 提取模型返回的评分字段
            is_correct = a.get("is_correct")
            if is_correct is not None and not isinstance(is_correct, bool):
                is_correct = None  # 非布尔值当null处理
            score_val = a.get("score")
            if score_val is not None:
                try:
                    score_val = int(score_val)
                except (ValueError, TypeError):
                    score_val = None
            normalized[qnum] = {
                "question_number": qnum,
                "student_answer": str(a.get("student_answer", "")).strip().upper()
                if a.get("student_answer") else "",
                "confidence": float(a.get("confidence", 0.0)),
                "is_correct": is_correct,
                "score": score_val,
            }

        # 确保覆盖所有题目（缺失题补充空答案）
        answers = []
        recognized = 0
        for i, q in enumerate(questions):
            qnum = q.get("question_number", i + 1)
            if qnum in normalized:
                entry = normalized[qnum]
            else:
                entry = {
                    "question_number": qnum,
                    "student_answer": "",
                    "confidence": 0.0,
                    "is_correct": False,
                    "score": 0,
                }
            answers.append(entry)
            if entry["student_answer"]:
                recognized += 1

        result["answers"] = answers
        result["recognized_count"] = recognized

        return result

    # ==================== 错误结果 ====================

    @staticmethod
    def _error_result(message: str, start_time: float) -> dict:
        """构建错误结果"""
        return {
            "success": False,
            "error": message,
            "exam_number": "",
            "student_name": "",
            "answers": [],
            "recognized_count": 0,
            "total_score": 0,
            "max_score": 0,
            "confidence_overall": 0.0,
            "detail_summary": message,
            "duration_ms": int((time.time() - start_time) * 1000),
        }


# ==================== 自定义异常 ====================

class NotRetryableError(Exception):
    """
    不可重试的错误

    包括：认证失败(401)、权限不足(403)、内容被过滤、
    图片过大(413)、请求格式错误(422)等
    这些错误重试也不能解决，应立即返回给用户
    """
    pass


# ==================== 异步辅助 ====================

async def _async_sleep(seconds: float):
    """异步睡眠"""
    await _run_in_executor(lambda: time.sleep(seconds))


async def _run_in_executor(func):
    """在线程池中执行同步函数，避免阻塞事件循环"""
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)
