"""
AI 智能对话路由 — 提供无状态 Chat API，直接调用 LLM
集成「小e」英语学习助手身份 + 错题总结RAG
"""

import json
import re
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.ai_service import AIService
from app.services.rag_service import RAGService
from app.services.mistake_book_service import MistakeBookService
from app.services.scenario_prompts import SCENARIO_PRESETS, build_scenario_system_prompt
from app.schemas.common import ResponseData

router = APIRouter(prefix="/ai", tags=["AI对话"])


# ========== 小e 身份系统提示词 ==========

XIAO_E_SYSTEM_PROMPT = """你是小e，一个专业、亲切、充满活力的AI英语学习辅导助手。你的使命是帮助中国学生高效、有趣地学习英语。

## 核心原则
1. 身份定位：你是专属英语私教「小e」，风格热情、鼓励、有耐心，像朋友一样陪伴学习。你的所有回答必须围绕英语学习展开，你只能被用于英语学习场景。
2. 语言策略：以中文为主进行讲解和指导，在涉及例句、知识点说明时穿插英文。学生水平较低时多使用中文，水平较高时可适当增加英文比例。
3. 输出风格：清晰有条理，善用 Markdown 排版（标题、列表、加粗、代码块），让回复一目了然。
4. 学习导向：每个回答都要有教学价值——不仅回答问题，更要解释原理、给出记忆技巧或举一反三。

## 回答规范
- 知识点讲解要配合例句，例句附带中文翻译
- 语法点用表格或结构化方式表达，便于理解
- 多鼓励学生，对进步给予肯定
- 学生犯错误时温和纠正，并提供改进建议

## 可提供的服务
- 单词/语法/句型讲解
- 造句批改与润色
- 英语学习方法建议
- 错题分析与归纳（当用户询问错题时）
- 学习计划制定

## PPT 课件上下文处理
你可能会收到【PPT上下文】信息，这包含了学生当前正在学习的PPT课件页面的内容（如单词、对话、语法、练习题等）以及整个课程的科目、年级等信息。
- 你必须始终以英语学习助教的身份回答，无论学生问什么问题
- 充分利用 PPT 上下文提供的信息来理解学生正在学什么，然后给出针对性的讲解和扩展
- 学生可能提问与当前PPT页面内容直接相关的问题（如"解释这个语法"、"这个单词怎么用"），也可能问其他英语学习问题
- 如果学生问的问题明显偏离英语学习（如数学题、编程、常识问答等），你有责任温和地将话题引导回英语学习，可以说"我是你的英语学习助手小e，让我们聚焦在英语学习上吧！"然后尝试从英语角度回答或给出英语学习建议
- ⚠️ 严禁将自己当作通用AI助手！你的身份只有一个：英语学习私教「小e」"""


class ChatRequest(BaseModel):
    """AI 对话请求"""
    messages: list[dict]  # [{"role": "user"/"assistant", "content": "..."}]
    scenario: str = ""    # 预设场景ID（如"coffee"），或 JSON 格式的 {"scene_desc":"...", "user_role":"...", "level":"..."}
    provider: str = "cloudbase"
    model: str = ""
    level: str = "intermediate"  # beginner / intermediate / advanced


# 错题总结意图关键词
_ERROR_SUMMARY_KEYWORDS = [
    "错题", "错题本", "错题报告", "错题总结",
    "总结错题", "汇总错题", "分析错题",
    "这周", "本周", "这个月", "本月", "这学期",
    "薄弱", "弱项", "知识盲区",
    "考试", "测验", "试卷", "exam", "test",
]


def _is_error_summary_request(text: str) -> bool:
    """判断用户是否在请求错题总结"""
    text_lower = text.lower()
    # 必须包含"错题"或"总结"+"错题"或"报告"+"错题"等核心词
    has_error_core = any(kw in text_lower for kw in ["错题", "mistake", "wrong", "错题本", "错题报告"])
    has_summary_core = any(kw in text_lower for kw in ["总结", "汇总", "报告", "分析", "summary", "report"])
    if has_error_core or has_summary_core:
        return True
    # 同时包含多个关键词也触发
    match_count = sum(1 for kw in _ERROR_SUMMARY_KEYWORDS if kw in text_lower)
    return match_count >= 2


def _extract_error_summary_params(text: str) -> dict:
    """从用户问题中提取错题总结参数"""
    params = {"exam_name": None, "days": None, "include_vocab": True}

    # 检测考试相关的查询（exam_name 在关键字前： "总结测试1试卷错题" → "测试1"）
    exam_patterns = [
        # 1) "总结/分析【考试名】考试/试卷/测验"
        r"(?:总结|分析|查看)(?:.*?)([\u4e00-\u9fff\w]+?)(?:考试|测验|试卷)(?:的错题|错题|的总结|)?$",
        # 2) "考试/试卷/测验【考试名】的错题"
        r"(?:考试|测验|试卷|exam|test)[：: ]*([\u4e00-\u9fff\w]+?)(?:的错题|错题|总结|报告|分析|$)",
    ]
    text_lower = text.lower()
    for pattern in exam_patterns:
        m = re.search(pattern, text_lower)
        if m:
            exam_name = m.group(1).strip()
            if exam_name and exam_name not in ("考试", "测验", "试卷", "exam", "test", "错题", "错题本"):
                params["exam_name"] = exam_name
                break

    # 检测时间范围
    week_patterns = [r"(?:这周|本周|这星期|本周|上周)"]
    month_patterns = [r"(?:这个月|本月|上个月)"]
    for p in week_patterns:
        if re.search(p, text_lower):
            params["days"] = 7
            break
    for p in month_patterns:
        if re.search(p, text_lower):
            params["days"] = 30
            break

    # 检测是否排除单词训练
    if params["exam_name"]:
        # 指定了具体考试 → 只总结考试错题，不包含单词训练
        params["include_vocab"] = False
    elif "只" in text_lower and ("考试" in text_lower or "试卷" in text_lower):
        params["include_vocab"] = False

    return params


@router.post("/chat", response_model=ResponseData)
async def ai_chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 对话 — 支持情景对话模式 + 智能错题总结"""
    messages = body.messages

    # 情景对话：注入场景 system prompt
    if body.scenario:
        scenario_config = _resolve_scenario(body.scenario, body.level)
        if scenario_config:
            system_prompt = build_scenario_system_prompt(
                scene_desc=scenario_config["scene_desc"],
                user_role=scenario_config["user_role"],
                level=body.level,
            )
            if not messages or messages[0].get("role") != "system":
                messages = [{"role": "system", "content": system_prompt}] + messages
            result = await AIService.chat_completion(db, messages, user_id)
            return ResponseData(data={"content": result})
    else:
        # 非情景对话 → 注入小e身份系统提示词
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": XIAO_E_SYSTEM_PROMPT}] + messages
        else:
            # 已有 system message（如 PPT 上下文），将小e身份合并到其中
            existing_system = messages[0]["content"]
            if "PPT上下文" in existing_system or "【PPT" in existing_system:
                messages[0]["content"] = XIAO_E_SYSTEM_PROMPT + "\n\n---\n" + existing_system

    # 检测错题总结意图
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    if last_user_msg and _is_error_summary_request(last_user_msg):
        params = _extract_error_summary_params(last_user_msg)
        try:
            report = await RAGService.generate_error_summary_report(
                db=db,
                user_id=user_id,
                exam_name=params["exam_name"],
                days=params["days"],
                include_vocab=params["include_vocab"],
                user_query=last_user_msg,
            )
            # 自动保存报告到错题本（小e总结类）
            title_parts = ["小e总结"]
            if params["days"] == 7:
                title_parts.append("本周")
            elif params["days"] == 30:
                title_parts.append("本月")
            elif params["exam_name"]:
                title_parts.append(f"「{params['exam_name']}」")
            from datetime import datetime
            title_parts.append(str(datetime.now())[:10])
            title = " · ".join(title_parts) + " 错题报告"
            try:
                await MistakeBookService.save_summary_report(
                    db=db,
                    user_id=user_id,
                    title=title,
                    content=report,
                    exam_name=params.get("exam_name") or "",
                    days=params.get("days") or 0,
                )
                await db.commit()
            except Exception as save_err:
                print(f"[AI] 保存错题报告失败: {save_err}")
            return ResponseData(data={"content": report})
        except Exception as e:
            # 如果错题总结失败，fallback 到普通对话
            print(f"[AI] 错题总结失败，fallback到普通对话: {e}")

    result = await AIService.chat_completion(db, messages, user_id)
    return ResponseData(data={"content": result})


@router.get("/scenarios", response_model=ResponseData)
async def list_scenarios():
    """获取情景对话预设场景列表"""
    presets = []
    for s in SCENARIO_PRESETS:
        presets.append({
            "id": s["id"],
            "name": s["name"],
            "icon": s["icon"],
        })
    return ResponseData(data={"presets": presets})


@router.get("/scenario-detail", response_model=ResponseData)
async def get_scenario_detail(scenario_id: str = ""):
    """获取指定场景的详细信息（含完整场景描述）"""
    for s in SCENARIO_PRESETS:
        if s["id"] == scenario_id:
            return ResponseData(data=s)
    return ResponseData(code=1, message="场景不存在")


def _resolve_scenario(scenario: str, level: str = "intermediate") -> dict | None:
    """解析场景参数，返回 {scene_desc, user_role}"""
    # 尝试 JSON 格式：自定义场景
    try:
        parsed = json.loads(scenario)
        if isinstance(parsed, dict) and "scene_desc" in parsed and "user_role" in parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # 预设场景ID
    for s in SCENARIO_PRESETS:
        if s["id"] == scenario:
            return {"scene_desc": s["scene_desc"], "user_role": s["user_role"]}

    return None
