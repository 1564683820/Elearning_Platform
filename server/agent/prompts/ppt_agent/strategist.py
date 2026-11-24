"""PPT Strategist — 设计总监角色，负责分析内容并推荐视觉方案

职责：
- 分析课程内容（课型、学科、年级、氛围）
- 推荐最优视觉风格（含候选方案）
- 生成设计规格书（design_spec）
- 生成执行锁定协议（spec_lock）
"""

# ─── 策略师系统提示词 ──────────────────────────────────────────────
STRATEGIST_SYSTEM_PROMPT = """[Role: PPT Design Strategist / 设计总监]

你是一位资深课程设计策略师。你的任务是分析教学内容，为每节课程推荐最优的视觉呈现方案。

## 你的输出

为每节课程输出一份设计规格书（design_spec），包含以下决策：

```json
{
  "design_spec": {
    "course_profile": {
      "title": "课程标题",
      "lesson_type": "new_lesson|review|exercise|conversation",
      "subject": "学科",
      "grade": "年级",
      "content_vibe": "structured|playful|serious|warm|tech|creative|data_driven|eastern"
    },
    "visual_style": {
      "primary": "swiss-minimal",
      "candidates": ["editorial", "warm-simple"],
      "rationale": "选择理由（1-2句）"
    },
    "color_scheme": {
      "primary": "#2B6CB0",
      "secondary": "#4A90D9",
      "accent": "#E53E3E",
      "background": "#FFFFFF",
      "text": "#1A202C",
      "mood": "professional-warm"
    },
    "typography": {
      "title_font_character": "clean geometric sans",
      "body_font_character": "neutral sans-serif",
      "title_size": 28,
      "body_size": 15
    },
    "layout_strategy": {
      "page_rhythm": ["breathing", "anchor", "breathing", "anchor", "highlight", "anchor", "highlight", "anchor"],
      "card_density": "medium",
      "decoration_level": "minimal"
    },
    "image_strategy": {
      "style": "none|sparse|supportive|core",
      "description": "图片策略说明"
    }
  }
}
```

## 视觉风格选择指南

### 按课型推荐
| 课型 | 首选风格 | 备选1 | 备选2 |
|-----|---------|------|------|
| 新授课 | swiss-minimal | editorial | blueprint |
| 少儿新授 | soft-rounded | sketch-notes | memphis |
| 复习课 | editorial | brutalist | ink-notes |
| 考前冲刺 | brutalist | data-journalism | swiss-minimal |
| 练习课 | data-journalism | swiss-minimal | editorial |
| 口语课 | soft-rounded | editorial | warm-simple |
| 听力课 | soft-rounded | editorial | warm-simple |

### 按学科推荐
| 学科 | 首选风格 | 备选1 | 备选2 |
|-----|---------|------|------|
| 英语 | swiss-minimal | editorial | soft-rounded |
| 语文 | ink-wash | editorial | vintage-poster |
| 古诗词 | ink-wash | vintage-poster | editorial |
| 数学 | data-journalism | blueprint | swiss-minimal |
| 物理 | blueprint | data-journalism | dark-tech |
| 化学 | blueprint | dark-tech | swiss-minimal |
| 生物 | photo-editorial | editorial | paper-cut |
| 历史 | vintage-poster | editorial | photo-editorial |
| 地理 | photo-editorial | vintage-poster | editorial |
| 美术 | memphis | zine | photo-editorial |
| 音乐 | editorial | vintage-poster | warm-simple |
| 编程 | dark-tech | pixel-art | blueprint |
| 德育 | warm-simple | paper-cut | editorial |
| 通用 | warm-simple | swiss-minimal | editorial |

### 按年级推荐
| 年级段 | 首选风格 | 特点 |
|-------|---------|------|
| 幼儿园 | soft-rounded | 圆润、大图标、色彩丰富 |
| 1-3年级 | soft-rounded / sketch-notes | 亲和、趣味、手绘感 |
| 4-6年级 | editorial / warm-simple | 过渡期、开始结构化 |
| 初中 | swiss-minimal / editorial | 严谨、清晰、专业 |
| 高中 | editorial / brutalist | 信息密度高、专业 |
| 成人 | swiss-minimal / editorial | 极简、专业 |

### 按内容氛围推荐
| 氛围 | 首选风格 | 关键特征 |
|-----|---------|---------|
| structured | swiss-minimal | 网格对齐、直角、清晰层级 |
| playful | memphis | 碰撞色、几何装饰、活泼 |
| serious | editorial | 杂志排版、衬线标题、克制 |
| warm | paper-cut | 层叠阴影、剪纸质感、温暖 |
| tech | dark-tech / glassmorphism | 暗色/玻璃、发光、科技感 |
| minimal | ink-notes | 手绘线稿、大面积留白 |
| classic | vintage-poster | 半色调、复古色板、海报感 |
| creative | zine | 套印偏移、拼贴、独立出版 |
| data_driven | data-journalism | 微型图表、多栏、数据标签 |
| eastern | ink-wash | 水墨渲染、印章红、宣纸底 |
| game | pixel-art | 像素网格、HUD栏、8-bit |

## 颜色方案生成规则

1. 主色（Primary）：从预设主题色板中选择，或根据学科/氛围推荐
2. 辅色（Secondary）：主色的邻近色或互补色的低饱和度版本
3. 强调色（Accent）：与主色形成对比（互补色或暖/冷对比），仅占3-5%
4. 背景色（Background）：浅色为主（#FFFFFF 或 #FAFAFA），深色风格除外
5. 文字色（Text）：深色（#1A202C 或 #2D3748）

### 预设学科色板
```python
SUBJECT_COLORS = {
    "english":    {"primary": "#2B6CB0", "secondary": "#63B3ED", "accent": "#E53E3E"},  # 蓝+红
    "chinese":    {"primary": "#8B4513", "secondary": "#D2691E", "accent": "#C41E3A"},  # 棕+红
    "math":       {"primary": "#2D3748", "secondary": "#4A5568", "accent": "#3182CE"},  # 灰+蓝
    "physics":    {"primary": "#1A365D", "secondary": "#2B6CB0", "accent": "#DD6B20"},  # 深蓝+橙
    "chemistry":  {"primary": "#22543D", "secondary": "#38A169", "accent": "#9B2C2C"},  # 绿+红
    "biology":    {"primary": "#276749", "secondary": "#48BB78", "accent": "#D69E2E"},  # 绿+金
    "history":    {"primary": "#744210", "secondary": "#B7791F", "accent": "#9B2C2C"},  # 棕+红
    "geography":  {"primary": "#2B6CB0", "secondary": "#48BB78", "accent": "#DD6B20"},  # 蓝+绿+橙
    "art":        {"primary": "#6B46C1", "secondary": "#ED64A6", "accent": "#F6E05E"},  # 紫+粉+黄
    "music":      {"primary": "#553C9A", "secondary": "#9F7AEA", "accent": "#ED8936"},  # 紫+橙
    "programming":{"primary": "#1A202C", "secondary": "#2D3748", "accent": "#38B2AC"},  # 暗色+青
    "moral":      {"primary": "#C53030", "secondary": "#FC8181", "accent": "#2B6CB0"},  # 红+蓝
    "general":    {"primary": "#2B6CB0", "secondary": "#63B3ED", "accent": "#ED8936"},  # 蓝+橙
}
```

## 字体配对规则

### 无衬线（Sans-serif）组
适合：结构化、现代、科技感场景
- 标题：几何无衬线（Montserrat, Futura, SCDream）
- 正文：人文无衬线（Inter, Noto Sans SC, Microsoft YaHei）

### 衬线（Serif）组
适合：经典、人文、阅读型场景
- 标题：优雅衬线（Georgia, Playfair Display, Source Han Serif SC）
- 正文：中性无衬线（Inter, SCDream, Microsoft YaHei）

### 手写（Hand-drawn）组
适合：亲和、创意、笔记型场景
- 标题：手写/书法（Caveat, Architects Daughter, KaiTi）
- 正文：清晰无衬线（Inter, Noto Sans SC, Microsoft YaHei）

### 等宽（Monospace）组
适合：技术、数据、工程场景
- 标题：等宽粗体（Courier New, Press Start 2P, Source Code Pro）
- 正文：中性无衬线（Inter, Microsoft YaHei）

## 页面节奏策略

根据幻灯片数量确定节奏模式：

```
3-5页:  [breathing, anchor, highlight, anchor, breathing]
6-8页:  [breathing, anchor, breathing, anchor, highlight, anchor, highlight, anchor]
9-12页: [breathing, anchor, breathing, anchor, highlight, anchor, breathing, anchor, highlight, anchor, highlight, anchor]
13+页:  [breathing, anchor, breathing, anchor, highlight, anchor, breathing, anchor, highlight, anchor, breathing, anchor, highlight, anchor, ...]
```

规则：
- 首尾必为 breathing（封面和总结留空间呼吸）
- 中间 anchor 和 highlight 交替
- 两个同类型页面不连续（避免疲劳）
- highlight 不超过总页数 30%

## 输出要求

1. 输出纯 JSON，不包含 markdown 代码块标记
2. 所有推荐必须有 rationale（理由）
3. candidates 提供 2 个备选方案
4. 颜色使用 hex 格式
5. 字体使用"字符特征"描述（如 "clean geometric sans"），而非具体字体名""""


# ─── 执行锁定协议模板 ──────────────────────────────────────────────
SPEC_LOCK_TEMPLATE = """# Design Spec Lock — {course_title}

> This is the execution contract. Do not deviate without explicit user approval.
> Generated by: PPT Strategist AI
> Date: {date}

## 1. Content Profile
- Course: {course_title}
- Type: {lesson_type_text}
- Subject: {subject}
- Grade: {grade}
- Vibe: {content_vibe}

## 2. Visual Style — {style_name} ({style_codename})
- Shape language: {shape_language}
- Decoration DNA: {decoration_dna}
- Card treatment: {card_treatment}
- Divider style: {divider_style}
- Shadow: {shadow}

## 3. Color Lock
```
Primary:    {primary_color}   → titles, top bars, accent markers
Secondary:  {secondary_color} → card borders, bg tones
Accent:     {accent_color}    → CTAs, interactive, warnings (≤10%)
Background: {bg_color}        → page canvas
Text:       {text_color}      → body copy
```

## 4. Typography Lock
```
Title:   {title_font_character} — {title_size}pt Bold
Body:    {body_font_character} — {body_size}pt Regular
Small:   {body_font_character} — {small_size}pt Regular
Tiny:    {body_font_character} — {tiny_size}pt Light
```

## 5. Page Rhythm
```
{page_rhythm_diagram}
```

## 6. Image Strategy
- Style: {image_style}
- Description: {image_description}

## 7. Constraints
- Card density: {card_density}
- Decoration level: {decoration_level}
- Max words per vocabulary slide: 8
- Max questions per practice slide: 4
- Text item max length: 80 chars
- Option max length: 40 chars

---
**LOCKED.** Executor must follow this spec. Any deviation requires user approval.
"""


# ─── 19种视觉风格完整映射 ──────────────────────────────────────────
VISUAL_STYLE_MAP = {
    "swiss-minimal": {
        "name": "瑞士极简",
        "shape_language": "sharp直角卡片，无圆角",
        "decoration_dna": "左侧色标(2px) + 实线分隔",
        "card_treatment": "直角 0px，扁平无阴影",
        "divider_style": "solid 实线",
        "shadow": "none",
        "title_font": "clean geometric sans",
        "body_font": "neutral sans-serif",
    },
    "soft-rounded": {
        "name": "圆润亲和",
        "shape_language": "大圆角卡片 12px",
        "decoration_dna": "顶部色条 + 背景装饰圆",
        "card_treatment": "圆角 12px，柔光投影",
        "divider_style": "solid 实线",
        "shadow": "soft",
        "title_font": "rounded friendly sans",
        "body_font": "neutral sans-serif",
    },
    "editorial": {
        "name": "杂志风格",
        "shape_language": "微圆角卡片 6px",
        "decoration_dna": "顶部色条 + 网格背景 + 左侧色标",
        "card_treatment": "圆角 6px，微投影",
        "divider_style": "dotted 点线",
        "shadow": "subtle",
        "title_font": "elegant serif",
        "body_font": "clean sans-serif",
    },
    "dark-tech": {
        "name": "暗色科技",
        "shape_language": "圆角卡片 8px",
        "decoration_dna": "发光顶部色条 + 径向渐变背景 + 左侧色标",
        "card_treatment": "圆角 8px，发光投影",
        "divider_style": "glow-dashed 发光虚线",
        "shadow": "glow-medium",
        "title_font": "modern geometric sans",
        "body_font": "lightweight sans",
    },
    "blueprint": {
        "name": "工程蓝图",
        "shape_language": "直角线框 0px",
        "decoration_dna": "网格线(20px) + 十字标节点 + 工程标记",
        "card_treatment": "直角 0px，线框无填充",
        "divider_style": "engineering-dashed 工程虚线",
        "shadow": "none",
        "title_font": "monospace technical",
        "body_font": "neutral sans-serif",
    },
    "brutalist": {
        "name": "粗野主义",
        "shape_language": "直角规则线框 0px",
        "decoration_dna": "粗黑边框(2px) + 规则线",
        "card_treatment": "直角 0px，粗线框包围",
        "divider_style": "heavy-solid 粗实线 2px",
        "shadow": "none",
        "title_font": "bold display sans",
        "body_font": "monospace condensed",
    },
    "data-journalism": {
        "name": "数据新闻",
        "shape_language": "微圆角 2px",
        "decoration_dna": "微型图表线 + 竖线栏间分隔",
        "card_treatment": "微圆角 2px，无投影",
        "divider_style": "hairline 极细线 1px",
        "shadow": "none",
        "title_font": "elegant serif",
        "body_font": "lightweight sans",
    },
    "photo-editorial": {
        "name": "摄影杂志",
        "shape_language": "全出血大图 0px",
        "decoration_dna": "极细规则线 + 图注编号",
        "card_treatment": "无边距，文字浮图",
        "divider_style": "hairline 极细线 0.5px",
        "shadow": "none",
        "title_font": "editorial serif",
        "body_font": "clean sans-serif",
    },
    "memphis": {
        "name": "孟菲斯",
        "shape_language": "圆角 4-6px，粗黑轮廓",
        "decoration_dna": "波尔卡圆点 + 几何撒点 + 锯齿线",
        "card_treatment": "圆角 4-6px，粗黑轮廓",
        "divider_style": "wavy-dashed 锯齿虚线",
        "shadow": "none",
        "title_font": "bold display black",
        "body_font": "rounded friendly sans",
    },
    "zine": {
        "name": "独立杂志",
        "shape_language": "直角/微圆角 0-2px",
        "decoration_dna": "套印偏移(2-4px) + 拼贴边框",
        "card_treatment": "直角 0-2px，套印效果",
        "divider_style": "offset-double 偏移双线",
        "shadow": "none",
        "title_font": "bold condensed sans",
        "body_font": "monospace typewriter",
    },
    "vintage-poster": {
        "name": "复古海报",
        "shape_language": "直角色块 0px",
        "decoration_dna": "半色调网点 + 放射线 + 大色块",
        "card_treatment": "直角 0px，丝网印刷质感",
        "divider_style": "vintage-double 复古双线",
        "shadow": "none",
        "title_font": "classic serif display",
        "body_font": "geometric sans",
    },
    "paper-cut": {
        "name": "剪纸风格",
        "shape_language": "不规则剪边 4px圆角",
        "decoration_dna": "层叠阴影(8-12%) + 剪纸图案",
        "card_treatment": "圆角 4px，层叠投影",
        "divider_style": "craft-dotted 工艺点线",
        "shadow": "layered-drop",
        "title_font": "warm rounded sans",
        "body_font": "warm rounded sans",
    },
    "sketch-notes": {
        "name": "手绘风格",
        "shape_language": "无边框自由布局 0px",
        "decoration_dna": "网格纸背景 + 波浪分隔 + 涂鸦标记",
        "card_treatment": "无边框，网格纸背景",
        "divider_style": "wavy-dashed 波浪虚线",
        "shadow": "none",
        "title_font": "hand-lettered casual",
        "body_font": "neutral sans-serif",
    },
    "ink-notes": {
        "name": "墨迹笔记",
        "shape_language": "手绘线框 0px",
        "decoration_dna": "墨点标记 + 语义色彩(≤10%) + 手绘线",
        "card_treatment": "手绘线框，大面积留白",
        "divider_style": "sketch-dashed 手绘虚线",
        "shadow": "none",
        "title_font": "humanist hand-lettered",
        "body_font": "clean sans-serif",
    },
    "chalkboard": {
        "name": "黑板风格",
        "shape_language": "圆角卡片 6px",
        "decoration_dna": "左侧色标 + 虚线分隔 + 粉笔纹理",
        "card_treatment": "圆角 6px，微投影",
        "divider_style": "dashed 虚线 2px",
        "shadow": "subtle",
        "title_font": "clean sans-serif",
        "body_font": "neutral sans-serif",
    },
    "ink-wash": {
        "name": "水墨风格",
        "shape_language": "微圆角 4px，含蓄东方感",
        "decoration_dna": "水墨渲染 + 印章红点缀 + 宣纸纹理",
        "card_treatment": "圆角 4px，无投影",
        "divider_style": "wash-line 水墨渲染线",
        "shadow": "none",
        "title_font": "classic serif (Song/Hei)",
        "body_font": "classic serif",
    },
    "pixel-art": {
        "name": "像素艺术",
        "shape_language": "像素锯齿边缘 0px",
        "decoration_dna": "HUD状态栏 + 像素网格(8px) + 精灵图标",
        "card_treatment": "像素锯齿边框，无投影",
        "divider_style": "pixel-step 像素阶梯线",
        "shadow": "none",
        "title_font": "pixel bitmap display",
        "body_font": "clean sans-serif",
    },
    "warm-simple": {
        "name": "温暖简洁",
        "shape_language": "圆角卡片 8px",
        "decoration_dna": "顶部色条 + 背景装饰圆 + 左侧色标",
        "card_treatment": "圆角 8px，微投影",
        "divider_style": "solid 实线",
        "shadow": "light",
        "title_font": "clean sans-serif",
        "body_font": "neutral sans-serif",
    },
    "glassmorphism": {
        "name": "玻璃拟态",
        "shape_language": "大圆角透明面板 12-20px",
        "decoration_dna": "径向发光 + 玻璃边缘高光 + 多层透明",
        "card_treatment": "圆角 12-20px，明亮边缘",
        "divider_style": "glass-edge 玻璃边缘",
        "shadow": "glow-layered",
        "title_font": "modern lightweight sans",
        "body_font": "lightweight sans",
    },
}


# ─── 风格选择函数 ──────────────────────────────────────────────────
def recommend_style(
    lesson_type: str = "",
    subject: str = "",
    grade: str = "",
    content_vibe: str = "",
) -> dict:
    """根据课程参数推荐视觉风格

    返回包含首选和备选风格的字典。
    """
    # 课型 → 风格映射
    lesson_type_styles = {
        "new_lesson":    ["swiss-minimal", "editorial", "blueprint"],
        "review":        ["editorial", "brutalist", "ink-notes"],
        "exercise":      ["data-journalism", "swiss-minimal", "editorial"],
        "conversation":  ["soft-rounded", "editorial", "warm-simple"],
    }

    # 学科 → 风格映射
    subject_styles = {
        "english":       ["swiss-minimal", "editorial", "soft-rounded"],
        "chinese":       ["ink-wash", "editorial", "vintage-poster"],
        "math":          ["data-journalism", "blueprint", "swiss-minimal"],
        "physics":       ["blueprint", "data-journalism", "dark-tech"],
        "chemistry":     ["blueprint", "dark-tech", "swiss-minimal"],
        "biology":       ["photo-editorial", "editorial", "paper-cut"],
        "history":       ["vintage-poster", "editorial", "photo-editorial"],
        "geography":     ["photo-editorial", "vintage-poster", "editorial"],
        "art":           ["memphis", "zine", "photo-editorial"],
        "music":         ["editorial", "vintage-poster", "warm-simple"],
        "programming":   ["dark-tech", "pixel-art", "blueprint"],
        "moral":         ["warm-simple", "paper-cut", "editorial"],
        "general":       ["warm-simple", "swiss-minimal", "editorial"],
    }

    # 年级 → 风格映射
    grade_styles = {
        "preschool":     ["soft-rounded", "sketch-notes", "memphis"],
        "grade1-3":      ["soft-rounded", "sketch-notes", "paper-cut"],
        "grade4-6":      ["editorial", "warm-simple", "soft-rounded"],
        "middle_school": ["swiss-minimal", "editorial", "data-journalism"],
        "high_school":   ["editorial", "brutalist", "swiss-minimal"],
        "college":       ["editorial", "swiss-minimal", "data-journalism"],
        "adult":         ["swiss-minimal", "editorial", "warm-simple"],
    }

    # 氛围 → 风格映射
    vibe_styles = {
        "structured":    ["swiss-minimal", "editorial", "blueprint"],
        "playful":       ["memphis", "soft-rounded", "pixel-art"],
        "serious":       ["editorial", "swiss-minimal", "brutalist"],
        "warm":          ["paper-cut", "warm-simple", "soft-rounded"],
        "tech":          ["dark-tech", "glassmorphism", "blueprint"],
        "minimal":       ["ink-notes", "swiss-minimal", "sketch-notes"],
        "classic":       ["vintage-poster", "editorial", "ink-wash"],
        "creative":      ["zine", "memphis", "sketch-notes"],
        "data_driven":   ["data-journalism", "blueprint", "swiss-minimal"],
        "eastern":       ["ink-wash", "vintage-poster", "editorial"],
        "game":          ["pixel-art", "memphis", "chalkboard"],
        "engineering":   ["blueprint", "dark-tech", "swiss-minimal"],
        "photo_rich":     ["photo-editorial", "editorial", "vintage-poster"],
        "info_dense":    ["brutalist", "data-journalism", "editorial"],
        "modern_tech":   ["glassmorphism", "dark-tech", "swiss-minimal"],
        "sketch":        ["sketch-notes", "ink-notes", "chalkboard"],
        "classroom":     ["chalkboard", "warm-simple", "editorial"],
    }

    # 收集所有候选
    candidates = []
    sources = {}

    if lesson_type and lesson_type in lesson_type_styles:
        for s in lesson_type_styles[lesson_type]:
            if s not in sources:
                sources[s] = 0
            sources[s] += 3  # 课型权重最高
    if subject and subject in subject_styles:
        for s in subject_styles[subject]:
            if s not in sources:
                sources[s] = 0
            sources[s] += 2  # 学科权重次之
    if grade and grade in grade_styles:
        for s in grade_styles[grade]:
            if s not in sources:
                sources[s] = 0
            sources[s] += 2  # 年级权重
    if content_vibe and content_vibe in vibe_styles:
        for s in vibe_styles[content_vibe]:
            if s not in sources:
                sources[s] = 0
            sources[s] += 1  # 氛围辅助

    # 如果没有匹配，用默认
    if not sources:
        return {
            "primary": "warm-simple",
            "candidates": ["swiss-minimal", "editorial"],
            "rationale": "默认通用风格，适用于未指定场景",
        }

    # 按得分排序
    ranked = sorted(sources.items(), key=lambda x: -x[1])

    primary = ranked[0][0]
    candidates_list = [s for s, _ in ranked[1:4] if s != primary][:2]
    if not candidates_list:
        candidates_list = ["editorial", "warm-simple"]

    return {
        "primary": primary,
        "candidates": candidates_list,
        "rationale": f"综合课型、学科、年级推荐，得分最高为 {VISUAL_STYLE_MAP[primary]['name']}",
    }
