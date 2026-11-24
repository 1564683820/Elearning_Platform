"""PPT Agent — Teacher-side PPT courseware generation

Responsibilities:
- Knowledge graph AI generation (Stage 1)
- Knowledge graph -> PPT slides AI generation (Stage 2)
- PPT template and prompt management
- PPTX export (via Node.js pptxgenjs subprocess)

Related services (CRUD + DB in original):
- app.services.ppt_service.PPTService
- app.services.knowledge_graph_service.KnowledgeGraphService
"""

import json
import re
import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from agent.agents.base import BaseAgent
from agent.prompts.ppt_agent.lesson_templates import LESSON_TEMPLATES, GENERATE_SYSTEM_PROMPT
from app.services.ai_service import AIService


LESSON_TYPE_NAMES = {
    "new_lesson": "\u65b0\u6388\u8bfe",
    "review": "\u590d\u4e60\u8bfe",
    "exercise": "\u7ec3\u4e60\u8bfe",
    "conversation": "\u53e3\u8bed\u8bfe",
}

KG_GENERATE_SYSTEM_PROMPT = """You are a curriculum design AI. Based on the course information entered by the teacher, generate a structured knowledge graph.
Output strictly in pure JSON format, do not include markdown code block markers or any extra text.

Output format:
{
  "sections": [
    {
      "title": "Section title",
      "order": 1,
      "children": [
        {
          "title": "Knowledge point title",
          "order": 1,
          "description": "Core content description (optional)",
          "suggested_page_type": "objective|vocabulary|grammar|dialogue|practice|interactive|summary|listening|speaking"
        }
      ]
    }
  ]
}

Design principles:
1. Each section is an independent module, knowledge points can be displayed on separate pages
2. If the teacher has supplementary notes, fully consider the supplementary content
3. The number of knowledge points should be moderate with logical progression
4. Adjust the focus according to the lesson type"""

PPT_FROM_KG_USER_PROMPT_TEMPLATE = """Please generate PPT slide content for a {lesson_type_name} course.

Course title: {title}
Subject: {subject}
Grade: {grade}

The following is the confirmed knowledge graph structure. Please generate 1-2 slides for each knowledge point strictly following the section and knowledge point order in the graph.
Use the suggested_page_type for each page when possible.

Knowledge graph structure:
{sections_str}

{knowledge_points_constraint}

Generation rules:
1. First page is a title cover page, last page is a summary page
2. Each knowledge point has 1-2 slides, strictly following the graph order
3. Practice pages include specific questions and answer explanations
4. Vocabulary pages show phonetic symbols, definitions, and example sentences
5. Dialogue pages provide real-life scenario conversations
6. Grammar pages display rules, example sentences, and explanations
7. Output a valid JSON array, no extra text

IMPORTANT — JSON format (ALL content fields MUST be inside the "content" object):
{{
  "type": "slide type string",
  "title": "page title",
  "content": {{
    "words": [],
    "items": [],
    "dialogues": [],
    "points": [],
    "questions": [],
    "key_points": [],
    "audio_text": "",
    "text": ""
  }}
}}
For the title page, put main_title, subtitle, grade inside "content".
For summary, put key_points and homework inside "content".
NEVER put content fields at the top level of the slide object."""

# ─── PPT 设计系统 Skill（增强版 — Strategist 级设计指导） ────────────
PPT_DESIGN_SYSTEM_SKILL = """[PPT Design System — Strategist-Level Visual Design Guide]

## PART 0: DESIGN PHILOSOPHY

You are the Design Director for this courseware. Every decision you make serves pedagogy:
1. **Content First** — Form follows function. Design amplifies learning, never distracts.
2. **Rhythm Over Uniformity** — Alternate anchor pages (dense), breathing pages (sparse), and highlight pages (hero).
3. **Signal Through Restraint** — Color carries semantic meaning: red=error/danger, green=correct/success, blue=structure/info, orange=warning/attention.
4. **Progressive Disclosure** — One primary takeaway per slide. Complexity revealed step by step.
5. **Typography = Hierarchy** — Size + weight + spacing = structure without extra UI.

## PART 1: SLIDE ARCHITECTURE (16:9, 10" × 5.625")

### Canvas Grid
- Margin: 0.5" all sides → Content area: 9" × 4.625"
- Title zone: top 0.9" reserved for slide title + top accent bar
- Content zone: remaining 3.2" for primary content
- Footer zone: bottom 0.3" for page number / branding

### Visual Style Selection (19 styles available — see visual_styles/_index.md)

Choose the appropriate visual style based on:
- **Lesson type** (new_lesson, review, exercise, conversation)
- **Subject** (english, chinese, math, physics, history, art, etc.)
- **Grade level** (preschool, primary, middle, high, college)
- **Content vibe** (structured, playful, serious, warm, tech, creative)

### Key Style Properties (apply per selected style):

| Style Element | Options | Usage |
|--------------|---------|-------|
| **Card corners** | 0px (sharp) / 2-8px (rounded) / 12-20px (pill) | Determined by style |
| **Top bar** | present / absent / heavy / glow / wavy | Style DNA |
| **Left accent** | vertical bar / dot / block / circle / crosshair | Title marker |
| **Background** | plain / grid / radial-glow / wash / dots / sunburst | Atmosphere |
| **Divider** | solid / dashed / dotted / double / glow / sketch | Separator type |
| **Shadow** | none / subtle / medium / layered | Depth layer |

### Page Rhythm Pattern
```
Page 1 (Title)    → Breathing  (bold, spacious, visual)
Page 2 (Catalog)  → Anchor      (structured, numbered, clear)
Page 3 (Objective)→ Breathing   (icon-led, airy, motivational)
Page 4 (Content)  → Anchor      (vocabulary/grammar — information-dense)
Page 5 (Content)  → Anchor      (continue knowledge delivery)
Page 6 (Practice) → Highlight   (interactive, engaging)
Page 7 (Content)  → Anchor      (dialogue/listening)
Page 8 (Activity) → Highlight   (interactive/game/ai)
Page N (Summary)  → Anchor      (recap, structured closure)
```

Alternate densities — never place two Anchor pages of the same density back-to-back.

## PART 2: CARD-BASED COMPONENT SYSTEM

### Title (Cover) Page
- Full-width gradient background or hero image area
- Large decorative elements (circles, shapes at low opacity)
- Course title: 32pt bold, centered or left-aligned
- Subtitle + grade: 16pt, below title, lighter weight

### Objective Page
- Numbered circle/icon indicators (1-6)
- Each objective: icon + text, evenly spaced
- Icons: target, book, speak, write, think, star
- Max 6 items, each ≤60 chars

### Vocabulary Page
- Card grid: 2 columns × 4 rows = 8 cards max
- Each card: accent top-bar + word(bold) + phonetic(italic) + definition + example
- Card width ~4.2", height auto-adjust
- Max 8 words per page

### Dialogue Page
- L/R speech bubbles with color-coded sides
- Speaker A (left): light accent background
- Speaker B (right): primary-tinted background
- Max 6 exchanges per page

### Grammar Page
- Rule cards with warm border accent
- Pattern: Formula (bold) → Example (italic) → Explanation (small)
- 2-4 rules per page
- Each rule: title bar + content area

### Practice Page
- Question cards with show/hide answer
- Options: A/B/C/D in 2×2 grid
- Correct answer highlighted after interaction
- Max 4 questions per page

### Interactive / Activity Page
- Activity badge (top-right corner)
- Numbered step list: 1 → 2 → 3 → 4 → 5
- Duration indicator
- Max 5 steps per page

### Summary Page
- Dot-point key points list (max 7)
- Optional homework card (highlighted, bottom section)
- Each point ≤50 chars

### Listening Page
- Audio player area (top) with play button
- Audio text display (50-150 words)
- Questions below (2-3)
- Chinese subtitle/translation

### Speaking Page
- Microphone icon (large, centered top)
- Read-aloud text (30-80 words, centered)
- Chinese translation below
- Pronunciation tips (bottom)

## PART 3: COLOR DISCIPLINE

### Semantic Color Map
```
PRIMARY     → Titles, top bars, accent markers, key highlights
SECONDARY   → Card borders, secondary emphasis, background tones
ACCENT      → Call-to-action, interactive elements, warnings (≤10% of canvas)
SUCCESS     → Correct answers, positive feedback (green tones)
ERROR       → Incorrect answers, important warnings (red tones)
BACKGROUND  → Page background — light for most styles, dark for dark-tech
TEXT        → Body text — dark-on-light for readability
```

### Color Usage Ratios
```
Background:     60-70%  (canvas fill)
Primary:        15-20%  (structural elements)
Secondary:      8-12%   (supporting visual elements)
Accent:         3-5%    (emphasis points only)
```

Never use more than 4 distinct colors on a single slide. The background doesn't count.

## PART 4: TYPOGRAPHY SYSTEM

### Hierarchy Scale
```
H1 (Slide Title):   26-28pt  Bold      # Title of each slide
H2 (Section Head):  20-22pt  SemiBold  # Section labels within slides
Body:               14-15pt  Regular   # Main content text
Small:              11-12pt  Regular   # Secondary info, captions
Tiny:               9-10pt   Light     # Footnotes, page numbers
```

### Font Pairing by Style
| Style Group | Title Font Character | Body Font Character |
|------------|---------------------|-------------------|
| Corporate (swiss, soft, blueprint, brutalist) | Clean geometric sans | Neutral sans-serif |
| Editorial (editorial, photo, data) | Elegant serif | Clean sans-serif |
| Expressive (memphis, zine, vintage) | Bold display | Readable sans/slab |
| Hand-drawn (sketch, ink-notes, chalkboard) | Cursive/hand-lettered | Legible sans |
| Eastern (ink-wash) | Serif (Song/Hei style) | Serif |
| Tech (dark-tech, glassmorphism) | Modern geometric sans | Lightweight sans |
| Specialty (pixel-art, paper-cut) | Themed display (pixel/rounded) | Clean sans |

### Spacing Rules
- Line height: 1.5-1.8 for body text (readability)
- Letter spacing: 0 for body, +0.5px for titles
- Paragraph spacing: 1.5× line height between paragraphs
- Card padding: 12-16px internal, 8-14px between cards

## PART 5: DECORATION RULES

### When to Decorate
- Title/cover pages: YES — atmosphere-setting elements
- Content pages: MINIMAL — accent bars and structural dividers only
- Practice pages: MINIMAL — focus on question content
- Summary pages: STRUCTURAL — clear hierarchy through spacing

### Decoration Types by Style
```
swiss-minimal:    left-accent-bar + solid divider
soft-rounded:     top-color-bar + background circles
editorial:        top-bar + grid-bg + left-accent
dark-tech:        glow-radial + glow-dividers
blueprint:        crosshair-node + engineering-grid
brutalist:        heavy-black-border + ruled-lines
data-journalism:  micro-chart-lines + column-rules
photo-editorial:  none — image IS the decoration
memphis:          polka-dots + geometric-shapes + bold-outlines
zine:             offset-overprint + collage-borders
vintage-poster:   halftone-dots + sunburst + thick-borders
paper-cut:        layered-shadows + cut-out-shapes
sketch-notes:     grid-paper + wavy-dividers
ink-notes:        hand-drawn-lines + ink-dots (sparse)
chalkboard:       chalk-dust + dashed-lines
ink-wash:         wash-gradient + seal-stamp
pixel-art:        pixel-grid + HUD-bar
warm-simple:      top-bar + background-circle (safe default)
glassmorphism:    radial-bloom + glass-edge-highlight
```

## PART 6: CONTENT QUALITY CHECKLIST

Before finalizing each slide, verify:
[ ] ONE primary message per slide
[ ] Content fits within density limits (words ≤8, questions ≤4, etc.)
[ ] All text within character limits (items ≤80, options ≤40)
[ ] Knowledge points are all covered, no fabricated content
[ ] Visual hierarchy is clear (Title → Subtitle → Body → Caption)
[ ] Color usage is semantic, not decorative
[ ] Page rhythm alternates: anchor → breathing → highlight
[ ] Student can scan and understand the page in ≤5 seconds"""


class PPTAgent(BaseAgent):

    """PPT lesson preparation Agent - knowledge graph generation and PPT slide generation"""

    @staticmethod
    def _get_lesson_type_name(lesson_type: str) -> str:
        return LESSON_TYPE_NAMES.get(lesson_type, lesson_type)

    @staticmethod
    def _generate_node_id(prefix: str = "node") -> str:
        return "{}-{}".format(prefix, uuid.uuid4().hex[:8])

    @staticmethod
    def _generate_section_id() -> str:
        return PPTAgent._generate_node_id("sec")

    @staticmethod
    def _parse_kg_json(text: str) -> list:
        """Parse AI knowledge graph JSON, return sections list"""
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            raise ValueError("AI response does not contain valid JSON")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            cleaned = re.sub(r'^```(?:json)?\s*', '', text)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if not json_match:
                raise ValueError("AI JSON parse failed")
            data = json.loads(json_match.group())

        sections = data.get("sections", [])
        if not isinstance(sections, list) or not sections:
            raise ValueError("AI returned empty or invalid sections")

        validated = []
        for sec in sections:
            children = []
            for child in sec.get("children", []):
                children.append({
                    "id": child.get("id") or PPTAgent._generate_node_id(),
                    "title": child.get("title", ""),
                    "description": child.get("description", ""),
                    "order": child.get("order", len(children) + 1),
                    "suggested_page_type": child.get("suggested_page_type", ""),
                })
            validated.append({
                "id": sec.get("id") or PPTAgent._generate_section_id(),
                "title": sec.get("title", ""),
                "order": sec.get("order", len(validated) + 1),
                "children": children,
            })
        return validated

    @staticmethod
    async def generate_graph_content(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        supplement: str = "",
    ) -> str:
        """Call AI to generate knowledge graph content. Returns raw AI response text."""
        type_name = PPTAgent._get_lesson_type_name(lesson_type)
        supplement_text = "\n\u8865\u5145\u8bf4\u660e: " + supplement if supplement else ""

        user_prompt = """Please design a knowledge graph for the following course:

Course Title: {title}
Lesson Type: {type_name}
Subject: {subject or title}
Grade: {grade or 'Not specified'}{supplement_text}

Expected number of sections: 4
Expected knowledge points per section: 3""".format(
            title=title,
            type_name=type_name,
            subject=subject or title,
            grade=grade or "\u672a\u6307\u5b9a",
            supplement_text=supplement_text,
        )

        result_text = await AIService.chat_completion(
            db=db,
            messages=[
                {"role": "system", "content": KG_GENERATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            user_id=teacher_id,
            key_type="llm",
        )
        return result_text

    @staticmethod
    async def generate_ppt_content(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str,
        grade: str,
        sections: list,
        knowledge_points: list[str] | None = None,
    ) -> str:
        """Call AI to generate PPT slides from a knowledge graph. Returns raw AI response text.

        If knowledge_points is not provided, extracts them from sections' children titles.
        """
        type_name = PPTAgent._get_lesson_type_name(lesson_type)
        sections_str_parts = []
        for sec in sections:
            parts = ["Section {order}: {title}".format(
                order=sec.get('order', 0),
                title=sec.get('title', '')
            )]
            for child in sec.get("children", []):
                parts.append(
                    "  - Knowledge point {order}: {title} (recommended page type: {ptype})".format(
                        order=child.get('order', 0),
                        title=child.get('title', ''),
                        ptype=child.get('suggested_page_type', '\u672a\u6307\u5b9a'),
                    )
                )
            sections_str_parts.append("\n".join(parts))
        sections_str = "\n\n".join(sections_str_parts)

        # 从 sections 提取知识点标题构建强约束
        if not knowledge_points:
            knowledge_points = []
            for sec in sections:
                for child in sec.get("children", []):
                    kp = child.get("title", "").strip()
                    if kp:
                        knowledge_points.append(kp)

        if knowledge_points:
            kp_lines = "\n".join(f"  [{i+1}] {kp}" for i, kp in enumerate(knowledge_points))
            knowledge_points_constraint = f"""========== 知识点内容强制约束（严格遵循） ==========
以下知识图谱中定义了具体的知识点。所有幻灯片的内容必须严格遵循这些知识点：

用户指定的知识点（必须使用以下精确的内容）：
{kp_lines}

强制规则（优先级高于所有其他指示）：
1. 词汇页 (vocabulary) — 所有单词必须来自以上知识点，不得添加无关单词
2. 语法页 (grammar) — 必须讲解以上列出的语法点，不得讲授其他语法
3. 对话页 (dialogue) — 对话内容必须使用以上知识点中的词汇/句型
4. 练习页 (practice) — 所有题目必须围绕以上知识点
5. 听力页 (listening) — 听力文本必须包含以上知识点中的词汇/句型
6. 口语页 (speaking) — 跟读文本必须围绕以上知识点中的主题/句型
7. 目标页 (objective) — 学习目标必须紧扣以上知识点
8. 互动页 (interactive/ai_interaction) — 活动内容必须基于以上知识点设计
9. 总结页 (summary) — 总结要点必须覆盖以上所有知识点
10. 严禁编造以上知识点之外的新词汇、新语法、新内容
11. 每个知识点必须在至少一页幻灯片中出现，不可遗漏任何一个知识点"""
        else:
            knowledge_points_constraint = ""

        user_prompt = PPT_FROM_KG_USER_PROMPT_TEMPLATE.format(
            lesson_type_name=type_name,
            title=title,
            subject=subject or title,
            grade=grade or "\u672a\u6307\u5b9a",
            sections_str=sections_str,
            knowledge_points_constraint=knowledge_points_constraint,
        )

        # 注入设计系统 skill 作为系统级约束
        system_prompt = GENERATE_SYSTEM_PROMPT + "\n\n" + PPT_DESIGN_SYSTEM_SKILL

        result_text = await AIService.chat_completion(
            db=db,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            user_id=teacher_id,
            key_type="llm",
        )
        return result_text

    async def run(self, **kwargs) -> dict:
        """Execute PPT generation or export. Delegates to the static methods above."""
        action = kwargs.get("action", "generate_graph")
        if action == "generate_graph":
            text = await self.generate_graph_content(**kwargs)
            return {"sections": self._parse_kg_json(text)}
        elif action == "generate_ppt":
            text = await self.generate_ppt_content(**kwargs)
            return {"pages": json.loads(text)} if text else {"pages": []}
        raise ValueError("Unknown action: {}".format(action))
