"""AI 备课 PPT 生成服务

支持四种课型:
- new_lesson (新授课): 导入→词汇→对话→练习→总结
- review (复习课): 快速检测→要点回顾→纠错→小组→总结
- exercise (练习课): 热身→练习题→配对→游戏→总结
- conversation (口语课): 主题导入→示范对话→角色扮演→自由讨论→反馈
"""
import asyncio
import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.db.database import async_session as get_async_session
from app.core.paths import UPLOADS_DIR
from app.services.ai_service import AIService
from agent.agents.ppt_agent import PPTAgent
from agent.prompts.ppt_agent.lesson_templates import LESSON_TEMPLATES, GENERATE_SYSTEM_PROMPT
from app.services.embedding_service import EmbeddingService
from app.services.document_service import (
    STAGE_TEACHING_STYLES, infer_stage_from_grade,
)
from app.services.ppt_html_renderer import PPTHtmlRenderer
from app.services.ppt_theme_service import PPTThemeService
from app.models.ppt_models import LessonPPT, ClassroomSession
from app.models.ppt_theme_models import PptVersion
from datetime import datetime


# 幻灯片类型的中文标签
SLIDE_TYPE_LABELS = {
    "catalog": "目录页",
    "title": "标题页",
    "objective": "学习目标",
    "vocabulary": "词汇展示",
    "dialogue": "对话练习",
    "grammar": "语法讲解",
    "practice": "课堂练习",
    "interactive": "互动活动",
    "ai_interaction": "人机互动",
    "summary": "总结回顾",
}

# AI 生成提示词模板（本地版本，可用于替代 agent 模块中的英文版本）
# TODO: 过渡完成后可以删除本地版本，完全使用 agent.prompts.ppt_agent.lesson_templates.GENERATE_SYSTEM_PROMPT
GENERATE_SYSTEM_PROMPT = """你是一位经验丰富的小学英语教师，正在用 AI 备课工具制作互动 PPT。
请严格按照 JSON 格式输出，不要输出任何其他文字。

课型说明：
- new_lesson 新授课：导入 → 目标 → 词汇 → 对话 → 语法 → 练习 → 人机互动 → 总结
- review 复习课：检测 → 要点 → 纠错 → 小组活动 → 人机互动 → 总结
- exercise 练习课：基础 → 提升 → 配对 → 游戏 → 人机互动 → 总结
- conversation 口语课：话题 → 示范对话 → 实用表达 → 角色扮演 → 讨论 → 人机互动 → 反馈

每页 slide 的 JSON 格式：
{{"type": "<slide_type>", "title": "<页面标题>", "content": {{"xxxx": "yyyy"}} }}

slide_type 可选值: catalog, title, objective, vocabulary, dialogue, grammar, practice, interactive, ai_interaction, summary, listening, speaking

各 type 的 content 字段规范：
- catalog（目录导航页）：{{ "sections": ["章节1", "章节2", "章节3", ...] }}
- title: {{ "main_title": "主标题", "subtitle": "副标题(英文)", "grade": "年级" }}
- objective: {{ "items": ["目标1", "目标2", ...] }}
- vocabulary: {{ "words": [{{"word": "apple", "phonetic": "/ˈæp.əl/", "translation": "苹果", "example": "I eat an apple."}}] }}
- dialogue: {{ "dialogues": [{{"speaker": "A", "text": "Hello!", "translation": "你好！"}}] }}
- grammar: {{ "points": [{{"rule": "语法规则", "example": "例句", "explanation": "说明"}}] }}
- practice: {{ "questions": [{{"stem": "题目", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "解析"}}] }}
- interactive: {{ "activity_type": "game/vote/roleplay/discussion", "description": "活动说明", "steps": ["步骤1", "步骤2"] }}
- ai_interaction: {{ "prompt": "人机互动环节引导语", "questions": [{"question": "建议学生提出的问题", "hint": "回答提示或示范答案"}] }}
- summary: {{ "key_points": ["要点1", "要点2", ...], "homework": "课后作业（可选）" }}
- listening（听力练习页）：{{ "audio_text": "AI朗读的英文文本(50-150词)", "subtitle": "中文翻译", "questions": [{"stem": "题干", "options": ["A. ...", "B. ..."], "answer": "A", "explanation": "解析"}] }}
- speaking（口语跟读页）：{{ "text": "学生跟读的英文文本(30-80词)", "translation": "中文翻译", "tips": "发音技巧提示（可选）" }}

通用注意事项：
1. 内容必须符合教学大纲，单词和句子使用英文
2. 练习题的答案必须正确，解析要简洁易懂
3. 对话和词汇要贴近学生生活
4. 互动活动要设计具体、可操作
5. 输出必须是合法的 JSON 数组，不要包含任何额外的文字

视觉质量与可读性规则（强制执行）：
6. 文字对比度：所有文字颜色必须与背景有足够差异。深色主题用明亮的白色/浅色文字；浅色主题用深色文字。禁止在深色背景上使用灰色(#888/#999)小字。
7. 内容密度：每页核心信息 3-5 条为宜，不要堆砌。词汇页 5-8 个词，语法页 2-4 条规则，练习页 3-5 题。
8. 严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐📌✅❌➡️❗❓等 Unicode 表情/符号）。标题用完整短句（非碎片词），副标题/说明文字用完整句子。一律用文字符号（▶ ▸ ● ❖ ◆）引导视觉层次。
9. 排版留白：标题和正文间留空行，卡片间使用适当间距。不要在 content 字段中写连续大段文字。"""


# ========== 各主题详细内容生成提示词 ==========
# 每个主题的提示词从视觉风格、内容深度、排版建议、交互设计四方面引导 AI
# 生成与该主题 CSS 风格匹配的高质量内容

THEME_CONTENT_PROMPTS = {
    "classic": """
【当前主题：经典简约 - 蓝白清新风】

视觉与内容风格：干净、清晰、主次分明。蓝白基调配合绿色点缀。

各页具体内容要求：
- title（标题页）：main_title 用中英文双语（英文在上），subtitle 为一句励志或有趣的英文短句，grade 标注年级
- objective（目标页）：items 写 3-4 条，每条以"能够/能"开头，表述具体可测量（如"能正确朗读 5 个新单词"）
- vocabulary（词汇页）：words 写 4-6 个词。每个必须有：word（英文）、phonetic（完整音标）、translation（中文）、example（英文例句，带中文翻译）。例句要用学生学过的简单句
- dialogue（对话页）：dialogues 写 2-3 轮对话。speaker 用 A/B 或角色名。每句配 translation。话题要贴近校园/家庭/日常生活
- grammar（语法页）：points 写 1-2 个语法点。rule 用中文表述规则，example 给 2-3 个英文例句（附中文），explanation 用 1-2 句话解释用法和注意事项
- practice（练习页）：questions 写 2-3 道题。题型交替：选择题+填空题+排序题等。stem 语言简洁，options 个数 3-4 个，answer 为正确选项索引（从 0 开始），explanation 说明为什么对/错
- interactive（互动页）：activity_type 选 game/vote/roleplay/discussion 之一。description 用一句中文描述活动目标。steps 写 3-4 个具体可执行步骤
- summary（总结页）：key_points 写 3-5 个关键点。homework 布置 1-2 项有意义的作业（非机械抄写）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问的环节。prompt 写一句热情的中文引导语（如"学完新知识，来向 AI 老师提问吧！"）。questions 写 4-5 个问题，每个包含 question（英文提问）和 hint（中文提示方向）。问题紧扣本课词汇/语法/对话话题，覆盖"理解→应用→拓展"三级。


- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为浅色/白色背景）：
- ❌ 禁止使用浅灰色（#90a4ae 及其相近色）作为文字颜色，在白色背景上学生完全看不清
- ❌ 禁止使用任何与白色/浅色背景亮度接近的文字颜色
- ✅ 正文/标题必须使用最深色（#2c3e50、#1b5e20、#37474f 等级别）
- ✅ 辅助文字（翻译、音标、例句、提示）至少使用中等深度（如 #455a64、#546e7a、#607d8b）
- ✅ 确保最后一排学生也能看清所有文字内容
""",
    "cartoon": """
【当前主题：小学卡通 - 明亮活泼风】

视觉与内容风格：色彩明亮、圆角柔和、趣味性强。使用 Comic Sans 风格字体。

各页具体内容要求：
- title：main_title 用英文大字+中文小字，subtitle 写一句押韵或有韵律的英文口号，grade 写"Grade X"。大号加粗展示
- objective：items 写 3 条，语言要简单亲切，像给小朋友的承诺
- vocabulary：words 写 5-6 个。word 要大写首字母，示例句要超级简单（3-5 个词）。给每个词配一个可爱的联想记忆法（放在 example 里，用括号标注）
- dialogue：dialogues 写 2 轮对话，每轮 2-3 句。speaker 用卡通角色名（如 Tommy/Mimi/Panda）。语言要口语化、有童趣
- grammar：points 写 1 个语法点。rule 用儿歌/顺口溜的方式表述（如"我是 I，你是 you，男女 he/she 要分清"），example 给 3 个配图的例句
- practice：questions 写 2 道。第一道用图片选择题（stem 写"看看图片选答案"），第二道用判断题。选项用 A/B 字母形式。解析要鼓励性语气（"太棒了！" / "再想想哦～"）
- interactive：activity_type 用 game。description 写游戏名称，steps 写 3-4 步，语言要有游戏感（"第 1 关"、"加油"）
- summary：key_points 写 3-4 个。homework 布置趣味性任务（如画一画、唱给家长听）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 写一句可爱的引导语（如"小AI老师来啦！你有问题想问吗？"）。questions 写 4-5 个，每个包含 question（英文，用小朋友的简单语气）和 hint（提示回答方向）。问题超级简单有趣。

整体要求：内容要像幼儿绘本一样有趣，多用感叹号，每页都要让学生感到开心和期待。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为浅暖色背景）：
- ❌ 禁止浅色文字（如 #8d6e63、#a1887f 等在浅暖色背景上很难看清）
- ✅ 正文/标题使用最深棕色（#4e342e、#bf360c）
- ✅ 辅助文字至少使用中等深度（如 #6d4c41、#5d4037）
- ✅ 确保教室投影时所有文字清晰可读
""",
    "academic": """
【当前主题：初中简约 - 清新学术风】

视觉与内容风格：蓝色主调、结构清晰、适中的字号。适合初中生认知水平。

各页具体内容要求：
- title：main_title 英文，subtitle 中文释义，grade 写"七年级/八年级/九年级"。采用"英文 + 中文副标题"的双行结构
- objective：items 写 4 条，按"认知→理解→应用→拓展"四级递进。每条用"掌握/理解/运用/能够"等明确动词
- vocabulary：words 写 5-7 个。每个词配 2 个 example（一个教材原句、一个生活场景句）。translation 写中文释义。加粗展示关键搭配
- dialogue：dialogues 写 3 轮对话。speaker 用真实英文名（Lucy/Tom/Mike）。内容要有信息差，包含实用句型。每句配 translation
- grammar：points 写 1-2 个语法点。rule 用"公式化"表达（如 "主语 + be + 动词-ing"）。每个语法点配 3 个 positive + 2 个 negative 例句，explanation 对比易混淆点
- practice：questions 写 3 道题。题型包括：单项选择 + 完形填空 + 句型转换。难度递进（易→中→难）。explanation 要讲清解题思路
- interactive：activity_type 选 roleplay 或 discussion。description 描述任务型教学场景。steps 写 4 步：准备→练习→展示→评价
- summary：key_points 写 4-5 个，按知识点模块分组。homework 布置分层作业（必做+选做）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 用中文写有学术感的引导语（如"学完本课后，还有哪些疑惑？向 AI 老师提问吧"）。questions 写 4-5 个，每个包含 question（英文，初中生能理解的句式）和 hint（中文提示回答方向或易错提醒）。覆盖课文理解+语言运用+拓展思考三级。

整体要求：语言准确严谨，题型设计有梯度，体现"教学评一体化"理念。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为浅灰蓝背景）：
- ❌ 禁止浅灰/浅蓝色文字（如 #90a4ae、#b0bec5 等在浅灰蓝背景上几乎消失）
- ✅ 正文使用最深色（#2c3e50）
- ✅ 辅助文字至少使用 #455a64 或 #607d8b 等级别
- ✅ 确保投影时每个字都清晰可辨
""",
    "senior": """
【当前主题：高中学术 - 深色严谨风】

视觉与内容风格：深灰主色、严谨排版、紧凑高效。适合高中/雅思备考场景。

各页具体内容要求：
- title：main_title 纯英文大标题，subtitle 写课程/考纲编号（如"IELTS Speaking Part 2"），grade 写"Senior X / IELTS Band X"
- objective：items 写 3-5 条，每条对标具体考点或能力要求（如"掌握并列句在写作中的 4 种连接方式"）。使用学科标准术语
- vocabulary：words 写 6-8 个。word 用学术词汇/考纲词汇，每个配：phonetic（英式音标）、translation、definition（英文释义）、example（COCA/BNC 语料库风格例句）、collocation（常用搭配）
- dialogue：dialogues 写 3-4 轮。speaker 用英语全名。对话包含：高级词汇、复杂句型（从句/倒装/虚拟语气）、习语表达。翻译用中文+英文注释
- grammar：points 写 2 个语法点。rule 用英文语法术语表述（如 "Present Perfect vs. Past Simple"），example 给 4 个对比例句，explanation 写出考点+易错点+解题技巧
- practice：questions 写 3 道。模拟考试题型：阅读推理 + 语法填空 + 句子改写。stem 用全英文，options 4 个，explanation 标注考点编号
- interactive：activity_type 选 discussion 或 debate。description 用英文写讨论主题（含参考论点）。steps 写 4-5 步：分组→准备→辩论/讨论→互评→总结
- summary：key_points 写 5-6 个，用知识框架/思维导图的形式（以英文条目排列）。homework 布置真题练习或拓展阅读
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 用英文写正式引导语（如"Any questions about today's lesson? Ask your AI tutor!"）。questions 写 4-5 个，全英文，每个包含 question（含从句/学术词汇的提问）和 hint（英文答题思路）。对标雅思/高考题型思路。

整体要求：全英文为主（目标语授课），内容对标考纲，语言精确且学术化。每页内容信息量较大，适合快节奏课堂。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为白色背景+深色严谨排版）：
- ❌ 禁止浅灰/浅蓝文字（如 #90a4ae、#78909c 等在白色背景太淡）
- ✅ 正文使用纯黑深色系（#263238、#1a237e、#37474f）
- ✅ 辅助文字至少使用 #455a64 或 #546e7a 等级别的中深色
- ✅ 高中/雅思备考场景，信息量大、字体偏小，更需保证每个字都清晰可辨
""",
    "blackboard": """
【当前主题：黑板风格 - 传统课堂风】

视觉与内容风格：绿色黑板背景，白色/黄色粉笔字，边框为木质。仿传统板书课堂氛围。

各页具体内容要求：
- title：main_title 用英文大号粉笔字效果，subtitle 写中文课题说明，grade 写年级
- objective：items 写 3-4 条，每条用"▸ "开头（模拟粉笔勾画）。语言如老师板书，简洁扼要，多用"重点掌握/理解/牢记"等课堂用语
- vocabulary：words 写 4-5 个。word 前加"●"，phonetic 用方括号标注。example 写 1 个"课堂例句"和 1 个"课后练习"区分
- dialogue：dialogues 写 2-3 轮。speaker 用"Teacher/Student"形式。左侧写英文对话，右侧用括号标注中文翻译
- grammar：points 写 1 个语法点。rule 用"【规则】"标记，example 写在"板书示例"下，用表格方式展示
- practice：questions 写 2 道。题型用"随堂小测"形式，stem 前加"【题】"。选项用编号。explanation 用"教师点拨："开头
- interactive：activity_type 选 game。description 用中文描述活动，steps 写 3-4 步，用"① ② ③"编号。活动要适合全班参与
- summary：key_points 写 3-4 个。homework 写课后作业
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 写引导语（如"学到这里，有不懂的可以向老师提问"）。questions 写 4-5 个，每个包含 question（英文，像学生举手问老师）和 hint（用"点拨："开头）。问题贴近课堂真实疑问。

整体要求：内容要体现"教师板书→学生笔记"的传统课堂感。语言像老师在黑板上写的要点，简洁有力，层次分明。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为深绿色黑板背景）：
- ✅ 白色/米黄色文字在深绿背景上本身对比度高，保持即可
- ❌ 禁止使用深绿色或暗色文字（会被背景吞没）
- ❌ 禁止使用与 #2e7d32 亮度相近的任何颜色作为文字颜色
- ✅ 文字全部使用纯白 #ffffff 或亮黄色 #fff176
""",
    "warm": """
【当前主题：暖色温馨 - 柔和启蒙风】

视觉与内容风格：暖橙/米色渐变背景，柔和的圆角卡片。适合幼儿/启蒙教育。

各页具体内容要求：
- title：main_title 用英文 + 可爱文字组合，subtitle 写一句充满爱的英文欢迎语，grade 写"K1/K2/K3"或"启蒙班"
- objective：items 写 2-3 条，语言要充满鼓励（如"我们一起快乐地学会 3 个新单词吧！"）
- vocabulary：words 写 3-4 个。word 要用自然拼读的方式展示（如 "cat /k/ /æ/ /t/ - cat"）。example 用最简单的主谓宾句型（3-4 词）
- dialogue：dialogues 写 1-2 轮简短对话。speaker 用"Mommy/Baby"或"老师/宝贝"等亲切称呼。每句 3-5 个英文词，配中文翻译
- grammar：不要出现"语法"概念。改为"句型"或"魔法句式"。rule 写一句朗朗上口的句型歌谣，example 给 2 个配动作的例句
- practice：questions 写 1-2 道。用"连连看"或"找朋友"形式。stem 写游戏规则（用温柔的指导语），options 用图片文字。解析要热情鼓励（"你真棒！"）
- interactive：activity_type 用 game。description 写一个具体游戏名（如"音乐椅子"）。steps 写 3 步简单指令
- summary：key_points 写 2-3 个，以"我们学会了"开头。homework 布置亲子互动任务（"和爸爸妈妈一起……"）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 写温柔的引导语（如"宝贝们，有不懂的可以问 AI 老师哦～"）。questions 写 3-4 个，每个包含 question（英文，3-5 个词，最简单的主谓宾）和 hint（"小提示："开头，极其简单）。问题像妈妈在启发孩子思考。

整体要求：内容要像妈妈讲绘本一样温暖亲切。句子短小，充满鼓励和肯定。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为暖色渐变背景）：
- ❌ 禁止浅棕/浅粉色文字（如 #8d6e63、#a1887f 在暖色渐变上很难看清）
- ✅ 正文使用最深棕色（#4e342e、#bf360c、#3e2723）
- ✅ 辅助文字至少使用中等深度（如 #6d4c41、#5d4037）
- ✅ 幼儿启蒙场景投影尺寸大，文字必须粗重清晰
""",
    "tech": """
【当前主题：科技蓝调 - 未来科技风】

视觉与内容风格：深蓝渐变背景，荧光青/蓝点缀色。科技感、未来感、数据可视化。

各页具体内容要求：
- title：main_title 用英文 + 数字风格，subtitle 写一句"未来感"引言，grade 写年级。整体要像科幻海报
- objective：items 写 3-4 条。将学习目标包装为"学习任务"或"技能解锁"，用"Level 1/Level 2"递进式表述
- vocabulary：words 写 5-6 个。translation 前加"译："。example 用现代科技/数字生活相关的场景。每个词配一个"记忆密码"（联想记忆法）
- dialogue：dialogues 写 2-3 轮。speaker 用类似"Ava/Bot/User"的未来感角色名。内容可以是"与AI助手对话"或"未来校园"主题。语言带点科技元素
- grammar：points 写 1-2 个语法点。rule 用"系统规则/算法"的方式表述（如"规则 001：……"）。explanation 像"系统提示"一样简洁
- practice：questions 写 2-3 道。包装成"系统测试 / 任务挑战"形式。stem 前加"任务 1："。选项用 Futuristic 描述。explanation 用"系统反馈"语气
- interactive：activity_type 选 game 或 vote。description 写互动任务描述。steps 写 4 步。活动如"全班投票选择最佳方案"
- summary：key_points 写 3-5 个，以"核心数据"作为标题。homework 布置搜索/探究类作业（"课后探索：……"）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 写系统提示风格（如"AI 助手已就绪！请输入你的问题"）。questions 写 4-5 个，每个包含 question（英文，包装成"任务指令"风格）和 hint（"提示："开头，系统反馈语气）。

整体要求：内容有科技感、数字化、创新性。适当使用"系统/数据/任务/解锁"等词创造沉浸感。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为深蓝渐变背景）：
- ❌ 禁止在深色背景上使用暗蓝色或灰色文字
- ✅ 正文全部使用高亮色（#ffffff、#e8f0ff、#90caf9）
- ✅ 辅助文字至少使用中等亮度的蓝白色（如 #bbdefb、#90caf9）
- ✅ 深色背景上文字亮度必须足够高，确保投影清晰
""",
    "nature": """
【当前主题：自然绿意 - 清新生态风】

视觉与内容风格：绿色渐变背景，自然元素点缀。适合科学/环保主题及自然相关的英语课。

各页具体内容要求：
- title：main_title 用英文 + 中文展示，subtitle 写与自然相关的英文谚语或短诗，grade 写年级
- objective：items 写 3-4 条。目标与自然元素关联（如"能说出 5 种植物的英文名"）
- vocabulary：words 写 4-6 个与自然/动植物/环保相关的词汇。如果主题不是自然类，就正常词汇+自然风格的展示
- dialogue：dialogues 写 2-3 轮。speaker 用自然元素角色（Tree/Bee/Sun 或 Tom/Mary 在公园场景）。对话内容融入自然/环保元素
- grammar：points 写 1-2 个。rule 用"自然法则"来包装，example 配大自然场景例句
- practice：questions 写 2-3 道。"环保主题"和"常规题"各半
- interactive：activity_type 选 game 或 discussion。description 写自然探索主题。steps 写 3-4 步
- summary：key_points 写 3-4 个。布置与自然/环保相关的作业（如观察记录、环保小行动）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 写自然风引导语（如"大自然是本最好的书，你有什么疑问？"）。questions 写 4-5 个，每个包含 question（英文，融入自然元素）和 hint（提示观察方向）。问题鼓励发现自然规律。

整体要求：内容清新、自然、有生命力。即使用常规英语话题，也要融入自然意象。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为浅绿色渐变背景）：
- ❌ 禁止中绿色/浅绿色文字（如 #558b2f、#689f38 在绿背景上完全融在一起）
- ✅ 正文使用最深绿色（#1b5e20、#2e7d32）
- ✅ 辅助文字必须足够深（至少 #2e7d32），不能使用浅绿色系
- ✅ 纯黑文字也可以（#212121），在绿背景上对比鲜明
""",
    "business": """
【当前主题：商务专业 - 灰调商务风】

视觉与内容风格：灰色系主调，简洁线条，专业正式。适合成人英语/商务英语场景。

各页具体内容要求：
- title：main_title 用正式英文标题，subtitle 写"Presented by / Course Code"等商务格式，grade 写"Business English / Adult"
- objective：items 写 3-4 条，每条用"▶ "开头。使用商务领域术语。目标要实用、可量化
- vocabulary：words 写 5-7 个商务词汇/短语。每个配：word（词组）、phonetic、translation、definition（英文定义）、example（商务场合例句 2 个）
- dialogue：dialogues 写 3-4 轮。speaker 用正式英文名或职位（Mr. Smith / Manager / Client）。场景为：会议、谈判、电话、邮件往来等
- grammar：points 写 1-2 个商务语法点（如"条件句在商务谈判中的运用"）。rule 用英文写，example 给 3 个商务场景例句
- practice：questions 写 2-3 道。题型：邮件排序 + 情景选择 + 纠错。stem 和 options 全英文。场景要真实商务
- interactive：activity_type 选 roleplay 或 discussion。description 用英文写商务场景。steps 写 4 步：Scenario Setup → Preparation → Roleplay → Debrief
- summary：key_points 用英文写 3-5 个关键知识点/实用句型。homework 布置真实商务任务（"Write a follow-up email"）
- ai_interaction（人机互动页 - 在总结页之前）：让学生向 AI 提问。prompt 用英文写专业引导语（如"Any questions about today's business topic? Ask the AI assistant."）。questions 写 4-5 个，全英文，每个包含 question（正式商务英文提问）和 hint（英文回答方向提示）。场景对标真实商务沟通。

整体要求：全英文输出（对应成人英语水平），内容专业、实用、真实。排版紧凑、信息密度高。

- listening（听力练习页）：audio_text 写适合该年级段的英文听力短文（50-150词），subtitle 写中文翻译，questions 写 2-3 道听力理解题（选择题），每题含 options/answer/explanation
- speaking（口语跟读页）：text 写适合跟读的英文文本（30-80词），translation 写中文翻译，tips 写发音提示（可选，如注意连读、重音等）

格式提示：仅使用文字符号（▶ ▸ ●）引导视觉层次，严禁使用任何 emoji 表情符号和特殊符号（如🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等）。

高对比度安全规则（本主题为浅灰背景，灰色系主调）：
- ❌ 禁止浅灰色文字（如 #90a4ae、#b0bec5 等在浅灰背景上几乎隐形）
- ✅ 正文使用最深色（#263238、#37474f）
- ✅ 辅助文字至少使用中等深度（如 #546e7a、#607d8b）
- ✅ 商务场景正式严肃，文字必须清晰锐利，不能有任何模糊感
""",
}


class PPTService:
    """AI 备课 PPT 生成服务"""

    # 需要独立 LLM 调用的重内容页面类型（确保习题、例句等完整）
    HEAVY_CONTENT_TYPES = {"vocabulary", "dialogue", "grammar", "practice", "listening", "speaking"}

    @staticmethod
    def _should_synthesize_audio(
        lesson_type: str,
        pages: list | None = None,
        grade: str = "",
        explicit: bool | None = None,
    ) -> bool:
        """意图识别：判断 PPT 是否需要合成 TTS 音频

        优先级：
        1. explicit 参数（用户显式指定）
        2. 课型判断（口语课必须合成音频）
        3. 页面类型判断（含 listening/speaking 页则合成）
        4. 年级判断（低学段倾向合成，但不强制）

        Returns:
            bool: True 表示需要合成音频
        """
        if explicit is not None:
            return explicit

        # 口语课始终需要音频
        if lesson_type == "conversation":
            return True

        # 检查是否包含 listening 或 speaking 类型的页面
        if pages:
            for page in pages:
                if page.get("type") in ("listening", "speaking"):
                    return True

        # 低学段（学前/小学低年级）建议合成音频
        if grade and any(g in str(grade).lower() for g in ("preschool", "k1", "k2", "k3", "grade 1", "grade 2", "一年级", "二年级", "三年级")):
            return True

        return False

    @staticmethod
    def _split_template_into_sections(template: list) -> list[list]:
        """将 PPT 模板拆分为多个内容段，每个重内容类型独立调用 LLM

        拆分策略：
        - catalog/title/objective/interactive/summary/ai_interaction → 分组合并（内容轻量）
        - vocabulary/dialogue/grammar/practice/listening/speaking → 每种独立一段（防内容截断）
        """
        sections = []
        current_group = []

        for item in template:
            t = item["type"]
            if t in PPTService.HEAVY_CONTENT_TYPES:
                # 提交当前分组
                if current_group:
                    sections.append(current_group)
                    current_group = []
                # 重内容类型独立一段
                sections.append([item])
            else:
                current_group.append(item)

        # 提交最后一个分组
        if current_group:
            sections.append(current_group)

        return sections

    @staticmethod
    def _extract_audio_text(page: dict, ptype: str) -> str:
        """从页面中提取 TTS 合成所需的文本，支持多种字段名回退。"""
        content = page.get("content", {})
        if not isinstance(content, dict):
            content = {}

        # listening 页面：检查多个可能的字段名
        if ptype == "listening":
            for key in ("audio_text", "text", "passage", "english_text", "english", "content", "audio", "dialogue"):
                val = content.get(key, "") or page.get(key, "")
                if val and isinstance(val, str) and len(val.strip()) >= 3:
                    return val.strip()
        else:
            # speaking 页面
            for key in ("text", "audio_text", "content", "sentence", "english", "passage"):
                val = content.get(key, "") or page.get(key, "")
                if val and isinstance(val, str) and len(val.strip()) >= 3:
                    return val.strip()

        # 最后回退：用页面标题
        title = page.get("title", "")
        return title.strip() if len(title.strip()) >= 5 else ""

    @staticmethod
    async def _synthesize_ppt_audio(pages: list, theme_name: str = "", progress_callback=None) -> list:
        """Scan pages for listening/speaking types and pre-generate TTS audio.
        Injects audio_url into each page's content.
        Falls back silently on failure.
        
        If progress_callback is provided, calls it with (current, total, page_type).
        """
        from app.services.tts_service import TTSService
        import os, hashlib, logging
        from app.core.config import get_settings as _get_settings
        _settings = _get_settings()
        logger = logging.getLogger("ppt.tts")

        audio_pages = [p for p in pages if p.get("type", "") in ("listening", "speaking")]
        total = len(audio_pages)
        if total == 0:
            return pages
        done = 0

        for page in pages:
            ptype = page.get("type", "")
            if ptype not in ("listening", "speaking"):
                continue
            content = page.get("content", {})
            if not isinstance(content, dict):
                content = {}
                page["content"] = content

            # 使用增强的文本提取
            text = PPTService._extract_audio_text(page, ptype)

            if not text or len(text.strip()) < 3:
                logger.warning(
                    "[PPT TTS] %s 页「%s」缺少有效音频文本，跳过音频合成",
                    ptype, page.get("title", f"第{done+1}页"),
                )
                done += 1
                continue

            try:
                audio_bytes = await TTSService.synthesize(
                    text=text.strip(),
                    voice_type=_settings.TTS_VOICE,
                )
                if audio_bytes:
                    text_hash = hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:12]
                    audio_dir = str(UPLOADS_DIR / "ppt_audio")
                    os.makedirs(audio_dir, exist_ok=True)
                    filename = f"ppt_audio_{theme_name}_{ptype}_{text_hash}.mp3"
                    filepath = os.path.join(audio_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)
                    content["audio_url"] = f"/uploads/ppt_audio/{filename}"
                    page["content"] = content
                    logger.info(
                        "[PPT TTS] %s 页「%s」音频合成成功: %s",
                        ptype, page.get("title", f"第{done+1}页"), filename,
                    )
                else:
                    logger.warning(
                        "[PPT TTS] %s 页「%s」TTS 返回空",
                        ptype, page.get("title", f"第{done+1}页"),
                    )
            except Exception as e:
                logger.error(
                    "[PPT TTS] %s 页「%s」合成异常: %s",
                    ptype, page.get("title", f"第{done+1}页"), e,
                )

            done += 1
            if progress_callback:
                await progress_callback(done, total, ptype)

        return pages

    @staticmethod
    def _get_lesson_type_name(lesson_type: str) -> str:
        """获取课型中文名称"""
        names = {
            "new_lesson": "新授课",
            "review": "复习课",
            "exercise": "练习课",
            "conversation": "口语课",
        }
        return names.get(lesson_type, lesson_type)

    @staticmethod
    async def _fetch_rag_references(
        db: AsyncSession,
        teacher_id: int,
        stage_category: str,
        title: str = "",
        subject: str = "",
        knowledge_points: list[str] | None = None,
        lesson_type: str = "",
        top_k: int = 5,
    ) -> list[str]:
        """从 Milvus 检索教案/课件参考文档片段

        构建动态查询语义，利用标题、主题、知识点和课型提高检索精准度，
        改用 hybrid_search 融合稠密+稀疏双路召回。
        """
        # 构建动态查询：标题 + 主题 + 知识点 + 课型关键词
        kps = knowledge_points or []
        lesson_labels = {
            "new_lesson": "新授课 新课 导入",
            "review": "复习课 回顾 巩固",
            "exercise": "练习课 习题 训练",
            "conversation": "口语课 对话 交际",
        }
        lesson_keywords = lesson_labels.get(lesson_type, "")
        query_parts = [title, subject, "英语教案 课件 教学设计 课堂活动"]
        if kps:
            query_parts.extend(kps)
        if lesson_keywords:
            query_parts.append(lesson_keywords)
        query = " ".join(p for p in query_parts if p)

        # 用 hybrid_search 替代纯稠密搜索，提升召回质量
        refs = []
        for source_type in ["doc_teaching_plan", "doc_courseware"]:
            results = await EmbeddingService.hybrid_search(
                db, query, EmbeddingService.TEACHER_DOCUMENTS,
                top_k=top_k, user_id=teacher_id,
                stage=stage_category,
                source_type=source_type,
            )
            refs.extend(r["content"] for r in results)
        return refs[:top_k * 2]  # 最多 10 条

    @staticmethod
    async def _generate_section_pages(
        section_items: list,
        section_index: int,
        total_sections: int,
        context: dict,
        base_system_prompt: str,
        previous_context: str = "",
        api_config: tuple | None = None,
        teacher_id: int = 0,
    ) -> list:
        """为模板的一个内容段调用 LLM 生成页面数据

        Args:
            section_items: 该段的模板项目列表 [{"type": "xxx", "title": "yyy"}]
            section_index: 当前段索引 (0-based)
            total_sections: 总段数
            context: 全局上下文 {title, grade, subject, lesson_type, knowledge_points, stage_style}
            base_system_prompt: 完整 system prompt（含主题 + RAG）
            previous_context: 已生成页面的摘要（用于保持内容连贯）
            api_config: 预获取的 (api_key, api_base, model)
            teacher_id: 教师 ID

        Returns:
            生成的页面列表 [{"type": "...", "title": "...", "content": {...}}]
        """
        import logging
        logger = logging.getLogger("ppt.section")

        kps = context.get("knowledge_points", [])
        kps_text = "、".join(kps) if kps else "无特定限制"

        # 构建该段的页面类型描述
        type_descs = []
        for item in section_items:
            t = item["type"]
            title = item.get("title", t)
            type_descs.append(f"  - {t}: {title}")
        types_text = "\n".join(type_descs)

        # 判断是否为重内容段
        section_types = [item["type"] for item in section_items]
        is_heavy = any(t in PPTService.HEAVY_CONTENT_TYPES for t in section_types)
        heavy_type = section_types[0] if len(section_types) == 1 and section_types[0] in PPTService.HEAVY_CONTENT_TYPES else ""

        # 根据内容类型构建专项提示
        completeness_rule = ""
        if heavy_type == "vocabulary":
            completeness_rule = (
                "\n## 词汇页完整性要求（强制执行）\n"
                "每个单词必须包含完整字段：word（英文）、phonetic（完整音标）、translation（中文释义）、example（英文例句，附中文翻译）。\n"
                "例句必须是完整句子，不可截断。每页 4-8 个词。\n"
            )
        elif heavy_type == "dialogue":
            completeness_rule = (
                "\n## 对话页完整性要求（强制执行）\n"
                "每轮对话必须包含：speaker（角色名）、text（完整英文句子，不可截断）、translation（中文翻译）。\n"
                "对话内容要有逻辑连贯性，3-6 轮交换。每句话必须是完整句子。\n"
            )
        elif heavy_type == "grammar":
            completeness_rule = (
                "\n## 语法页完整性要求（强制执行）\n"
                "每个语法点必须包含：rule（规则表述）、example（2-3 个完整英文例句，附中文翻译）、explanation（清晰解释）。\n"
                "例句必须是完整句子，用公式化表达规则（如 '主语 + be + 动词-ing'）。\n"
            )
        elif heavy_type == "practice":
            completeness_rule = (
                "\n## 练习页完整性要求（强制执行）\n"
                "每道题必须包含完整字段：stem（题干）、options（3-4 个选项，每个选项为完整文本）、answer（正确选项索引）、explanation（解析）。\n"
                "题目不能截断，选项必须有区分度，解析要清楚说明为什么对/错。\n"
                "题型不少于 2 道，不超过 4 道，覆盖不同难度。\n"
            )
        elif heavy_type == "listening":
            completeness_rule = (
                "\n## 听力页完整性要求（强制执行）\n"
                "audio_text 必须是一段完整的英文短文（50-150 词），不可截断。\n"
                "subtitle 提供中文翻译。questions 需 2-3 道完整题目，每题含 stem/options/answer/explanation。\n"
            )
        elif heavy_type == "speaking":
            completeness_rule = (
                "\n## 口语页完整性要求（强制执行）\n"
                "text 必须是一段完整的英文文本（30-80 词），适合跟读练习，不可截断。\n"
                "translation 提供中文翻译，tips 给出发音技巧提示。\n"
            )

        # 构建该段专属 system prompt
        section_system = base_system_prompt
        if completeness_rule:
            section_system += completeness_rule

        # 构建 user prompt
        section_prompt = f"""你正在为一份英语 PPT 课件的第 {section_index + 1}/{total_sections} 段生成内容。

## 课件全局信息
- 标题: {context.get('title', '')}
- 主题: {context.get('subject', context.get('title', ''))}
- 年级: {context.get('grade', '未知')}
- 课型: {context.get('lesson_type_name', '')}
- 知识点: {kps_text}
{context.get('stage_style', '')}

{previous_context}

## 本段需要生成的页面类型
{types_text}

{'⚠️ 本段为重内容页面（' + heavy_type + '），请务必生成完整、详细、不截断的内容！每个例句、每道习题都必须完整。' if is_heavy else ''}

请严格按照 JSON 数组格式输出这 {len(section_items)} 页的内容，不要包含任何额外文字。
每页格式: {{"type": "...", "title": "...", "content": {{...}}}}"""

        try:
            result_text = await AIService.chat_completion(
                db=None if api_config else None,
                messages=[
                    {"role": "system", "content": section_system},
                    {"role": "user", "content": section_prompt},
                ],
                user_id=teacher_id,
                key_type="llm",
                api_config=api_config,
                max_tokens=4096 if is_heavy else 2048,
            )
        except Exception as e:
            logger.error("[PPT Section] LLM 调用失败 section=%d/%d: %s", section_index + 1, total_sections, e)
            raise

        # 解析该段结果
        pages = PPTService._parse_section_result(result_text, section_items)
        logger.info("[PPT Section] 第 %d/%d 段生成完成，获得 %d 页", section_index + 1, total_sections, len(pages))
        return pages

    @staticmethod
    def _parse_section_result(text: str, section_items: list) -> list:
        """解析单个分段的 LLM 返回结果"""
        if not text or not isinstance(text, str):
            return PPTService._generate_section_fallback(section_items)

        import re, json

        # 去掉 markdown 代码块
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.find("\n")
            if first_nl != -1:
                cleaned = cleaned[first_nl + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].rstrip()
            elif "```" in cleaned:
                cleaned = cleaned.rsplit("```", 1)[0].rstrip()

        # 提取 JSON 数组
        json_match = re.search(r'\[[\s\S]*\]', cleaned)
        if not json_match:
            return PPTService._generate_section_fallback(section_items)

        try:
            pages = json.loads(json_match.group())
            if not isinstance(pages, list):
                return PPTService._generate_section_fallback(section_items)

            # 规范化每页内容
            validated = []
            for i, item in enumerate(section_items):
                if i < len(pages) and isinstance(pages[i], dict):
                    p = pages[i]
                    validated.append({
                        "type": p.get("type", item["type"]),
                        "title": p.get("title", item.get("title", "")),
                        "content": p.get("content", {}),
                    })
                else:
                    validated.append({
                        "type": item["type"],
                        "title": item.get("title", ""),
                        "content": PPTService._get_default_content(item["type"]),
                    })
            return validated
        except (json.JSONDecodeError, ValueError):
            return PPTService._generate_section_fallback(section_items)

    @staticmethod
    def _generate_section_fallback(section_items: list) -> list:
        """分节生成失败时的兜底页面"""
        return [
            {
                "type": item["type"],
                "title": item.get("title", ""),
                "content": PPTService._get_default_content(item["type"]),
            }
            for item in section_items
        ]

    @staticmethod
    def _build_previous_context(pages: list) -> str:
        """构建已生成页面的上下文摘要，供后续分节保持内容连贯"""
        if not pages:
            return ""

        summary_parts = []
        for p in pages:
            t = p.get("type", "")
            title = p.get("title", "")
            content = p.get("content", {})
            if not isinstance(content, dict):
                content = {}

            # 提取关键信息
            if t == "vocabulary":
                words = content.get("words", [])
                if words:
                    word_list = [w.get("word", "") for w in words if isinstance(w, dict)]
                    summary_parts.append(f"[词汇] {', '.join(word_list[:5])}")
            elif t == "dialogue":
                summary_parts.append(f"[对话] {title}")
            elif t == "grammar":
                points = content.get("points", [])
                if points:
                    rules = [p.get("rule", "") for p in points if isinstance(p, dict)]
                    summary_parts.append(f"[语法] {', '.join(rules[:3])}")
            elif t == "practice":
                summary_parts.append(f"[练习] {title}")
            else:
                summary_parts.append(f"[{t}] {title}")

        return "## 已生成的前序页面\n" + "\n".join(summary_parts[:8]) + "\n\n请确保本段内容与上述前序页面逻辑连贯、知识点一致。"

    @staticmethod
    async def generate_ppt(
        db: AsyncSession | None,
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        class_id: int | None = None,
        slide_count: int = 6,
        knowledge_points: list[str] | None = None,
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
        theme_name: str = "classic",
        synthesize_audio: bool | None = None,
        layout_intent: str = "auto",
        transition_type: str = "slide",
        transition_duration: int = 400,
        layout_overrides: dict | None = None,
        spec_lock: dict | None = None,
        api_config: tuple[str, str, str] | None = None,
    ) -> dict:
        """AI 生成完整 PPT（大纲 + 逐页内容），保存到数据库

        参数:
            db - 数据库会话（可传 None，此时需通过 api_config 提供 AI 配置）
            teacher_id - 教师 ID
            stage_category - 学段: preschool/primary/junior/senior/other
            use_rag - 是否启用 RAG 知识库参考教案/课件
            additional_references - 用户补充的参考内容（教材片段、教学要求等）
            synthesize_audio - 是否合成 TTS 音频，None=自动判断
            layout_intent - 布局意图
            transition_type - 页面切换动画(fade/slide/push)
            transition_duration - 切换动画时长(ms)
            layout_overrides - 各 slide type 布局覆盖
            spec_lock - 设计规格锁定 Phase 3.3（含视觉风格/配色/字体/布局/节奏）
        """
        if lesson_type not in LESSON_TEMPLATES:
            raise ValueError(f"不支持的课型: {lesson_type}，可选: {list(LESSON_TEMPLATES.keys())}")

        # 如果未指定学段，尝试从 grade 推断
        if not stage_category:
            stage_category = infer_stage_from_grade(grade)

        kps = knowledge_points or []
        template = LESSON_TEMPLATES[lesson_type]
        # 确保期望页数至少与模板长度持平，避免 AI 遗漏关键页面类型（如 ai_interaction）
        if slide_count < len(template):
            slide_count = len(template)
        type_name = PPTService._get_lesson_type_name(lesson_type)

        # 学段教学风格描述
        stage_style = STAGE_TEACHING_STYLES.get(stage_category, "")

        # Phase 3.3: 处理 spec_lock — 设计规格锁定，覆盖 theme/layout/visual_style
        effective_layout_overrides = layout_overrides
        if spec_lock:
            from app.ppt_generator.analysis.spec_lock_manager import spec_lock_manager as slm
            design_spec = slm.build_spec(
                visual_style=spec_lock.get("visual_style", "warm-simple"),
                color_scheme_name=spec_lock.get("color_scheme_name"),
                font_family_name=spec_lock.get("font_family_name"),
                layout_strategy=spec_lock.get("layout_strategy"),
                canvas_format=spec_lock.get("canvas_format", "ppt169"),
            )
            # 风格锁定 → 覆盖 theme_name（使 HTML 渲染使用风格对应的主题）
            locked_style = design_spec.visual_style
            theme_name = spec_lock.get("theme_name") or PPTService._style_to_theme(locked_style) or theme_name
            # 合并布局策略：spec_lock 中的 layout_strategy 优先于请求传入的 layout_overrides
            overrides_from_spec = design_spec.layout_strategy.to_overrides()
            if effective_layout_overrides:
                overrides_from_spec.update(effective_layout_overrides)
            effective_layout_overrides = overrides_from_spec if overrides_from_spec else None
            # 保存完整 spec_lock_dict 供后续存入数据库
            spec_lock_dict = design_spec.to_dict()
            # 保留用户传入的原始覆盖字段
            for k in ("visual_style", "color_scheme_name", "font_family_name", "canvas_format"):
                if k in spec_lock:
                    spec_lock_dict[k] = spec_lock[k]
        else:
            spec_lock_dict = None

        # 构建 system prompt（含 RAG 参考 + 用户补充）
        system_prompt = GENERATE_SYSTEM_PROMPT

        # 1. 知识库 RAG 检索：用标题+知识点构建动态语义查询
        if use_rag:
            refs = await PPTService._fetch_rag_references(
                db, teacher_id, stage_category,
                title=title, subject=subject,
                knowledge_points=kps, lesson_type=lesson_type,
                top_k=5,
            )
            if refs:
                ref_text = "\n\n".join(
                    [f"[参考教案/课件 {i+1}]\n{r[:500]}" for i, r in enumerate(refs)]
                )
                system_prompt += (
                    "\n\n以下是您之前上传的教案和课件中的参考内容，请参考这些内容的教学目标、"
                    "教学环节设计和课堂活动来生成新的 PPT：\n"
                    f"{ref_text}"
                )

        # 2. 用户补充参考内容
        if additional_references:
            system_prompt += (
                "\n\n以下是用户提供的补充参考资料，请结合这些内容来生成 PPT：\n"
                f"{additional_references[:3000]}"
            )

        # 3. 主题风格提示词：根据选中主题注入详细内容生成建议
        theme_prompt = THEME_CONTENT_PROMPTS.get(theme_name)
        if theme_prompt:
            system_prompt += "\n\n" + theme_prompt

        # 1. AI 分节生成 PPT 内容（每段独立并行调用 LLM，确保重内容完整）
        sections = PPTService._split_template_into_sections(template)
        total_sections = len(sections)
        print(f"[PPT] 模板拆分为 {total_sections} 段，开始并行调用 LLM...", flush=True)

        # 构建全局上下文（所有段共享同一个上下文，互不依赖）
        global_context = {
            "title": title,
            "grade": grade or "未知",
            "subject": subject or title,
            "lesson_type": lesson_type,
            "lesson_type_name": PPTService._get_lesson_type_name(lesson_type),
            "knowledge_points": kps,
            "stage_style": STAGE_TEACHING_STYLES.get(stage_category, ""),
        }

        # 为每个分段创建独立的并行任务
        async def _generate_one_section(s_idx: int, section_items: list):
            """并行任务：独立调用 LLM 生成单个分段的内容"""
            try:
                section_pages = await PPTService._generate_section_pages(
                    section_items=section_items,
                    section_index=s_idx,
                    total_sections=total_sections,
                    context=global_context,
                    base_system_prompt=system_prompt,
                    previous_context="",  # 并行模式：各段独立，不传递前序上下文
                    api_config=api_config,
                    teacher_id=teacher_id,
                )
                print(f"[PPT] 第 {s_idx + 1}/{total_sections} 段并行生成完成，获得 {len(section_pages)} 页", flush=True)
                return (s_idx, section_pages, None)
            except Exception as e:
                print(f"[PPT] 第 {s_idx + 1}/{total_sections} 段生成失败: {e}，使用默认内容", flush=True)
                fallback = PPTService._generate_section_fallback(section_items)
                return (s_idx, fallback, str(e))

        # 所有分段同时并行调用 LLM API
        tasks = [_generate_one_section(s_idx, section_items) for s_idx, section_items in enumerate(sections)]
        results = await asyncio.gather(*tasks)

        # 按模板原始顺序重排结果（并行返回顺序不可预测）
        results.sort(key=lambda x: x[0])
        all_pages = []
        failed_sections = []
        for s_idx, section_pages, error in results:
            all_pages.extend(section_pages)
            if error:
                failed_sections.append(s_idx + 1)

        pages = all_pages
        print(f"[PPT] 全部分段生成完成，共 {len(pages)} 页"
              + (f"，{len(failed_sections)} 段使用默认内容（段: {failed_sections}）" if failed_sections else ""),
              flush=True)

        # 2.5 补齐缺失的模板页面类型（如 ai_interaction 被 AI 遗漏时）
        pages = PPTService._ensure_template_types(pages, template)

        # 2.6 应用布局覆盖（含 spec_lock 增强）：将 layout_overrides 注入每个 page
        effective_layout_overrides = locals().get("effective_layout_overrides", layout_overrides)
        if effective_layout_overrides:
            for p in pages:
                ptype = p.get("type", "")
                if ptype in effective_layout_overrides:
                    if "content" not in p or not isinstance(p.get("content"), dict):
                        p["content"] = {}
                    p["content"]["_layout"] = effective_layout_overrides[ptype]

        # 3. 生成大纲
        outline = [
            {"index": i, "title": p.get("title", f"第{i+1}页"),
             "slide_type": p.get("type", "practice"),
             "description": SLIDE_TYPE_LABELS.get(p.get("type", ""), "")}
            for i, p in enumerate(pages)
        ]

        # 3.5 合成 TTS 音频（意图识别：根据课型和页面类型判断是否需要合成）
        if PPTService._should_synthesize_audio(
            lesson_type=lesson_type, pages=pages, grade=grade, explicit=synthesize_audio,
        ):
            try:
                pages = await PPTService._synthesize_ppt_audio(pages, theme_name)
            except Exception as audio_err:
                print(f"[PPT] TTS 合成失败（不影响 PPT 生成）: {audio_err}", flush=True)
        else:
            print(f"[PPT] 意图识别：跳过音频合成（课型={lesson_type}, 未检测到 listening/speaking 页面）", flush=True)

        # 4. 渲染 HTML 内容（使用传入的主题 + 切换动画参数）
        try:
            theme = await PPTThemeService.get_theme_by_name(db, theme_name)
            theme_css = theme["css_content"] if theme else ""
            theme_vars = theme.get("css_variables", "") if theme else ""
            # 从主题设计规范读取推荐动画，用户参数优先
            style_skill = theme.get("style_skill") if theme else None
            t_type = transition_type
            t_dur = transition_duration
            if style_skill and isinstance(style_skill, dict):
                anim_cfg = style_skill.get("recommended_animations", {})
                if isinstance(anim_cfg, dict) and transition_type == "slide":
                    t_type = anim_cfg.get("transition", t_type)
                    t_dur = anim_cfg.get("duration", t_dur)
            # Phase 3.5: 从 spec_lock 提取 visual_style
            vs = ""
            sd = locals().get("spec_lock_dict")
            if sd:
                vs = sd.get("visual_style", "")
            html_content = PPTHtmlRenderer.render_html_from_pages(
                pages=pages, title=title, theme_css=theme_css, theme_name=theme_name,
                css_variables=theme_vars,
                transition_type=t_type,
                transition_duration=t_dur,
                visual_style=vs,
            )
        except Exception as render_err:
            print(f"[PPT] HTML 渲染失败: {type(render_err).__name__}: {render_err}", flush=True)
            import traceback
            traceback.print_exc()
            html_content = ""

        # 5. 保存到数据库（含学段 + HTML 格式 + 布局/动画配置 + spec_lock）
        spec_lock_dict = locals().get("spec_lock_dict")
        ppt = LessonPPT(
            teacher_id=teacher_id,
            class_id=class_id,
            title=title,
            lesson_type=lesson_type,
            subject=subject,
            grade=grade,
            stage_category=stage_category,
            outline=outline,
            pages_json=pages,
            html_content=html_content,
            theme_name=theme_name,
            version=1,
            slide_count=len(pages),
            layout_intent=layout_intent,
            transition_type=t_type,
            transition_duration=t_dur,
            layout_overrides=effective_layout_overrides if locals().get("effective_layout_overrides") else layout_overrides,
            spec_lock=spec_lock_dict,
            status="draft",
        )
        db.add(ppt)
        await db.commit()
        await db.refresh(ppt)

        return {
            "id": ppt.id,
            "title": ppt.title,
            "outline": outline,
            "pages_json": pages,
            "html_content": html_content,
            "theme_name": theme_name,
            "slide_count": len(pages),
            "stage_category": stage_category,
            "layout_intent": layout_intent,
            "transition_type": t_type,
            "transition_duration": t_dur,
            "spec_lock": spec_lock_dict if locals().get("spec_lock_dict") else None,
        }

    @staticmethod
    def _style_to_theme(visual_style: str) -> str:
        """视觉风格 → PPT 主题名称映射（HTML 渲染使用 PPT 主题体系）"""
        mapping = {
            "swiss-minimal": "classic",
            "soft-rounded": "cartoon",
            "editorial": "academic",
            "dark-tech": "tech",
            "sketch-notes": "warm",
            "chalkboard": "blackboard",
            "glassmorphism": "tech",
            "paper-cut": "nature",
            "warm-simple": "warm",
        }
        return mapping.get(visual_style, "classic")

    @staticmethod
    async def generate_outline(
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        knowledge_points: list[str] | None = None,
        api_config: tuple[str, str, str] | None = None,
    ) -> dict:
        """教学助手：AI 生成 PPT 大纲（章节 + 子主题），不生成完整页面"""
        if lesson_type not in LESSON_TEMPLATES:
            raise ValueError(f"不支持的课型: {lesson_type}，可选: {list(LESSON_TEMPLATES.keys())}")
        type_name = PPTService._get_lesson_type_name(lesson_type)
        kps = knowledge_points or []

        kp_hint = ""
        if kps:
            kp_hint = "知识点要求：" + "、".join(kps)

        prompt = f"""你是一位经验丰富的英语教师。请为以下课件生成详细的大纲结构。

标题：{title}
课型：{type_name}
年级：{grade or '未知'}
{kp_hint}

请为这份 PPT 生成 4-6 个章节，每个章节包含：
1. title：章节标题（如"词汇学习""语法讲解""课堂练习""总结回顾"等）
2. subtopics：该章节下的子主题列表（列出具体教学内容，如词汇例句、语法规则、练习题等）

要求：
- 章节结构合理，符合 {type_name} 的教学流程
- 子主题具体可操作，每章节 2-4 个子主题
- 内容紧密围绕标题和知识点
- 输出严格的 JSON 格式，不要包含任何额外文字

JSON 格式：
{{"sections": [
    {{"title": "章节标题", "subtopics": ["子主题1", "子主题2"]}},
    ...
]}}"""

        try:
            result_text = await AIService.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一位教学设计专家。请严格输出 JSON 格式。不要包含任何额外文字。"},
                    {"role": "user", "content": prompt},
                ],
                api_config=api_config,
                max_tokens=4096,
            )
        except Exception as e:
            raise ValueError(f"AI 大纲生成失败: {str(e)}")

        # 解析 JSON
        import json, re
        text = result_text.strip()
        # 去除可能的 markdown 代码标记
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 对象
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                data = json.loads(m.group())
            else:
                raise ValueError("AI 返回格式异常，无法解析为 JSON")

        sections = data.get("sections", []) if isinstance(data, dict) else []
        if not sections:
            # 兜底：返回默认大纲
            sections = [
                {"title": "课程导入", "subtopics": [title, "学习目标"]},
                {"title": type_name, "subtopics": ["核心知识点讲解", "示例演示"]},
                {"title": "课堂练习", "subtopics": ["基础练习", "拓展练习"]},
                {"title": "总结回顾", "subtopics": ["知识要点", "课后任务"]},
            ]

        return {"sections": sections}

    @staticmethod
    async def generate_from_outline(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        knowledge_points: list[str] | None = None,
        sections: list[dict] | None = None,
        theme_name: str = "classic",
        stage_category: str = "",
        synthesize_audio: bool | None = None,
        api_config: tuple[str, str, str] | None = None,
        visual_style: str = "",
    ) -> dict:
        """基于预定义大纲 + 主题，生成完整 PPT 并保存到数据库

        Phase 3.5: 新增 visual_style 参数用于 HTML 渲染风格对齐。
        """
        if lesson_type not in LESSON_TEMPLATES:
            raise ValueError(f"不支持的课型: {lesson_type}，可选: {list(LESSON_TEMPLATES.keys())}")
        if not stage_category:
            stage_category = infer_stage_from_grade(grade)

        kps = knowledge_points or []
        sections = sections or []
        template = LESSON_TEMPLATES[lesson_type]
        slide_count = max(len(template), 6)
        type_name = PPTService._get_lesson_type_name(lesson_type)
        stage_style = STAGE_TEACHING_STYLES.get(stage_category, "")

        # 构建 system prompt
        system_prompt = GENERATE_SYSTEM_PROMPT
        theme_prompt = THEME_CONTENT_PROMPTS.get(theme_name)
        if theme_prompt:
            system_prompt += "\n\n" + theme_prompt

        # 构建大纲段落
        outline_text = ""
        if sections:
            outline_text = "请严格按照以下大纲结构生成每一页内容：\n"
            for i, sec in enumerate(sections, 1):
                sec_title = sec.get("title", f"第{i}节")
                subtopics = sec.get("subtopics", [])
                outline_text += f"{i}. {sec_title}\n"
                for j, st in enumerate(subtopics, 1):
                    outline_text += f"   {i}.{j} {st}\n"

        # 构建 user prompt
        kp_constraints = ""
        if kps:
            kp_constraints = "========== 知识点约束（必须严格执行） ==========\n"
            kp_constraints += "用户指定的知识点如下，所有幻灯片的内容必须紧紧围绕这些知识点：\n\n"
            for i, kp in enumerate(kps, 1):
                kp_constraints += f"  [{i}] {kp}\n"
            kp_constraints += "\n词汇、语法、对话、练习等所有页面都必须围绕上述知识点。\n"

        user_prompt = f"""请为{'小学/初中/高中' if not grade else grade}英语 {grade or '未知'} 年级生成一份 {type_name} PPT。
标题: {title}
主题: {subject or title}
课型: {type_name}
期望页数: {slide_count} 页
{stage_style}

{outline_text}
{kp_constraints}

请为每页生成完整的 JSON 内容。严格输出 JSON 数组格式，不要包含任何额外的文字。"""

        try:
            result_text = await AIService.chat_completion(
                db=None if api_config else db,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                user_id=teacher_id,
                key_type="llm",
                api_config=api_config,
            )
        except Exception as e:
            raise ValueError(f"AI 生成失败: {str(e)}")

        pages = PPTService._parse_pages(result_text, slide_count, template)
        pages = PPTService._ensure_template_types(pages, template)

        outline = [
            {"index": i, "title": p.get("title", f"第{i+1}页"),
             "slide_type": p.get("type", "practice"),
             "description": SLIDE_TYPE_LABELS.get(p.get("type", ""), "")}
            for i, p in enumerate(pages)
        ]

        # 合成 TTS 音频（意图识别）
        if PPTService._should_synthesize_audio(
            lesson_type=lesson_type, pages=pages, grade=grade, explicit=synthesize_audio,
        ):
            try:
                pages = await PPTService._synthesize_ppt_audio(pages, theme_name)
            except Exception as audio_err:
                print(f"[PPT] TTS 合成失败: {audio_err}", flush=True)
        else:
            print(f"[PPT] 意图识别：跳过音频合成（课型={lesson_type}）", flush=True)

        # 渲染 HTML
        try:
            theme = await PPTThemeService.get_theme_by_name(db, theme_name)
            theme_css = theme["css_content"] if theme else ""
            theme_vars = theme.get("css_variables", "") if theme else ""
            html_content = PPTHtmlRenderer.render_html_from_pages(
                pages=pages, title=title, theme_css=theme_css, theme_name=theme_name,
                css_variables=theme_vars,
                visual_style=visual_style,
            )
        except Exception as render_err:
            print(f"[PPT] HTML 渲染失败: {render_err}", flush=True)
            html_content = ""

        # 保存到数据库
        ppt = LessonPPT(
            teacher_id=teacher_id,
            title=title,
            lesson_type=lesson_type,
            subject=subject,
            grade=grade,
            stage_category=stage_category,
            outline=outline,
            pages_json=pages,
            html_content=html_content,
            theme_name=theme_name,
            version=1,
            slide_count=len(pages),
            status="draft",
        )
        db.add(ppt)
        await db.commit()
        await db.refresh(ppt)

        return {
            "id": ppt.id,
            "title": ppt.title,
            "outline": outline,
            "pages_json": pages,
            "html_content": html_content,
            "theme_name": theme_name,
            "slide_count": len(pages),
        }

    @staticmethod
    async def generate_ppt_stream(
        db: AsyncSession | None, teacher_id: int,
        title: str = "", lesson_type: str = "", subject: str = "", grade: str = "",
        class_id: int | None = None, slide_count: int = 10,
        knowledge_points: list[str] | None = None,
        stage_category: str = "",
        use_rag: bool = True,
        additional_references: str = "",
        theme_name: str = "classic",
        synthesize_audio: bool | None = None,
        layout_intent: str = "auto",
        transition_type: str = "slide",
        transition_duration: int = 400,
        layout_overrides: dict | None = None,
        spec_lock: dict | None = None,
        api_config: tuple[str, str, str] | None = None,
    ):
        """SSE streaming variant of generate_ppt. Yields progress dicts:
        {"type": "progress", "progress": 0-100, "message": "..."}
        {"type": "complete", "data": {...}}
        {"type": "error", "message": "..."}

        优化：db 可传 None（SSE 预获取 API 配置后释放 DB 连接），
        通过 api_config 参数传递预获取的 API 配置，AI 调用期间不持有 DB 会话。
        """
        yield {"type": "progress", "progress": 5, "message": "正在生成 PPT 内容..."}
        # 当 db 为 None 时（SSE 预获取 API 配置后释放 DB 连接），
        # 内部创建临时会话用于快速 DB 操作（RAG/主题查询/保存），
        # LLM 调用使用 api_config 不持有 DB 连接。
        try:
            if db is None:
                async with get_async_session() as session:
                    result = await PPTService.generate_ppt(
                        db=session, teacher_id=teacher_id,
                        title=title, lesson_type=lesson_type, subject=subject, grade=grade,
                        class_id=class_id, slide_count=slide_count,
                        knowledge_points=knowledge_points, stage_category=stage_category,
                        use_rag=use_rag, additional_references=additional_references,
                        theme_name=theme_name, synthesize_audio=synthesize_audio,
                        layout_intent=layout_intent,
                        transition_type=transition_type, transition_duration=transition_duration,
                        layout_overrides=layout_overrides,
                        spec_lock=spec_lock,
                        api_config=api_config,
                    )
            else:
                result = await PPTService.generate_ppt(
                    db=db, teacher_id=teacher_id,
                    title=title, lesson_type=lesson_type, subject=subject, grade=grade,
                    class_id=class_id, slide_count=slide_count,
                    knowledge_points=knowledge_points, stage_category=stage_category,
                    use_rag=use_rag, additional_references=additional_references,
                    theme_name=theme_name, synthesize_audio=synthesize_audio,
                    layout_intent=layout_intent,
                    transition_type=transition_type, transition_duration=transition_duration,
                    layout_overrides=layout_overrides,
                    spec_lock=spec_lock,
                    api_config=api_config,
                )
        except Exception as e:
            yield {"type": "error", "message": f"AI 生成失败: {str(e)}"}
            return

        pages = result.get("pages_json", [])
        # 注：generate_ppt() 内部已根据意图识别条件调用 _synthesize_ppt_audio()
        yield {"type": "progress", "progress": 90, "message": "渲染 HTML 中..."}

        # Re-render HTML with audio URLs（临时获取 DB 连接用于主题查询）
        try:
            from app.services.ppt_html_renderer import PPTHtmlRenderer
            from app.services.ppt_theme_service import PPTThemeService

            theme_css = ""
            theme_vars = ""
            if db is not None:
                theme = await PPTThemeService.get_theme_by_name(db, theme_name)
                theme_css = theme["css_content"] if theme else ""
                theme_vars = theme.get("css_variables", "") if theme else ""
            else:
                async with get_async_session() as session:
                    theme = await PPTThemeService.get_theme_by_name(session, theme_name)
                    theme_css = theme["css_content"] if theme else ""
                    theme_vars = theme.get("css_variables", "") if theme else ""

            # Phase 3.5: 从 spec_lock 提取 visual_style
            vs = ""
            if spec_lock:
                vs = spec_lock.get("visual_style", "")
            html_content = PPTHtmlRenderer.render_html_from_pages(
                pages=pages, title=result["title"],
                theme_css=theme_css, theme_name=theme_name,
                css_variables=theme_vars,
                transition_type=transition_type, transition_duration=transition_duration,
                visual_style=vs,
            )
        except Exception as render_err:
            print(f"[PPT] 重新渲染失败: {render_err}", flush=True)
            html_content = result.get("html_content", "")

        result["html_content"] = html_content
        result["pages_json"] = pages
        yield {"type": "complete", "progress": 100, "message": "PPT 生成完成", "data": result}

    @staticmethod
    def _normalize_page_content(page: dict) -> dict:
        """规范化页面字典：确保 content 字段不为空。

        当 AI 返回的内容字段被放在页面顶层而不是 content 子对象中时，
        将它们自动迁移到 content 字段中。
        """
        content = page.get("content", {})
        if content and isinstance(content, dict) and any(v for v in content.values() if v):
            # content 已有有效内容，无需处理
            return page

        # content 为空或无效 — 从顶层提取非结构字段作为内容
        structural_keys = {"type", "title", "kg_node_ref", "layout", "_index", "audio_url", "content"}
        promoted = {}
        for k, v in page.items():
            if k not in structural_keys and v is not None:
                promoted[k] = v

        if promoted:
            print(f"[PPT_PARSE] 将顶层字段 {list(promoted.keys())} 提权到 content", flush=True)
            page["content"] = promoted

        return page

    @staticmethod
    def _parse_pages(text: str, expected_count: int, template: list) -> list:
        """解析 AI 返回的 JSON 页面内容"""
        if not text or not isinstance(text, str):
            print(f"[PPT_PARSE] text 为空或类型错误: type={type(text).__name__}, 回退到默认模板", flush=True)
            return PPTService._generate_default_pages(expected_count, template)

        # 输出 LLM 原始响应（截断）以便排查格式问题
        raw_preview = text[:3000]
        print(f"[PPT_PARSE] LLM 原始响应预览（前 3000 字符）: {raw_preview}", flush=True)

        # 1. 尝试去掉 markdown 代码块标记
        cleaned = text.strip()
        # 去掉 ```json 或 ``` 包裹
        if cleaned.startswith("```"):
            # 找到第一个换行后的内容
            first_nl = cleaned.find("\n")
            if first_nl != -1:
                cleaned = cleaned[first_nl + 1:]
            # 去掉末尾的 ```
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].rstrip()
            elif "```" in cleaned:
                # 可能中间还有其他内容
                cleaned = cleaned.rsplit("```", 1)[0].rstrip()

        # 2. 尝试提取 JSON 数组（从第一个 [ 到能匹配的最后一个 ]）
        json_match = re.search(r'\[[\s\S]*\]', cleaned)
        if not json_match:
            print(f"[PPT_PARSE] 未找到 JSON 数组, 回退到默认模板", flush=True)
            return PPTService._generate_default_pages(expected_count, template)

        json_str = json_match.group()

        # 3. 尝试解析
        #   先尝试直接解析，如果失败则尝试找到最内层的有效 JSON 数组
        try:
            pages = json.loads(json_str)
            if not isinstance(pages, list):
                raise ValueError("AI 返回的不是数组")
            # 验证并补充字段，对每页进行 content 归一化
            validated = []
            for p in pages:
                if not isinstance(p, dict):
                    continue
                p = PPTService._normalize_page_content(p)
                validated.append({
                    "type": p.get("type", "practice"),
                    "title": p.get("title", ""),
                    "content": p.get("content", {}),
                })
            if validated:
                print(f"[PPT_PARSE] 成功解析 {len(validated)} 页", flush=True)
                return validated
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[PPT_PARSE] JSON 解析失败: {e}", flush=True)
            # 尝试逐段缩小范围：找到第一个 [ 和能匹配的最后一个 ]
            # 使用栈来找到最外层的 [] 范围
            stack = []
            start = -1
            for i, ch in enumerate(json_str):
                if ch == '[':
                    if not stack:
                        start = i
                    stack.append(i)
                elif ch == ']':
                    if stack:
                        stack.pop()
                        if not stack and start != -1:
                            # 找到最外层的完整数组
                            try:
                                outer = json_str[start:i+1]
                                pages = json.loads(outer)
                                if isinstance(pages, list):
                                    validated = []
                                    for p in pages:
                                        if not isinstance(p, dict):
                                            continue
                                        p = PPTService._normalize_page_content(p)
                                        validated.append({
                                            "type": p.get("type", "practice"),
                                            "title": p.get("title", ""),
                                            "content": p.get("content", {}),
                                        })
                                    if validated:
                                        print(f"[PPT_PARSE] 通过栈匹配成功解析 {len(validated)} 页", flush=True)
                                        return validated
                            except (json.JSONDecodeError, ValueError):
                                continue

        print(f"[PPT_PARSE] 所有解析尝试均失败, 回退到默认模板", flush=True)
        return PPTService._generate_default_pages(expected_count, template)

    @staticmethod
    def _ensure_template_types(pages: list, template: list) -> list:
        """确保页面列表包含模板定义的所有必需类型，缺失的用默认内容补齐"""
        # 收集 AI 已生成的页面类型（保留首次出现顺序）
        existing_types = []
        seen = set()
        for p in pages:
            t = p.get("type", "")
            if t not in seen:
                seen.add(t)
                existing_types.append(t)

        # 检查模板中是否有未出现的类型
        insert_queue = []  # (插入位置索引, type名称)
        for i, t_item in enumerate(template):
            t = t_item["type"]
            if t not in seen:
                insert_queue.append((i, t))
                seen.add(t)

        if not insert_queue:
            return pages  # 没有缺失，直接返回

        # 从后往前插入（避免索引偏移）
        result = list(pages)
        for pos, t in reversed(insert_queue):
            # 找到模板中该类型的 title
            t_title = ""
            for t_item in template:
                if t_item["type"] == t:
                    t_title = t_item.get("title", "")
                    break
            result.insert(pos, {
                "type": t,
                "title": t_title,
                "content": PPTService._get_default_content(t),
            })
        return result

    @staticmethod
    def _generate_default_pages(count: int, template: list) -> list:
        """生成默认页面内容（AI 解析失败时的回退方案）"""
        pages = []
        for i in range(min(count, len(template))):
            t = template[i]
            pages.append({
                "type": t["type"],
                "title": t["title"],
                "content": PPTService._get_default_content(t["type"]),
            })
        # 如果模板不够，重复最后一个类型
        while len(pages) < count:
            t = template[-1]
            pages.append({
                "type": t["type"],
                "title": f"{t['title']} ({len(pages)+1})",
                "content": PPTService._get_default_content(t["type"]),
            })
        return pages

    @staticmethod
    def _get_default_content(slide_type: str) -> dict:
        """获取默认页面内容"""
        defaults = {
            "catalog": {"sections": ["课程导入", "词汇学习", "句型练习", "课堂活动", "总结回顾"]},
            "title": {"main_title": "英语课堂", "subtitle": "English Class", "grade": ""},
            "objective": {"items": ["掌握本课核心词汇", "理解重点句型", "能够进行简单对话"]},
            "vocabulary": {"words": [
                {"word": "hello", "phonetic": "/həˈloʊ/", "translation": "你好", "example": "Hello, everyone!"},
                {"word": "goodbye", "phonetic": "/ɡʊdˈbaɪ/", "translation": "再见", "example": "Goodbye, teacher!"},
            ]},
            "dialogue": {"dialogues": [
                {"speaker": "A", "text": "Hello! How are you?", "translation": "你好！你怎么样？"},
                {"speaker": "B", "text": "I'm fine, thank you!", "translation": "我很好，谢谢！"},
            ]},
            "grammar": {"points": [
                {"rule": "一般现在时", "example": "I like apples.", "explanation": "表示经常发生的动作或状态"},
            ]},
            "practice": {"questions": [
                {"stem": "What does \"apple\" mean?", "options": ["香蕉", "苹果", "橘子", "葡萄"], "answer": 1, "explanation": "apple 的意思是苹果"},
            ]},
            "interactive": {"activity_type": "game", "description": "课堂互动活动", "steps": ["教师说明规则", "学生分组练习", "展示成果"]},
            "ai_interaction": {"prompt": "你对今天学的内容有什么疑问吗？试试向我提问吧！", "questions": [
                {"question": "What does this word mean?", "hint": "问老师某个单词的意思"},
                {"question": "Can you give me another example?", "hint": "请老师再举一个例子"},
                {"question": "How do I use this grammar?", "hint": "问某个语法怎么用"},
            ]},
            "summary": {"key_points": ["本课重点回顾"], "homework": "复习本课内容"},
            "listening": {
                "audio_text": "This is a listening exercise. Please listen carefully and answer the questions.",
                "subtitle": "听力练习",
                "questions": [
                    {"stem": "What is the main topic of this listening passage?", "options": ["A. Greetings", "B. School Life", "C. Weather"], "answer": "B", "explanation": "Please listen to the passage again."}
                ],
            },
            "speaking": {
                "text": "Practice reading this sentence aloud. Pay attention to your pronunciation.",
                "translation": "请大声朗读这个句子，注意发音。",
                "tips": "注意语调和重音",
            },
        }
        return defaults.get(slide_type, {"content": "待编辑"})

    # ========== PPT CRUD ==========

    @staticmethod
    async def list_ppts(
        db: AsyncSession, teacher_id: int,
        status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> dict:
        """获取教师的 PPT 列表"""
        query = select(LessonPPT).where(LessonPPT.teacher_id == teacher_id)
        if status:
            query = query.where(LessonPPT.status == status)
        query = query.order_by(desc(LessonPPT.updated_at))

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        pp_ts = result.scalars().all()

        items = []
        for p in pp_ts:
            items.append({
                "id": p.id,
                "title": p.title,
                "lesson_type": p.lesson_type,
                "lesson_type_name": PPTService._get_lesson_type_name(p.lesson_type),
                "subject": p.subject,
                "grade": p.grade,
                "slide_count": p.slide_count,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else "",
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def get_ppt(db: AsyncSession, ppt_id: int, teacher_id: int) -> dict | None:
        """获取单个 PPT 详情"""
        result = await db.execute(
            select(LessonPPT).where(LessonPPT.id == ppt_id, LessonPPT.teacher_id == teacher_id)
        )
        ppt = result.scalar_one_or_none()
        if not ppt:
            return None

        return {
            "id": ppt.id,
            "teacher_id": ppt.teacher_id,
            "class_id": ppt.class_id,
            "title": ppt.title,
            "lesson_type": ppt.lesson_type,
            "lesson_type_name": PPTService._get_lesson_type_name(ppt.lesson_type),
            "subject": ppt.subject,
            "grade": ppt.grade,
            "outline": ppt.outline,
            "pages_json": ppt.pages_json,
            "html_content": ppt.html_content or "",
            "theme_name": ppt.theme_name or "classic",
            "version": ppt.version or 1,
            "thumbnail_url": ppt.thumbnail_url or "",
            "slide_count": ppt.slide_count,
            "interaction_config": ppt.interaction_config,
            "spec_lock": ppt.spec_lock,
            "layout_intent": ppt.layout_intent or "auto",
            "transition_type": ppt.transition_type or "slide",
            "transition_duration": ppt.transition_duration or 400,
            "layout_overrides": ppt.layout_overrides,
            "status": ppt.status,
            "created_at": ppt.created_at.isoformat() if ppt.created_at else "",
            "updated_at": ppt.updated_at.isoformat() if ppt.updated_at else "",
        }

    @staticmethod
    async def _build_html_content(
        db: AsyncSession, pages: list, title: str, theme_name: str,
        transition_type: str = "slide",
        transition_duration: int = 400,
        visual_style: str = "",
    ) -> str:
        """根据页面数据和主题名生成 HTML 内容

        Phase 3.5: 新增 visual_style 参数。
        """
        try:
            theme = await PPTThemeService.get_theme_by_name(db, theme_name)
            theme_css = theme["css_content"] if theme else ""
            theme_vars = theme.get("css_variables", "") if theme else ""
            # 从主题设计规范读取推荐切换动画
            style_skill = theme.get("style_skill") if theme else None
            t_type = transition_type
            t_dur = transition_duration
            if style_skill and isinstance(style_skill, dict):
                anim_cfg = style_skill.get("recommended_animations", {})
                if isinstance(anim_cfg, dict) and transition_type == "slide":
                    t_type = anim_cfg.get("transition", t_type)
                    t_dur = anim_cfg.get("duration", t_dur)
            return PPTHtmlRenderer.render_html_from_pages(
                pages=pages, title=title, theme_css=theme_css, theme_name=theme_name,
                css_variables=theme_vars,
                transition_type=t_type,
                transition_duration=t_dur,
                visual_style=visual_style,
            )
        except Exception:
            return ""

    @staticmethod
    async def _save_version(
        db: AsyncSession, ppt: LessonPPT, change_summary: str = "",
    ) -> None:
        """保存当前 PPT 快照到版本历史表"""
        version = PptVersion(
            ppt_id=ppt.id,
            version=ppt.version,
            html_content=ppt.html_content or "",
            pages_json=ppt.pages_json,
            theme_name=ppt.theme_name or "classic",
            change_summary=change_summary,
        )
        db.add(version)

    @staticmethod
    async def update_ppt(
        db: AsyncSession, ppt_id: int, teacher_id: int, update_data: dict,
    ) -> dict | None:
        """更新 PPT，当 pages_json 或 theme_name 变化时自动重新渲染 HTML 并保存版本"""
        result = await db.execute(
            select(LessonPPT).where(LessonPPT.id == ppt_id, LessonPPT.teacher_id == teacher_id)
        )
        ppt = result.scalar_one_or_none()
        if not ppt:
            return None

        needs_html_rebuild = False
        needs_version_save = False
        change_summary_parts = []

        allowed_fields = {
            "title", "lesson_type", "subject", "grade", "class_id",
            "pages_json", "outline", "interaction_config", "status",
            "stage_category", "theme_name",
            "layout_intent", "transition_type", "transition_duration", "layout_overrides",
        }
        for key, value in update_data.items():
            if key in allowed_fields and value is not None:
                if key == "pages_json":
                    ppt.pages_json = value
                    ppt.slide_count = len(value) if isinstance(value, list) else 0
                    needs_html_rebuild = True
                    needs_version_save = True
                    change_summary_parts.append("页面内容更新")
                elif key == "theme_name":
                    ppt.theme_name = value
                    needs_html_rebuild = True
                    change_summary_parts.append(f"主题切换为 {value}")
                elif key == "outline":
                    ppt.outline = value
                elif key == "layout_overrides":
                    ppt.layout_overrides = value
                    needs_html_rebuild = True
                    change_summary_parts.append("布局覆盖更新")
                else:
                    setattr(ppt, key, value)
                    if key in ("transition_type", "transition_duration"):
                        needs_html_rebuild = True

        # 重新渲染 HTML
        if needs_html_rebuild:
            # 先保存旧版本
            if needs_version_save:
                await PPTService._save_version(
                    db, ppt, change_summary=", ".join(change_summary_parts) or "自动保存"
                )
            # 生成新 HTML，传入当前过渡动画配置和视觉风格
            trans_type = ppt.transition_type or "slide"
            trans_dur = ppt.transition_duration or 400
            spec_lock_data = ppt.spec_lock if isinstance(ppt.spec_lock, dict) else {}
            vs = spec_lock_data.get("visual_style", "")
            ppt.html_content = await PPTService._build_html_content(
                db, ppt.pages_json, ppt.title, ppt.theme_name or "classic",
                transition_type=trans_type,
                transition_duration=trans_dur,
                visual_style=vs,
            )
            ppt.version = (ppt.version or 1) + 1

        await db.commit()
        await db.refresh(ppt)
        return await PPTService.get_ppt(db, ppt_id, teacher_id)

    @staticmethod
    async def delete_ppt(db: AsyncSession, ppt_id: int, teacher_id: int) -> bool:
        """删除 PPT"""
        result = await db.execute(
            select(LessonPPT).where(LessonPPT.id == ppt_id, LessonPPT.teacher_id == teacher_id)
        )
        ppt = result.scalar_one_or_none()
        if not ppt:
            return False
        await db.delete(ppt)
        await db.commit()
        return True

    # ========== 单页重新生成 ==========

    @staticmethod
    async def regenerate_page(
        db: AsyncSession, teacher_id: int,
        ppt_id: int, page_index: int, outline_title: str,
        lesson_type: str, subject: str = "", grade: str = "",
    ) -> dict | None:
        """使用 AI 重新生成 PPT 的某一页"""
        # 验证 PPT 归属
        result = await db.execute(
            select(LessonPPT).where(LessonPPT.id == ppt_id, LessonPPT.teacher_id == teacher_id)
        )
        ppt = result.scalar_one_or_none()
        if not ppt:
            return None
        if page_index < 0 or page_index >= len(ppt.pages_json):
            raise ValueError(f"页码超出范围: {page_index}")

        type_name = PPTService._get_lesson_type_name(lesson_type)

        # 构建 system prompt（含主题提示词）
        system_prompt = GENERATE_SYSTEM_PROMPT
        theme_name = ppt.theme_name or "classic"
        theme_prompt = THEME_CONTENT_PROMPTS.get(theme_name)
        if theme_prompt:
            system_prompt += "\n\n" + theme_prompt

        user_prompt = f"""请为小学英语 {grade or '未知'} 年级的 {type_name} 生成一页 PPT 内容。
标题: {outline_title}
主题: {subject or outline_title}
当前主题: {theme_name}

请仅生成一个 JSON 对象，不要包含数组标签。
格式参考: {{"type": "<slide_type>", "title": "{outline_title}", "content": {{...}}}}"""

        try:
            result_text = await AIService.chat_completion(
                db=db,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                user_id=teacher_id,
                key_type="llm",
            )
        except Exception:
            return None

        # 解析单个页面 JSON
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            try:
                new_page = json.loads(json_match.group())
                if isinstance(new_page, dict) and "type" in new_page:
                    pages = list(ppt.pages_json)
                    pages[page_index] = {
                        "type": new_page.get("type", pages[page_index].get("type", "practice")),
                        "title": new_page.get("title", outline_title),
                        "content": new_page.get("content", pages[page_index].get("content", {})),
                    }
                    ppt.pages_json = pages
                    # 重新渲染 HTML（传递过渡动画配置和视觉风格）
                    trans_type = ppt.transition_type or "slide"
                    trans_dur = ppt.transition_duration or 400
                    spec_lock_data = ppt.spec_lock if isinstance(ppt.spec_lock, dict) else {}
                    vs = spec_lock_data.get("visual_style", "")
                    ppt.html_content = await PPTService._build_html_content(
                        db, ppt.pages_json, ppt.title, ppt.theme_name or "classic",
                        transition_type=trans_type,
                        transition_duration=trans_dur,
                        visual_style=vs,
                    )
                    ppt.version = (ppt.version or 1) + 1
                    await db.commit()
                    await db.refresh(ppt)
                    return pages[page_index]
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    # ========== 课堂互动 ==========

    @staticmethod
    async def start_classroom(
        db: AsyncSession, teacher_id: int, ppt_id: int,
    ) -> dict:
        """开始课堂互动会话"""
        # 验证 PPT 归属和状态
        result = await db.execute(
            select(LessonPPT).where(LessonPPT.id == ppt_id, LessonPPT.teacher_id == teacher_id)
        )
        ppt = result.scalar_one_or_none()
        if not ppt:
            raise ValueError("PPT 不存在")

        # 将 PPT 标记为已发布
        if ppt.status == "draft":
            ppt.status = "published"

        # 创建课堂会话
        session = ClassroomSession(
            ppt_id=ppt_id,
            teacher_id=teacher_id,
            title=ppt.title,
            status="active",
            current_page=0,
            student_count=0,
            interaction_data={
                "votes": [],
                "quizzes": [],
                "danmaku": [],
                "questions": [],
                "page_log": [],
            },
            started_at=datetime.now(),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        return {
            "id": session.id,
            "ppt_id": session.ppt_id,
            "title": session.title,
            "status": session.status,
            "current_page": session.current_page,
            "student_count": session.student_count,
            "interaction_data": session.interaction_data or {},
            "started_at": session.started_at.isoformat() if session.started_at else "",
        }

    @staticmethod
    async def end_classroom(db: AsyncSession, session_id: int, teacher_id: int) -> dict | None:
        """结束课堂并生成报告"""
        result = await db.execute(
            select(ClassroomSession).where(
                ClassroomSession.id == session_id,
                ClassroomSession.teacher_id == teacher_id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        session.status = "ended"
        session.ended_at = datetime.now()

        # 生成互动汇总
        interaction_data = session.interaction_data or {}
        summary = PPTService._generate_classroom_summary(interaction_data)

        await db.commit()

        return {
            "session_id": session.id,
            "status": "ended",
            "duration_minutes": (
                (session.ended_at - session.started_at).total_seconds() / 60
                if session.ended_at and session.started_at else 0
            ),
            "summary": summary,
        }

    @staticmethod
    def _generate_classroom_summary(data: dict) -> dict:
        """生成课堂互动数据汇总"""
        votes = data.get("votes", [])
        quizzes = data.get("quizzes", [])
        danmaku = data.get("danmaku", [])
        questions = data.get("questions", [])
        page_log = data.get("page_log", [])

        return {
            "total_votes": len(votes),
            "total_quizzes": len(quizzes),
            "total_danmaku": len(danmaku),
            "total_questions": len(questions),
            "total_page_flips": len(page_log),
            "quiz_accuracy_summary": PPTService._summarize_quiz_results(quizzes),
        }

    @staticmethod
    def _summarize_quiz_results(quizzes: list) -> dict:
        """汇总答题结果"""
        if not quizzes:
            return {"total": 0, "correct": 0, "accuracy": 0}
        total = len(quizzes)
        correct = sum(1 for q in quizzes if q.get("is_correct", False))
        return {"total": total, "correct": correct, "accuracy": round(correct / total * 100, 1) if total > 0 else 0}

    @staticmethod
    async def get_classroom_report(db: AsyncSession, session_id: int, teacher_id: int) -> dict | None:
        """获取课堂报告"""
        result = await db.execute(
            select(ClassroomSession).where(
                ClassroomSession.id == session_id,
                ClassroomSession.teacher_id == teacher_id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        interaction_data = session.interaction_data or {}
        summary = PPTService._generate_classroom_summary(interaction_data)

        return {
            "session": {
                "id": session.id,
                "ppt_id": session.ppt_id,
                "title": session.title,
                "status": session.status,
                "current_page": session.current_page,
                "student_count": session.student_count,
                "interaction_data": interaction_data,
                "started_at": session.started_at.isoformat() if session.started_at else "",
                "ended_at": session.ended_at.isoformat() if session.ended_at else "",
            },
            "interaction_summary": summary,
            "page_stats": interaction_data.get("page_log", []),
        }

    @staticmethod
    async def list_classroom_sessions(
        db: AsyncSession, teacher_id: int,
        status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> dict:
        """获取课堂会话列表"""
        query = select(ClassroomSession).where(ClassroomSession.teacher_id == teacher_id)
        if status:
            query = query.where(ClassroomSession.status == status)
        query = query.order_by(desc(ClassroomSession.started_at))

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        sessions = result.scalars().all()

        items = []
        for s in sessions:
            items.append({
                "id": s.id,
                "ppt_id": s.ppt_id,
                "title": s.title,
                "status": s.status,
                "current_page": s.current_page,
                "student_count": s.student_count,
                "started_at": s.started_at.isoformat() if s.started_at else "",
                "ended_at": s.ended_at.isoformat() if s.ended_at else "",
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}


