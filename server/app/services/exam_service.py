# AI 出卷 + AI 批卷核心服务
import asyncio
import json
import logging
import math
import re
import traceback

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from sqlalchemy.orm.attributes import flag_modified
from starlette.concurrency import run_in_threadpool
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.services.document_service import (
    STAGE_QUESTION_TYPES, STAGE_TEACHING_STYLES,
    QUESTION_TYPE_LABELS, infer_stage_from_grade,
)
from app.models.exam_models import TeacherExam, ExamSubmission, ExamGradingLog, AnswerSheetTemplate
from app.models.scan_models import ExamScanRecord
from app.services.exam_result_state import effective_time, paper_readiness, paper_source_exam_ids, paper_state, result_state
from app.utils.revisions import is_paper_draft, template_revision
from app.models.class_models import Class, ClassStudent, ClassStudentInfo, ClassTeacher
from app.models.user import User
from app.utils.redis_client import get_redis, RedisCache
from app.services.answer_sheet_generator import (
    _build_computed_regions, _make_digit_labels, _make_option_letters,
    save_answer_sheet_html, save_answer_sheet_html_from_json,
    _build_computed_regions_from_json,
    _build_graderflow_regions, save_graderflow_sheet_html,
    save_graderflow_sheet_html_from_json,
)

# Agent integration — AI generation logic delegated to agent module
# from agent.agents.exam_agent import ExamAgent  # uncomment to use agent

# 题型定义
QUESTION_TYPES = {
    "choice": "选择题",
    "fill": "填空题",
    "translation": "翻译题",
    "reading": "阅读理解",
    "cloze": "完形填空",
    "seven_choice": "七选五",
    "grammar_fill": "语法填空",
    "writing": "写作题",
    "applied_writing": "应用写作",
    "continuation_writing": "读后续写",
    "listening": "听力题",
}

# 批改维度（写作）
WRITING_DIMENSIONS = ["内容完整性", "语法正确性", "词汇丰富度", "结构逻辑", "拼写标点"]


def _extract_json(text: str) -> dict:
    """从 AI 响应文本中健壮地提取 JSON 对象

    处理以下常见问题:
    - 代码块包裹 ```json ... ```
    - 多余的前导/尾部文本
    - JSON 内未转义的特殊字符
    - 尾部逗号
    - 多个代码块
    """
    cleaned = text.strip()
    print(f"[JSON DEBUG] 原始响应前 500 字符: {cleaned[:500]}", flush=True)

    # 1) 尝试找 ```json 或 ``` 代码块
    if "```" in cleaned:
        parts = cleaned.split("```")
        # 优先找标记了 json 的代码块
        for i, part in enumerate(parts):
            stripped = part.strip()
            if stripped.startswith("json"):
                content = stripped[4:].strip()
                print(f"[JSON DEBUG] 从 json 代码块中提取: {content[:300]}", flush=True)
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"[JSON DEBUG] json 代码块解析失败: {e}", flush=True)
                    cleaned = content
                    break
        else:
            # 没有找到 json 标记，取第一个非空代码块
            for part in parts:
                stripped = part.strip()
                if stripped and not stripped.startswith("```"):
                    print(f"[JSON DEBUG] 从代码块中提取: {stripped[:300]}", flush=True)
                    try:
                        return json.loads(stripped)
                    except json.JSONDecodeError as e:
                        print(f"[JSON DEBUG] 普通代码块解析失败: {e}", flush=True)
                        cleaned = stripped
                        break

    # 2) 尝试直接解析整段文本
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # ---- 括号匹配辅助函数 ----
    def _find_matching_brace(text: str, open_idx: int) -> int | None:
        """找到与 open_idx 处 '{' 匹配的 '}' 位置（跳过字符串内部的括号）"""
        depth = 0
        in_str = False
        esc = False
        for j in range(open_idx, len(text)):
            c = text[j]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"' and not esc:
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j
        return None

    def _try_parse(text: str) -> dict | None:
        """尝试用四种策略解析 JSON，返回解析结果或 None"""
        for loads_fn in [
            lambda s: json.loads(s),
            lambda s: json.loads(_fix_json_string(s)),
            lambda s: json.loads(s, strict=False),
            lambda s: json.loads(_fix_json_string(s), strict=False),
        ]:
            try:
                r = loads_fn(text)
                if isinstance(r, dict):
                    return r
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    # 2.5) 直接搜索 "questions" 键 — 绕开括号匹配无法定位最外层 {} 的问题
    questions_key_pos = cleaned.find('"questions"')
    if questions_key_pos != -1:
        outer_start = cleaned.rfind("{", 0, questions_key_pos)
        if outer_start != -1:
            outer_end = _find_matching_brace(cleaned, outer_start)
            if outer_end is not None:
                outer_text = cleaned[outer_start:outer_end + 1]
                result = _try_parse(outer_text)
                if result is not None and "questions" in result:
                    print(f"[JSON DEBUG] 按 questions 键定位提取成功, 长度 {len(outer_text)}", flush=True)
                    return result
            # 如果 bracket matching 失败或 _try_parse 失败，再次尝试 rindex 方式
            try:
                last_close = cleaned.rindex("}")
                first_open = cleaned.index("{")
                trimmed = cleaned[first_open:last_close + 1]
                result2 = _try_parse(trimmed)
                if result2 is not None and "questions" in result2:
                    print(f"[JSON DEBUG] questions 键定位 + rindex 方式成功", flush=True)
                    return result2
            except (ValueError, json.JSONDecodeError):
                pass

    # 2.6) outer wrapper 解析失败时，逐题提取 questions 数组内的题目对象
    # AI 响应中的阅读理解 passage 等长文本可能含未转义字符导致外层 JSON 解析失败，
    # 但单个题目对象仍是合法 JSON。此策略逐个提取并组合。
    if questions_key_pos != -1:
        try:
            arr_start = cleaned.find("[", questions_key_pos)
            if arr_start != -1:
                arr_end = cleaned.rfind("]")
                if arr_end != -1 and arr_end > arr_start:
                    parsed_questions = []
                    pos = arr_start + 1
                    while True:
                        obj_start = cleaned.find("{", pos)
                        if obj_start == -1 or obj_start > arr_end:
                            break
                        obj_end = _find_matching_brace(cleaned, obj_start)
                        if obj_end is None or obj_end > arr_end:
                            break
                        q_text = cleaned[obj_start:obj_end + 1]
                        q = _try_parse(q_text)
                        if q is not None and isinstance(q, dict):
                            parsed_questions.append(q)
                        pos = obj_end + 1

                    if len(parsed_questions) > 0:
                        print(f"[JSON DEBUG] 逐题提取成功, 共 {len(parsed_questions)} 题", flush=True)
                        return {"questions": parsed_questions}
        except Exception as e:
            print(f"[JSON DEBUG] 逐题提取失败: {e}", flush=True)

    # 3) 括号匹配 — 找所有被外层 {} 包裹的 JSON 候选
    # 找所有可能的 JSON 对象起始位置
    json_candidates = []
    search_pos = 0
    while True:
        obj_start = cleaned.find("{", search_pos)
        if obj_start == -1:
            break
        obj_end = _find_matching_brace(cleaned, obj_start)
        if obj_end is not None:
            candidate = cleaned[obj_start:obj_end + 1]
            json_candidates.append(candidate)
            search_pos = obj_end + 1
        else:
            search_pos = obj_start + 1

    print(f"[JSON DEBUG] 括号匹配找到 {len(json_candidates)} 个 JSON 候选", flush=True)

    # 第一轮：按长度降序，优先找有 questions 键的候选
    json_candidates.sort(key=len, reverse=True)
    for idx, candidate in enumerate(json_candidates):
        if idx < 5:
            print(f"[JSON DEBUG] 候选 {idx} (长度 {len(candidate)}): {candidate[:200]}", flush=True)
        result = _try_parse(candidate)
        if result is not None and "questions" in result:
            print(f"[JSON DEBUG] 选中候选 {idx}（含 questions 键）", flush=True)
            return result

    # 第二轮：找任意可解析的 JSON 对象（无 questions 键也可）
    for idx, candidate in enumerate(json_candidates):
        result = _try_parse(candidate)
        if result is not None:
            print(f"[JSON DEBUG] 备用选中候选 {idx}（无 questions 键）", flush=True)
            return result

    # 4) 终极回退：用 rindex 从尾部找最后一个完整的 {} 对象
    try:
        last_close = cleaned.rindex("}")
        last_open = cleaned.rindex("{", 0, last_close)
        final_fragment = cleaned[last_open:last_close + 1]
        print(f"[JSON DEBUG] 终极回退截取: {final_fragment[:300]}", flush=True)
        fixed = _fix_json_string(final_fragment)
        try:
            return json.loads(fixed, strict=False)
        except json.JSONDecodeError:
            return json.loads(fixed)
    except (ValueError, json.JSONDecodeError):
        pass

    # 5) 尝试修复截断的 JSON（AI 输出被 token 限制截断时）
    try:
        print(f"[JSON DEBUG] 尝试修复截断 JSON", flush=True)
        truncated = _try_complete_json(cleaned)
        result = _try_parse(truncated)
        if result is not None:
            print(f"[JSON DEBUG] 截断修复成功", flush=True)
            return result
    except Exception as e:
        print(f"[JSON DEBUG] 截断修复失败: {e}", flush=True)

    raise json.JSONDecodeError(f"Cannot extract valid JSON", cleaned[:200], 0)


def _try_complete_json(text: str) -> str:
    """尝试修复被截断的 JSON：找到最外层完整对象，补全缺少的 ]}} 等

    当 AI 输出被 token 限制截断时，JSON 末尾可能缺少 } ] 等字符。
    此函数会计算大括号和方括号的差额，补全缺失的符号。
    还会移除尾部的非 JSON 字符（如多余的文本）。
    """
    # 找第一个 { 和最后一个 }（如果存在）
    first_brace = text.find("{")
    if first_brace == -1:
        # 没有找到 {，尝试找 [
        first_bracket = text.find("[")
        if first_bracket == -1:
            return text
        # JSON 是数组
        content = text[first_bracket:]
    else:
        # 找最后一个 }，可能不存在（截断了）
        last_brace = text.rfind("}")
        if last_brace != -1 and last_brace > first_brace:
            content = text[first_brace:last_brace + 1]
        else:
            content = text[first_brace:]

    # 统计花括号和方括号的差额
    open_braces = 0   # {
    open_brackets = 0  # [
    in_str = False
    escape = False
    for ch in content:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1

    # 补全缺少的闭符号
    result = content
    result += "]" * open_brackets
    result += "}" * open_braces

    if result != content:
        print(f"[JSON DEBUG] 补全了 {open_brackets} 个 ] 和 {open_braces} 个 }}", flush=True)

    return result





def _fix_json_string(s: str) -> str:
    """启发式修复 JSON 字符串中常见的格式问题

    只修正字符串值内部的问题，不破坏 JSON 结构。
    """
    # 1) 修复键名（无引号的键名）
    s = re.sub(r"(?<![\\\"\w])(\w+)(?=\s*:)", r'"\1"', s)

    # 2) 只修复字符串值内部的未转义控制字符
    # 原理：遍历字符串，在字符串值内部进行替换
    result = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch in "\r\n\t":
            # 字符串内部的未转义控制字符 -> 转义为 \\r \\n \\t
            if ch == "\r":
                result.append("\\r")
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\t":
                result.append("\\t")
            continue
        result.append(ch)

    return "".join(result)


class ExamService:
    """考试服务：AI 出卷、AI 批卷、成绩汇总"""

    # ===================== 出卷 =====================

    @staticmethod
    async def _fetch_rag_references(
        db: AsyncSession,
        teacher_id: int,
        stage_category: str,
        source_type_pattern: str,
        title: str = "",
        knowledge_points: list[str] | None = None,
        question_types: list[str] | None = None,
        top_k: int = 5,
    ) -> list[str]:
        """从 Milvus 检索参考文档片段

        构建动态查询语义，融合标题、知识点和题型关键词，
        使用 hybrid_search 提升召回质量。
        """
        kps = knowledge_points or []
        qt_labels = [QUESTION_TYPES.get(t, t) for t in (question_types or [])]
        query_parts = [title, "英语试卷 题目 考试题"]
        if kps:
            query_parts.extend(kps)
        if qt_labels:
            query_parts.extend(qt_labels)
        query = " ".join(p for p in query_parts if p)

        results = await EmbeddingService.hybrid_search(
            db, query, EmbeddingService.TEACHER_DOCUMENTS,
            top_k=top_k, user_id=teacher_id,
            stage=stage_category,
            source_type=source_type_pattern,
        )
        return [r["content"] for r in results]

    # ===================== 方案 A：按题型并行生成 =====================

    @staticmethod
    def _build_type_system_prompt(
        qtype: str, count: int, grade: str, difficulty: int,
        difficulty_names: dict, is_senior: bool,
        rag_text: str, extra_ref: str, kps: list[str],
    ) -> str:
        """为单题型构建轻量级 system prompt（仅含该题型模板）"""
        base = (
            "你是一个专业的英语试卷出题AI。\n"
            f"请生成 {count} 道{QUESTION_TYPES.get(qtype, qtype)}，难度{difficulty_names.get(difficulty, '中等')}。\n"
            "要求：\n"
            "1. 题目难度适中，符合给定的年级\n"
            f"2. 必须恰好生成 {count} 道，不得多出或少出\n"
            "3. 每题包含标准答案和详细解析\n"
            "4. 选择题给出4个选项(A/B/C/D)\n"
            "5. 题干中的引号用\\\"转义，不得使用中文引号"
        )
        if grade:
            base += f"\n6. 适用年级：{grade}"

        if rag_text:
            base += rag_text
        if extra_ref:
            base += extra_ref

        base += "\n9. 【重要】不要在 stem 或文章正文中包含任何题号或序号（如1.、2.、第一段、第一篇等），系统会自动为整张试卷统一编号。"
        base += "\n10. 【重要】不要在选项文本中包含字母前缀（如A.、B.、C.、D.等），选项只需提供纯文本内容，系统会自动为每个选项添加A. B. C. D.字母标签。"

        # 各题型的 JSON 模板（仅该题型，极简）
        if qtype == "choice":
            template = (
                "\n\n请按以下JSON格式返回（仅该题型，不要其他内容）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "choice",\n'
                '      "difficulty": 2,\n'
                '      "stem": "题干（英文）",\n'
                '      "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
                '      "answer": "A",\n'
                '      "explanation": "解析",\n'
                '      "score": 2,\n'
                '      "knowledge_point": "语法-时态"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n每个题目对象必须包含 type、stem、options、answer、explanation、knowledge_point 字段。"
            )
        elif qtype == "reading":
            sub_qty = "3-4" if is_senior else "5"
            template = (
                "\n\n请按以下JSON格式返回（每篇含 passage + sub_questions）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "reading",\n'
                '      "difficulty": 2,\n'
                '      "passage": "阅读理解文章正文（300-500词，分4段以上，有实质内容，不得为空）",\n'
                '      "sub_questions": [\n'
                "        {\n"
                '          "stem": "第1道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "A",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        }"
              f"  // 共{sub_qty}题\n"
                "      ],\n"
                '      "score": 10,\n'
                '      "knowledge_point": "阅读理解-主旨大意"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                f"\n重要：每篇必须包含 {sub_qty} 道子题（sub_questions），passage 不得为空。"
            )
        elif qtype == "cloze":
            template = (
                "\n\n请按以下JSON格式返回（每道完形题为一篇短文，设15空，每空4个选项）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "cloze",\n'
                '      "difficulty": 2,\n'
                '      "stem": "完形填空文章正文（约400-500词），文中每个空白位置必须嵌入____标记（不能遗漏任何空白），注意：首句不设空。文章是完整的叙事或说明文，有明确语境。每个空格涉及时态变化、固定搭配、介词辨析、词义辨析等考点。",\n'
                '      "options": [\n'
                '        ["finished","designed","followed","changed"],\n'
                '        ["delay","chance","trouble","excuse"],\n'
                '        ["judge","volunteer","classmate","competitor"],\n'
                '        ["race","school","town","training"],\n'
                '        ["agreed","returned","stopped","promised"]\n'
                "      ],\n"
                '      "answers": ["D","A","D","A","C"],\n'
                '      "explanations": ["解析1","解析2","解析3","解析4","解析5"],\n'
                '      "score": 15,\n'
                '      "knowledge_point": "完形填空-语境推断"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：\n"
                "1. 每篇短文设15个空，首句不设空，空格间距至少5个词以上。文章正文中每个空位必须用____标记，不得遗漏！\n"
                "2. options 是二维数组，长度为15，每空对应一组4个选项（A/B/C/D）\n"
                "3. 每空选项必须是用真实英语词汇/短语的4选1，不能是占位符\n"
                "4. 考查点涉及时态变化、固定搭配、介词辨析、语境词义辨析、非谓语动词等\n"
                "5. 干扰项要具有迷惑性，不能明显错误\n"
                "6. 【重要】选项只需提供纯文本内容，不要包含A. B. C. D.等字母前缀"
            )
        elif qtype == "writing":
            template = (
                "\n\n请按以下JSON格式返回：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "writing",\n'
                '      "difficulty": 2,\n'
                '      "stem": "写作题目要求（中文，含背景和要求）",\n'
                '      "score": 25,\n'
                '      "knowledge_point": "写作-应用文"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：写作题只需 stem（含明确的中文写作背景和要求），不需要 options/answer/explanation。"
            )
        elif qtype == "applied_writing":
            template = (
                "\n\n请按以下JSON格式返回（应用写作，15分）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "applied_writing",\n'
                '      "difficulty": 2,\n'
                '      "stem": "写作题目要求（中文，含情景背景和写作要求），例如：假定你是李华，外教Ryan准备将学生随机分为两人一组，让大家课后练习口语，你认为这样分组存在问题。请你给外教写一封邮件，内容包括：1. 说明问题；2. 提出建议。写作词数应为80个左右。",\n'
                '      "score": 15,\n'
                '      "knowledge_point": "写作-应用文"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：\n"
                "1. stem 包含完整的中文写作背景和要求，明确写作场景和要点\n"
                "2. 写作类型：回信、写报道、写评论文、邮件、通知、演讲稿等\n"
                "3. 词数80词左右\n"
                "4. 不需要 options/answer/explanation"
            )
        elif qtype == "continuation_writing":
            template = (
                "\n\n请按以下JSON格式返回（读后续写，25分）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "continuation_writing",\n'
                '      "difficulty": 2,\n'
                '      "stem": "读后续写题目（包含完整的前文阅读材料，350词以上，不要分过多段落（建议3-4段）），必须包含：\\n1. 前文材料：一篇完整的记叙文前文，有情节发展、人物情感变化和冲突转折\\n2. 注意：续写词数应为150个左右\\n3. 已给出两段段落开头语，不能改动\\n题目格式示例：\\n阅读下面材料，根据其内容和所给段落开头语续写两段，使之构成一篇完整的短文。\\n[此处是前文材料，总字数350词以上]\\n注意：\\n1. 续写词数应为150个左右；\\n2. 请按如下格式在答题卡的相应位置作答。\\n[段落1开头语]\\n[段落2开头语]",\n'
                '      "score": 25,\n'
                '      "knowledge_point": "写作-读后续写"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：\n"
                "1. stem 包含完整的前文阅读材料（记叙文，总字数350词以上，段落数适中不宜过多，有完整情节发展和情感变化）\n"
                "2. 已给出两段段落开头语，不可修改\n"
                "3. 续写总词数150词左右\n"
                "4. 续写必须包含：动作描写、心理描写、环境烘托、对话/间接引语\n"
                "5. 不需要 options/answer/explanation"
            )
        elif qtype == "seven_choice":
            template = (
                "\n\n请按以下JSON格式返回（每道为1篇短文，5个空，7个选项）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "seven_choice",\n'
                '      "difficulty": 2,\n'
                '      "stem": "七选五文章正文（约400-500词），文章中的空白用____标记（如____36____）。文章是完整的说理性文章（如自我成长/学习方法/人际关系/心理健康），有完整逻辑，分4-5段。",\n'
              '      "options": [\n'
              '        "A little self-forgiveness also goes a long way.",\n'
              '        "Now list all the characteristics you like about yourself.",\n'
              '        "They might even like to have a go at doing the exercise.",\n'
              '        "It\'s just as important to show yourself some forgiveness.",\n'
              '        "It doesn\'t mean you have to ignore what\'s happened or forget it.",\n'
              '        "Whatever it is, no matter how small it might seem, write it down.",\n'
              '        "Whatever the mistake, remember it isn\'t a fixed aspect of your personality."\n'
              "      ],\n"
                '      "answers": ["C","B","F","A","G"],\n'
                '      "explanations": ["解析1","解析2","解析3","解析4","解析5"],\n'
                '      "score": 12.5,\n'
                '      "knowledge_point": "七选五-篇章结构"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：\n"
                "1. stem 是一篇约400-500词的完整短文，用____标记5处空白（空白要标注题号如____36____）\n"
                "2. options 包含7个选项(A-G)，每个选项是**一句完整的英文句子**（不能是单词或短语），其中2个为多余干扰项。选项内容不能包含A. B. C.等字母前缀，只需纯文本。\n"
                "3. answers 为5个正确选项字母的数组\n"
                "4. 空格位置分布：段首至少1个、段中至少2个、段尾至少1个\n"
                "5. 干扰项特征：与文中某处词汇相似但逻辑不通，或过于宽泛/片面\n"
                "6. 所有选项必须是完整的英语句子，有主语和谓语，独立成句"
            )
        elif qtype == "grammar_fill":
            template = (
                "\n\n请按以下JSON格式返回：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "grammar_fill",\n'
                '      "difficulty": 2,\n'
                '      "stem": "语法填空文章正文（约200词），其中有10处空白用____标记。有提示词的空格写成____(hint_word)，无提示词的空格只写____。",\n'
                '      "answers": ["答案1","答案2","答案3","答案4","答案5","答案6","答案7","答案8","答案9","答案10"],\n'
                '      "hints": ["present","","","","reveal","","","strategy","",""],\n'
                '      "score": 15,\n'
                '      "knowledge_point": "语法填空-词形变化"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n注意：\n"
                "1. stem 是一篇约200词的完整短文，用____标记10处空白\n"
                "2. 有提示词的空白在____后加括号给出提示词，如：____(present)\n"
                "3. 约6-7个空白有提示词（动词时态/语态/非谓语/词性转换），约3-4个无提示词（冠词/介词/连词/关系代词）\n"
                "4. answers 为10个答案的数组，按空白顺序排列\n"
                "5. hints 为10个元素的数组，有提示词时放提示词，无提示词时放空字符串\n"
                "6. 文章题材：中国传统文化/人物故事/科技发展/社会现象"
            )
        elif qtype == "fill":
            template = (
                "\n\n请按以下JSON格式返回（每个题目为独立填空，用于词汇/语法单项填空）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "fill",\n'
                '      "difficulty": 1,\n'
                '      "stem": "填空题题干（含____空白）",\n'
                '      "answer": "正确答案",\n'
                '      "explanation": "解析",\n'
                '      "score": 2,\n'
                '      "knowledge_point": "词汇-固定搭配"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n每个题目对象必须包含 type、stem、answer、explanation、knowledge_point 字段。"
            )
        elif qtype == "translation":
            template = (
                "\n\n请按以下JSON格式返回：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "translation",\n'
                '      "difficulty": 2,\n'
                '      "stem": "待翻译的中文句子或段落",\n'
                '      "answer": "参考英文翻译",\n'
                '      "explanation": "解析（翻译要点说明）",\n'
                '      "score": 5,\n'
                '      "knowledge_point": "翻译-中译英"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "\n每个题目必须包含 type、stem（中文待翻译内容）、answer（英文翻译）、explanation（解析）。"
            )
        else:
            # 通用模板
            template = (
                "\n\n请按以下JSON格式返回：\n"
                '{"questions": [{"type": "' + qtype + '", "stem": "题干", "answer": "答案", "explanation": "解析", "score": 2}]}\n'
            )

        return base + template

    @staticmethod
    def _build_type_user_prompt(
        qtype: str, count: int, title: str, grade: str,
        stage_category: str, kps: list[str], difficulty: int,
        difficulty_names: dict,
    ) -> str:
        """为单题型构建 user prompt"""
        grade_desc = f"适用年级：{grade}\n" if grade else ""
        stage_desc = STAGE_TEACHING_STYLES.get(stage_category, "")
        if stage_desc:
            stage_desc = f"学段风格：{stage_desc}\n"
        passage_types = {"reading", "cloze", "seven_choice", "grammar_fill"}
        unit = "篇" if qtype in passage_types else "道"

        return (
            f"请为以下英语考试生成试卷题目：\n"
            f"标题：{title}\n"
            f"{grade_desc}"
            f"{stage_desc}"
            f"知识点：{', '.join(kps)}\n"
            f"题型：{QUESTION_TYPES.get(qtype, qtype)}\n"
            f"数量：{count}{unit}\n"
            f"难度：{difficulty_names.get(difficulty, '中等')}\n\n"
            f"请严格按要求的 JSON 格式返回，恰好生成 {count}{unit}，不要多出或少出。"
        )

    @staticmethod
    async def _generate_type(
        db: AsyncSession,
        teacher_id: int,
        qtype: str,
        count: int,
        title: str = "",
        knowledge_points: list[str] | None = None,
        difficulty: int = 2,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
    ) -> list[dict]:
        """为单个题型调用 AI 生成题目，带自动重试"""
        kps = knowledge_points or []
        difficulty_names = {1: "简单", 2: "中等", 3: "困难"}
        is_senior = (stage_category == "senior")

        # 构建 RAG 参考
        rag_text = ""
        if use_rag:
            refs = await ExamService._fetch_rag_references(
                db, teacher_id, stage_category, "doc_exam",
                title=title, knowledge_points=kps,
                question_types=[qtype],
                top_k=3,
            )
            if refs:
                ref_text = "\n\n".join([f"[参考{QUESTION_TYPES.get(qtype, qtype)} {i+1}]\n{r[:500]}" for i, r in enumerate(refs)])
                rag_text = f"\n\n以下是参考题目（请参考其难度和考察方式）：\n{ref_text}"

        extra_ref = ""
        if additional_references:
            extra_ref = f"\n\n用户补充参考：\n{additional_references[:2000]}"

        system_prompt = ExamService._build_type_system_prompt(
            qtype, count, grade, difficulty, difficulty_names,
            is_senior, rag_text, extra_ref, kps,
        )
        user_prompt = ExamService._build_type_user_prompt(
            qtype, count, title, grade, stage_category,
            kps, difficulty, difficulty_names,
        )

        # 题型专属 max_tokens
        passage_types = {"reading", "cloze", "seven_choice", "grammar_fill"}
        type_max_tokens = {
            "choice": 8192,
            "reading": 32768,
            "cloze": 16384,
            "seven_choice": 16384,
            "grammar_fill": 12288,
            "writing": 4096,
            "fill": 8192,
            "translation": 8192,
        }
        max_tokens = type_max_tokens.get(qtype, 16384)
        # 篇章类题型需要更长的超时
        passage_types = {"reading", "cloze", "seven_choice", "grammar_fill"}
        timeout = 240.0 if qtype in passage_types else 180.0

        # ── 阅读理解特殊处理：每篇单独调用一次，避免一次性生成多篇导致文章过短 ──
        if qtype == "reading" and count > 1:
            return await ExamService._generate_reading_passages_separately(
                db, teacher_id, count, title, kps, difficulty,
                grade, stage_category, is_senior,
                rag_text, extra_ref, timeout, max_tokens,
            )

        all_questions = []
        last_error = None

        for attempt in range(2):  # 最多重试1次
            if attempt == 0:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            else:
                # 重试：告诉 AI 缺少多少题
                existing_count = len(all_questions)
                missing = count - existing_count
                if missing <= 0:
                    break
                passage_types = {"reading", "cloze", "seven_choice", "grammar_fill"}
                unit = "篇" if qtype in passage_types else "道"
                retry_prompt = (
                    f"你只生成了 {existing_count}{unit}，"
                    f"还需 {missing}{unit}。请只生成缺失的 {missing}{unit}，"
                    f"不要重复已有题目。按之前的 JSON 格式返回。"
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": retry_prompt},
                ]

            response = await AIService.chat_completion(
                db, messages, teacher_id,
                timeout_seconds=timeout,
                max_tokens=max_tokens,
            )
            print(f"[EXAM TYPE:{qtype}] 第{attempt}次调用 | 响应长度={len(response)}", flush=True)

            try:
                exam_data = _extract_json(response)
            except (json.JSONDecodeError, IndexError) as e:
                print(f"[EXAM TYPE:{qtype}] 解析失败: {e}", flush=True)
                last_error = str(e)
                continue

            new_qs = (exam_data.get("questions") or exam_data.get("question")
                      or exam_data.get("items") or [])
            if not isinstance(new_qs, list):
                new_qs = []

            if not new_qs:
                print(f"[EXAM TYPE:{qtype}] 响应中 questions 为空", flush=True)
                continue

            # 去重
            seen = {q.get("stem", "")[:60] or q.get("passage", "")[:60] for q in all_questions}
            for q in new_qs:
                key = q.get("stem", "")[:60] or q.get("passage", "")[:60]
                if key not in seen:
                    all_questions.append(q)
                    seen.add(key)

            if len(all_questions) >= count:
                break

        return all_questions[:count]

    @staticmethod
    async def _generate_reading_passages_separately(
        db: AsyncSession, teacher_id: int,
        count: int, title: str, kps: list[str], difficulty: int,
        grade: str, stage_category: str, is_senior: bool,
        rag_text: str, extra_ref: str, timeout: float, max_tokens: int,
    ) -> list[dict]:
        """每篇阅读理解单独调用一次LLM，避免一次性生成多篇导致文章过短"""
        difficulty_names = {1: "简单", 2: "中等", 3: "困难"}
        all_passages = []
        seen_passages = set()

        async def generate_one_passage(index: int) -> list[dict]:
            """生成一篇阅读理解，返回题目列表"""
            passage_prompt = ExamService._build_type_system_prompt(
                "reading", 1, grade, difficulty, difficulty_names,
                is_senior, rag_text, extra_ref, kps,
            )
            passage_user = (
                f"请为以下英语考试生成试卷题目：\n"
                f"标题：{title}\n"
                f"题型：阅读理解（第{index+1}篇/共{count}篇）\n"
                f"数量：1篇\n"
                f"难度：{difficulty_names.get(difficulty, '中等')}\n\n"
                f"请严格按要求的 JSON 格式返回，恰好生成 1 篇，"
                f"文章正文要求300-500词，分4段以上，内容充实、有实质信息。"
            )
            messages = [
                {"role": "system", "content": passage_prompt},
                {"role": "user", "content": passage_user},
            ]
            for attempt in range(2):
                response = await AIService.chat_completion(
                    db, messages, teacher_id,
                    timeout_seconds=timeout,
                    max_tokens=max_tokens,
                )
                print(f"[EXAM READING PASSAGE {index+1}] 第{attempt}次调用 | 响应长度={len(response)}", flush=True)
                try:
                    exam_data = _extract_json(response)
                except (json.JSONDecodeError, IndexError) as e:
                    print(f"[EXAM READING PASSAGE {index+1}] 解析失败: {e}", flush=True)
                    continue

                questions = (exam_data.get("questions") or exam_data.get("question")
                             or exam_data.get("items") or [])
                if not isinstance(questions, list) or not questions:
                    continue
                return questions[:1]  # 最多返回1篇
            return []

        # 并行生成所有阅读篇章
        passage_coroutines = [generate_one_passage(i) for i in range(count)]
        passage_results = await asyncio.gather(*passage_coroutines, return_exceptions=True)

        for i, result in enumerate(passage_results):
            if isinstance(result, Exception):
                print(f"[EXAM READING PASSAGE {i+1}] 生成异常: {result}", flush=True)
                continue
            for q in result:
                key = q.get("passage", "")[:80]
                if key and key not in seen_passages:
                    all_passages.append(q)
                    seen_passages.add(key)

        print(f"[EXAM READING] 逐篇生成完成: 实际获得 {len(all_passages)} 篇, 目标 {count} 篇", flush=True)
        return all_passages[:count]

    @staticmethod
    async def _generate_exam_monolithic(
        db: AsyncSession, teacher_id: int, class_id: int,
        title: str, knowledge_points: list[str],
        question_types: list[str], difficulty: int,
        question_count: int, duration_minutes: int,
        question_type_counts: dict | None, grade: str,
        stage_category: str, use_rag: bool,
        additional_references: str,
    ) -> dict:
        """旧版单次生成（后备方案，当没有 question_type_counts 时使用）"""
        # ===== 保留原有的 generate_exam 完整逻辑 =====
        type_names = [QUESTION_TYPES.get(t, t) for t in question_types]
        difficulty_names = {1: "简单", 2: "中等", 3: "困难"}
        if question_type_counts:
            passage_type_set = {"reading", "cloze", "seven_choice", "grammar_fill"}
            type_desc = "、".join(
                f"{QUESTION_TYPES.get(t, t)}{c}篇" if t in passage_type_set else f"{QUESTION_TYPES.get(t, t)}{c}道"
                for t, c in question_type_counts.items() if c > 0
            )
        else:
            type_desc = "、".join(type_names)
        grade_desc = f"适用年级：{grade}\n" if grade else ""
        stage_desc = STAGE_TEACHING_STYLES.get(stage_category, "")
        if stage_desc:
            stage_desc = f"学段风格：{stage_desc}\n"
        system_prompt = (
            "你是一个专业的英语试卷出题AI。请根据以下要求生成试卷。\n"
            "要求：\n1. 题目难度适中，符合给定的难度级别和年级\n2. 按指定题型和数量出题\n"
            "3. 题目标注题型标签\n4. 每题包含标准答案和详细解析\n"
            "5. 选择题给出4个选项(A/B/C/D)\n6. 写作题给出评分标准\n"
            '7. 题干文本中的引号必须用\\"进行转义，不得使用中文引号'
        )
        if use_rag:
            refs = await ExamService._fetch_rag_references(
                db, teacher_id, stage_category, "doc_exam",
                title=title, knowledge_points=knowledge_points,
                question_types=question_types, top_k=5,
            )
            if refs:
                ref_text = "\n\n".join([f"[参考题目 {i+1}]\n{r[:500]}" for i, r in enumerate(refs)])
                system_prompt += f"\n\n以下参考题目，请参考难度、题型和考察方式来出新试卷：\n{ref_text}"
        if additional_references:
            system_prompt += f"\n\n以下是用户提供的补充参考资料：\n{additional_references[:3000]}"

        is_senior = (stage_category == "senior")
        if is_senior:
            format_template = (
                "\n\n请严格按JSON格式返回（参照高考英语全国卷风格）：\n"
                '{"questions":[{"type":"cloze","stem":"完形文章","options":[[...]],"answers":["A","C"],"score":2},'
                '{"type":"reading","passage":"文章","sub_questions":[{"stem":"子题","options":[...],"answer":"A","score":2.5}],"score":10}]}\n'
                "【重要：高考题型规范】阅读理解400-600词/3-4子题，完形250词/15空，七选五300词，语法填空200词。"
            )
        else:
            format_template = (
                "\n\n请严格按JSON格式返回：\n"
                '{"questions":[{"type":"choice","stem":"题干","options":["A","B","C","D"],"answer":"A","explanation":"解析","score":2},'
                '{"type":"reading","passage":"文章(300-500词)","sub_questions":[{"stem":"子题","options":[...],"answer":"A","score":2}],"score":10}]}\n'
                "【重要：阅读理解题型规范】passage 300-500词，每篇5道子题。"
            )
        system_prompt += format_template

        def count_major():
            if not question_type_counts: return 0
            return sum(c for c in question_type_counts.values() if c > 0)
        major_count = count_major()
        reading_sub_qty = "3-4" if is_senior else "5"
        exam_style = "请参照高考英语全国卷风格，为以下英语考试生成试卷：\n" if is_senior else "请为以下英语考试生成试卷：\n"

        user_prompt = (
            f"{exam_style}标题：{title}\n{grade_desc}{stage_desc}"
            f"知识点：{', '.join(knowledge_points)}\n题型与数量：{type_desc}\n"
            f"难度：{difficulty_names.get(difficulty, '中等')}\n建议用时：{duration_minutes}分钟\n\n"
            f"总题数（大题）为 {major_count} 道，总分为100分。"
            f"各题型务必按指定篇/道数精确出题，阅读理解每篇包含{reading_sub_qty}道子题。\n"
            f"【强制要求】以下题型必须全部覆盖：\n"
            + "\n".join(f"  - {QUESTION_TYPES.get(t, t)}" for t in question_types)
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        all_questions = []
        last_error = None
        for attempt in range(3):
            if attempt == 0:
                cur_prompt = user_prompt
            else:
                missing_detail = ExamService._get_missing_detail(all_questions, question_types, question_type_counts)
                cur_prompt = f"你之前生成的不完整，缺少：{missing_detail}。请只生成缺失的题目。"
            retry_msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": cur_prompt}]
            response = await AIService.chat_completion(db, retry_msgs, teacher_id, timeout_seconds=300.0, max_tokens=32768)
            try:
                exam_data = _extract_json(response)
            except (json.JSONDecodeError, IndexError):
                try:
                    start_idx = response.index("{")
                    end_idx = response.rindex("}") + 1
                    exam_data = json.loads(_fix_json_string(response[start_idx:end_idx]))
                except (ValueError, json.JSONDecodeError):
                    last_error = f"AI 响应解析失败"
                    continue
            new_qs = (exam_data.get("questions") or exam_data.get("question") or exam_data.get("items") or [])
            if not isinstance(new_qs, list): new_qs = []
            existing_stems = {q.get("stem", "")[:50] for q in all_questions}
            for q in new_qs:
                stem_key = q.get("stem", "")[:50]
                if stem_key not in existing_stems:
                    all_questions.append(q)
                    existing_stems.add(stem_key)
            v = ExamService._validate_exam_output(all_questions, question_types, question_type_counts, response)
            if v is None:
                break
            last_error = v.get("error", "验证失败")

        if not all_questions:
            return {"error": last_error or "AI 生成试卷失败，请重试"}
        questions = all_questions
        total_score = 100
        v2 = ExamService._validate_exam_output(questions, question_types, question_type_counts, "")
        partial_warning = ""
        if v2 is not None:
            partial_warning = v2.get("error", "部分题目未生成，请手动补充")
        score_per = round(total_score / len(questions), 1)
        for q in questions:
            if q.get("type") == "reading" and q.get("sub_questions"):
                sub_score = sum(sq.get("score", round(score_per / max(len(q["sub_questions"]), 1), 1)) for sq in q["sub_questions"])
                q["score"] = sub_score
                for sq in q["sub_questions"]:
                    if "score" not in sq: sq["score"] = round(score_per / len(q["sub_questions"]), 1)
            else:
                q["score"] = q.get("score", score_per)
        result = {"title": title, "questions": questions, "total_score": total_score, "question_count": len(questions),
                   "difficulty": difficulty, "duration_minutes": duration_minutes, "knowledge_points": knowledge_points,
                   "question_types": question_types, "stage_category": stage_category}
        if partial_warning: result["_partial_warning"] = partial_warning
        return result

    @staticmethod
    async def generate_exam_parallel(
        db: AsyncSession,
        teacher_id: int,
        class_id: int,
        title: str,
        knowledge_points: list[str],
        question_types: list[str],
        difficulty: int,
        duration_minutes: int,
        question_type_counts: dict,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
        progress_callback: callable = None,
    ) -> dict:
        """方案 A：按题型并行生成试卷

        对每种题型独立调用 AI，通过 asyncio.gather 并行执行，
        最后合并所有题目的结果。相比整体生成（方案 B）：
        - 更快的响应速度（题型并行）
        - 更好的题型聚焦（每个 prompt 只需关注 1 种题型）
        - 更好的容错性（单个题型失败不影响其他题型）

        参数:
            progress_callback - 可选进度回调函数，签名: (qtype: str, status: str, detail: str)
                status: 'start' / 'success' / 'error'
        """
        # 分离需要生成的题型
        active_types = {t: c for t, c in question_type_counts.items() if c > 0}
        if not active_types:
            return {"error": "未指定有效的题型数量"}

        difficulty_names = {1: "简单", 2: "中等", 3: "困难"}

        # 为每种题型创建协程
        async def gen_single_type(qtype: str, count: int) -> tuple[str, list[dict], str | None]:
            """生成单个题型，返回 (题型, 题目列表, 错误信息)"""
            try:
                if progress_callback:
                    progress_callback(qtype, "start", f"开始生成{QUESTION_TYPES.get(qtype, qtype)}...")
                questions = await ExamService._generate_type(
                    db, teacher_id, qtype, count,
                    title=title, knowledge_points=knowledge_points,
                    difficulty=difficulty, grade=grade,
                    stage_category=stage_category,
                    use_rag=use_rag,
                    additional_references=additional_references,
                )
                if progress_callback:
                    status = "success" if questions else "error"
                    detail = f"生成{len(questions)}道" if questions else "生成结果为空"
                    progress_callback(qtype, status, detail)
                return qtype, questions, None
            except Exception as e:
                error_msg = f"{QUESTION_TYPES.get(qtype, qtype)}生成失败: {str(e)[:200]}"
                print(f"[EXAM PARALLEL] {error_msg}", flush=True)
                traceback.print_exc()
                if progress_callback:
                    progress_callback(qtype, "error", error_msg)
                return qtype, [], error_msg

        # 并发执行所有题型
        coroutines = [gen_single_type(qtype, count) for qtype, count in active_types.items()]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # 合并结果
        all_questions = []
        errors = []
        type_summary = {}

        for r in results:
            if isinstance(r, Exception):
                errors.append(f"题型生成异常: {str(r)[:200]}")
                continue
            qtype, questions, error = r
            type_summary[qtype] = {
                "label": QUESTION_TYPES.get(qtype, qtype),
                "count": len(questions),
                "error": error,
            }
            if error:
                errors.append(error)
            all_questions.extend(questions)

        if not all_questions:
            error_detail = "；".join(errors) if errors else "所有题型生成结果均为空"
            return {"error": f"AI 并行生成试卷失败：{error_detail}"}

        # 分数分配
        total_score = 100
        score_per = round(total_score / len(all_questions), 1)
        for q in all_questions:
            if q.get("type") == "reading" and q.get("sub_questions"):
                sub_score = sum(
                    sq.get("score", round(score_per / max(len(q["sub_questions"]), 1), 1))
                    for sq in q["sub_questions"]
                )
                q["score"] = sub_score
                for sq in q["sub_questions"]:
                    if "score" not in sq:
                        sq["score"] = round(score_per / len(q["sub_questions"]), 1)
            else:
                q["score"] = q.get("score", score_per)

        # 构建结果
        result = {
            "title": title,
            "questions": all_questions,
            "total_score": total_score,
            "question_count": len(all_questions),
            "difficulty": difficulty,
            "duration_minutes": duration_minutes,
            "knowledge_points": knowledge_points,
            "question_types": list(active_types.keys()),
            "stage_category": stage_category,
            "_type_summary": type_summary,
        }
        if errors:
            partial_msg = "部分题型生成异常：" + "；".join(errors[:3])
            result["_partial_warning"] = partial_msg

        print(f"[EXAM PARALLEL] 并行生成完成: {len(all_questions)} 题, 类型分布: "
              f"{ {k: v['count'] for k, v in type_summary.items()} }", flush=True)
        return result

    @staticmethod
    async def generate_exam_stream(
        db: AsyncSession,
        teacher_id: int,
        class_id: int,
        title: str,
        knowledge_points: list[str],
        question_types: list[str],
        difficulty: int,
        question_count: int,
        duration_minutes: int,
        question_type_counts: dict | None = None,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
    ):
        """SSE 流式生成试卷（异步生成器）

        按题型生成过程中通过 yield 逐事件推送进度，事件格式：
        - {"type":"type_start","qtype":"choice","label":"选择题","count":5}
        - {"type":"type_done","qtype":"choice","label":"选择题","count":5}
        - {"type":"type_error","qtype":"choice","label":"选择题","error":"..."}
        - {"type":"exam_done","data":{...}}  — 最终结果
        - {"type":"error","message":"..."}     — 整体失败

        调用方使用 `async for event in generate_exam_stream(...)` 消费。
        """
        progress_queue = asyncio.Queue()
        active_types = (question_type_counts or {}).copy()

        def _callback(qtype: str, status: str, detail: str):
            """通过队列将回调转发到异步生成器"""
            progress_queue.put_nowait((qtype, status, detail))

        # 后台任务：运行试卷生成
        async def _run():
            try:
                result = await ExamService.generate_exam(
                    db=db, teacher_id=teacher_id, class_id=class_id,
                    title=title, knowledge_points=knowledge_points,
                    question_types=question_types, difficulty=difficulty,
                    question_count=question_count, duration_minutes=duration_minutes,
                    question_type_counts=question_type_counts, grade=grade,
                    stage_category=stage_category, use_rag=use_rag,
                    additional_references=additional_references,
                    progress_callback=_callback,
                )
                # 将最终结果放入队列
                await progress_queue.put(("_done", result, None))
            except Exception as e:
                traceback.print_exc()
                await progress_queue.put(("_error", None, str(e)))

        # 启动后台任务
        task = asyncio.create_task(_run())

        # 消费回调事件，yield 给 SSE
        try:
            while True:
                event_type, data, error = await progress_queue.get()
                if event_type == "_done":
                    # 生成成功，yield 最终结果
                    yield {"type": "exam_done", "data": data}
                    return
                elif event_type == "_error":
                    yield {"type": "error", "message": error or "未知错误"}
                    return
                else:
                    qtype, status, detail = event_type, data, error
                    label = QUESTION_TYPES.get(qtype, qtype)
                    count = active_types.get(qtype, 0)
                    if status == "start":
                        yield {
                            "type": "type_start",
                            "qtype": qtype,
                            "label": label,
                            "count": count,
                        }
                    elif status == "success":
                        yield {
                            "type": "type_done",
                            "qtype": qtype,
                            "label": label,
                            "count": count,
                        }
                    else:
                        yield {
                            "type": "type_error",
                            "qtype": qtype,
                            "label": label,
                            "error": detail,
                        }
        finally:
            # 确保后台任务在不完整消费时被取消
            if not task.done():
                task.cancel()

    @staticmethod
    async def generate_exam(
        db: AsyncSession,
        teacher_id: int,
        class_id: int,
        title: str,
        knowledge_points: list[str],
        question_types: list[str],
        difficulty: int,
        question_count: int,
        duration_minutes: int,
        question_type_counts: dict | None = None,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
        progress_callback: callable = None,
    ) -> dict:
        """AI 生成试卷（支持 RAG 参考知识库 + 用户补充参考）

        自动路由：当提供了 question_type_counts 时，使用方案 A（按题型并行生成）；
        否则使用方案 B（整体生成，适用于旧版调用和无具体数量指定的场景）。

        参数:
            teacher_id - 教师ID
            class_id - 班级ID
            title - 试卷标题
            knowledge_points - 知识点列表
            question_types - 题型列表 ['choice', 'fill', 'translation']
            difficulty - 难度 1-3
            question_count - 题目数量（总和）
            duration_minutes - 建议用时
            question_type_counts - 各题型数量，如 {"choice":5,"fill":3}
            grade - 适用年级，如 "五年级", "七年级"
            stage_category - 学段: preschool/primary/junior/senior/other
            use_rag - 是否启用 RAG 知识库参考
            additional_references - 用户补充的参考内容（教材片段、教学重点等）
        """
        # ===== 方案 A（推荐）：按题型并行生成 =====
        if question_type_counts:
            print(f"[EXAM] 使用方案 A（并行生成）: {question_type_counts}", flush=True)
            return await ExamService.generate_exam_parallel(
                db, teacher_id, class_id, title,
                knowledge_points, question_types, difficulty,
                duration_minutes, question_type_counts,
                grade=grade, stage_category=stage_category,
                use_rag=use_rag,
                additional_references=additional_references,
                progress_callback=progress_callback,
            )

        # ===== 方案 B（后备）：整体生成 =====
        print(f"[EXAM] 使用方案 B（整体生成）: types={question_types}", flush=True)
        type_names = [QUESTION_TYPES.get(t, t) for t in question_types]
        difficulty_names = {1: "简单", 2: "中等", 3: "困难"}

        # 构建题型描述（带具体数量）
        if question_type_counts:
            passage_type_set = {"reading", "cloze", "seven_choice", "grammar_fill"}
            type_desc = "、".join(
                f"{QUESTION_TYPES.get(t, t)}{c}篇" if t in passage_type_set else f"{QUESTION_TYPES.get(t, t)}{c}道"
                for t, c in question_type_counts.items()
                if c > 0
            )
        else:
            type_desc = "、".join(type_names)

        # 年级 & 学段描述
        grade_desc = f"适用年级：{grade}\n" if grade else ""
        stage_desc = STAGE_TEACHING_STYLES.get(stage_category, "")
        if stage_desc:
            stage_desc = f"学段风格：{stage_desc}\n"

        # 构建 system prompt（含 RAG 参考 + 用户补充）
        system_prompt = (
            "你是一个专业的英语试卷出题AI。请根据以下要求生成试卷。\n"
            "要求：\n"
            "1. 题目难度适中，符合给定的难度级别和年级\n"
            "2. 按指定题型和数量出题，不得多出或少出\n"
            "3. 题目标注题型标签\n"
            "4. 每题包含标准答案和详细解析\n"
            "5. 选择题给出4个选项(A/B/C/D)\n"
            "6. 写作题给出评分标准\n"
            "7. 题干文本中的引号必须用\\\"进行转义，不得使用中文引号"
        )

        # 1. 知识库 RAG 检索：用标题+知识点+题型构建动态语义查询
        if use_rag:
            refs = await ExamService._fetch_rag_references(
                db, teacher_id, stage_category, "doc_exam",
                title=title, knowledge_points=knowledge_points,
                question_types=question_types,
                top_k=5,
            )
            if refs:
                ref_text = "\n\n".join([f"[参考题目 {i+1}]\n{r[:500]}" for i, r in enumerate(refs)])
                system_prompt += (
                    "\n\n以下是您之前上传的试卷中的参考题目，请参考这些题目的难度、题型和考察方式来出新的试卷：\n"
                    f"{ref_text}"
                )

        # 2. 用户补充参考内容
        if additional_references:
            system_prompt += (
                "\n\n以下是用户提供的补充参考资料，请结合这些内容来出题：\n"
                f"{additional_references[:3000]}"
            )

        # 3. 根据学段使用不同的题型格式模板
        is_senior = (stage_category == "senior")
        if is_senior:
            # ===== 高考风格（高中专属）=====
            format_template = (
                "\n\n请严格按以下JSON格式返回，务必返回完整的、可解析的JSON对象（参照高考英语全国卷风格）：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
              '      "type": "cloze",\n'
              '      "difficulty": 2,\n'
              '      "stem": "完形填空文章正文（约400-500词），文中每个空白位置必须嵌入____标记（不能遗漏任何空白），注意：首句不设空。文章是完整的叙事或说明文，有明确语境。每个空格涉及时态变化、固定搭配、介词辨析、词义辨析等考点。",\n'
              '      "options": [\n'
              '        ["finished","designed","followed","changed"],\n'
              '        ["delay","chance","trouble","excuse"],\n'
              '        ["judge","volunteer","classmate","competitor"],\n'
              '        ["race","school","town","training"],\n'
              '        ["agreed","returned","stopped","promised"]\n'
              "      ],\n"
              '      "answers": ["D","A","D","A","C"],\n'
                '      "explanations": ["解析1","解析2","解析3","解析4","解析5"],\n'
                '      "score": 15,\n'
                '      "knowledge_point": "完形填空-语境推断"\n'
                "    },\n"
                "    {\n"
                '      "type": "reading",\n'
                '      "difficulty": 2,\n'
              '      "passage": "此处是完整的阅读理解文章正文（400-600词），可以是新闻报道、科技说明文、社会文化、故事或名著节选等与高考难度相当的长文章，内容有深度，词汇丰富。文章需与题目分开存放，文章本身不是题目！",\n'
              '      "sub_questions": [\n'
              "        {\n"
              '          "stem": "根据短文内容，此处是第1道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "A",\n'
              '          "explanation": "解析",\n'
              '          "score": 2.5\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第2道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "B",\n'
              '          "explanation": "解析",\n'
              '          "score": 2.5\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第3道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "C",\n'
              '          "explanation": "解析",\n'
              '          "score": 2.5\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第4道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "D",\n'
              '          "explanation": "解析",\n'
              '          "score": 2.5\n'
              "        }\n"
              "      ],\n"
              '      "score": 10,\n'
              '      "knowledge_point": "阅读理解-主旨大意"\n'
              "    },\n"
              "    {\n"
              '      "type": "seven_choice",\n'
              '      "difficulty": 2,\n'
              '      "stem": "七选五文章正文（约400-500词），文章中的空白用____标记（如____36____）。文章是完整的说理性文章（如自我成长/学习方法/人际关系/心理健康），有完整逻辑，分4-5段。",\n'
              '      "options": [\n'
              '        "A little self-forgiveness also goes a long way.",\n'
              '        "Now list all the characteristics you like about yourself.",\n'
              '        "They might even like to have a go at doing the exercise.",\n'
              "        \"It's just as important to show yourself some forgiveness.\",\n"
              '        "It doesn\'t mean you have to ignore what\'s happened or forget it.",\n'
              '        "Whatever it is, no matter how small it might seem, write it down.",\n'
              '        "Whatever the mistake, remember it isn\'t a fixed aspect of your personality."\n'
              "      ],\n"
                '      "answers": ["C","B","F","A","G"],\n'
                '      "explanations": ["解析1","解析2","解析3","解析4","解析5"],\n'
                '      "score": 12.5,\n'
                '      "knowledge_point": "七选五-篇章结构"\n'
                "    },\n"
                "    {\n"
                '      "type": "grammar_fill",\n'
                '      "difficulty": 2,\n'
                '      "stem": "语法填空文章正文（约200词），其中有10个空白处，部分空白处给出单词提示需要变形",\n'
                '      "answers": ["has","the","to present","guidance","are revealed","tries","by","strategic","and","digitally"],\n'
                '      "score": 15,\n'
                '      "knowledge_point": "语法填空-词形变化"\n'
                "    },\n"
                "    {\n"
                '      "type": "error_correction",\n'
                '      "difficulty": 2,\n'
                '      "stem": "以下短文有10处错误，每句中最多有两处错误。错误涉及一个单词的增加、删除或修改。\\n此处是短文正文...",\n'
                '      "answers": [{"type":"modify","original":"word","correct":"word2"},{"type":"delete","original":"word"},{"type":"add","word":"new_word"}],\n'
                '      "score": 10,\n'
                '      "knowledge_point": "短文改错-语法综合"\n'
                "    },\n"
                "    {\n"
                '      "type": "applied_writing",\n'
                '      "difficulty": 2,\n'
                '      "stem": "应用写作题目（15分）。包含完整的中文写作背景和要求。写作类型：回信、写报道、写评论文、邮件、通知、演讲稿等。词数80词左右。例如：假定你是李华，外教Ryan准备将学生随机分为两人一组，让大家课后练习口语，你认为这样分组存在问题。请你给外教写一封邮件，内容包括：1. 说明问题；2. 提出建议。",\n'
                '      "score": 15,\n'
                '      "knowledge_point": "写作-应用文"\n'
                "    },\n"
                "    {\n"
'      "type": "continuation_writing",\n'
              '      "difficulty": 2,\n'
              '      "stem": "读后续写题目（25分）。包含完整的前文阅读材料（记叙文，350词以上，不要分过多段落），已给出两段段落开头语（不可改动），续写总词数150词左右。格式：\\n阅读下面材料，根据其内容和所给段落开头语续写两段，使之构成一篇完整的短文。\\n[前文材料]\\n注意：1. 续写词数应为150个左右；2. 请按如下格式在答题卡的相应位置作答。\\n[段落1开头语]\\n[段落2开头语]",\n'
                '      "score": 25,\n'
                '      "knowledge_point": "写作-读后续写"\n'
                "    }\n"
                "  ],\n"
                '  "total_score": 100\n'
                "}\n"
                "\n"
                "【重要：高考题型规范】\n"
                "1. 阅读理解：每篇 passage 为400-600词的长文章，可以是新闻报道、科技说明文、社会文化、故事或名著节选。每篇文章包含3-4道子题。\n"
                "2. 完形填空（cloze）：一篇约400-500词的短文，设15个空，每题从4个选项中选最佳。\n"
                "3. 七选五（seven_choice）：一篇约400-500词的短文，有5处空白，从7个选项中选5个填入。\n"
                "4. 语法填空（grammar_fill）：一篇约200词的短文，10个空白，部分给出提示词需变形。\n"
                "5. 短文改错（error_correction）：一篇短文有10处错误，涉及增加/删除/修改。\n"
                "6. 应用写作（applied_writing）：回信/报道/评论文等，80词左右，15分。\n"
                "7. 读后续写（continuation_writing）：给定前文(350词以上)+2段首句，续写150词左右，25分。\n"
                "8. 所有题型严格参照高考英语全国卷风格出题，文章要有深度，词汇丰富。\n"
                "9. 子题可以是选择题（带 options）或简答题（不带 options）。\n"
                "10. 【重要】不要在 stem/passage/article 中包含任何题号或序号（如1.、2.、第一段、第一篇等），系统会自动为整张试卷统一编号。\n"
                "11. 【试卷结构格式】大题用中文序号：\"第二部分 阅读（共两节，满分50分）\"、\"第三部分 语言运用（共两节，满分30分）\"、\"第四部分 写作（共两节，满分40分）\"。小节用\"第一节\"、\"第二节\"。小题编号从21开始整卷连续（听力占用1-20）。写作题无题号。\n"
                "12. 【重要】不要在选项文本中包含字母前缀（如A.、B.、C.、D.等），选项只需提供纯文本内容，系统会自动为每个选项添加A. B. C. D.字母标签。\n"
            )
        else:
            # ===== 通用风格（小学/初中/其他）=====
            format_template = (
                "\n\n请严格按以下JSON格式返回，务必返回完整的、可解析的JSON对象：\n"
                "{\n"
                '  "questions": [\n'
                "    {\n"
                '      "type": "choice",\n'
                '      "difficulty": 1,\n'
                '      "stem": "题干文本",\n'
                '      "options": ["A选项","B选项","C选项","D选项"],\n'
                '      "answer": "A",\n'
                '      "explanation": "解析",\n'
                '      "score": 2,\n'
                '      "knowledge_point": "语法-时态"\n'
                "    },\n"
                "    {\n"
                '      "type": "reading",\n'
                '      "difficulty": 2,\n'
              '      "passage": "此处是完整的阅读理解文章正文（300-500词），不得为空。文章需与题目分开存放，文章本身不是题目！",\n'
              '      "sub_questions": [\n'
              "        {\n"
              '          "stem": "根据短文内容，此处是第1道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "A",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第2道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "B",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第3道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "C",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第4道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "D",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        },\n"
              "        {\n"
              '          "stem": "根据短文内容，此处是第5道子题题干",\n'
              '          "options": ["选项内容1","选项内容2","选项内容3","选项内容4"],\n'
              '          "answer": "A",\n'
              '          "explanation": "解析",\n'
              '          "score": 2\n'
              "        }\n"
              "      ],\n"
                '      "score": 10,\n'
                '      "knowledge_point": "阅读理解-主旨大意"\n'
                "    }\n"
                "  ],\n"
                '  "total_score": 100\n'
                "}\n"
                "\n"
                "【重要：阅读理解题型规范】\n"
                "1. passage 字段存放文章正文（300-500词），不得为空，不得与题目混在一起\n"
                "2. 每篇阅读理解必须恰好包含 5 道子题（sub_questions），不得多出或少出\n"
                "3. sub_questions 数组存放子题，每道子题包含 stem（题干）、options（选项）、answer（答案）、explanation（解析）、score（该子题分值）\n"
                "4. 最外层的 score 是该阅读理解题的总分，应等于所有 sub_questions 的 score 之和\n"
                "5. 文章需较长（300-500词），可以是新闻报道、短篇故事或名著节选等有实质内容的文章\n"
                "6. 子题可以是选择题（带 options）或简答题（不带 options）\n"
                "7. 【重要】不要在 stem/passage/article 中包含任何题号或序号（如1.、2.、第一段、第一篇等），系统会自动为整张试卷统一编号。\n"
                "8. 【重要】不要在选项文本中包含字母前缀（如A.、B.、C.、D.等），选项只需提供纯文本内容，系统会自动为每个选项添加A. B. C. D.字母标签。"
            )

        system_prompt += format_template

        # 计算实际大题数（阅读理解每篇算1道大题）
        def _count_major_questions():
            if not question_type_counts:
                return 0
            total = 0
            for t, c in question_type_counts.items():
                if c > 0:
                    total += c  # 每种题型按"篇"或"道"计数，都是1个顶级题目对象
            return total

        major_count = _count_major_questions()

        # 根据学段构建 user_prompt
        reading_sub_qty = "3-4" if is_senior else "5"
        exam_style = "请参照高考英语全国卷风格，为以下英语考试生成试卷：\n" if is_senior else "请为以下英语考试生成试卷：\n"

        user_prompt = (
            f"{exam_style}"
            f"标题：{title}\n"
            f"{grade_desc}"
            f"{stage_desc}"
            f"知识点：{', '.join(knowledge_points)}\n"
            f"题型与数量：{type_desc}\n"
            f"难度：{difficulty_names.get(difficulty, '中等')}\n"
            f"建议用时：{duration_minutes}分钟\n\n"
            f"注意：总题数（大题）为 {major_count} 道（阅读理解每篇算1道大题），总分为100分。\n"
            f"各题型务必按指定篇/道数精确出题，不得多出或少出。"
            f"其中阅读理解每篇必须包含{reading_sub_qty}道子题。\n"
            f"\n"
            f"【⚠️ 强制要求】以下题型必须全部覆盖，缺一不可：\n"
            + "\n".join(f"  - {QUESTION_TYPES.get(t, t)}" for t in question_types if t != "reading" or "reading" in question_types)
            + f"\n"
            f"请逐一检查输出的 questions 数组，确保上述每一种题型都至少出现一次。"
            f"如果遗漏了任何题型，整个输出将视为无效需要重来！"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ===== 带自动重试的生成循环 =====
        # 最多重试 2 次（共 3 次尝试），每次告诉 AI 还缺哪些题目
        MAX_RETRIES = 2
        all_questions = []
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            # 构建当前轮次的 messages
            if attempt == 0:
                # 首次：直接用原始 user_prompt（system_prompt 复用外部的）
                current_user_prompt = user_prompt
            else:
                # 重试：只让 AI 补全缺失的题目
                missing_detail = ExamService._get_missing_detail(
                    all_questions, question_types, question_type_counts
                )
                print(f"[EXAM RETRY] 第 {attempt} 次重试，缺失信息: {missing_detail}", flush=True)
                current_user_prompt = (
                    f"你之前生成的试卷不完整，缺少以下题目：\n"
                    f"{missing_detail}\n\n"
                    f"请只生成上述缺失的题目，按之前要求的 JSON 格式返回，"
                    f"只包含一个 questions 数组，不要重复生成已有的题目。"
                    f"\n每个题目对象必须包含 type、stem、options（如有）、answer、explanation、knowledge_point 等字段。"
                )

            retry_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": current_user_prompt},
            ]

            response = await AIService.chat_completion(
                db, retry_messages, teacher_id,
                timeout_seconds=300.0,
                max_tokens=32768,
            )

            # 解析 JSON 响应（健壮模式）
            try:
                exam_data = _extract_json(response)
            except (json.JSONDecodeError, IndexError) as e:
                try:
                    start_idx = response.index("{")
                    end_idx = response.rindex("}") + 1
                    fragment = response[start_idx:end_idx]
                    fixed = _fix_json_string(fragment)
                    exam_data = json.loads(fixed)
                except (ValueError, json.JSONDecodeError):
                    print(f"[EXAM ERROR] 第 {attempt} 次尝试 AI 响应解析失败: {e}", flush=True)
                    print(f"[EXAM ERROR] 响应长度: {len(response)} 字符", flush=True)
                    print(f"[EXAM ERROR] 响应末尾 200 字符: {response[-200:]}", flush=True)
                    last_error = f"AI 响应解析失败（响应 {len(response)} 字符）：{str(e)[:100]}"
                    continue

            # 防御性检查
            if not isinstance(exam_data, dict) or "questions" not in exam_data:
                print(f"[EXAM WARN] 第 {attempt} 次尝试不含 questions, 尝试 rindex 回退", flush=True)
                try:
                    start_idx = response.index("{")
                    end_idx = response.rindex("}") + 1
                    fragment = response[start_idx:end_idx]
                    fixed = _fix_json_string(fragment)
                    exam_data = json.loads(fixed)
                    print(f"[EXAM WARN] rindex 回退成功", flush=True)
                except (ValueError, json.JSONDecodeError) as e2:
                    print(f"[EXAM ERROR] rindex 回退也失败: {e2}", flush=True)
                    last_error = f"AI 响应格式异常"
                    continue

            # 兼容多种 key 名
            new_questions = (exam_data.get("questions")
                             or exam_data.get("question")
                             or exam_data.get("items")
                             or exam_data.get("data")
                             or [])
            if not isinstance(new_questions, list):
                new_questions = []

            if not new_questions:
                print(f"[EXAM WARN] 第 {attempt} 次尝试 questions 为空", flush=True)
                last_error = "AI 生成的试卷题目为空，请重试或联系管理员"
                continue

            # 合并题目（去重：防止重试时 AI 又生成已有的题）
            existing_stems = {q.get("stem", "")[:50] for q in all_questions}
            for q in new_questions:
                stem_key = q.get("stem", "")[:50]
                if stem_key not in existing_stems:
                    all_questions.append(q)
                    existing_stems.add(stem_key)

            # 本轮验证（针对已合并的 all_questions）
            validation = ExamService._validate_exam_output(
                all_questions, question_types, question_type_counts, response
            )
            if validation is None:
                # 验证通过
                print(f"[EXAM RETRY] 第 {attempt} 次尝试验证通过, 共 {len(all_questions)} 题", flush=True)
                break
            else:
                last_error = validation.get("error", "验证失败")
                print(f"[EXAM RETRY] 第 {attempt} 次尝试仍不完整: {last_error[:200]}", flush=True)
                # validation 非空 → 继续循环重试

        # 循环结束后，如果仍有缺失但至少有一些题目，使用 partial 结果
        if not all_questions:
            return {"error": last_error or "AI 生成试卷失败，请重试"}

        questions = all_questions
        total_score = 100

        # 如果仍有缺失但用户至少拿到题目，记录日志但不报错
        remaining_validation = ExamService._validate_exam_output(
            questions, question_types, question_type_counts, ""
        )
        partial_warning = ""
        if remaining_validation is not None:
            print(f"[EXAM PARTIAL] 最终仍有缺失但返回部分结果: {len(questions)} 题, 缺失: {remaining_validation.get('error', '')[:200]}", flush=True)
            partial_warning = remaining_validation.get("error", "部分题目未生成，请手动补充")
            # 不阻断，直接返回部分结果让用户手动补

        # 为每题分配分数
        score_per = round(total_score / len(questions), 1)
        for q in questions:
            if q.get("type") == "reading" and q.get("sub_questions"):
                # 阅读理解：总分 = 所有子题分数之和
                sub_score = sum(
                    sq.get("score", round(score_per / max(len(q["sub_questions"]), 1), 1))
                    for sq in q["sub_questions"]
                )
                q["score"] = sub_score
                # 如果没有子题分数，均分
                for sq in q["sub_questions"]:
                    if "score" not in sq:
                        sq["score"] = round(score_per / len(q["sub_questions"]), 1)
            else:
                q["score"] = q.get("score", score_per)

        result = {
            "title": title,
            "questions": questions,
            "total_score": total_score,
            "question_count": len(questions),
            "difficulty": difficulty,
            "duration_minutes": duration_minutes,
            "knowledge_points": knowledge_points,
            "question_types": question_types,
            "stage_category": stage_category,
        }
        if partial_warning:
            result["_partial_warning"] = partial_warning
        return result

    @staticmethod
    def _get_missing_detail(
        questions: list,
        requested_types: list[str],
        question_type_counts: dict | None,
    ) -> str:
        """生成给 AI 重试 prompt 的「缺失题目详情」"""
        if not questions:
            # 全部缺失
            if question_type_counts:
                parts = []
                for t, c in question_type_counts.items():
                    if c > 0:
                        name = QUESTION_TYPES.get(t, t)
                        unit = "篇" if t == "reading" else "道"
                        parts.append(f"{name}{c}{unit}")
                return "全部题目都缺失，请重新生成本次要求的所有题目：" + "、".join(parts)
            return "全部题目都缺失"

        actual_type_counts: dict[str, int] = {}
        for q in questions:
            t = q.get("type", "unknown")
            actual_type_counts[t] = actual_type_counts.get(t, 0) + 1

        missing_items = []

        # 检查缺失的题型
        missing_types = [t for t in requested_types if t not in actual_type_counts]
        for t in missing_types:
            name = QUESTION_TYPES.get(t, t)
            if question_type_counts and t in question_type_counts:
                unit = "篇" if t == "reading" else "道"
                missing_items.append(f"{name}{question_type_counts[t]}{unit}（该题型完全缺失）")
            else:
                missing_items.append(f"{name}（该题型完全缺失）")

        # 检查数量不足的题型
        if question_type_counts:
            for t, req_count in question_type_counts.items():
                if t in missing_types or req_count <= 0:
                    continue
                actual_count = actual_type_counts.get(t, 0)
                if actual_count < req_count:
                    name = QUESTION_TYPES.get(t, t)
                    unit = "篇" if t == "reading" else "道"
                    missing_items.append(f"{name}还需{req_count - actual_count}{unit}（已有{actual_count}{unit}，要求{req_count}{unit}）")

        if not missing_items:
            return "所有题目已满足要求，无需补充"

        return "\n".join(missing_items)

    @staticmethod
    def _validate_exam_output(
        questions: list,
        requested_types: list[str],
        question_type_counts: dict | None,
        raw_response: str,
    ) -> dict | None:
        """验证 AI 生成的题目是否满足要求的题型和数量，不满足时返回错误信息 dict。"""
        if not questions:
            return None  # 空检测已在外层处理

        # 统计实际生成的题型分布
        actual_type_counts: dict[str, int] = {}
        for q in questions:
            t = q.get("type", "unknown")
            actual_type_counts[t] = actual_type_counts.get(t, 0) + 1

        # 1. 检查是否所有请求的题型都有覆盖
        missing_types = [t for t in requested_types if t not in actual_type_counts]

        # 2. 如果指定了具体数量，检查数量是否匹配
        type_count_mismatch = {}
        if question_type_counts:
            for t, req_count in question_type_counts.items():
                if req_count <= 0:
                    continue
                actual_count = actual_type_counts.get(t, 0)
                if actual_count != req_count:
                    type_count_mismatch[t] = {"requested": req_count, "actual": actual_count}

        # 3. 如果没有缺失也没有数量不匹配，验证通过
        if not missing_types and not type_count_mismatch:
            return None

        # 4. 构建详细的诊断日志
        print(f"[EXAM VALIDATION FAILED] ====== 试卷验证失败 ======", flush=True)
        print(f"[EXAM VALIDATION] 请求的题型: {requested_types}", flush=True)
        if question_type_counts:
            print(f"[EXAM VALIDATION] 请求的数量分布: {question_type_counts}", flush=True)
        print(f"[EXAM VALIDATION] 实际生成的题型分布: {actual_type_counts}", flush=True)
        print(f"[EXAM VALIDATION] 实际题目数量: {len(questions)}", flush=True)
        print(f"[EXAM VALIDATION] 缺失的题型: {missing_types}", flush=True)
        if type_count_mismatch:
            print(f"[EXAM VALIDATION] 数量不匹配: {type_count_mismatch}", flush=True)
        for i, q in enumerate(questions):
            print(f"[EXAM VALIDATION]   Q{i}: type={q.get('type')} stem_preview={str(q.get('stem',''))[:60]}", flush=True)
        print(f"[EXAM VALIDATION] ====== 原始响应前 3000 字符 ======", flush=True)
        print(raw_response[:3000], flush=True)
        print(f"[EXAM VALIDATION] ====== 原始响应末尾 2000 字符 ======", flush=True)
        print(raw_response[-2000:], flush=True)

        # 5. 构建用户友好的错误信息
        err_parts = []
        if missing_types:
            missing_names = [QUESTION_TYPES.get(t, t) for t in missing_types]
            err_parts.append(f"缺少题型：{'、'.join(missing_names)}")
        if type_count_mismatch:
            for t, m in type_count_mismatch.items():
                tname = QUESTION_TYPES.get(t, t)
                err_parts.append(f"{tname}数量不匹配（要求 {m['requested']} 道，实际生成 {m['actual']} 道）")
        if err_parts:
            detail = "；".join(err_parts)
            print(f"[EXAM VALIDATION] stacktrace:", flush=True)
            traceback.print_stack()

        return {
            "error": (
                f"AI 生成的试卷不完整：{detail}。"
                f"请重试，AI 仅生成了 {len(questions)} 道题（类型：{actual_type_counts}）。"
            )
        }

    @staticmethod
    async def save_exam(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        questions: list,
        total_score: int,
        difficulty: int,
        duration_minutes: int,
        knowledge_points: list,
        status: str = "draft",
        class_id: int = 0,  # 生成时可不选班级，发布时再设
        grade: str = "",
        stage_category: str = "",
        source_exam_ids: str = "",
        choice_questions: list = None,  # 选择题JSON（用于生成答题卡配置）
    ) -> TeacherExam:
        """保存试卷到数据库（支持学段和组卷来源，支持选择题JSON配置答题卡）"""
        # 固化题号：根据学段确定起始编号并增强题目
        is_senior = bool(grade and (
            grade.startswith("高") or "高中" in grade or "高三" in grade
            or "senior" in grade.lower() or "高考" in grade
        ))
        start_num = 21 if is_senior else 1
        final_questions = ExamService._enhance_questions(questions, start_number=start_num)

        exam = TeacherExam(
            teacher_id=teacher_id,
            class_id=class_id,
            title=title,
            questions=final_questions,
            total_score=total_score,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            knowledge_points=",".join(knowledge_points) if knowledge_points else "",
            status=status,
            grade=grade,
            stage_category=stage_category,
            source_exam_ids=source_exam_ids,
        )
        db.add(exam)
        await db.flush()
        await db.refresh(exam)

        # 如果提供了选择题JSON，基于它生成答题卡配置
        if choice_questions:
            answer_sheet_config = ExamService._build_answer_sheet_config_from_json(
                exam.id, choice_questions, title,
            )
            exam.answer_sheet_config = answer_sheet_config
            flag_modified(exam, "answer_sheet_config")
            await db.flush()
            await db.refresh(exam)

        return exam

    @staticmethod
    async def update_exam(
        db: AsyncSession,
        exam_id: int,
        teacher_id: int,
        **kwargs,
    ) -> TeacherExam | None:
        """更新试卷（含 knowledge_points 列表转字符串，自动固化题号）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return None
        for key, value in kwargs.items():
            if key == "questions":
                # 固化题号：根据学段确定起始编号并增强题目
                grade_val = kwargs.get("grade") or getattr(exam, "grade", "") or ""
                is_senior = bool(grade_val and (
                    grade_val.startswith("高") or "高中" in grade_val or "高三" in grade_val
                    or "senior" in grade_val.lower() or "高考" in grade_val
                ))
                start_num = 21 if is_senior else 1
                value = ExamService._enhance_questions(value, start_number=start_num)
            if key == "knowledge_points" and isinstance(value, list):
                value = ",".join(value)
            if hasattr(exam, key):
                setattr(exam, key, value)
        # 标记 JSON 列已修改（expire_on_commit=False 时必要）
        if kwargs.get("questions") is not None:
            flag_modified(exam, "questions")
        await db.flush()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def publish_exam(
        db: AsyncSession, exam_id: int, teacher_id: int, class_id: int = 0
    ) -> TeacherExam | None:
        """发布试卷（同时设置目标班级，自动生成答题卡配置）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return None
        if exam.status not in ("draft",):
            return None

        # 自动生成 GraderFlow 答题卡配置（4列矩形填涂框，B模式扫描）
        questions = exam.questions or []
        if questions:
            is_senior = bool(exam.grade and (
                exam.grade.startswith("高") or "高中" in exam.grade or "高三" in exam.grade
                or "senior" in exam.grade.lower() or "高考" in exam.grade
            ))
            start_num = 21 if is_senior else 1
            choice_questions = ExamService._extract_choice_questions(questions, exam.title, start_number=start_num)
            if choice_questions:
                answer_sheet_config = ExamService._build_graderflow_sheet_config_from_json(exam_id, choice_questions, exam.title, id_digits=7)
            else:
                answer_sheet_config = ExamService._build_graderflow_sheet_config(exam_id, questions, exam.title, id_digits=7)
            exam.answer_sheet_config = answer_sheet_config
            flag_modified(exam, "answer_sheet_config")

        exam.status = "published"
        exam.published_at = datetime.now()
        if class_id and class_id != exam.class_id:
            exam.class_id = class_id
            flag_modified(exam, "class_id")
        flag_modified(exam, "status")
        flag_modified(exam, "published_at")
        await db.flush()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def list_exams(
        db: AsyncSession,
        teacher_id: int,
        class_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        *,
        search: str = "",
        paper_status: str | None = None,
        grading_view: bool = False,
    ) -> dict:
        """获取试卷列表（支持按状态筛选）"""
        filters = [TeacherExam.teacher_id == teacher_id]
        if class_id:
            filters.append(TeacherExam.class_id == class_id)
        if status:
            filters.append(TeacherExam.status == status)
        if search:
            filters.append(TeacherExam.title.icontains(search, autoescape=True))

        grading_view = grading_view or bool(paper_status)
        recent = TeacherExam.created_at
        if grading_view:
            edited = func.coalesce(TeacherExam.updated_at, TeacherExam.created_at)
            scanned = select(func.max(func.coalesce(ExamScanRecord.updated_at, ExamScanRecord.created_at))).where(
                ExamScanRecord.exam_id == TeacherExam.id, ExamScanRecord.teacher_id == teacher_id,
            ).scalar_subquery()
            submitted = select(func.max(effective_time(ExamSubmission))).where(
                ExamSubmission.exam_id == TeacherExam.id,
            ).scalar_subquery()
            # Compare the three timestamps without dialect-specific NULL handling.
            last_grade = func.coalesce(submitted, edited)
            last_scan = func.coalesce(scanned, edited)
            recent = case(
                (and_(last_grade >= last_scan, last_grade >= edited), last_grade),
                (last_scan >= edited, last_scan), else_=edited,
            )
        stmt = select(TeacherExam, recent.label("recent")).where(*filters).order_by(
            recent.desc(), TeacherExam.id.desc(),
        )
        offset = (page - 1) * page_size
        layouts = {}
        cards = []
        if paper_status:
            total = 0
            cursor = 0
            while True:
                batch = (await db.execute(stmt.offset(cursor).limit(100))).all()
                candidates = await ExamService._list_exam_cards(db, teacher_id, batch, layouts, grading_view=True)
                for card in candidates:
                    state = card["paper_state"] or ("completed" if card["status"] == "done" else card["status"])
                    if state == paper_status:
                        if offset <= total < offset + page_size:
                            cards.append(card)
                        total += 1
                if len(batch) < 100:
                    break
                cursor += len(batch)
        else:
            total = await db.scalar(select(func.count()).select_from(TeacherExam).where(*filters)) or 0
            batch = (await db.execute(stmt.offset(offset).limit(page_size))).all()
            cards = await ExamService._list_exam_cards(db, teacher_id, batch, layouts, grading_view=grading_view)
        return {"items": cards, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def _list_exam_cards(db: AsyncSession, teacher_id: int, rows, layouts: dict, *, grading_view: bool) -> list[dict]:
        exams = [exam for exam, _ in rows]
        paper_ids = {exam.id for exam in exams if is_paper_draft(exam.answer_sheet_config)}
        scans = {}
        confirmed = {}
        if paper_ids:
            scans = {exam_id: (activity, pending) for exam_id, activity, pending in (await db.execute(select(
                ExamScanRecord.exam_id, func.count(),
                func.count(case((ExamScanRecord.status == "pending_review", True))),
            ).where(
                ExamScanRecord.exam_id.in_(paper_ids), ExamScanRecord.teacher_id == teacher_id,
                ExamScanRecord.status.in_(("pending_review", "withdrawn")),
            ).group_by(ExamScanRecord.exam_id))).all()}
            confirmed = dict((await db.execute(select(ExamSubmission.exam_id, func.count())
                .join(TeacherExam, TeacherExam.id == ExamSubmission.exam_id)
                .where(ExamSubmission.exam_id.in_(paper_ids), result_state(TeacherExam) == "confirmed")
                .group_by(ExamSubmission.exam_id))).all())
        source_ids = await paper_source_exam_ids(db, teacher_id, paper_ids)
        blockers = await run_in_threadpool(lambda: {
            exam.id: paper_readiness(exam, has_source=exam.id in source_ids, layouts=layouts)
            for exam in exams if exam.id in paper_ids
        })
        class_ids = {exam.class_id for exam in exams if exam.class_id}
        class_names = {}
        if grading_view and class_ids:
            class_names = dict((await db.execute(select(Class.id, Class.name)
                .join(ClassTeacher, ClassTeacher.class_id == Class.id)
                .where(Class.id.in_(class_ids), ClassTeacher.teacher_id == teacher_id))).all())

        return [
            {
                "id": e.id,
                "title": e.title,
                "class_id": e.class_id,
                "status": e.status,
                "total_score": e.total_score,
                "difficulty": e.difficulty,
                "duration_minutes": e.duration_minutes,
                "question_count": len(e.questions) if e.questions else 0,
                "submission_count": e.submission_count or 0,
                "avg_score": e.avg_score,
                "grade": e.grade or "",
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                # 答题卡配置摘要（如果有）
                "paper_draft": e.id in paper_ids,
                "paper_state": paper_state(e, has_activity=bool(scans.get(e.id) or confirmed.get(e.id)),
                                           ready=blockers[e.id] is None)
                    if e.id in paper_ids else None,
                "has_answer_sheet": isinstance(e.answer_sheet_config, dict) and not is_paper_draft(e.answer_sheet_config),
                "answer_sheet_summary": {
                    "total_questions": e.answer_sheet_config.get("total_questions", 0),
                    "option_count": e.answer_sheet_config.get("option_count", 0),
                    "html_url": e.answer_sheet_config.get("html_url", ""),
                    "pdf_url": e.answer_sheet_config.get("pdf_url", ""),
                } if isinstance(e.answer_sheet_config, dict) and not is_paper_draft(e.answer_sheet_config) else None,
                **({
                    "class_name": class_names.get(e.class_id),
                    "updated_at": updated.isoformat() if updated else None,
                    "confirmed_count": confirmed.get(e.id, 0),
                    "pending_count": scans.get(e.id, (0, 0))[1],
                    "paper_blocker": blockers.get(e.id),
                } if grading_view else {}),
            }
            for e, updated in rows
        ]

    @staticmethod
    async def student_list_exams(
        db: AsyncSession,
        student_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """学生端：获取已发布且学生所属班级的试卷列表"""
        # 1. 获取学生所属的所有班级ID
        class_stmt = select(ClassStudent.class_id).where(
            ClassStudent.student_id == student_id
        )
        class_result = await db.execute(class_stmt)
        class_ids = [row[0] for row in class_result.all()]

        if not class_ids:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # 2. 查询发布到这些班级的试卷
        stmt = (
            select(TeacherExam)
            .where(
                TeacherExam.class_id.in_(class_ids),
                TeacherExam.status.in_(["published", "done"]),
            )
        )
        # 按提交状态过滤时，只查一次学生提交记录
        if status in ("submitted", "pending"):
            sub_result = await db.execute(
                select(ExamSubmission.exam_id)
                .where(ExamSubmission.student_id == student_id)
            )
            submitted_ids = {row[0] for row in sub_result.all()}
            if status == "submitted":
                stmt = stmt.where(TeacherExam.id.in_(submitted_ids))
            elif submitted_ids:
                stmt = stmt.where(~TeacherExam.id.in_(submitted_ids))

        stmt = stmt.order_by(TeacherExam.published_at.desc(), TeacherExam.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        exams = result.scalars().all()

        # 3. 统计总数
        count_stmt = (
            select(func.count())
            .select_from(TeacherExam)
            .where(
                TeacherExam.class_id.in_(class_ids),
                TeacherExam.status.in_(["published", "done"]),
            )
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        # 4. 查询学生提交状态
        exam_ids = [e.id for e in exams]
        submission_map = {}
        if exam_ids:
            sub_stmt = (
                select(ExamSubmission.exam_id, ExamSubmission.score, ExamSubmission.submitted_at)
                .where(
                    ExamSubmission.exam_id.in_(exam_ids),
                    ExamSubmission.student_id == student_id,
                )
            )
            sub_result = await db.execute(sub_stmt)
            for row in sub_result.all():
                submission_map[row.exam_id] = {
                    "score": row.score,
                    "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                }

        # 5. 查询班级名称
        class_names = {}
        if class_ids:
            name_stmt = select(Class.id, Class.name).where(Class.id.in_(class_ids))
            name_result = await db.execute(name_stmt)
            for row in name_result.all():
                class_names[row.id] = row.name

        return {
            "items": [
                {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description or "",
                    "class_id": e.class_id,
                    "class_name": class_names.get(e.class_id, ""),
                    "status": e.status,
                    "total_score": e.total_score,
                    "difficulty": e.difficulty,
                    "duration_minutes": e.duration_minutes,
                    "question_count": len(e.questions) if e.questions else 0,
                    "submission_count": e.submission_count or 0,
                    "avg_score": e.avg_score,
                    "grade": e.grade or "",
                    "my_submission": submission_map.get(e.id),
                    "published_at": e.published_at.isoformat() if e.published_at else None,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in exams
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def student_get_exam_result(
        db: AsyncSession, exam_id: int, student_id: int
    ) -> dict | None:
        """学生端：获取已提交试卷的批改结果"""
        # 查询提交记录
        sub_stmt = (
            select(ExamSubmission)
            .where(
                ExamSubmission.exam_id == exam_id,
                ExamSubmission.student_id == student_id,
            )
        )
        sub_result = await db.execute(sub_stmt)
        submission = sub_result.scalar_one_or_none()
        if not submission or submission.score is None:
            return None

        # 查询试卷信息
        exam = await db.get(TeacherExam, exam_id)
        if not exam:
            return None

        return {
            "exam_id": exam.id,
            "exam_title": exam.title,
            "total_score": submission.score,
            "max_score": submission.max_score or exam.total_score or 100,
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "grading_status": submission.grading_status,
            "details": submission.ai_grade_detail or [],
        }

    @staticmethod
    async def student_get_exam_detail(
        db: AsyncSession, exam_id: int, student_id: int
    ) -> dict | None:
        """学生端：获取已发布试卷的完整详情（含题目），需校验学生属于该试卷的班级"""
        # 1. 获取试卷
        exam = await db.get(TeacherExam, exam_id)
        if not exam:
            return None
        if exam.status not in ("published", "done"):
            return None

        # 2. 验证学生属于该班级
        class_stmt = select(ClassStudent).where(
            ClassStudent.class_id == exam.class_id,
            ClassStudent.student_id == student_id,
        )
        class_result = await db.execute(class_stmt)
        if not class_result.scalar_one_or_none():
            return None

        # 3. 查询班级名称
        name_stmt = select(Class.name).where(Class.id == exam.class_id)
        name_result = await db.execute(name_stmt)
        class_name = name_result.scalar() or ""

        # 4. 查询学生提交状态
        sub_stmt = (
            select(ExamSubmission.score, ExamSubmission.submitted_at)
            .where(
                ExamSubmission.exam_id == exam_id,
                ExamSubmission.student_id == student_id,
            )
        )
        sub_result = await db.execute(sub_stmt)
        sub_row = sub_result.one_or_none()
        my_submission = None
        if sub_row:
            my_submission = {
                "score": sub_row.score,
                "submitted_at": sub_row.submitted_at.isoformat() if sub_row.submitted_at else None,
            }

        questions = exam.questions or []

        # 高中学段（含高考）：从21开始编号（听力占用1-20）
        is_senior = exam.grade and (
            "高中" in exam.grade
            or "高三" in exam.grade
            or exam.grade.startswith("高")
            or "senior" in exam.grade.lower()
            or "高考" in exam.grade
        )
        start_num = 21 if is_senior else 1
        enhanced_questions = ExamService._enhance_questions(questions, start_number=start_num)

        return {
            "id": exam.id,
            "title": exam.title,
            "description": exam.description or "",
            "class_id": exam.class_id,
            "class_name": class_name,
            "questions": enhanced_questions,
            "total_score": exam.total_score,
            "difficulty": exam.difficulty,
            "duration_minutes": exam.duration_minutes,
            "question_count": len(questions) if questions else 0,
            "knowledge_points": exam.knowledge_points.split(",") if exam.knowledge_points else [],
            "grade": exam.grade or "",
            "status": exam.status,
            "my_submission": my_submission,
            "published_at": exam.published_at.isoformat() if exam.published_at else None,
            "created_at": exam.created_at.isoformat() if exam.created_at else None,
        }

    # ===================== 答题卡 & 题型增强 =====================

    @staticmethod
    def _enhance_questions(questions: list, start_number: int = 1) -> list:
        """为每道题添加题号、选项数、是否多选题等元数据

        返回增强后的 questions 列表（不修改原始对象）:
            - question_number: 题号（默认从1开始，可指定偏移如 start_number=21）
            - option_count: 选项数量
            - is_multi_choice: 是否多选题（仅 choice 型有效）
            - question_type: 题型（choice/fill/translation/reading 等）

        参数:
            start_number: 起始题号，新课标高考卷听力占用1-20，从21开始

        编号规则:
            - reading: 每个子题(sub_questions)分配独立连续编号
            - cloze: 按答案个数占用连续编号
            - seven_choice: 按答案个数占用连续编号
            - 其他类型: 每题一个编号
        """
        enhanced = []
        counter = start_number  # 全局计数器，用于全体小题连续编号

        for i, q in enumerate(questions):
            qtype = q.get("type", "choice")
            options = q.get("options", [])
            answer = q.get("answer", "")

            # 判断是否多选题：有 multi/multi_select 标记，或 answer 包含多个字母
            is_multi = False
            if qtype == "choice":
                if q.get("multi") or q.get("multi_select"):
                    is_multi = True
                elif isinstance(answer, str) and len(answer) > 1:
                    # answer 如 "AB"、"ACD" 表示多选
                    is_multi = True
                elif isinstance(answer, list) and len(answer) > 1:
                    is_multi = True

            enriched = dict(q)  # 浅拷贝，保留原有字段

            # ── 分配题号：按题型展开为连续编号 ──
            # 注意：编号逻辑放在 stem cleanup 之前，因为 grammar_fill 的 stem 开头是
            # "1.____(word)"，cleanup 不能删掉这个属于空格的编号前缀
            if qtype == "reading":
                # 阅读理解：每个子题独立编号
                sub_list = enriched.get("sub_questions") or enriched.get("questions") or []
                if sub_list and isinstance(sub_list, list) and len(sub_list) > 0:
                    for sq in sub_list:
                        sq["question_number"] = counter
                        counter += 1
                    enriched["question_number"] = sub_list[0]["question_number"]
                else:
                    enriched["question_number"] = counter
                    counter += 1
            elif qtype in ("cloze", "seven_choice", "grammar_fill"):
                # 这些题型在 passage/stem 中有空格编号，需要重新编号
                answers = enriched.get("answers", enriched.get("answer", []))
                blank_count = len(answers) if isinstance(answers, list) and len(answers) > 1 else 1
                enriched["question_number"] = counter
                enriched["blank_start_number"] = counter  # 供前端选项列表显示

                # ── 重新编号 passage/stem 中的空格序号 ──
                text_field = "stem" if qtype == "grammar_fill" else "passage"
                text_content = enriched.get(text_field, "")
                if text_content and isinstance(text_content, str) and blank_count > 1:
                    it = iter(range(counter, counter + blank_count))
                    if qtype == "cloze":
                        # 格式: (1) ____ → 替换括号内数字
                        enriched[text_field] = re.sub(
                            r'\((\d+)\)', lambda m: f'({next(it)})', text_content
                        )
                    elif qtype == "seven_choice":
                        # 格式: ____36____ → 替换下划线中间的数字
                        enriched[text_field] = re.sub(
                            r'(_+)(\d+)(_+)', lambda m: f'{m.group(1)}{next(it)}{m.group(3)}', text_content
                        )
                    elif qtype == "grammar_fill":
                        # 格式: 1.____(originate) → 替换数字前缀
                        enriched[text_field] = re.sub(
                            r'(\d+)([.、]?\s*_+)', lambda m: f'{next(it)}{m.group(2)}', text_content
                        )
                counter += blank_count
            else:
                enriched["question_number"] = counter
                counter += 1

            # ── 清理 stem/question/passage 中 AI 可能自带的序号 ──
            # 注意：不删除紧跟着下划线的数字前缀（属于 grammar_fill 空格的编号）
            for sk in ("stem", "question", "passage"):
                val = enriched.get(sk)
                if val and isinstance(val, str):
                    cleaned = re.sub(r'^\s*\d+\s*[.、)）]\s*(?!_+)', '', val)
                    if cleaned != val:
                        enriched[sk] = cleaned

            # 也清理子题（sub_questions）中的 stem 序号
            subs = enriched.get("sub_questions")
            if subs and isinstance(subs, list):
                for sq in subs:
                    sq_stem = sq.get("stem", "")
                    if sq_stem and isinstance(sq_stem, str):
                        cleaned = re.sub(r'^\s*\d+\s*[.、)）]\s*(?!_+)', '', sq_stem)
                        if cleaned != sq_stem:
                            sq["stem"] = cleaned

            enriched.update({
                "option_count": len(options),
                "is_multi_choice": 1 if is_multi else 0,
                "question_type": qtype,
            })
            enhanced.append(enriched)
        return enhanced

    @staticmethod
    def _build_answer_sheet_config(exam_id: int, questions: list, title: str = "标准答题卡") -> dict:
        """基于试卷题目自动构建答题卡配置

        生成并保存答题卡HTML文件到磁盘（uploads/answer_sheets/），
        通过 StaticFiles 提供公开访问（无需认证），解决浏览器
        <a> 标签预览答题卡时的认证问题。

        返回配置字典，包含坐标配置和下载地址。
        """
        total_questions = len(questions)
        if not questions:
            return {"total_questions": 0, "option_count": 0, "options": []}

        # 取第一道题的有效选项
        first_opts = questions[0].get("options", [])
        if first_opts:
            unified_options = first_opts
        else:
            unified_options = ["A", "B", "C", "D"]

        # 复用答题卡生成器的坐标计算逻辑
        coord_config = _build_computed_regions(
            question_count=total_questions,
            options=unified_options,
            id_digits=6,
            id_options=_make_digit_labels(9),
        )

        # 构建每题区域信息
        regions = []
        for i, q in enumerate(questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = q.get("options", unified_options)
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": q.get("question_number", i + 1),
                "type": q.get("type", "single"),
                "score": q.get("score", 0),
                "correct_answer": q.get("correct_answer") or q.get("answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })

        # 生成并保存答题卡HTML文件到磁盘（公开静态访问，无需认证）
        try:
            html_url = save_answer_sheet_html(exam_id, title, questions)
        except Exception:
            # 文件保存失败时回退到需要认证的API端点
            html_url = f"/teacher/exam/{exam_id}/answer-sheet-html"

        scan_layout = coord_config.get("scan_layout")
        result_dict = {
            "total_questions": total_questions,
            "option_count": len(unified_options),
            "options": unified_options,
            "coordinate_config": {
                "canvas_width": coord_config["canvas_width"],
                "canvas_height": coord_config["canvas_height"],
                "id_regions": coord_config["id_regions"],
                "id_digits": coord_config["id_digits"],
                "id_options": coord_config["id_options"],
                "question_regions": coord_config.get("question_regions", []),
                "scan_layout": scan_layout,
            },
            "regions": regions,
            "html_url": html_url,
            "pdf_url": f"/teacher/exam/{exam_id}/answer-sheet-pdf",
            "png_url": f"/teacher/exam/{exam_id}/answer-sheet-png",
        }
        return result_dict

    @staticmethod
    async def get_exam_detail(
        db: AsyncSession, exam_id: int, teacher_id: int
    ) -> dict | None:
        """获取试卷详情（含增强题型信息和答题卡配置）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return None

        questions = exam.questions or []

        # 高中学段（含高考）：从21开始编号（听力占用1-20）
        is_senior = exam.grade and (
            "高中" in exam.grade
            or "高三" in exam.grade
            or exam.grade.startswith("高")
            or "senior" in exam.grade.lower()
            or "高考" in exam.grade
        )
        start_num = 21 if is_senior else 1
        enhanced_questions = ExamService._enhance_questions(questions, start_number=start_num)

        result = {
            "id": exam.id,
            "teacher_id": exam.teacher_id,
            "class_id": exam.class_id,
            "title": exam.title,
            "questions": enhanced_questions,
            "description": exam.description or "",
            "paper_draft": is_paper_draft(exam.answer_sheet_config),
            "paper_draft_editable": exam.status == "draft" and not exam.submission_count and (
                is_paper_draft(exam.answer_sheet_config) or not exam.answer_sheet_config
            ) and all(q.get("type", "choice") in ("choice", "single", "single_choice") for q in questions),
            "question_count": len(questions),
            "total_score": exam.total_score,
            "difficulty": exam.difficulty,
            "duration_minutes": exam.duration_minutes,
            "knowledge_points": exam.knowledge_points.split(",") if exam.knowledge_points else [],
            "grade": exam.grade or "",
            "status": exam.status,
            "submission_count": exam.submission_count or 0,
            "avg_score": exam.avg_score,
            "published_at": exam.published_at.isoformat() if exam.published_at else None,
            "created_at": exam.created_at.isoformat() if exam.created_at else None,
            "updated_at": exam.updated_at.isoformat() if exam.updated_at else None,
        }

        # 返回答题卡配置（优先用存储的，否则动态生成）
        stored_config = exam.answer_sheet_config
        if is_paper_draft(stored_config):
            result["answer_sheet"] = None
        elif stored_config:
            # 兼容旧数据：如果 html_url 指向需要认证的旧API端点，
            # 且有题目数据，则重新生成HTML文件并更新为公开静态URL
            html_url = stored_config.get("html_url", "")
            if "/teacher/exam/" in html_url and questions:
                try:
                    new_html_url = save_answer_sheet_html(exam_id, exam.title, enhanced_questions)
                    stored_config["html_url"] = new_html_url
                except Exception:
                    pass  # 文件保存失败时保持旧URL不变
            # 兼容旧数据：将存储的选项文本转换为字母标签
            stored_regions = stored_config.get("regions", [])
            for r in stored_regions:
                raw_opts = r.get("options", [])
                if raw_opts and not all(o in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for o in raw_opts):
                    r["options"] = _make_option_letters(r.get("option_count", len(raw_opts)))
            # 兼容旧数据：coordinate_config 缺少 question_regions 或为 printable sheet 格式时从 regions 补充
            cc = stored_config.get("coordinate_config")
            needs_qr_rebuild = False
            existing_qr = cc.get("question_regions", []) if cc else []
            if not existing_qr:
                needs_qr_rebuild = True
            elif stored_regions:
                # 检测 printable sheet 格式（只有 number/x/y，没有 option_regions）
                first_has_opt = any(r.get("option_regions") for r in existing_qr[:3])
                if not first_has_opt:
                    needs_qr_rebuild = True
            if cc and needs_qr_rebuild and stored_regions:
                qr_list = []
                for sr in stored_regions:
                    qr_list.append({
                        "question_number": sr.get("question_number", 0),
                        "options": sr.get("options", []),
                        "option_regions": sr.get("option_regions", []),
                    })
                cc["question_regions"] = qr_list
                logger.info(f"get_exam_detail: 已从 regions 重建 question_regions({len(qr_list)} 道题)")
            result["answer_sheet"] = stored_config
        else:
            result["answer_sheet"] = ExamService._build_answer_sheet_config(exam_id, enhanced_questions, exam.title)

        return result

    @staticmethod
    def _build_answer_sheet_config_from_json(exam_id: int, choice_questions: list, title: str = "标准答题卡") -> dict:
        """基于选择题JSON构建答题卡配置（支持每题不同选项数）

        生成并保存答题卡HTML文件到磁盘（uploads/answer_sheets/），
        通过 StaticFiles 提供公开访问（无需认证）。

        参数:
            exam_id: 试卷ID
            choice_questions: SKILL.md格式的choice_questions列表
            title: 试卷标题
        """
        if not choice_questions:
            return {"total_questions": 0, "option_count": 0, "options": []}

        id_options = _make_digit_labels(9)
        coord_config = _build_computed_regions_from_json(
            choice_questions=choice_questions,
            id_digits=6,
            id_options=id_options,
        )

        # 构建每题区域信息
        regions = []
        for i, q in enumerate(choice_questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = q.get("options", ["A", "B", "C", "D"])
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": q.get("question_number", i + 1),
                "type": q.get("question_type", "single_choice"),
                "score": q.get("score", 1.0),
                "correct_answer": q.get("correct_answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })

        max_oc = max(
            (q.get("option_count", len(q.get("options", ["A","B","C","D"]))) for q in choice_questions),
            default=4,
        )

        # 生成并保存答题卡HTML文件到磁盘（公开静态访问，无需认证）
        try:
            html_url = save_answer_sheet_html_from_json(exam_id, title, choice_questions)
        except Exception:
            # 文件保存失败时回退到需要认证的API端点
            html_url = f"/teacher/exam/{exam_id}/answer-sheet-html"

        scan_layout = coord_config.get("scan_layout")
        return {
            "total_questions": len(choice_questions),
            "option_count": max_oc,
            "options": list(sorted(set(
                opt for q in choice_questions
                for opt in q.get("options", ["A","B","C","D"])
            ))),
            "coordinate_config": {
                "canvas_width": coord_config["canvas_width"],
                "canvas_height": coord_config["canvas_height"],
                "id_regions": coord_config["id_regions"],
                "id_digits": coord_config["id_digits"],
                "id_options": coord_config["id_options"],
                "question_regions": coord_config.get("question_regions", []),
                "scan_layout": scan_layout,
            },
            "regions": regions,
            "html_url": html_url,
            "pdf_url": f"/teacher/exam/{exam_id}/answer-sheet-pdf",
            "png_url": f"/teacher/exam/{exam_id}/answer-sheet-png",
        }

    @staticmethod
    def _build_graderflow_sheet_config(exam_id: int, questions: list, title: str = "答题卡", id_digits: int = 7) -> dict:
        """基于题目列表构建 GraderFlow 答题卡配置（支持每题不同选项数）"""
        total_questions = len(questions)
        if not questions:
            return {"total_questions": 0, "option_count": 0, "options": []}

        first_opts = questions[0].get("options", [])
        unified_options = first_opts if first_opts else ["A", "B", "C", "D"]
        options_per_question = len(unified_options)

        # 计算每题的实际选项数（支持混合选项试卷）
        question_option_counts = [
            len(q.get("options", unified_options)) for q in questions
        ]
        max_oc = max(question_option_counts) if question_option_counts else options_per_question
        max_options_per_question = max_oc

        id_opts = _make_digit_labels(9)
        columns_per_row = 2 if max_options_per_question > 4 else 4

        coord_config = _build_graderflow_regions(
            question_count=total_questions,
            options_per_question=max_options_per_question,
            id_digits=id_digits,
            id_options=id_opts,
            questions_per_area=5,
            columns_per_row=columns_per_row,
            question_option_counts=question_option_counts,
        )

        # 构建每题区域信息
        regions = []
        for i, q in enumerate(questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = q.get("options", unified_options)
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": q.get("question_number", i + 1),
                "type": q.get("type", "single"),
                "score": q.get("score", 0),
                "correct_answer": q.get("correct_answer") or q.get("answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })

        try:
            html_url = save_graderflow_sheet_html(exam_id, title, questions, id_digits=id_digits)
        except Exception:
            html_url = f"/teacher/exam/{exam_id}/graderflow-sheet-html"

        scan_layout = coord_config.get("scan_layout")
        return {
            "total_questions": total_questions,
            "option_count": max_options_per_question,
            "options": unified_options,
            "sheet_format": "graderflow",
            "coordinate_config": {
                "canvas_width": coord_config["canvas_width"],
                "canvas_height": coord_config["canvas_height"],
                "id_regions": coord_config["id_regions"],
                "id_digits": coord_config["id_digits"],
                "id_options": coord_config["id_options"],
                "question_regions": coord_config.get("question_regions", []),
                "scan_layout": scan_layout,
            },
            "regions": regions,
            "html_url": html_url,
            "pdf_url": f"/teacher/exam/{exam_id}/graderflow-sheet-pdf",
        }

    @staticmethod
    def _build_graderflow_sheet_config_from_json(exam_id: int, choice_questions: list, title: str = "答题卡", id_digits: int = 7) -> dict:
        """基于选择题JSON构建 GraderFlow 答题卡配置（支持每题不同选项数）"""
        if not choice_questions:
            return {"total_questions": 0, "option_count": 0, "options": []}

        total_questions = len(choice_questions)
        id_opts = _make_digit_labels(9)

        # 计算每题的实际选项数和最大选项数
        question_option_counts = [
            q.get("option_count", len(q.get("options", ["A","B","C","D"])))
            for q in choice_questions
        ]
        max_oc = max(question_option_counts, default=4)
        columns_per_row = 2 if max_oc > 4 else 4

        coord_config = _build_graderflow_regions(
            question_count=total_questions,
            options_per_question=max_oc,
            id_digits=id_digits,
            id_options=id_opts,
            questions_per_area=5,
            columns_per_row=columns_per_row,
            question_option_counts=question_option_counts,
        )

        # 构建每题区域信息
        regions = []
        for i, q in enumerate(choice_questions):
            qr = coord_config["question_regions"][i] if i < len(coord_config["question_regions"]) else {}
            raw_opts = q.get("options", ["A", "B", "C", "D"])
            opt_labels = _make_option_letters(len(raw_opts))
            regions.append({
                "question_number": q.get("question_number", i + 1),
                "type": q.get("question_type", "single_choice"),
                "score": q.get("score", 1.0),
                "correct_answer": q.get("correct_answer", ""),
                "options": opt_labels,
                "option_count": len(raw_opts),
                "option_regions": qr.get("option_regions", []),
            })

        try:
            html_url = save_graderflow_sheet_html_from_json(exam_id, title, choice_questions, id_digits=id_digits)
        except Exception:
            html_url = f"/teacher/exam/{exam_id}/graderflow-sheet-html"

        scan_layout = coord_config.get("scan_layout")
        return {
            "total_questions": total_questions,
            "option_count": max_oc,
            "options": list(sorted(set(
                opt for q in choice_questions
                for opt in q.get("options", ["A","B","C","D"])
            ))),
            "sheet_format": "graderflow",
            "coordinate_config": {
                "canvas_width": coord_config["canvas_width"],
                "canvas_height": coord_config["canvas_height"],
                "id_regions": coord_config["id_regions"],
                "id_digits": coord_config["id_digits"],
                "id_options": coord_config["id_options"],
                "question_regions": coord_config.get("question_regions", []),
                "scan_layout": scan_layout,
            },
            "regions": regions,
            "html_url": html_url,
            "pdf_url": f"/teacher/exam/{exam_id}/graderflow-sheet-pdf",
        }

    @staticmethod
    def _extract_choice_questions(questions: list, title: str = "试卷", start_number: int = 1) -> list:
        """从AI生成的题目列表中提取选择题，转换为choice_questions JSON格式

        筛选出有选项的选择题（choice/single/multiple/cloze/reading/seven_choice等），
        阅读理解的每道子题展开为独立的答题卡条目。

        参数:
            start_number: 起始题号，高考试卷从21开始

        返回: [
            {
                "question_number": int,
                "section": str,
                "question_type": "single_choice" | "multiple_choice",
                "correct_answer": str,
                "option_count": int,
                "options": ["A","B","C","D",...],
                "score": float,
            },
            ...
        ]
        """
        # 需要提取选项的题型
        choice_types = {
            "choice", "single", "multiple", "single_choice", "multiple_choice",
            "cloze", "seven_choice",
        }
        result = []
        idx = start_number - 1  # 从 start_number 开始编号
        for source_index, q in enumerate(questions):
            qtype = q.get("type", "choice")
            if q.get("question_number") is not None:
                idx = int(q["question_number"]) - 1

            # ── 阅读理解：将每道子题展开为独立的答题卡条目 ──
            if qtype == "reading":
                sub_questions = q.get("sub_questions") or q.get("questions") or []
                if not sub_questions:
                    continue
                for sub_index, sq in enumerate(sub_questions):
                    idx += 1
                    if sq.get("question_number") is not None:
                        idx = int(sq["question_number"])
                    sq_options = sq.get("options", [])
                    sq_oc = sq.get("option_count", len(sq_options) if sq_options else 4)
                    sq_labels = _make_option_letters(sq_oc)
                    sq_answer = sq.get("answer", "")
                    if isinstance(sq_answer, list):
                        sq_answer = "".join([str(a).strip() for a in sq_answer])
                    result.append({
                        "question_number": idx,
                        "source_index": source_index,
                        "sub_index": sub_index,
                        "section": title,
                        "question_type": "single_choice",
                        "correct_answer": str(sq_answer).strip().upper(),
                        "option_count": sq_oc,
                        "options": sq_labels,
                        "score": float(sq.get("score", float(q.get("score", 5.0)) / len(sub_questions))),
                    })
                continue

            # ── 完形填空：每空展开为独立条目（共用4选1选项） ──
            if qtype == "cloze":
                answers = q.get("answers", q.get("answer", []))
                if isinstance(answers, str):
                    answers = [answers]
                if not answers:
                    # 回退：当作文本题
                    continue
                options_2d = q.get("options", [])
                total_score = float(q.get("score", 15.0))
                per_score = round(total_score / max(len(answers), 1), 1)
                for ai, ans in enumerate(answers):
                    idx += 1
                    # 取该空对应的选项组，或默认4个选项
                    blank_opts = options_2d[ai] if isinstance(options_2d, list) and ai < len(options_2d) else []
                    oc = len(blank_opts) if blank_opts else 4
                    labels = _make_option_letters(oc)
                    result.append({
                        "question_number": idx,
                        "source_index": source_index,
                        "sub_index": ai,
                        "section": title,
                        "question_type": "single_choice",
                        "correct_answer": str(ans).strip().upper(),
                        "option_count": oc,
                        "options": labels,
                        "score": per_score,
                    })
                continue

            # ── 七选五：5个空展开为独立条目（共用7个选项A-G） ──
            if qtype == "seven_choice":
                answers = q.get("answers", q.get("answer", []))
                if isinstance(answers, str):
                    answers = [answers]
                if not answers:
                    continue
                total_score = float(q.get("score", 12.5))
                per_score = round(total_score / max(len(answers), 1), 1)
                for ai, ans in enumerate(answers):
                    idx += 1
                    result.append({
                        "question_number": idx,
                        "source_index": source_index,
                        "sub_index": ai,
                        "section": title,
                        "question_type": "single_choice",
                        "correct_answer": str(ans).strip().upper(),
                        "option_count": 7,
                        "options": _make_option_letters(7),
                        "score": per_score,
                    })
                continue

            # ── 普通选择题 ──
            if qtype not in choice_types:
                skipped_answers = q.get("answers", q.get("answer", []))
                idx += len(skipped_answers) if qtype == "grammar_fill" and isinstance(skipped_answers, list) else 1
                continue
            idx += 1
            options = q.get("options", [])
            option_count = q.get("option_count", len(options) if options else 4)
            option_labels = _make_option_letters(option_count)
            answer = q.get("answer", "")
            if isinstance(answer, list):
                answer = "".join([str(a).strip() for a in answer])
            is_multi = q.get("is_multi_choice", 0) == 1 or qtype in ("multiple", "multiple_choice")
            result.append({
                "question_number": idx,
                "source_index": source_index,
                "section": title,
                "question_type": "multiple_choice" if is_multi else "single_choice",
                "correct_answer": str(answer).strip().upper(),
                "option_count": option_count,
                "options": option_labels,
                "score": float(q.get("score", 5.0)),
            })
        return result

    # ===================== 答题卡模板管理 =====================

    @staticmethod
    def _template_to_dict(template: AnswerSheetTemplate) -> dict:
        """将 AnswerSheetTemplate ORM 模型转为字典"""
        return {
            "id": template.id,
            "id_str": str(template.id),
            "name": template.name,
            "grade": template.grade,
            "description": template.description,
            "question_count": template.question_count,
            "total_score": template.total_score,
            "choice_questions": template.choice_questions,
            "revision": template_revision(template),
            "is_default": template.is_default,
            "archived_at": template.archived_at.isoformat() if template.archived_at else None,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        }

    @staticmethod
    async def _unset_other_defaults(db: AsyncSession, teacher_id: int, exclude_id: int = 0):
        """将教师的其他默认模板取消默认标记"""
        stmt = select(AnswerSheetTemplate).where(
            AnswerSheetTemplate.teacher_id == teacher_id,
            AnswerSheetTemplate.is_default == 1,
            AnswerSheetTemplate.archived_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(AnswerSheetTemplate.id != exclude_id)
        others = (await db.execute(stmt)).scalars().all()
        for o in others:
            o.is_default = 0

    @staticmethod
    async def create_answer_sheet_template(
        db: AsyncSession,
        teacher_id: int,
        name: str,
        choice_questions: list,
        grade: str = "",
        description: str = "",
        is_default: int = 0,
        *,
        create_only: bool = False,
        template_id: int | None = None,
        expected_revision: str | None = None,
    ) -> dict:
        """创建或更新答题卡模板

        参数:
            teacher_id - 教师ID
            name - 模板名称（同一教师下唯一）
            choice_questions - SKILL.md格式的选择题JSON列表
            grade - 适用年级
            description - 模板描述
            is_default - 是否设为默认模板

        返回: 模板数据字典
        """
        # Serialize name checks for a teacher using the existing owner row.
        await db.scalar(select(User.id).where(User.id == teacher_id).with_for_update())
        active = select(AnswerSheetTemplate).where(
            AnswerSheetTemplate.teacher_id == teacher_id,
            AnswerSheetTemplate.archived_at.is_(None),
        )
        existing = None
        same_name = active.where(AnswerSheetTemplate.name == name)
        if template_id is not None:
            owned = await db.scalar(select(AnswerSheetTemplate).where(
                AnswerSheetTemplate.teacher_id == teacher_id, AnswerSheetTemplate.id == template_id,
            ).with_for_update())
            if owned is None:
                raise LookupError("模板不存在或无权访问")
            if owned.archived_at is not None:
                raise ValueError("模板已停用，请选择其他模板")
            if expected_revision != template_revision(owned):
                raise ValueError("模板已更新，请重新打开")
            existing = owned
            same_name = same_name.where(AnswerSheetTemplate.id != template_id)

        duplicate = await db.scalar(same_name.order_by(AnswerSheetTemplate.id).limit(1).with_for_update())
        if duplicate is not None:
            if create_only or template_id is not None:
                raise ValueError("模板名称已存在")
            existing = duplicate

        # 计算统计信息
        question_count = len(choice_questions)
        total_score = sum(q.get("score", 5) for q in choice_questions)

        if existing:
            # 更新已有模板
            existing.name = name
            existing.choice_questions = choice_questions
            existing.question_count = question_count
            existing.total_score = total_score
            existing.grade = grade
            existing.description = description
            flag_modified(existing, "choice_questions")
            if is_default:
                await ExamService._unset_other_defaults(db, teacher_id, exclude_id=existing.id)
                existing.is_default = 1
            elif existing.is_default == 1:
                existing.is_default = 0
            await db.flush()
            await db.refresh(existing)
            return ExamService._template_to_dict(existing)

        # 创建新模板
        if is_default:
            await ExamService._unset_other_defaults(db, teacher_id)

        template = AnswerSheetTemplate(
            teacher_id=teacher_id,
            name=name,
            grade=grade,
            description=description,
            choice_questions=choice_questions,
            question_count=question_count,
            total_score=total_score,
            is_default=is_default,
        )
        db.add(template)
        await db.flush()
        await db.refresh(template)
        return ExamService._template_to_dict(template)

    @staticmethod
    async def list_answer_sheet_templates(
        db: AsyncSession,
        teacher_id: int,
        grade: str = "",
    ) -> list[dict]:
        """获取教师的答题卡模板列表

        参数:
            teacher_id - 教师ID
            grade - 可选年级过滤
        """
        stmt = select(AnswerSheetTemplate).where(
            AnswerSheetTemplate.teacher_id == teacher_id,
            AnswerSheetTemplate.archived_at.is_(None),
        )
        if grade:
            stmt = stmt.where(AnswerSheetTemplate.grade == grade)
        stmt = stmt.order_by(AnswerSheetTemplate.is_default.desc(), AnswerSheetTemplate.updated_at.desc(), AnswerSheetTemplate.id.desc())

        result = await db.execute(stmt)
        templates = result.scalars().all()
        return [ExamService._template_to_dict(t) for t in templates]

    @staticmethod
    async def get_answer_sheet_template(
        db: AsyncSession,
        template_id: int,
        teacher_id: int,
    ) -> dict | None:
        """获取单个答题卡模板详情"""
        template = await db.get(AnswerSheetTemplate, template_id)
        if not template or template.teacher_id != teacher_id:
            return None
        return ExamService._template_to_dict(template)

    @staticmethod
    async def archive_answer_sheet_template(
        db: AsyncSession,
        template_id: int,
        teacher_id: int,
    ) -> bool:
        """停用模板，保留已应用试卷的来源。重复停用可安全重试。"""
        template = await db.scalar(select(AnswerSheetTemplate).where(
            AnswerSheetTemplate.id == template_id, AnswerSheetTemplate.teacher_id == teacher_id,
        ).with_for_update())
        if template is None:
            return False
        if template.archived_at is None:
            template.archived_at = func.now()
            template.is_default = 0
            await db.flush()
        return True

    # ===================== 组卷 =====================

    @staticmethod
    async def list_exams_for_pick(
        db: AsyncSession,
        teacher_id: int,
        stage_category: str = "",
    ) -> list[dict]:
        """获取教师所有试卷及其题目预览（用于选题组卷）

        参数:
            teacher_id - 教师ID
            stage_category - 学段过滤（可选）

        返回: 每张试卷含题目预览列表
        """
        stmt = select(TeacherExam).where(TeacherExam.teacher_id == teacher_id)
        if stage_category:
            stmt = stmt.where(TeacherExam.stage_category == stage_category)
        stmt = stmt.order_by(TeacherExam.created_at.desc())

        result = await db.execute(stmt)
        exams = result.scalars().all()

        items = []
        for exam in exams:
            questions = exam.questions or []
            items.append({
                "exam_id": exam.id,
                "title": exam.title,
                "grade": exam.grade or "",
                "stage_category": exam.stage_category or "",
                "question_count": len(questions),
                "total_score": exam.total_score or 100,
                "difficulty": exam.difficulty,
                "duration_minutes": exam.duration_minutes,
                "status": exam.status,
                "questions": [
                    {
                        "index": i,
                        "type": q.get("type", "choice"),
                        "difficulty": q.get("difficulty", 1),
                        "stem": q.get("stem", ""),
                        "options": q.get("options", []),
                        "score": q.get("score", 0),
                        "knowledge_point": q.get("knowledge_point", ""),
                    }
                    for i, q in enumerate(questions)
                ],
            })

        return items

    @staticmethod
    async def compose_exam(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        class_id: int,
        selected_questions: list[dict],
        shuffle: bool = True,
        grade: str = "",
    ) -> dict:
        """从多张试卷选取题目组合成新试卷

        参数:
            teacher_id - 教师ID
            title - 新试卷标题
            class_id - 目标班级ID
            selected_questions - 选题列表
                [{"exam_id": 1, "question_index": 0, "score": 2}, ...]
            shuffle - 是否打乱题目顺序
            grade - 适用年级
        """
        if not selected_questions:
            raise ValueError("未选择任何题目")

        # 1. 收集所有来源试卷ID
        source_exam_ids_set = set()
        for sq in selected_questions:
            eid = sq.get("exam_id")
            if eid:
                source_exam_ids_set.add(eid)

        # 2. 批量加载来源试卷，校验归属
        source_exams = {}
        for eid in source_exam_ids_set:
            exam = await db.get(TeacherExam, eid)
            if not exam or exam.teacher_id != teacher_id:
                raise ValueError(f"试卷 {eid} 不存在或无权限")
            source_exams[eid] = exam.questions or []

        # 3. 从各试卷提取题目
        composed_questions = []
        total_score = 0
        inferred_stage = ""
        for sq in selected_questions:
            eid = sq["exam_id"]
            qidx = sq["question_index"]
            custom_score = sq.get("score")

            if eid not in source_exams or qidx >= len(source_exams[eid]):
                raise ValueError(f"试卷 {eid} 中索引 {qidx} 的题目不存在")

            question = dict(source_exams[eid][qidx])  # 深拷贝
            if custom_score is not None:
                question["score"] = custom_score
            composed_questions.append(question)
            total_score += question.get("score", 0)

            # 从来源试卷推断学段
            if not inferred_stage:
                src_exam = source_exams[eid]  # 这里应该用完整的 exam 对象
                # 重新加载以便获取 stage_category
                exam_obj = await db.get(TeacherExam, eid)
                if exam_obj and exam_obj.stage_category:
                    inferred_stage = exam_obj.stage_category

        # 4. 可选：打乱顺序
        if shuffle and len(composed_questions) > 1:
            import random
            random.shuffle(composed_questions)

        # 5. 构建 source_exam_ids 字符串
        source_ids_str = ",".join(str(eid) for eid in sorted(source_exam_ids_set))

        # 6. 保存为新试卷
        exam = await ExamService.save_exam(
            db=db,
            teacher_id=teacher_id,
            class_id=class_id,
            title=title,
            questions=composed_questions,
            total_score=total_score,
            difficulty=2,  # 组卷默認中等难度
            duration_minutes=60,
            knowledge_points=[],
            grade=grade,
            stage_category=inferred_stage,
            source_exam_ids=source_ids_str,
        )

        return {
            "id": exam.id,
            "exam_id": exam.id,
            "title": exam.title,
            "questions": composed_questions,
            "total_score": total_score,
            "question_count": len(composed_questions),
            "source_exam_ids": source_ids_str,
            "stage_category": inferred_stage,
            "status": exam.status,
            "created_at": datetime.now().isoformat(),
        }

    @staticmethod
    async def delete_exam(
        db: AsyncSession, exam_id: int, teacher_id: int
    ) -> bool:
        """删除试卷（幂等：记录不存在也算成功，避免幽灵记录无法清理）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam:
            return True  # 记录已不存在，幂等返回成功
        if exam.teacher_id != teacher_id:
            return False
        await db.delete(exam)
        await db.flush()
        return True

    # ===================== 出卷 AI 接口 =====================

    @staticmethod
    async def generate_and_save(
        db: AsyncSession,
        teacher_id: int,
        class_id: int,
        title: str,
        knowledge_points: list[str],
        question_types: list[str],
        difficulty: int,
        question_count: int,
        duration_minutes: int,
        question_type_counts: dict | None = None,
        grade: str = "",
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
    ) -> dict:
        """AI 生成并保存试卷"""
        exam_data = await ExamService.generate_exam(
            db, teacher_id, class_id, title,
            knowledge_points, question_types,
            difficulty, question_count, duration_minutes,
            question_type_counts, grade,
            stage_category=stage_category,
            use_rag=use_rag,
            additional_references=additional_references,
        )

        if "error" in exam_data:
            return exam_data

        exam = await ExamService.save_exam(
            db, teacher_id,
            title=exam_data["title"],
            questions=exam_data["questions"],
            total_score=exam_data["total_score"],
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            knowledge_points=knowledge_points,
            class_id=class_id,
            grade=grade,
        )

        from datetime import datetime

        return {
            "id": exam.id,
            "exam_id": exam.id,
            "title": exam.title,
            "class_id": class_id,
            "questions": exam_data["questions"],
            "total_score": exam_data["total_score"],
            "question_count": exam_data["question_count"],
            "difficulty": difficulty,
            "duration_minutes": duration_minutes,
            "knowledge_points": knowledge_points,
            "grade": grade,
            "status": exam.status,
            "created_at": datetime.now().isoformat(),
        }

    # ===================== 批卷 =====================

    @staticmethod
    def _extract_option_letter(text: str) -> str:
        """从选项文本中提取字母前缀，如 'A. 内容' → 'A', 'A选项' → 'A', 'A)' → 'A'
        如果提取不到字母前缀，返回原文的大写形式"""
        s = text.strip().upper()
        # 匹配 "A." / "A、" / "A。" / "A)" / "A " 等前缀
        m = re.match(r'^([A-Z])[.、。）)）\s]', s)
        if m:
            return m.group(1)
        # 匹配 "A选项" / "A内容" 等（第一个字母 + 中文）
        m = re.match(r'^([A-Z])[\u4e00-\u9fff]', s)
        if m:
            return m.group(1)
        # 纯字母
        if len(s) == 1 and s.isalpha():
            return s
        return s

    @staticmethod
    async def auto_grade_submission(
        db: AsyncSession,
        exam_id: int,
        student_id: int,
        answers: list[dict],
        teacher_id: int,
        exam_number: str = "",
    ) -> dict:
        """AI 自动批改学生提交

        answers 格式: [{"question_index": 0, "answer": "A"}, {"question_index": 1, "answer": "..."}]
        exam_number: 考号（OCR批卷时传入，用于考号匹配）
        """
        exam = await db.get(TeacherExam, exam_id)
        if not exam:
            return {"error": "试卷不存在"}

        questions = exam.questions
        if not questions:
            return {"error": "试卷无题目"}

        total_score = exam.total_score or 100
        score_perq = total_score / len(questions)

        # 逐题批改 — 第一遍：收集题目信息，选择题直接评分
        graded_questions = []
        auto_score = 0.0
        need_teacher_review = False
        ai_batch_items = []  # [(index, question, user_answer), ...]

        for i, q in enumerate(questions):
            user_answer = ""
            for a in answers:
                if a.get("question_index") == i:
                    user_answer = a.get("answer", "")
                    break

            q_type = q.get("type", "choice")
            correct = q.get("answer", "")
            max_score = q.get("score", score_perq)

            # 先构建基础 result 结构
            result = {
                "index": i,
                "type": q_type,
                "stem": q.get("stem", ""),
                "user_answer": user_answer,
                "correct_answer": correct,
                "max_score": max_score,
            }

            if q_type == "choice":
                # 选择题：精确匹配（选项字母前缀匹配），无需 AI
                user_letter = ExamService._extract_option_letter(str(user_answer))
                correct_str = str(correct).strip().upper()
                is_correct = user_letter == correct_str
                result["score"] = max_score if is_correct else 0
                result["is_correct"] = is_correct
                auto_score += result["score"]

            elif q_type == "fill":
                # 填空题：精确匹配（不区分大小写、忽略首尾空格），无需 AI
                is_correct = str(user_answer).strip().lower() == str(correct).strip().lower()
                result["score"] = max_score if is_correct else 0
                result["is_correct"] = is_correct
                auto_score += result["score"]

            elif q_type in ("translation", "writing", "reading"):
                # 翻译/写作/阅读：收集到批改队列中，稍后一次 AI 调用完成
                ai_batch_items.append((i, q, user_answer))
                if q_type in ("translation", "writing"):
                    need_teacher_review = True
            else:
                # 其他题型默认给一半分，需教师复核
                need_teacher_review = True
                result["score"] = max_score * 0.5
                result["is_correct"] = False
                result["ai_comment"] = "待教师手动评分"
                auto_score += result["score"]

            graded_questions.append(result)

        # 批量 AI 批改：将所有非选择题合并为一次 AI 调用
        if ai_batch_items:
            batch_results = await ExamService._ai_batch_grade(
                db, ai_batch_items, teacher_id
            )
            # 将批改结果写入对应的 graded_questions
            for idx, q, user_answer in ai_batch_items:
                result = graded_questions[idx]
                ai_result = batch_results.get(idx, {})
                result["score"] = ai_result.get("score", 0)
                result["ai_comment"] = ai_result.get("comment", "")
                auto_score += result["score"]

                q_type = q.get("type", "")
                if q_type in ("translation", "writing"):
                    result["dimensions"] = ai_result.get("dimensions", [])
                elif q_type == "reading":
                    result["passage"] = q.get("passage", "")
                    result["sub_questions"] = q.get("sub_questions", [])
                    result["sub_details"] = ai_result.get("sub_details", [])

        # 保存提交记录
        submission = ExamSubmission(
            exam_id=exam_id,
            student_id=student_id,
            exam_number=exam_number,
            answers=answers,
            score=round(auto_score, 1),
            max_score=total_score,
            ai_grade_detail=graded_questions,
            grading_status="ai_done" if not need_teacher_review else "pending",
            submitted_at=datetime.now(),
        )
        db.add(submission)
        await db.flush()
        await db.refresh(submission)

        # 记录 AI 批改日志
        log = ExamGradingLog(
            submission_id=submission.id,
            grader_type="ai",
            grader_id=0,
            action="auto_grade",
            detail={
                "total_score": round(auto_score, 1),
                "max_score": total_score,
                "need_review": need_teacher_review,
            },
        )
        db.add(log)
        await db.flush()

        # 更新试卷统计数据
        exam.submission_count = (exam.submission_count or 0) + 1
        if exam.avg_score is None:
            exam.avg_score = round(auto_score, 1)
        else:
            exam.avg_score = round(
                (exam.avg_score * (exam.submission_count - 1) + auto_score) / exam.submission_count,
                1,
            )
        await db.flush()

        return {
            "submission_id": submission.id,
            "total_score": round(auto_score, 1),
            "max_score": total_score,
            "graded_questions": graded_questions,
            "need_teacher_review": need_teacher_review,
            "grading_status": submission.grading_status,
        }

    @staticmethod
    async def _ai_batch_grade(
        db: AsyncSession,
        items: list[tuple[int, dict, str]],
        user_id: int,
    ) -> dict[int, dict]:
        """将多道非选择题合并为一次 AI 调用进行批量批改

        Args:
            items: [(question_index, question_dict, user_answer), ...]

        Returns:
            {question_index: {score, comment, ...}}
        """
        # 如果没有题目或仅含空答案，跳过 AI 调用
        non_empty = [(idx, q, ans) for idx, q, ans in items if ans.strip()]
        if not non_empty:
            # 所有题目都未作答
            result = {}
            for idx, q, ans in items:
                r = {"score": 0, "comment": "未作答"}
                if q.get("type") in ("translation", "writing"):
                    r["dimensions"] = []
                if q.get("type") == "reading":
                    r["sub_details"] = []
                result[idx] = r
            return result

        # 构建批量批改的题目描述
        question_descriptions = []
        for idx, q, ans in items:
            q_type = q.get("type", "fill")
            stem = q.get("stem", "")
            correct = q.get("answer", "")
            max_score = q.get("score", 10)
            display_ans = ans if ans else "（未作答）"

            desc_parts = [
                f"【题目 {idx + 1}】",
                f"类型：{q_type}",
                f"题目内容：{stem}",
            ]

            if q_type == "fill":
                desc_parts.append(f"标准答案：{correct}")
                desc_parts.append(f"学生答案：{display_ans}")
                desc_parts.append(f"满分：{max_score}")
                desc_parts.append(f"返回格式：{{\"score\": 0~{max_score}(float), \"comment\": \"评语\"}}")
            elif q_type in ("translation", "writing"):
                desc_parts.append(f"参考标准：{correct}")
                desc_parts.append(f"学生答案：{display_ans}")
                desc_parts.append(f"满分：{max_score}")
                desc_parts.append(
                    f"返回格式：{{\"score\": 0~{max_score}(float), \"comment\": \"总体评语\", "
                    f"\"dimensions\": [{{\"name\": \"维度名\", \"score\": 8, \"comment\": \"评语\"}}], "
                    f"\"suggestions\": \"改进建议\"}}"
                )
            elif q_type == "reading":
                passage = q.get("passage", "")[:1500]
                desc_parts.append(f"文章：\n{passage}")
                sub_qs = q.get("sub_questions", [])
                if sub_qs:
                    for j, sq in enumerate(sub_qs):
                        opts = f"选项: {', '.join(sq.get('options', []))}" if sq.get("options") else ""
                        sq_ans = sq.get("answer", "")
                        desc_parts.append(f"  子题{j+1}: {sq.get('stem', '')} ({opts}) 标准答案: {sq_ans}")
                else:
                    desc_parts.append(f"标准答案：{correct}")
                desc_parts.append(f"学生答案：{display_ans}")
                desc_parts.append(f"满分：{max_score}")
                desc_parts.append(
                    f"返回格式：{{\"score\": 0~{max_score}(float), \"comment\": \"总体评语\", "
                    f"\"sub_details\": [{{\"index\": 0, \"score\": 2.0, \"comment\": \"正确\"}}]}}"
                )

            question_descriptions.append("\n".join(desc_parts))

        prompt = (
            "你是一位英语评分教师，请批量评判以下试卷中的主观题。\n\n"
            "评分原则：\n"
            "- 翻译/写作题：按内容完整性、语法正确性、词汇丰富度、结构逻辑、拼写标点五个维度评分，给出总得分和改进建议\n"
            "- 阅读理解题：先逐个判断子题正确性，选择题必须与标准答案完全一致才得分，简答/填空子题按语义酌情给分\n\n"
            "题目列表：\n\n"
            + "\n---\n".join(question_descriptions)
            + "\n\n"
            "请严格按照上述每道题指定的 JSON 格式返回结果，并以 JSON 数组形式输出，数组中每个元素对应一道题：\n"
            '[{"index": 0, "score": ..., "comment": "..."}, {"index": 1, "score": ..., ...}]'
            "\n\n重要：只输出 JSON 数组，不要添加任何其他文字说明。"
        )

        messages = [{"role": "user", "content": prompt}]
        response = await AIService.chat_completion(
            db, messages, user_id, max_tokens=4096
        )

        logger = logging.getLogger("exam.ai_grade")
        logger.info("AI 批量批改原始响应: %s", response[:500] if response else "空")

        # 解析批量返回结果
        parsed_list = await ExamService._parse_ai_grade_response(response)
        if parsed_list and isinstance(parsed_list, list):
            result_map = {}
            for item in parsed_list:
                idx = item.get("index")
                if idx is not None:
                    # 找到原始题目的类型
                    orig_q = None
                    for q_idx, q, _ in items:
                        if q_idx == idx:
                            orig_q = q
                            break
                    result_map[idx] = item
                    # 翻译/写作的分数换算
                    if orig_q and orig_q.get("type") in ("translation", "writing"):
                        max_score = orig_q.get("score", 10)
                        # 如果 AI 返回了 total_10，按10分制换算
                        total_10 = item.get("total_10")
                        if total_10 is not None:
                            item["score"] = round(total_10 / 10 * max_score, 1)
            # 填充未返回结果的题目
            for idx, q, _ in items:
                if idx not in result_map:
                    result_map[idx] = {"score": 0, "comment": "AI 评分异常"}
                    q_type = q.get("type", "")
                    if q_type in ("translation", "writing"):
                        result_map[idx]["dimensions"] = []
                    if q_type == "reading":
                        result_map[idx]["sub_details"] = []
            return result_map

        logger.warning("AI 评分解析失败，使用兜底方案。原始响应前300字符: %s", response[:300] if response else "空")

        # 解析失败时的兜底
        result = {}
        for idx, q, _ in items:
            q_type = q.get("type", "")
            max_score = q.get("score", 10)
            r = {"score": 0, "comment": "AI 评分异常"}
            if q_type in ("translation", "writing"):
                r["dimensions"] = []
                r["score"] = round(max_score * 0.5, 1)
                r["comment"] = "AI 评分异常，暂按50%计，请教师复核"
            if q_type == "reading":
                r["sub_details"] = []
            result[idx] = r
        return result

    @staticmethod
    def _parse_ai_grade_response(response: str) -> list | None:
        """从 AI 返回文本中提取并解析 JSON 数组"""
        if not response:
            return None
        text = response.strip()
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 代码块
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 尝试提取 [...] 数组
        m = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    # ===================== 成绩查询 =====================

    @staticmethod
    async def get_submissions(
        db: AsyncSession,
        exam_id: int,
        teacher_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """获取试卷提交列表"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        stmt = (
            select(ExamSubmission)
            .where(ExamSubmission.exam_id == exam_id)
            .order_by(ExamSubmission.submitted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        submissions = result.scalars().all()

        count_stmt = select(func.count()).where(ExamSubmission.exam_id == exam_id)
        total = (await db.execute(count_stmt)).scalar() or 0

        return {
            "items": [
                {
                    "id": s.id,
                    "student_id": s.student_id,
                    "score": s.score,
                    "max_score": s.max_score,
                    "grading_status": s.grading_status,
                    "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
                }
                for s in submissions
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_class_exam_results(
        db: AsyncSession,
        exam_id: int,
        class_id: int,
        teacher_id: int,
    ) -> dict:
        """获取某班级所有学生的考试成绩列表

        从 ClassStudent（班级成员）出发，LEFT JOIN ExamSubmission 获取成绩，
        同时兼容 OCR 答题卡场景（ClassStudentInfo 花名册中不在 ClassStudent 的提交）。
        按成绩降序排列（未批改的在最后）。

        与班级功能「学生列表」调用同样的数据源（ClassStudent + User），
        确保考试结果页能看到班级全部成员，而不仅是导入花名册中的学生。
        """
        # ── 校验：试卷存在 ──
        exam = await db.get(TeacherExam, exam_id)
        if not exam:
            return {"error": "试卷不存在"}

        # 校验当前教师对该班级有权限（同班级学生列表的 _verify_class_ownership 逻辑）
        from app.models.class_models import ClassTeacher
        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == teacher_id,
            )
        )
        if not ct.scalar_one_or_none():
            return {"error": "无权操作该班级"}

        # ── 从 exam 对象获取试卷标题 ──
        exam_title = exam.title or ""

        # ── 先查 ClassStudentInfo 花名册，建立 student_name → exam_number 映射 ──
        info_stmt = select(ClassStudentInfo).where(
            ClassStudentInfo.class_id == class_id
        )
        info_result = await db.execute(info_stmt)
        info_rows = info_result.scalars().all()
        exam_number_map: dict[str, str] = {}
        for info_row in info_rows:
            name_key = info_row.student_name
            if name_key not in exam_number_map:
                exam_number_map[name_key] = info_row.exam_number

        # ── 直接按 class_id 查询班级全部学生（ClassStudent）+ User 昵称 + ExamSubmission 成绩 ──
        stmt = (
            select(
                ClassStudent.student_id,
                User.nickname.label("student_name"),
                Class.name.label("class_name"),
                ExamSubmission.exam_number,
                ExamSubmission.score,
                ExamSubmission.grading_status,
                ExamSubmission.id.label("submission_id"),
            )
            .join(User, User.id == ClassStudent.student_id)
            .join(Class, Class.id == ClassStudent.class_id)
            .outerjoin(
                ExamSubmission,
                and_(
                    ExamSubmission.exam_id == exam_id,
                    ExamSubmission.student_id == ClassStudent.student_id,
                ),
            )
            .where(ClassStudent.class_id == class_id)
            .order_by(ExamSubmission.score.desc())
        )
        result = await db.execute(stmt)
        member_rows = result.all()

        # ── 查询2：OCR-only 提交 —— 有 ExamSubmission + ClassStudentInfo 但无对应的 ClassStudent ──
        ocr_stmt = (
            select(
                ClassStudentInfo.student_name,
                Class.name.label("class_name"),
                ClassStudentInfo.exam_number,
                ExamSubmission.score,
                ExamSubmission.grading_status,
                ExamSubmission.id.label("submission_id"),
            )
            .join(Class, Class.id == ClassStudentInfo.class_id)
            .join(
                ExamSubmission,
                and_(
                    ExamSubmission.exam_id == exam_id,
                    ExamSubmission.exam_number == ClassStudentInfo.exam_number,
                ),
            )
            .outerjoin(
                ClassStudent,
                and_(
                    ClassStudent.class_id == class_id,
                    ClassStudent.student_id == ExamSubmission.student_id,
                ),
            )
            .where(
                ClassStudentInfo.class_id == class_id,
                ClassStudent.student_id.is_(None),  # 不在 ClassStudent 中
            )
        )
        ocr_result = await db.execute(ocr_stmt)
        ocr_rows = ocr_result.all()

        # ── 合并结果 ──
        items = []
        seen_names = set()

        for row in member_rows:
            grading_status = row.grading_status or "pending"
            # exam_number 优先取自花名册（ClassStudentInfo），其次才是提交记录
            exam_num = row.exam_number or exam_number_map.get(row.student_name, "")
            items.append({
                "student_id": row.student_id,
                "exam_number": exam_num,
                "student_name": row.student_name,
                "class_name": row.class_name,
                "score": row.score if grading_status != "pending" else None,
                "grading_status": grading_status,
                "submission_id": row.submission_id,
            })
            seen_names.add(row.student_name)

        for row in ocr_rows:
            if row.student_name in seen_names:
                continue
            grading_status = row.grading_status or "pending"
            items.append({
                "student_id": None,  # OCR-only 学生没有注册账户
                "exam_number": row.exam_number or "",
                "student_name": row.student_name,
                "class_name": row.class_name,
                "score": row.score if grading_status != "pending" else None,
                "grading_status": grading_status,
                "submission_id": row.submission_id,
            })
            seen_names.add(row.student_name)

        # 按成绩降序（未批改排在最后）
        items.sort(key=lambda x: x["score"] if x["score"] is not None else -1, reverse=True)

        # ── 班级名称：从第一行数据获取 ──
        class_name = member_rows[0].class_name if member_rows else ""

        return {
            "items": items,
            "total": len(items),
            "exam_title": exam_title,
            "class_name": class_name,
        }

    @staticmethod
    async def teacher_review(
        db: AsyncSession,
        submission_id: int,
        teacher_id: int,
        adjustments: list[dict],
    ) -> dict:
        """教师复核/调整评分

        adjustments: [{"question_index": 0, "adjusted_score": 8, "comment": "..."}]
        """
        sub = await db.get(ExamSubmission, submission_id)
        if not sub:
            return {"error": "提交记录不存在"}

        # 更新分数
        total_adjustment = 0
        new_detail = sub.ai_grade_detail or []
        for adj in adjustments:
            idx = adj.get("question_index")
            new_score = adj.get("adjusted_score")
            comment = adj.get("comment", "")
            for q in new_detail:
                if q.get("index") == idx:
                    old_score = q.get("score", 0)
                    q["score"] = new_score
                    q["teacher_comment"] = comment
                    q["adjusted"] = True
                    total_adjustment += new_score - old_score
                    break

        sub.adjusted_score = (sub.score or 0) + total_adjustment
        sub.teacher_adjustment = adjustments
        sub.grading_status = "teacher_reviewed"
        sub.graded_by = teacher_id
        sub.ai_grade_detail = new_detail
        await db.flush()

        # 记录教师复核日志
        log = ExamGradingLog(
            submission_id=submission_id,
            grader_type="teacher",
            grader_id=teacher_id,
            action="teacher_review",
            detail={
                "adjustments": adjustments,
                "old_score": sub.score,
                "new_score": sub.adjusted_score,
            },
        )
        db.add(log)
        await db.flush()

        return {
            "submission_id": submission_id,
            "adjusted_score": sub.adjusted_score,
            "original_score": sub.score,
            "adjustments": adjustments,
        }

    @staticmethod
    async def get_exam_statistics(
        db: AsyncSession, exam_id: int, teacher_id: int
    ) -> dict:
        """获取试卷统计"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        # 基本统计
        stmt = select(
            func.count().label("total"),
            func.avg(ExamSubmission.score).label("avg"),
            func.max(ExamSubmission.score).label("max"),
            func.min(ExamSubmission.score).label("min"),
        ).where(ExamSubmission.exam_id == exam_id)
        result = await db.execute(stmt)
        stats = result.one()

        # 分数分布
        dist_stmt = select(
            func.sum(func.if_(ExamSubmission.score >= 90, 1, 0)).label("excellent"),
            func.sum(func.if_(ExamSubmission.score.between(80, 89), 1, 0)).label("good"),
            func.sum(func.if_(ExamSubmission.score.between(60, 79), 1, 0)).label("pass"),
            func.sum(func.if_(ExamSubmission.score < 60, 1, 0)).label("fail"),
        ).where(ExamSubmission.exam_id == exam_id)
        dist_result = await db.execute(dist_stmt)
        dist = dist_result.one()

        return {
            "exam_id": exam_id,
            "title": exam.title,
            "total_submissions": stats.total or 0,
            "avg_score": round(stats.avg, 1) if stats.avg else 0,
            "max_score": stats.max or 0,
            "min_score": stats.min or 0,
            "full_score": exam.total_score or 100,
            "distribution": {
                "excellent": dist.excellent or 0,
                "good": dist.good or 0,
                "pass": getattr(dist, "pass") or 0,
                "fail": dist.fail or 0,
            },
        }

    # ==================== 摄像头批卷相关 ====================

    @staticmethod
    async def submit_scan_result(
        db: AsyncSession,
        exam_id: int,
        teacher_id: int,
        body: dict,
    ) -> dict:
        """教师端：提交摄像头扫描批改结果"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        exam_number = body.get("exam_number", "")
        student_id = body.get("student_id")
        score = body.get("score", 0)
        max_score = body.get("max_score", 0)
        multi_score = body.get("multi_score", 0)
        multi_max_score = body.get("multi_max_score", 0)
        grading_status = body.get("grading_status", "ai_done")
        pending_count = body.get("pending_count", 0)
        answers = body.get("answers", [])
        wrong_questions = body.get("wrong_questions", [])
        scan_image_url = body.get("scan_image_url", "")

        # 按考号或 student_id 查找已有提交记录
        stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
        )
        if student_id:
            stmt = stmt.where(ExamSubmission.student_id == student_id)
        elif exam_number:
            stmt = stmt.where(ExamSubmission.exam_number == exam_number)
        else:
            return {"error": "缺少考号或学生ID"}

        result = await db.execute(stmt)
        submission = result.scalar_one_or_none()

        if submission:
            # 更新已有记录
            submission.answers = answers
            submission.score = score
            submission.max_score = max_score
            submission.grading_status = grading_status
            submission.exam_number = exam_number
            if scan_image_url:
                setattr(submission, "scan_image_url", scan_image_url)
            submission.submitted_at = datetime.utcnow()
        else:
            # 创建新记录
            submission = ExamSubmission(
                exam_id=exam_id,
                student_id=student_id or 0,
                exam_number=exam_number,
                answers=answers,
                score=score,
                max_score=max_score,
                grading_status=grading_status,
                submitted_at=datetime.utcnow(),
            )
            db.add(submission)

        await db.flush()
        submission_id = submission.id

        # 更新试卷提交计数和均值
        count_stmt = select(func.count()).where(ExamSubmission.exam_id == exam_id)
        total_sub = (await db.execute(count_stmt)).scalar() or 0
        avg_stmt = select(func.avg(ExamSubmission.score)).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.score.isnot(None),
        )
        avg_result = (await db.execute(avg_stmt)).scalar()
        exam.submission_count = total_sub
        exam.avg_score = round(avg_result, 1) if avg_result else None
        await db.flush()

        return {
            "submission_id": submission_id,
            "exam_id": exam_id,
            "student_id": student_id,
            "score": score,
            "max_score": max_score,
            "multi_score": multi_score,
            "multi_max_score": multi_max_score,
            "grading_status": grading_status,
            "pending_count": pending_count,
            "wrong_count": len(wrong_questions),
            "total_questions": len(answers),
        }

    @staticmethod
    async def get_scan_progress(
        db: AsyncSession,
        exam_id: int,
        teacher_id: int,
    ) -> dict:
        """获取批改进度"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        # 已批改人数
        graded_stmt = select(func.count()).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.score.isnot(None),
        )
        graded_count = (await db.execute(graded_stmt)).scalar() or 0

        # 总人数：从班级花名册获取
        class_id = exam.class_id
        from app.models.class_models import ClassStudentInfo
        total_stmt = select(func.count()).where(ClassStudentInfo.class_id == class_id)
        total_students = (await db.execute(total_stmt)).scalar() or 0

        # 未批学生列表（考号已知但无提交记录的学生）
        ungraded = []
        if total_students > 0:
            info_stmt = select(ClassStudentInfo).where(
                ClassStudentInfo.class_id == class_id,
            )
            info_result = await db.execute(info_stmt)
            all_students = info_result.scalars().all()

            # 已提交考号列表
            sub_stmt = select(ExamSubmission.exam_number).where(
                ExamSubmission.exam_id == exam_id,
                ExamSubmission.exam_number != "",
            )
            sub_result = await db.execute(sub_stmt)
            submitted_numbers = {row[0] for row in sub_result}

            for s in all_students:
                if s.exam_number and s.exam_number not in submitted_numbers:
                    ungraded.append({
                        # 导入花名册不一定关联已注册 User，不能将其主键当用户 ID。
                        "student_id": None,
                        "roster_id": s.id,
                        "student_name": s.student_name,
                        "exam_number": s.exam_number,
                        "student_number": s.student_number,
                    })

        return {
            "exam_id": exam_id,
            "graded_count": graded_count,
            "total_students": total_students,
            "ungraded_students": ungraded,
            "progress_pct": round(graded_count / total_students * 100, 1) if total_students > 0 else 0,
        }

    @staticmethod
    async def get_exam_report(
        db: AsyncSession,
        exam_id: int,
        teacher_id: int,
    ) -> dict:
        """获取试卷成绩统计报告（含逐题正确率、高频错题等）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        # 获取所有提交记录
        sub_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.score.isnot(None),
        )
        sub_result = await db.execute(sub_stmt)
        submissions = sub_result.scalars().all()

        if not submissions:
            # 有试卷但无人提交
            questions = exam.questions or []
            return {
                "exam_id": exam_id,
                "title": exam.title,
                "total_students": 0,
                "graded_students": 0,
                "avg_score": 0,
                "max_score": 0,
                "min_score": 0,
                "single_score_rate": 0,
                "multi_score_rate": 0,
                "score_distribution": [],
                "question_accuracy": [
                    {
                        "question_number": q.get("number", i + 1),
                        "accuracy": 0,
                        "type": q.get("type", "single"),
                    }
                    for i, q in enumerate(questions)
                ],
                "top_wrong_questions": [],
                "multi_choice_errors": None,
                "students": [],
            }

        # 基本统计
        scores = [s.score or 0 for s in submissions]
        total = len(scores)
        avg = sum(scores) / total if total > 0 else 0

        # 成绩分布
        distribution = [
            {"range": "0-59", "count": sum(1 for s in scores if s < 60)},
            {"range": "60-69", "count": sum(1 for s in scores if 60 <= s < 70)},
            {"range": "70-79", "count": sum(1 for s in scores if 70 <= s < 80)},
            {"range": "80-89", "count": sum(1 for s in scores if 80 <= s < 90)},
            {"range": "90-100", "count": sum(1 for s in scores if s >= 90)},
        ]

        # 逐题正确率
        questions = exam.questions or []
        question_accuracy = []
        total_single_score = 0
        earned_single_score = 0
        total_multi_score = 0
        earned_multi_score = 0

        for i, q in enumerate(questions):
            qtype = q.get("type", "single")
            qnum = q.get("number", i + 1)
            qscore = q.get("score", 0)
            correct_ans = q.get("correct_answer", "")
            correct_count = 0

            for sub in submissions:
                sub_answers = sub.answers or []
                for ans in sub_answers:
                    if isinstance(ans, dict) and ans.get("question_number") == qnum:
                        if ans.get("is_correct"):
                            correct_count += 1
                        break
                    # 兼容列表格式
                    if isinstance(ans, list) and len(ans) > 1 and ans[0] == qnum:
                        if ans[2]:  # is_correct
                            correct_count += 1
                        break

            accuracy = correct_count / total if total > 0 else 0
            question_accuracy.append({
                "question_number": qnum,
                "accuracy": round(accuracy, 2),
                "rate": round(accuracy, 2),
                "type": qtype,
                "correct_count": correct_count,
                "total_count": total,
            })

            if qtype == "multiple":
                total_multi_score += qscore
            else:
                total_single_score += qscore

        # 高频错题TOP5
        question_accuracy_sorted = sorted(question_accuracy, key=lambda x: x["accuracy"])
        top_wrong = []
        for qa in question_accuracy_sorted[:5]:
            q = questions[qa["question_number"] - 1] if qa["question_number"] - 1 < len(questions) else {}
            top_wrong.append({
                "question_number": qa["question_number"],
                "error_rate": round(1 - qa["accuracy"], 2),
                "type": qa["type"],
                "score": q.get("score", 0),
            })

        # 多选异常统计
        multi_error_stats = None
        multi_errors = [qa for qa in question_accuracy if qa["type"] == "multiple"]
        if multi_errors:
            multi_error_stats = {
                "total_multi_questions": len(multi_errors),
                "avg_accuracy": round(
                    sum(qa["accuracy"] for qa in multi_errors) / len(multi_errors), 2
                ) if multi_errors else 0,
            }

        # 学生成绩列表
        from app.models.user import User
        student_list = []
        for sub in submissions:
            user = await db.get(User, sub.student_id)
            student_list.append({
                "student_id": sub.student_id,
                "student_name": getattr(user, "username", "") if user else "",
                "score": sub.score or 0,
                "max_score": sub.max_score or exam.total_score or 100,
                "grading_status": sub.grading_status,
            })

        return {
            "exam_id": exam_id,
            "title": exam.title,
            "total_students": total,
            "graded_students": total,
            "avg_score": round(avg, 1),
            "max_score": max(scores),
            "min_score": min(scores),
            "full_score": exam.total_score or 100,
            "single_score_rate": round(earned_single_score / total_single_score * 100, 1) if total_single_score > 0 else 0,
            "multi_score_rate": round(earned_multi_score / total_multi_score * 100, 1) if total_multi_score > 0 else 0,
            "score_distribution": distribution,
            "question_accuracy": question_accuracy,
            "top_wrong_questions": top_wrong,
            "multi_choice_errors": multi_error_stats,
            "students": sorted(student_list, key=lambda x: x["score"], reverse=True),
        }

    @staticmethod
    async def get_question_detail(
        db: AsyncSession,
        exam_id: int,
        question_number: int,
        teacher_id: int,
    ) -> dict:
        """获取单题学情详情"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        questions = exam.questions or []
        if question_number < 1 or question_number > len(questions):
            return {"error": "题目不存在"}

        q = questions[question_number - 1]

        # 获取所有提交中本题的详情
        sub_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.score.isnot(None),
        )
        sub_result = await db.execute(sub_stmt)
        submissions = sub_result.scalars().all()

        correct_answers = []
        wrong_answers = []
        for sub in submissions:
            sub_answers = sub.answers or []
            for ans in sub_answers:
                if isinstance(ans, dict) and ans.get("question_number") == question_number:
                    entry = {
                        "student_id": sub.student_id,
                        "student_answer": ans.get("selected"),
                        "is_correct": ans.get("is_correct", False),
                        "status": ans.get("status", "normal"),
                        "grayscale": ans.get("grayscale"),
                    }
                    if ans.get("is_correct"):
                        correct_answers.append(entry)
                    else:
                        wrong_answers.append(entry)
                    break

        return {
            "question_number": question_number,
            "question": q,
            "total_answers": len(correct_answers) + len(wrong_answers),
            "correct_count": len(correct_answers),
            "wrong_count": len(wrong_answers),
            "accuracy": round(len(correct_answers) / (len(correct_answers) + len(wrong_answers)), 2)
            if (len(correct_answers) + len(wrong_answers)) > 0 else 0,
            "correct_details": correct_answers[:20],
            "wrong_details": wrong_answers[:20],
        }

    @staticmethod
    async def get_student_exam_detail(
        db: AsyncSession,
        exam_id: int,
        student_id: int,
        teacher_id: int,
    ) -> dict:
        """获取学生答卷详情（含逐题结果和错题）"""
        exam = await db.get(TeacherExam, exam_id)
        if not exam or exam.teacher_id != teacher_id:
            return {"error": "试卷不存在或无权限"}

        sub_stmt = select(ExamSubmission).where(
            ExamSubmission.exam_id == exam_id,
            ExamSubmission.student_id == student_id,
        )
        sub_result = await db.execute(sub_stmt)
        submission = sub_result.scalar_one_or_none()

        if not submission:
            return {"error": "未找到该学生的提交记录"}

        from app.models.user import User
        user = await db.get(User, student_id)
        student_name = getattr(user, "username", "") if user else ""

        return {
            "exam_id": exam_id,
            "exam_title": exam.title,
            "student_id": student_id,
            "student_name": student_name,
            "exam_number": submission.exam_number or "",
            "score": submission.score or 0,
            "max_score": submission.max_score or exam.total_score or 100,
            "grading_status": submission.grading_status,
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "answers": submission.answers or [],
            "wrong_questions": [
                a for a in (submission.answers or [])
                if isinstance(a, dict) and not a.get("is_correct", True)
            ],
        }
