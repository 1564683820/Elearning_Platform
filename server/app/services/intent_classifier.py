"""
意图分类器 — 使用 LLM 分析教师问题，返回意图分类 + 实体提取

10种意图与其检索策略：
- knowledge_lookup: 查找知识库内容（排名/语法/单词等）
- document_query: 文档内容查询（已上传的PDF/Word等）
- class_stats: 班级整体数据统计
- student_analysis: 具体学生学情分析
- error_summary: 错题总结与归纳
- teaching_advice: 教学建议咨询
- lesson_prep: 备课/教案相关
- ppt_generate: 制作PPT课件（"帮我做一份PPT""制作课件""帮我生成PPT"等）
- exam_generate: 生成试卷（"出一套试卷""帮我出题""生成考试卷"等）
- general_chat: 一般性对话/寒暄/其他
"""

import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.class_models import Class, ClassTeacher
from app.services.ai_service import AIService


# 意图分类 Prompt
INTENT_CLASSIFY_PROMPT = """你是一个专业的英语教学意图分类器。分析教师的问题，返回JSON格式的意图分类结果。

## 意图类型说明
1. **knowledge_lookup**: 查找知识库中的英语知识点（语法规则、词汇用法、句型结构等）
   - 示例："定语从句的用法是什么？"、"虚拟语气的规则"、"explain the usage of present perfect"
2. **document_query**: 查询已上传文档中的具体内容（试卷、教材等）
   - 示例："期中试卷第三题是什么？"、"Unit 4 的课文内容"、"上周上传的文档里关于分词的内容"
3. **class_stats**: 班级整体数据统计（正确率、做题量、活跃度等）
   - 示例："三班最近一周的语法正确率怎么样？"、"本周班级学习数据"、"全班平均分"
4. **student_analysis**: 具体学生学情分析
   - 示例："李明最近进步了吗？"、"张华的薄弱知识点"、"分析学生王芳的学习情况"
5. **error_summary**: 错题总结与归纳（含指定某学生的错题总结）
   - 示例："总结本周高频错题"、"最近考试的错误类型分布"、"帮我总结林冲这周的错题"、"分析张三最近的错误类型"、"总结李华本月的错题"
6. **teaching_advice**: 教学建议咨询
   - 示例："怎么提高学生的口语能力？"、"语法课有什么好的教学方法"
7. **lesson_prep**: 备课/教案相关
   - 示例："帮我设计一堂定语从句的课"、"Unit 4 的教案"、"准备一堂阅读课"
8. **ppt_generate**: 制作PPT课件
   - 示例："帮我做一份PPT"、"制作课件"、"生成PPT"、"帮我做一个关于现在进行时的PPT"
   - 注意：如果用户提到了具体的主题/知识点（如"关于现在进行时的PPT"），entities.knowledge_point 应提取该主题
9. **exam_generate**: 生成试卷
   - 示例："出一套试卷"、"帮我出题"、"生成考试卷"、"出一套关于定语从句的试卷"
   - 注意：如果用户提到了知识点（如"关于定语从句的试卷"），entities.knowledge_point 应提取该知识点
10. **general_chat**: 一般性对话/寒暄/非教学类
   - 示例："你好"、"谢谢"、"今天天气不错"

## 输出格式（严格JSON，不要其他内容）
{{
  "intent": "knowledge_lookup|document_query|class_stats|student_analysis|error_summary|teaching_advice|lesson_prep|general_chat",
  "entities": {{
    "class_name": "提取的班级名，没有则为空字符串",
    "student_name": "提取的学生名，没有则为空字符串",
    "knowledge_point": "提取的知识点/语法点，没有则为空字符串",
    "time_range": "时间范围(days)，本周=7，本月=30，近三个月=90，没有则为空字符串",
    "exam_name": "考试名称，没有则为空字符串"
  }},
  "rewritten_query": "优化后的检索查询语句，去除称谓和多余修饰，提取核心检索词"
}}

## 重要提示
- 当教师说「总结/分析 + 学生名 + 错题」时，意图为 error_summary，必须提取 student_name
- 当教师说「总结/分析 + 学生名 + 学习情况/薄弱点」时，意图为 student_analysis，必须提取 student_name
- 时间范围按语义提取：本周=7, 这周=7, 本月=30, 这个月=30, 近三个月=90
- ⚠️ 歧义警告：「历史」一词在「历史错题」「历史错误」「历史记录」「历史数据」等搭配中，表示"过往的/以前的"(past/historical)，**绝对不是指「历史学科」**。此时：
  * knowledge_point **不得**设为"历史"（应保持为空字符串）
  * time_range 应为空字符串（表示不限定时间范围）
  * rewritten_query 中应将"历史"替换为"过往"/"之前"，或直接移除
- ⚠️ 同理，「历史」出现在「错题」「错误」「记录」「数据」等语境中时，一律作时间副词处理，不作为知识点提取

问题：{question}
当前班级：{class_name}
仅返回JSON，不要其他内容。"""


class IntentClassifier:
    """教学助手意图分类器"""

    # 无需 LLM 调用的关键词直接匹配规则
    _KEYWORD_INTENT_MAP: list[tuple[list[str], str]] = [
        (["你好", "您好", "hi", "hello", "hey", "早上好", "晚上好", "下午好", "在吗", "在不在"], "general_chat"),
        (["谢谢", "感谢", "多谢", "thanks", "thank"], "general_chat"),
        (["再见", "拜拜", "bye", "goodbye", "明天见"], "general_chat"),
    ]

    # 文档查询关键词 — 命中时直接返回 document_query 意图，不走 LLM
    # 解决 LLM 分类不稳定导致同一问题在不同对话中意图不同的问题
    _DOCUMENT_KEYWORDS: list[str] = [
        "试卷", "考题", "真题", "高考", "中考", "模考", "月考", "期中", "期末",
        "阅读理解", "完形填空", "听力原文", "作文题",
        "原文", "翻译", "课文", "教材",
        "第x篇", "第x题", "第x段", "第x节",
        "文档", "上传的文件", "pdf", "word", "docx",
        "unit", "module", "passage",
    ]

    @classmethod
    async def classify(
        cls,
        db: AsyncSession,
        question: str,
        teacher_id: int,
        class_id: int | None = None,
    ) -> dict:
        """对教师问题进行意图分类

        Returns:
            {
                "intent": str,
                "entities": dict,
                "rewritten_query": str,
            }
        """
        question = question.strip()
        if not question:
            return {
                "intent": "general_chat",
                "entities": {},
                "rewritten_query": "",
            }

        # 1. 关键词预匹配（寒暄类）
        question_lower = question.lower()
        for keywords, intent in cls._KEYWORD_INTENT_MAP:
            if any(kw in question_lower for kw in keywords):
                return {
                    "intent": intent,
                    "entities": {"class_name": "", "student_name": "", "knowledge_point": "", "time_range": "", "exam_name": ""},
                    "rewritten_query": question,
                }

        # 1.5. 文档查询关键词预匹配 — 绕过 LLM，确保文档类查询始终命中 document_query
        for kw in cls._DOCUMENT_KEYWORDS:
            if kw.lower() in question_lower:
                return {
                    "intent": "document_query",
                    "entities": {"class_name": "", "student_name": "", "knowledge_point": "", "time_range": "", "exam_name": ""},
                    "rewritten_query": cls._clean_document_query(question),
                }

        # 3. 获取当前班级名
        class_name = ""
        if class_id:
            cls_obj = await db.get(Class, class_id)
            if cls_obj:
                class_name = cls_obj.name

        # 4. 调用 LLM 分类
        prompt = INTENT_CLASSIFY_PROMPT.format(
            question=question,
            class_name=class_name,
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await AIService.chat_completion(
                db, messages, user_id=teacher_id,
                max_tokens=256,
            )
            # 清理可能的 markdown 代码块
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                    text = text.strip()

            result = json.loads(text)
            # 确保必要的字段都存在
            result.setdefault("intent", "general_chat")
            result.setdefault("entities", {})
            result.setdefault("rewritten_query", question)

            # 后处理：安全网 — 修正 LLM 可能将"历史"误认为知识点的歧义
            entities = result.get("entities", {})
            kp = entities.get("knowledge_point", "")
            if kp and kp.strip() in ("历史", "历史学科") and result["intent"] in ("error_summary", "student_analysis", "class_stats"):
                # "历史"出现在错题分析/学情分析的上下文中，应为时间副词而非知识点
                entities["knowledge_point"] = ""
                # rewritten_query 中也清除被当做知识点的"历史"
                rq = result.get("rewritten_query", question)
                # 仅在"历史错题""历史错误"等语境下替换
                rq = re.sub(r'历史(?=(?:的)?(?:错题|错误|记录|数据|题目|做题记录|考试))', '过往', rq)
                result["rewritten_query"] = rq

            return result
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[IntentClassifier] LLM parsing failed: {e}, raw={raw[:200] if 'raw' in dir() else ''}")
            # fallback: 简单规则判断
            return cls._rule_fallback(question, class_name)

    @classmethod
    def _rule_fallback(cls, question: str, class_name: str = "") -> dict:
        """LLM 解析失败时的规则降级"""
        q = question.lower()
        entities = {
            "class_name": class_name,
            "student_name": "",
            "knowledge_point": "",
            "time_range": "",
            "exam_name": "",
        }

        # 时间范围
        if any(kw in q for kw in ["本周", "这周", "最近一周", "这星期", "最近7天", "近一周"]):
            entities["time_range"] = "7"
        elif any(kw in q for kw in ["本月", "这个月", "最近30天", "近30天", "近一个月"]):
            entities["time_range"] = "30"
        elif any(kw in q for kw in ["近三个月", "最近三个月"]):
            entities["time_range"] = "90"

        # 简单检测学生名（2-3个汉字的人名模式，在"帮我总结""分析""错题"等关键词附近）
        student_name_pattern = re.search(
            r'(?:帮[我你]?\s*(?:总结|分析|分析一下|看看|查查|查询|看一下))\s*([\u4e00-\u9fa5]{2,3})\s*(?:的|这|最近|本|同)',
            question
        )
        if student_name_pattern:
            entities["student_name"] = student_name_pattern.group(1)
        else:
            # 尝试匹配"分析/总结 + 人名"的模式
            name_pattern = re.search(
                r'(?:总结|分析|分析一下|看看|查查)\s*([\u4e00-\u9fa5]{2,3})\s*(?:的|这|最近|本|同)',
                question
            )
            if name_pattern:
                entities["student_name"] = name_pattern.group(1)

        # 意图判断
        if any(kw in q for kw in ["错题", "错误", "错误率", "错误类型", "高频错题", "错题总结"]):
            return {"intent": "error_summary", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["教案", "备课", "教学设计", "课堂设计", "lesson plan"]):
            return {"intent": "lesson_prep", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["做一份ppt", "制作ppt", "生成ppt", "做一个ppt", "帮.*ppt", "课件", "ppt课件", "制作课件"]):
            return {"intent": "ppt_generate", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["出一套试卷", "出卷", "生成试卷", "出题", "考试卷", "生成考卷", "邀请学生考试"]):
            return {"intent": "exam_generate", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["怎么提高", "学习方法", "教学建议", "有效性", "如何教", "教学方法"]):
            return {"intent": "teaching_advice", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["正确率", "平均分", "做题量", "班级数据", "学习数据", "统计", "dashboard"]):
            return {"intent": "class_stats", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["学生", "同学", "进步", "薄弱", "学习情况", "学习状态", "表现"]):
            return {"intent": "student_analysis", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["试卷", "文档", "教材", "课文", "unit", "上传"]):
            return {"intent": "document_query", "entities": entities, "rewritten_query": question}
        if any(kw in q for kw in ["语法", "单词", "词汇", "句型", "时态", "从句", "用法", "英语"]):
            return {"intent": "knowledge_lookup", "entities": entities, "rewritten_query": question}

        return {"intent": "general_chat", "entities": entities, "rewritten_query": question}

    @staticmethod
    def _clean_document_query(question: str) -> str:
        """清洗文档查询的原始问题，去除噪声词，提高语义搜索精准度

        将 "给出2023年高考英语试卷的阅读理解C篇的原文以及翻译"
        清洗为 "2023年高考英语试卷 阅读理解C篇 原文 翻译"
        """
        import re
        # 移除请求/命令类前缀
        noise_prefixes = [
            "给出", "提供", "帮我找", "帮我查", "请帮我", "请给我",
            "帮忙找", "找一下", "查一下", "看一下", "能不能找到",
            "可以找到", "有没有", "检索", "搜索",
        ]
        for prefix in noise_prefixes:
            if question.startswith(prefix):
                question = question[len(prefix):]
                break

        # 移除多余的语气助词和连接词（保留核心搜索词）
        question = re.sub(r'[的了吗呢吧]', ' ', question)  # 语气助词 → 空格
        question = re.sub(r'以及|还有|和|与|并', ' ', question)  # 连接词 → 空格
        question = re.sub(r'\s+', ' ', question).strip()  # 合并多余空格
        return question

    @staticmethod
    def get_search_strategy(intent: str) -> dict:
        """根据意图返回检索策略参数"""
        strategies = {
            "knowledge_lookup": {"knowledge_top_k": 10, "errors_top_k": 0, "use_mysql_stats": False},
            "document_query":   {"knowledge_top_k": 15, "errors_top_k": 0, "use_mysql_stats": False},
            "class_stats":      {"knowledge_top_k": 0,  "errors_top_k": 5, "use_mysql_stats": True},
            "student_analysis": {"knowledge_top_k": 3,  "errors_top_k": 10, "use_mysql_stats": True},
            "error_summary":    {"knowledge_top_k": 5,  "errors_top_k": 10, "use_mysql_stats": True},
            "teaching_advice":  {"knowledge_top_k": 8,  "errors_top_k": 5, "use_mysql_stats": True},
            "lesson_prep":      {"knowledge_top_k": 10, "errors_top_k": 0, "use_mysql_stats": False},
            "ppt_generate":     {"knowledge_top_k": 5,  "errors_top_k": 0, "use_mysql_stats": False},
            "exam_generate":    {"knowledge_top_k": 5,  "errors_top_k": 0, "use_mysql_stats": False},
            "general_chat":     {"knowledge_top_k": 5,  "errors_top_k": 0, "use_mysql_stats": False},
        }
        return strategies.get(intent, {"knowledge_top_k": 5, "errors_top_k": 0, "use_mysql_stats": False})
