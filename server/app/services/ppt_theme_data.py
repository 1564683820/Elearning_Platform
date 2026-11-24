"""内置 9 套教学主题 CSS 数据 + 设计规范 (Style as Skill)"""

# ========== 风格技能设计规范 ==========
# 每个主题的 style_skill 包含配色/排版/布局/动画/禁忌等完整设计指导
# 用于 AI 生成内容时注入提示词，以及渲染时选择合适的布局和动画

_THEME_STYLE_SKILLS = {
    "classic": {
        "color_scheme": {"primary": "#2d7d46", "primary_light": "#e8f5e9", "primary_dark": "#1b5e20",
                         "accent": "#1565c0", "accent_light": "#e3f2fd", "bg": "#ffffff",
                         "text": "#2c3e50", "text_secondary": "#546e7a", "border": "#e0e0e0"},
        "typography": {"title_font": "PingFang SC, Microsoft YaHei", "title_weight": 800,
                       "title_size": "2.8vw-3.2vw", "title_spacing": "-0.02em",
                       "body_font": "PingFang SC, Microsoft YaHei", "body_weight": 400,
                       "body_size": "1.4vw-1.6vw", "line_height": 1.7},
        "layout_rules": {"card_style": "bordered", "header_style": "left-border", "corner_radius": "12px",
                         "spacing": "generous", "prefer_grid": False, "max_items_per_page": 6},
        "recommended_animations": {"transition": "slide", "duration": 400, "entrance": "fade-up",
                                   "stagger": 0.05, "emphasis": "pulse"},
        "anti_patterns": ["不要使用荧光色", "不要使用超过3列布局", "不要在深色背景使用灰色文字",
                         "标题不要超过两行", "对话框不要混用太多说话人颜色",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["小学课堂", "日常教学", "各学段通用"],
    },
    "cartoon": {
        "color_scheme": {"primary": "#ff7043", "primary_light": "#fff3e0", "primary_dark": "#e64a19",
                         "accent": "#42a5f5", "accent_light": "#e3f2fd", "bg": "#fff8e1",
                         "text": "#4e342e", "text_secondary": "#8d6e63", "border": "#ffccbc"},
        "typography": {"title_font": "Comic Sans MS, PingFang SC", "title_weight": 900,
                       "title_size": "2.8vw-3.4vw", "title_spacing": "0",
                       "body_font": "Comic Sans MS, PingFang SC", "body_weight": 400,
                       "body_size": "1.6vw-1.8vw", "line_height": 1.8},
        "layout_rules": {"card_style": "rounded", "header_style": "centered-full", "corner_radius": "20px",
                         "spacing": "loose", "prefer_grid": True, "max_items_per_page": 5},
        "recommended_animations": {"transition": "push", "duration": 450, "entrance": "scale-in",
                                   "stagger": 0.08, "emphasis": "grow-shrink"},
        "anti_patterns": ["不要使用衬线字体", "不要使用深色背景", "不要在绿色背景上用红色文字",
                         "文字密度不要过高", "不要使用专业性太强的术语",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["小学低年级", "幼儿启蒙", "趣味教学"],
    },
    "academic": {
        "color_scheme": {"primary": "#1976d2", "primary_light": "#e3f2fd", "primary_dark": "#0d47a1",
                         "accent": "#388e3c", "accent_light": "#e8f5e9", "bg": "#f5f7fa",
                         "text": "#2c3e50", "text_secondary": "#546e7a", "border": "#cfd8dc"},
        "typography": {"title_font": "PingFang SC, Microsoft YaHei", "title_weight": 700,
                       "title_size": "2.2vw-2.8vw", "title_spacing": "0",
                       "body_font": "PingFang SC, Microsoft YaHei", "body_weight": 400,
                       "body_size": "1.3vw-1.5vw", "line_height": 1.7},
        "layout_rules": {"card_style": "flat", "header_style": "full-bg", "corner_radius": "8px",
                         "spacing": "medium", "prefer_grid": False, "max_items_per_page": 6},
        "recommended_animations": {"transition": "slide", "duration": 380, "entrance": "fade-up",
                                   "stagger": 0.04, "emphasis": "pulse"},
        "anti_patterns": ["不要使用过于幼稚的装饰", "不要超过4列布局",
                         "语法页不要用表格代替列表", "练习页不要只放一道题",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["初中课堂", "主题教学", "系统性讲解"],
    },
    "senior": {
        "color_scheme": {"primary": "#37474f", "primary_light": "#eceff1", "primary_dark": "#1a237e",
                         "accent": "#d32f2f", "accent_light": "#ffebee", "bg": "#ffffff",
                         "text": "#263238", "text_secondary": "#546e7a", "border": "#cfd8dc"},
        "typography": {"title_font": "Noto Sans SC, PingFang SC", "title_weight": 800,
                       "title_size": "2.0vw-2.6vw", "title_spacing": "-0.5px",
                       "body_font": "Noto Sans SC, PingFang SC", "body_weight": 400,
                       "body_size": "1.2vw-1.4vw", "line_height": 1.8},
        "layout_rules": {"card_style": "minimal", "header_style": "left-border",
                         "corner_radius": "4px", "spacing": "compact",
                         "prefer_grid": False, "max_items_per_page": 8},
        "recommended_animations": {"transition": "fade", "duration": 350, "entrance": "fade",
                                   "stagger": 0.03, "emphasis": "pulse"},
        "anti_patterns": ["严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替", "不要用卡通字体", "不要用渐变背景",
                         "词汇页不要少于6个词", "内容不要太稀松"],
        "best_for": ["高中课堂", "雅思备考", "学术英语"],
    },
    "blackboard": {
        "color_scheme": {"primary": "#a5d6a7", "primary_light": "#4caf50", "primary_dark": "#1b5e20",
                         "accent": "#fff176", "accent_light": "#ffee58", "bg": "#2e7d32",
                         "text": "#ffffff", "text_secondary": "#e8f5e9", "border": "#4caf50"},
        "typography": {"title_font": "Ma Shan Zheng, KaiTi, STKaiti", "title_weight": 700,
                       "title_size": "2.8vw-3.2vw", "title_spacing": "0.02em",
                       "body_font": "KaiTi, STKaiti, PingFang SC", "body_weight": 400,
                       "body_size": "1.6vw-1.8vw", "line_height": 1.8},
        "layout_rules": {"card_style": "chalk-border", "header_style": "underline",
                         "corner_radius": "0px", "spacing": "generous",
                         "prefer_grid": False, "max_items_per_page": 5},
        "recommended_animations": {"transition": "push", "duration": 500, "entrance": "fade-up",
                                   "stagger": 0.06, "emphasis": "pulse"},
        "anti_patterns": ["不要使用彩色背景", "不要使用圆角卡片", "不要使用现代简约风排版",
                         "文字不要太小（至少1.6vw）", "不要用衬线标题字体",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["传统课堂氛围", "古诗词教学", "文学赏析"],
    },
    "warm": {
        "color_scheme": {"primary": "#ff7043", "primary_light": "#fff3e0", "primary_dark": "#bf360c",
                         "accent": "#ec407a", "accent_light": "#fce4ec",
                         "bg": "linear-gradient(135deg,#fff3e0,#fce4ec)",
                         "text": "#4e342e", "text_secondary": "#8d6e63", "border": "#ffab91"},
        "typography": {"title_font": "PingFang SC, Microsoft YaHei", "title_weight": 800,
                       "title_size": "2.8vw-3.2vw", "title_spacing": "0",
                       "body_font": "PingFang SC, Microsoft YaHei", "body_weight": 400,
                       "body_size": "1.5vw-1.7vw", "line_height": 1.8},
        "layout_rules": {"card_style": "glass", "header_style": "centered-blur",
                         "corner_radius": "16px", "spacing": "loose",
                         "prefer_grid": False, "max_items_per_page": 5},
        "recommended_animations": {"transition": "fade", "duration": 500, "entrance": "fade-up",
                                   "stagger": 0.06, "emphasis": "grow-shrink"},
        "anti_patterns": ["不要使用冷色调", "不要用尖锐边角", "不要使用粗黑字体",
                         "文字密度要低", "不要放超过6个词汇",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["幼儿启蒙", "亲子课堂", "温暖主题"],
    },
    "tech": {
        "color_scheme": {"primary": "#42a5f5", "primary_light": "#bbdefb", "primary_dark": "#0d47a1",
                         "accent": "#00e5ff", "accent_light": "#80deea",
                         "bg": "linear-gradient(135deg,#0a1628,#0d47a1)",
                         "text": "#e8f0ff", "text_secondary": "#90caf9", "border": "#1565c0"},
        "typography": {"title_font": "Segoe UI, Microsoft YaHei", "title_weight": 800,
                       "title_size": "2.4vw-2.8vw", "title_spacing": "0.05em",
                       "body_font": "Segoe UI, Microsoft YaHei", "body_weight": 400,
                       "body_size": "1.3vw-1.5vw", "line_height": 1.7},
        "layout_rules": {"card_style": "glass", "header_style": "left-accent",
                         "corner_radius": "8px", "spacing": "medium",
                         "prefer_grid": True, "max_items_per_page": 6},
        "recommended_animations": {"transition": "slide", "duration": 350, "entrance": "slide-up",
                                   "stagger": 0.04, "emphasis": "pulse"},
        "anti_patterns": ["不要使用暖色系", "不要用过大的圆角", "不要在亮背景上放白色文字",
                         "不要使用手写字体", "不要密集排版",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["科普课程", "科技主题", "数字素养"],
    },
    "nature": {
        "color_scheme": {"primary": "#43a047", "primary_light": "#e8f5e9", "primary_dark": "#1b5e20",
                         "accent": "#ef6c00", "accent_light": "#fff3e0",
                         "bg": "linear-gradient(135deg,#e8f5e9,#c8e6c9)",
                         "text": "#1b5e20", "text_secondary": "#33691e", "border": "#81c784"},
        "typography": {"title_font": "PingFang SC, Microsoft YaHei", "title_weight": 800,
                       "title_size": "2.4vw-2.8vw", "title_spacing": "0",
                       "body_font": "PingFang SC, Microsoft YaHei", "body_weight": 400,
                       "body_size": "1.4vw-1.6vw", "line_height": 1.7},
        "layout_rules": {"card_style": "bordered", "header_style": "bottom-accent",
                         "corner_radius": "12px", "spacing": "generous",
                         "prefer_grid": False, "max_items_per_page": 6},
        "recommended_animations": {"transition": "fade", "duration": 500, "entrance": "fade-up",
                                   "stagger": 0.05, "emphasis": "grow-shrink"},
        "anti_patterns": ["不要用荧光色", "不要用纯黑文字", "不要用过于工业化的排版",
                         "背景不要用纯白", "标题不要用粗黑体",
                         "严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替"],
        "best_for": ["自然科学", "环保主题", "生物地理"],
    },
    "business": {
        "color_scheme": {"primary": "#607d8b", "primary_light": "#eceff1", "primary_dark": "#37474f",
                         "accent": "#e65100", "accent_light": "#fff3e0", "bg": "#fafafa",
                         "text": "#37474f", "text_secondary": "#607d8b", "border": "#bdbdbd"},
        "typography": {"title_font": "Segoe UI, PingFang SC", "title_weight": 700,
                       "title_size": "2.2vw-2.6vw", "title_spacing": "1px",
                       "body_font": "Segoe UI, PingFang SC", "body_weight": 400,
                       "body_size": "1.3vw-1.5vw", "line_height": 1.7},
        "layout_rules": {"card_style": "flat", "header_style": "full-bg-uppercase",
                         "corner_radius": "4px", "spacing": "compact",
                         "prefer_grid": False, "max_items_per_page": 7},
        "recommended_animations": {"transition": "fade", "duration": 300, "entrance": "fade",
                                   "stagger": 0.03, "emphasis": "pulse"},
        "anti_patterns": ["严禁使用任何emoji表情符号和特殊符号(🧑‍🏫🤖⚡🎈🌟🎉🔥⭐等)，一律用文字符号(●▸◆▶)代替", "不要用彩色渐变背景", "不要用圆体/手写字体",
                         "排版不要太松散", "不要使用过亮的强调色"],
        "best_for": ["成人英语", "商务英语", "企业培训"],
    },
}

# 每种主题对各类slide类型的推荐布局 (list/grid/cards)
_THEME_SLIDE_LAYOUTS = {
    "classic":     {"vocabulary": "list", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "list"},
    "cartoon":     {"vocabulary": "grid", "grammar": "cards", "practice": "list", "objective": "grid", "dialogue": "cards"},
    "academic":    {"vocabulary": "list", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "list"},
    "senior":      {"vocabulary": "list", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "list"},
    "blackboard":  {"vocabulary": "list", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "list"},
    "warm":        {"vocabulary": "cards", "grammar": "cards", "practice": "list", "objective": "list", "dialogue": "cards"},
    "tech":        {"vocabulary": "grid", "grammar": "list", "practice": "list", "objective": "grid", "dialogue": "list"},
    "nature":      {"vocabulary": "cards", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "cards"},
    "business":    {"vocabulary": "list", "grammar": "list", "practice": "list", "objective": "list", "dialogue": "list"},
}

# 为每个主题生成新CSS变量覆盖（基于 style_skill 中定义的设计token）
def _get_theme_css_variable_overrides(theme_name: str) -> str:
    """根据 style_skill 生成主题特有的 CSS 变量覆盖"""
    skill = _THEME_STYLE_SKILLS.get(theme_name)
    if not skill:
        return ""
    cs = skill.get("color_scheme", {})
    typo = skill.get("typography", {})
    layout = skill.get("layout_rules", {})
    anim = skill.get("recommended_animations", {})
    return f"""--slide-card-shadow:0 2px 12px {cs.get('primary','#333')}15;--slide-card-hover-shadow:0 4px 20px {cs.get('primary','#333')}25;--slide-font-title-weight:{typo.get('title_weight',800)};--slide-font-title-letter-spacing:{typo.get('title_spacing','0')};--slide-corner-radius:{layout.get('corner_radius','12px')};--slide-header-style:{layout.get('header_style','left-border')};--slide-anim-duration:{anim.get('duration','500')}ms;--slide-anim-easing:cubic-bezier(0.4,0,0.2,1);--slide-anim-entrance:fadeInUp;--slide-transition-type:{anim.get('transition','slide')};--slide-transition-duration:{anim.get('duration','400')}ms;--slide-card-border:1px solid {cs.get('border','#e0e0e0')};--slide-container-padding:{'1.8vw 2.5vw' if layout.get('spacing')=='loose' else '1.5vw 2.2vw'};--slide-list-item-spacing:{'0.7vw 0' if layout.get('spacing') in ('generous','loose') else '0.4vw 0'};--slide-paragraph-spacing:{'0.8vw' if layout.get('spacing') in ('generous','loose') else '0.5vw'};"""


BUILTIN_THEMES = [
    {
        "name": "classic","display_name": "经典简约","description": "蓝白经典配色，适合各学段通用","preview_color": "#2d7d46","sort_order": 0,
        "style_skill": _THEME_STYLE_SKILLS["classic"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["classic"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#ffffff;--slide-text:#2c3e50;--slide-title-color:#1b5e20;--slide-subtitle-color:#455a64;--slide-grade-color:#607d8b;--slide-header-text:#2d7d46;--slide-header-bg:#f0f7f0;--slide-card-bg:#f8faf8;--slide-code-bg:#f5f5f5;--slide-primary:#2d7d46;--slide-primary-light:#e8f5e9;--slide-primary-dark:#1b5e20;--slide-accent:#1565c0;--slide-accent-light:#e3f2fd;--slide-word-color:#1b5e20;--slide-phonetic-color:#607d8b;--slide-translation-color:#455a64;--slide-example-color:#546e7a;--slide-rule-color:#d84315;--slide-explain-color:#455a64;--slide-speaker-a-color:#1565c0;--slide-speaker-b-color:#c62828;--slide-label-color:#37474f;--slide-hint-color:#455a64;--slide-prompt-color:#37474f;--slide-footer-text:#607d8b;--slide-ai-question-bg:rgba(45,125,70,0.06);--slide-ai-question-text:#263238;--slide-option-bg:#f5f7fa;--slide-warm:#fff8e1;--slide-warm-border:#ffe082;--slide-border:#e0e0e0;--slide-shadow:0 2px 12px rgba(0,0,0,0.06);--slide-radius:12px;--slide-title-font:3.0vw;--slide-body-font:1.5vw;--slide-line-height:1.7}""",
        "css_content":""".ppt-presentation{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:3.2vw 3.6vw;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-header-bg);padding:0.9vw 1.6vw;border-radius:var(--slide-radius);margin-bottom:1.2vw;border-left:4px solid var(--slide-primary)}
.slide-header h2{margin:0;font-size:1.8vw;font-weight:700;color:var(--slide-header-text)}
.slide-body{flex:1;overflow-y:auto}
.main-title{font-size:var(--slide-title-font);font-weight:800;color:var(--slide-title-color);margin:0 0 0.6vw;letter-spacing:-0.02em}
.subtitle{font-size:1.8vw;color:var(--slide-subtitle-color);margin:0 0 0.3vw}
.grade{font-size:1.2vw;color:var(--slide-grade-color)}
.word-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:1.0vw 1.3vw;margin-bottom:0.6vw;border:1px solid var(--slide-border);box-shadow:var(--slide-shadow)}
.word-card .word{font-size:1.7vw;font-weight:700;color:var(--slide-word-color)}
.word-card .phonetic{font-size:1.2vw;color:var(--slide-phonetic-color);font-weight:400;margin-left:0.6vw}
.word-card .translation{font-size:1.2vw;color:var(--slide-translation-color);margin-top:0.2vw}
.word-card .example{font-size:1.1vw;color:var(--slide-example-color);font-style:italic;margin-top:0.3vw}
.dialogue-bubble{border-radius:12px;padding:0.8vw 1.3vw;max-width:78%;margin-bottom:0.6vw;box-shadow:var(--slide-shadow)}
.dialogue-bubble.a{align-self:flex-start;background:var(--slide-accent-light);border-left:3px solid var(--slide-accent)}
.dialogue-bubble.b{align-self:flex-end;background:#f5f0fa;border-right:3px solid var(--slide-speaker-b-color)}
.dialogue-bubble .speaker{font-weight:600;font-size:1.2vw}
.dialogue-bubble .text{font-size:1.3vw;margin-top:0.15vw}
.dialogue-bubble .translation{font-size:1.1vw;color:var(--slide-hint-color);margin-top:0.15vw}
.grammar-card{background:var(--slide-warm);border-radius:var(--slide-radius);padding:1.0vw 1.3vw;border:1px solid var(--slide-warm-border);margin-bottom:0.6vw}
.grammar-card .rule{font-weight:700;font-size:1.3vw;color:var(--slide-rule-color);margin-bottom:0.3vw}
.grammar-card .example{font-size:1.2vw;color:var(--slide-translation-color);font-style:italic}
.grammar-card .explanation{font-size:1.1vw;color:var(--slide-explain-color);margin-top:0.3vw}
.question-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:1.0vw 1.3vw;margin-bottom:0.8vw;border:1px solid var(--slide-border)}
.question-card .stem{font-weight:600;font-size:1.3vw;color:var(--slide-text);margin-bottom:0.5vw}
.option-item{padding:0.5vw 1.0vw;border-radius:6px;background:var(--slide-option-bg);border:1px solid var(--slide-border);font-size:1.2vw;color:var(--slide-text);margin-bottom:0.3vw}
.option-item.correct{background:#c8e6c9;border-color:#66bb6a}
.option-item.wrong{background:#ffebee;border-color:#ef5350;color:#c62828}
.objective-list{font-size:1.4vw;line-height:2.1;list-style:none;padding:0}
.objective-list li{padding:0.5vw 0;color:var(--slide-text)}
.objective-list li::before{content:"● ";color:var(--slide-primary)}
.summary-block{margin-bottom:1.2vw}
.summary-block .label{font-weight:600;font-size:1.3vw;color:var(--slide-label-color);margin-bottom:0.6vw}
.homework-box{background:var(--slide-warm);padding:1.0vw;border-radius:var(--slide-radius);border:1px solid var(--slide-warm-border)}""",
    },
    {
        "name": "cartoon","display_name": "小学卡通","description": "明亮色彩+圆角+大字体，适合低年级","preview_color": "#ff7043","sort_order": 1,
        "style_skill": _THEME_STYLE_SKILLS["cartoon"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["cartoon"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#fff8e1;--slide-text:#4e342e;--slide-title-color:#bf360c;--slide-subtitle-color:#6d4c41;--slide-grade-color:#8d6e63;--slide-header-text:#bf360c;--slide-header-bg:#ffccbc;--slide-card-bg:#fff3e0;--slide-code-bg:#fff8e1;--slide-primary:#ff7043;--slide-primary-light:#fff3e0;--slide-primary-dark:#e64a19;--slide-accent:#42a5f5;--slide-accent-light:#e3f2fd;--slide-word-color:#bf360c;--slide-phonetic-color:#6d4c41;--slide-translation-color:#4e342e;--slide-example-color:#6d4c41;--slide-rule-color:#d84315;--slide-explain-color:#4e342e;--slide-speaker-a-color:#42a5f5;--slide-speaker-b-color:#e91e63;--slide-label-color:#4e342e;--slide-hint-color:#6d4c41;--slide-prompt-color:#4e342e;--slide-footer-text:#6d4c41;--slide-ai-question-bg:rgba(255,112,67,0.08);--slide-ai-question-text:#4e342e;--slide-option-bg:#fff3e0;--slide-warm:#fff8e1;--slide-warm-border:#ffe0b2;--slide-border:#ffccbc;--slide-shadow:0 2px 12px rgba(255,112,67,0.15);--slide-radius:20px;--slide-title-font:3.1vw;--slide-body-font:1.7vw;--slide-line-height:1.8}""",
        "css_content":""".ppt-presentation{font-family:'Comic Sans MS','PingFang SC','Microsoft YaHei',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:32px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-primary-light);padding:12px 24px;border-radius:var(--slide-radius);margin-bottom:16px;text-align:center}
.slide-header h2{margin:0;font-size:2.2vw;font-weight:800;color:var(--slide-primary-dark)}
.main-title{font-size:var(--slide-title-font);font-weight:900;color:var(--slide-primary-dark);margin:0 0 12px;text-align:center;text-shadow:2px 2px 0 var(--slide-primary-light)}
.subtitle{font-size:2.2vw;color:#8d6e63;text-align:center}.grade{font-size:1.6vw;color:#a1887f;text-align:center}
.word-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:16px;margin-bottom:10px;border:2px solid var(--slide-warm-border);box-shadow:0 2px 8px var(--slide-shadow)}
.word-card .word{font-size:2.0vw;font-weight:800;color:var(--slide-primary-dark)}
.word-card .phonetic{font-size:1.6vw;color:#8d6e63;margin-left:8px}
.word-card .translation{font-size:1.6vw;color:#6d4c41}.word-card .example{font-size:1.3vw;color:#8d6e63;font-style:italic;margin-top:4px}
.dialogue-bubble{border-radius:20px;padding:12px 20px;max-width:80%;margin-bottom:8px}
.dialogue-bubble.a{align-self:flex-start;background:#bbdefb;border:2px solid #90caf9}
.dialogue-bubble.b{align-self:flex-end;background:#f8bbd0;border:2px solid #f48fb1}
.dialogue-bubble .speaker{font-weight:700;font-size:1.6vw}
.dialogue-bubble .text{font-size:1.6vw;margin-top:4px}
.grammar-card{background:#fff9c4;border-radius:var(--slide-radius);padding:16px;border:2px dashed #fff176;margin-bottom:10px}
.grammar-card .rule{font-weight:800;font-size:1.6vw;color:var(--slide-primary-dark)}
.question-card{background:#fff;border-radius:var(--slide-radius);padding:16px;margin-bottom:12px;border:2px solid var(--slide-border)}
.question-card .stem{font-weight:700;font-size:1.6vw;margin-bottom:8px}
.option-item{padding:8px 14px;border-radius:12px;background:var(--slide-primary-light);border:2px solid var(--slide-border);font-size:1.4vw;margin-bottom:6px}
.option-item.correct{background:#c8e6c9;border-color:#66bb6a}
.objective-list{font-size:1.6vw;line-height:2.2;padding-left:20px}
.summary-block{background:var(--slide-primary-light);border-radius:var(--slide-radius);padding:16px}
.homework-box{background:#fff9c4;padding:14px;border-radius:var(--slide-radius);border:2px dashed #fff176}""",
    },
    {
        "name": "academic","display_name": "初中简约","description": "清新蓝白，适中字号，适合初中课堂教学","preview_color": "#1976d2","sort_order": 2,
        "style_skill": _THEME_STYLE_SKILLS["academic"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["academic"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#f5f7fa;--slide-text:#2c3e50;--slide-title-color:#0d47a1;--slide-subtitle-color:#455a64;--slide-grade-color:#607d8b;--slide-header-text:#ffffff;--slide-header-bg:#1976d2;--slide-card-bg:#ffffff;--slide-code-bg:#eceff1;--slide-primary:#1976d2;--slide-primary-light:#e3f2fd;--slide-primary-dark:#0d47a1;--slide-accent:#388e3c;--slide-accent-light:#e8f5e9;--slide-word-color:#0d47a1;--slide-phonetic-color:#607d8b;--slide-translation-color:#455a64;--slide-example-color:#607d8b;--slide-rule-color:#0d47a1;--slide-explain-color:#37474f;--slide-speaker-a-color:#1976d2;--slide-speaker-b-color:#e64a19;--slide-label-color:#37474f;--slide-hint-color:#455a64;--slide-prompt-color:#2c3e50;--slide-footer-text:#607d8b;--slide-ai-question-bg:rgba(25,118,210,0.06);--slide-ai-question-text:#263238;--slide-option-bg:#f5f7fa;--slide-warm:#fff8e1;--slide-warm-border:#ffe082;--slide-border:#cfd8dc;--slide-shadow:0 2px 12px rgba(25,118,210,0.08);--slide-radius:8px;--slide-title-font:2.5vw;--slide-body-font:1.4vw;--slide-line-height:1.7}""",
        "css_content":""".ppt-presentation{font-family:'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:36px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-primary);padding:10px 20px;border-radius:var(--slide-radius);margin-bottom:16px}
.slide-header h2{margin:0;font-size:1.7vw;font-weight:700;color:#fff}
.main-title{font-size:var(--slide-title-font);font-weight:700;color:var(--slide-primary-dark);margin:0 0 6px}
.subtitle{font-size:1.7vw;color:#546e7a}.grade{font-size:1.2vw;color:#90a4ae}
.word-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;margin-bottom:8px;border:1px solid var(--slide-border)}
.word-card .word{font-size:1.6vw;font-weight:700}.word-card .phonetic{font-size:1.2vw;color:#78909c}
.word-card .translation{font-size:1.2vw;color:#546e7a}
.dialogue-bubble{border-radius:8px;padding:8px 14px;max-width:80%;margin-bottom:6px}
.dialogue-bubble.a{align-self:flex-start;background:var(--slide-accent-light)}
.dialogue-bubble.b{align-self:flex-end;background:#f3e5f5}
.grammar-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;border-left:4px solid var(--slide-primary);margin-bottom:8px}
.question-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;margin-bottom:10px}
.option-item{padding:5px 10px;border-radius:4px;background:#f5f5f5;border:1px solid var(--slide-border);font-size:1.2vw}
.objective-list{font-size:1.3vw;line-height:2}
.summary-block{border-left:4px solid var(--slide-primary);padding-left:12px;margin-bottom:12px}
.homework-box{background:var(--slide-warm);padding:10px;border-radius:var(--slide-radius)}""",
    },
    {
        "name": "senior","display_name": "高中学术","description": "深色标题+严谨排版，适合高中/雅思备考","preview_color": "#37474f","sort_order": 3,
        "style_skill": _THEME_STYLE_SKILLS["senior"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["senior"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#ffffff;--slide-text:#263238;--slide-title-color:#1a237e;--slide-subtitle-color:#455a64;--slide-grade-color:#607d8b;--slide-header-text:#ffffff;--slide-header-bg:#37474f;--slide-card-bg:#fafafa;--slide-code-bg:#f5f5f5;--slide-primary:#37474f;--slide-primary-light:#eceff1;--slide-primary-dark:#1a237e;--slide-accent:#d32f2f;--slide-accent-light:#ffebee;--slide-word-color:#1a237e;--slide-phonetic-color:#607d8b;--slide-translation-color:#455a64;--slide-example-color:#607d8b;--slide-rule-color:#1a237e;--slide-explain-color:#37474f;--slide-speaker-a-color:#37474f;--slide-speaker-b-color:#c62828;--slide-label-color:#37474f;--slide-hint-color:#455a64;--slide-prompt-color:#263238;--slide-footer-text:#607d8b;--slide-ai-question-bg:rgba(55,71,79,0.05);--slide-ai-question-text:#263238;--slide-option-bg:#fafafa;--slide-warm:#fafafa;--slide-warm-border:#e0e0e0;--slide-border:#cfd8dc;--slide-shadow:0 1px 8px rgba(0,0,0,0.06);--slide-radius:4px;--slide-title-font:2.3vw;--slide-body-font:1.3vw;--slide-line-height:1.8}""",
        "css_content":""".ppt-presentation{font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:32px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow-y:auto}
.slide-header{background:var(--slide-primary);padding:8px 16px;margin-bottom:16px}
.slide-header h2{margin:0;font-size:1.6vw;font-weight:700;color:#fff;letter-spacing:1px}
.main-title{font-size:var(--slide-title-font);font-weight:800;color:var(--slide-primary-dark);margin:0 0 4px;letter-spacing:-0.5px}
.subtitle{font-size:1.6vw;color:#546e7a}
.word-card{background:var(--slide-card-bg);padding:10px 14px;margin-bottom:6px;border-bottom:1px solid var(--slide-border)}
.word-card .word{font-size:1.4vw;font-weight:700;color:var(--slide-primary-dark)}
.word-card .phonetic{font-size:1.2vw;color:#78909c}
.word-card .translation{font-size:1.2vw;color:#546e7a}
.dialogue-bubble{padding:8px 14px;max-width:80%;margin-bottom:4px;border-left:3px solid transparent}
.dialogue-bubble.a{align-self:flex-start;border-left-color:var(--slide-primary);background:var(--slide-primary-light)}
.dialogue-bubble.b{align-self:flex-end;border-left-color:var(--slide-accent);background:var(--slide-accent-light)}
.grammar-card{padding:10px 14px;margin-bottom:6px;background:var(--slide-card-bg)}
.grammar-card .rule{font-weight:700;font-size:1.3vw;color:var(--slide-primary-dark)}
.question-card{padding:10px 14px;margin-bottom:8px;background:var(--slide-card-bg)}
.option-item{padding:4px 8px;font-size:1.2vw}
.objective-list{font-size:1.3vw;line-height:2}
.homework-box{background:var(--slide-card-bg);padding:10px;border-left:3px solid var(--slide-accent)}""",
    },
    {
        "name": "blackboard","display_name": "黑板风格","description": "绿色黑板+粉笔白字，传统课堂氛围","preview_color": "#2e7d32","sort_order": 4,
        "style_skill": _THEME_STYLE_SKILLS["blackboard"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["blackboard"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#2e7d32;--slide-text:#ffffff;--slide-title-color:#fff176;--slide-subtitle-color:#e8f5e9;--slide-grade-color:#c8e6c9;--slide-header-text:#fff176;--slide-header-bg:transparent;--slide-card-bg:rgba(255,255,255,0.08);--slide-code-bg:rgba(255,255,255,0.05);--slide-primary:#a5d6a7;--slide-primary-light:#4caf50;--slide-primary-dark:#1b5e20;--slide-accent:#fff176;--slide-accent-light:#ffee58;--slide-word-color:#ffffff;--slide-phonetic-color:#c8e6c9;--slide-translation-color:#e8f5e9;--slide-example-color:#c8e6c9;--slide-rule-color:#fff176;--slide-explain-color:#e8f5e9;--slide-speaker-a-color:#fff176;--slide-speaker-b-color:#ffcc80;--slide-label-color:#ffffff;--slide-hint-color:#c8e6c9;--slide-prompt-color:#ffffff;--slide-footer-text:#a5d6a7;--slide-ai-question-bg:rgba(255,255,255,0.1);--slide-ai-question-text:#ffffff;--slide-option-bg:rgba(255,255,255,0.06);--slide-warm:#388e3c;--slide-warm-border:#66bb6a;--slide-border:#4caf50;--slide-shadow:none;--slide-radius:0px;--slide-title-font:3.0vw;--slide-body-font:1.7vw;--slide-line-height:1.8}""",
        "css_content":""".ppt-presentation{font-family:'Ma Shan Zheng','KaiTi','STKaiti','PingFang SC',serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:3.2vw 3.6vw;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden;border:0.6vw solid #795548}
.slide-header{border-bottom:2px dashed var(--slide-accent);padding-bottom:0.6vw;margin-bottom:1.5vw}
.slide-header h2{margin:0;font-size:2.1vw;font-weight:700;color:var(--slide-accent)}
.main-title{font-size:var(--slide-title-font);font-weight:700;color:var(--slide-accent);margin:0 0 1.0vw}
.subtitle{font-size:1.9vw;color:var(--slide-subtitle-color)}
.grade{font-size:1.3vw;color:var(--slide-grade-color)}
.word-card{background:var(--slide-card-bg);padding:1.0vw 1.3vw;margin-bottom:0.8vw;border-left:4px solid var(--slide-accent)}
.word-card .word{font-size:1.9vw;font-weight:700;color:var(--slide-word-color)}
.word-card .phonetic{font-size:1.3vw;color:var(--slide-phonetic-color);margin-left:0.5vw}
.word-card .translation{font-size:1.5vw;color:var(--slide-translation-color)}
.word-card .example{font-size:1.2vw;color:var(--slide-example-color);font-style:italic;margin-top:0.2vw}
.dialogue-bubble{padding:0.8vw 1.4vw;max-width:80%;margin-bottom:0.6vw}
.dialogue-bubble.a{align-self:flex-start;background:rgba(255,255,255,0.1);border-left:4px solid var(--slide-accent)}
.dialogue-bubble.b{align-self:flex-end;background:rgba(255,255,255,0.08);border-right:4px solid #ffcc80}
.dialogue-bubble .speaker{font-weight:600;font-size:1.3vw}
.dialogue-bubble .text{font-size:1.4vw;color:var(--slide-text);margin-top:0.15vw}
.dialogue-bubble .translation{font-size:1.1vw;color:var(--slide-phonetic-color);margin-top:0.15vw}
.grammar-card{background:rgba(255,255,255,0.08);padding:1.0vw 1.3vw;margin-bottom:0.6vw;border:1px solid var(--slide-primary)}
.grammar-card .rule{font-weight:700;font-size:1.5vw;color:var(--slide-accent);margin-bottom:0.25vw}
.grammar-card .example{font-size:1.3vw;color:var(--slide-subtitle-color);font-style:italic}
.grammar-card .explanation{font-size:1.1vw;color:var(--slide-explain-color);margin-top:0.25vw}
.question-card{background:rgba(255,255,255,0.08);padding:1.0vw 1.3vw;margin-bottom:0.8vw}
.question-card .stem{font-weight:600;font-size:1.3vw;color:var(--slide-text);margin-bottom:0.5vw}
.option-item{padding:0.5vw 1.0vw;background:var(--slide-option-bg);border:1px solid var(--slide-primary);color:var(--slide-text);font-size:1.2vw;margin-bottom:0.3vw;border-radius:4px}
.option-item.correct{background:rgba(255,255,255,0.2);border-color:var(--slide-accent)}
.option-item.wrong{background:rgba(244,67,54,0.3);border-color:#f44336;color:#ffcdd2}
.objective-list{font-size:1.5vw;line-height:2.2;list-style:none;padding:0}
.objective-list li{color:var(--slide-text);padding:0.3vw 0}
.objective-list li::before{content:"▸ ";color:var(--slide-accent)}
.summary-block{margin-bottom:1.0vw}
.summary-block .label{font-weight:600;font-size:1.3vw;color:var(--slide-label-color)}
.homework-box{background:rgba(255,255,255,0.08);padding:1.0vw;border:1px dashed var(--slide-accent)}""",
    },
    {
        "name": "warm","display_name": "暖色温馨","description": "暖橙/米色+柔和渐变，适合幼儿/启蒙","preview_color": "#ff8a65","sort_order": 5,
        "style_skill": _THEME_STYLE_SKILLS["warm"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["warm"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:linear-gradient(135deg,#fff3e0,#fce4ec);--slide-text:#4e342e;--slide-title-color:#bf360c;--slide-subtitle-color:#6d4c41;--slide-grade-color:#8d6e63;--slide-header-text:#bf360c;--slide-header-bg:rgba(255,112,67,0.10);--slide-card-bg:rgba(255,255,255,0.70);--slide-code-bg:rgba(255,255,255,0.50);--slide-primary:#ff7043;--slide-primary-light:#fff3e0;--slide-primary-dark:#bf360c;--slide-accent:#ec407a;--slide-accent-light:#fce4ec;--slide-word-color:#bf360c;--slide-phonetic-color:#6d4c41;--slide-translation-color:#4e342e;--slide-example-color:#6d4c41;--slide-rule-color:#d84315;--slide-explain-color:#4e342e;--slide-speaker-a-color:#ff7043;--slide-speaker-b-color:#ec407a;--slide-label-color:#4e342e;--slide-hint-color:#6d4c41;--slide-prompt-color:#4e342e;--slide-footer-text:#6d4c41;--slide-ai-question-bg:rgba(255,112,67,0.10);--slide-ai-question-text:#4e342e;--slide-option-bg:rgba(255,255,255,0.50);--slide-warm:#fff8e1;--slide-warm-border:#ffe0b2;--slide-border:#ffab91;--slide-shadow:0 2px 16px rgba(255,112,67,0.12);--slide-radius:16px;--slide-title-font:3.0vw;--slide-body-font:1.6vw;--slide-line-height:1.8}""",
        "css_content":""".ppt-presentation{font-family:'PingFang SC','Microsoft YaHei','Comic Sans MS',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:36px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-header-bg);backdrop-filter:blur(10px);padding:12px 20px;border-radius:var(--slide-radius);margin-bottom:16px;text-align:center}
.slide-header h2{margin:0;font-size:2.0vw;font-weight:700;color:var(--slide-primary-dark)}
.main-title{font-size:var(--slide-title-font);font-weight:800;color:var(--slide-primary-dark);margin:0 0 10px;text-align:center}
.subtitle{font-size:2.0vw;color:#8d6e63;text-align:center}
.word-card{background:var(--slide-card-bg);backdrop-filter:blur(5px);border-radius:var(--slide-radius);padding:14px;margin-bottom:10px;border:1px solid var(--slide-border)}
.word-card .word{font-size:1.9vw;font-weight:700;color:var(--slide-primary-dark)}
.dialogue-bubble{border-radius:16px;padding:12px 18px;max-width:80%;margin-bottom:8px}
.dialogue-bubble.a{align-self:flex-start;background:rgba(255,255,255,0.6)}
.dialogue-bubble.b{align-self:flex-end;background:var(--slide-accent-light)}
.grammar-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:14px;border:1px solid var(--slide-border)}
.question-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:14px;margin-bottom:10px}
.objective-list{font-size:1.6vw;line-height:2.2;padding-left:20px}
.homework-box{background:var(--slide-card-bg);padding:12px;border-radius:var(--slide-radius)}""",
    },
    {
        "name": "tech","display_name": "科技蓝调","description": "深蓝科技感+荧光点缀，适合科普/兴趣课","preview_color": "#0d47a1","sort_order": 6,
        "style_skill": _THEME_STYLE_SKILLS["tech"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["tech"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:linear-gradient(135deg,#0a1628,#0d47a1);--slide-text:#e8f0ff;--slide-title-color:#ffffff;--slide-subtitle-color:#90caf9;--slide-grade-color:#64b5f6;--slide-header-text:#00e5ff;--slide-header-bg:rgba(0,0,0,0.3);--slide-card-bg:rgba(255,255,255,0.06);--slide-code-bg:rgba(0,0,0,0.25);--slide-primary:#42a5f5;--slide-primary-light:#bbdefb;--slide-primary-dark:#0d47a1;--slide-accent:#00e5ff;--slide-accent-light:#80deea;--slide-word-color:#ffffff;--slide-phonetic-color:#90caf9;--slide-translation-color:#bbdefb;--slide-example-color:#90caf9;--slide-rule-color:#00e5ff;--slide-explain-color:#b0bec5;--slide-speaker-a-color:#42a5f5;--slide-speaker-b-color:#ffab40;--slide-label-color:#ffffff;--slide-hint-color:#90caf9;--slide-prompt-color:#e8f0ff;--slide-footer-text:#64b5f6;--slide-ai-question-bg:rgba(0,229,255,0.08);--slide-ai-question-text:#e8f0ff;--slide-option-bg:rgba(255,255,255,0.05);--slide-warm:#1a237e;--slide-warm-border:#303f9f;--slide-border:#1565c0;--slide-shadow:0 0 20px rgba(0,229,255,0.12);--slide-radius:8px;--slide-title-font:2.7vw;--slide-body-font:1.4vw;--slide-line-height:1.7}""",
        "css_content":""".ppt-presentation{font-family:'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:2.8vw 3.2vw;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-header-bg);backdrop-filter:blur(10px);padding:0.8vw 1.6vw;margin-bottom:1.2vw;border:1px solid var(--slide-border);border-left:3px solid var(--slide-accent)}
.slide-header h2{margin:0;font-size:1.6vw;font-weight:700;color:var(--slide-accent);text-transform:uppercase;letter-spacing:0.05em}
.main-title{font-size:var(--slide-title-font);font-weight:800;color:var(--slide-title-color);margin:0 0 0.6vw;text-shadow:0 0 20px var(--slide-accent)}
.subtitle{font-size:1.6vw;color:var(--slide-subtitle-color)}
.grade{font-size:1.1vw;color:var(--slide-grade-color)}
.word-card{background:var(--slide-card-bg);backdrop-filter:blur(5px);padding:0.9vw 1.2vw;margin-bottom:0.6vw;border:1px solid rgba(255,255,255,0.08);border-left:3px solid var(--slide-accent)}
.word-card .word{font-size:1.6vw;font-weight:700;color:var(--slide-word-color)}
.word-card .phonetic{font-size:1.1vw;color:var(--slide-phonetic-color);margin-left:0.5vw}
.word-card .translation{font-size:1.1vw;color:var(--slide-translation-color)}
.word-card .example{font-size:1.0vw;color:var(--slide-example-color);font-style:italic;margin-top:0.2vw}
.dialogue-bubble{padding:0.7vw 1.2vw;max-width:78%;margin-bottom:0.5vw;border:1px solid transparent;backdrop-filter:blur(5px)}
.dialogue-bubble.a{align-self:flex-start;background:rgba(66,165,245,0.12);border-color:var(--slide-border)}
.dialogue-bubble.b{align-self:flex-end;background:rgba(0,229,255,0.08);border-color:rgba(0,229,255,0.3)}
.dialogue-bubble .speaker{font-weight:600;font-size:1.1vw}
.dialogue-bubble .text{font-size:1.2vw;color:var(--slide-text);margin-top:0.1vw}
.dialogue-bubble .translation{font-size:1.0vw;color:var(--slide-hint-color);margin-top:0.1vw}
.grammar-card{background:var(--slide-card-bg);padding:0.8vw 1.2vw;margin-bottom:0.5vw;border-left:3px solid var(--slide-accent)}
.grammar-card .rule{color:var(--slide-accent);font-weight:700;font-size:1.3vw;margin-bottom:0.25vw}
.grammar-card .example{font-size:1.1vw;color:var(--slide-translation-color);font-style:italic}
.grammar-card .explanation{font-size:1.0vw;color:var(--slide-explain-color);margin-top:0.25vw}
.question-card{background:var(--slide-card-bg);padding:0.8vw 1.2vw;margin-bottom:0.7vw;border:1px solid var(--slide-border)}
.question-card .stem{font-weight:600;font-size:1.2vw;color:var(--slide-text);margin-bottom:0.4vw}
.option-item{padding:0.4vw 0.8vw;background:var(--slide-option-bg);border:1px solid var(--slide-border);color:var(--slide-text);font-size:1.1vw;margin-bottom:0.25vw;border-radius:4px}
.option-item.correct{background:rgba(0,230,118,0.2);border-color:#00e676}
.option-item.wrong{background:rgba(255,82,82,0.2);border-color:#ff5252;color:#ffcdd2}
.objective-list{font-size:1.3vw;line-height:1.9;list-style:none;padding:0}
.objective-list li{color:var(--slide-text);padding:0.25vw 0}
.objective-list li::before{content:"◆ ";color:var(--slide-accent)}
.summary-block{margin-bottom:1.0vw}
.summary-block .label{font-size:1.2vw;color:var(--slide-label-color);font-weight:600}
.homework-box{background:var(--slide-card-bg);padding:0.8vw;border-left:3px solid var(--slide-accent)}""",
    },
    {
        "name": "nature","display_name": "自然绿意","description": "绿色生态+自然元素，适合科学/环保话题","preview_color": "#388e3c","sort_order": 7,
        "style_skill": _THEME_STYLE_SKILLS["nature"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["nature"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:linear-gradient(135deg,#e8f5e9,#c8e6c9);--slide-text:#1b5e20;--slide-title-color:#1b5e20;--slide-subtitle-color:#1b5e20;--slide-grade-color:#2e7d32;--slide-header-text:#1b5e20;--slide-header-bg:rgba(67,160,71,0.12);--slide-card-bg:rgba(255,255,255,0.70);--slide-code-bg:rgba(255,255,255,0.50);--slide-primary:#43a047;--slide-primary-light:#e8f5e9;--slide-primary-dark:#1b5e20;--slide-accent:#ef6c00;--slide-accent-light:#fff3e0;--slide-word-color:#1b5e20;--slide-phonetic-color:#2e7d32;--slide-translation-color:#1b5e20;--slide-example-color:#2e7d32;--slide-rule-color:#e65100;--slide-explain-color:#2e7d32;--slide-speaker-a-color:#43a047;--slide-speaker-b-color:#ef6c00;--slide-label-color:#1b5e20;--slide-hint-color:#2e7d32;--slide-prompt-color:#1b5e20;--slide-footer-text:#2e7d32;--slide-ai-question-bg:rgba(67,160,71,0.08);--slide-ai-question-text:#1b5e20;--slide-option-bg:rgba(255,255,255,0.50);--slide-warm:#f1f8e9;--slide-warm-border:#aed581;--slide-border:#81c784;--slide-shadow:0 2px 14px rgba(67,160,71,0.10);--slide-radius:12px;--slide-title-font:2.7vw;--slide-body-font:1.6vw;--slide-line-height:1.7}""",
        "css_content":""".ppt-presentation{font-family:'PingFang SC','Microsoft YaHei',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:36px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-header-bg);padding:10px 20px;border-radius:var(--slide-radius);margin-bottom:16px;border-bottom:3px solid var(--slide-primary)}
.slide-header h2{margin:0;font-size:1.9vw;font-weight:700;color:var(--slide-primary-dark)}
.main-title{font-size:var(--slide-title-font);font-weight:800;color:var(--slide-primary-dark);margin:0 0 8px}
.subtitle{font-size:1.9vw;color:#558b2f}
.word-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;margin-bottom:8px;border:1px solid var(--slide-border)}
.word-card .word{font-size:1.7vw;font-weight:700;color:var(--slide-primary-dark)}
.dialogue-bubble{border-radius:12px;padding:10px 16px;max-width:80%;margin-bottom:6px}
.dialogue-bubble.a{align-self:flex-start;background:rgba(255,255,255,0.6)}
.dialogue-bubble.b{align-self:flex-end;background:var(--slide-primary-light)}
.grammar-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;border-left:4px solid var(--slide-accent)}
.question-card{background:var(--slide-card-bg);border-radius:var(--slide-radius);padding:12px;margin-bottom:8px}
.option-item{padding:5px 10px;background:rgba(255,255,255,0.5);border:1px solid var(--slide-border)}
.objective-list{font-size:1.4vw;line-height:2}.homework-box{background:var(--slide-warm);padding:10px;border-radius:var(--slide-radius);border-left:4px solid var(--slide-accent)}""",
    },
    {
        "name": "business","display_name": "商务专业","description": "灰色系+简洁线条，适合成人英语/商务","preview_color": "#607d8b","sort_order": 8,
        "style_skill": _THEME_STYLE_SKILLS["business"],
        "slide_layouts": _THEME_SLIDE_LAYOUTS["business"],
        "font_pairings": [],
        "css_variables":""":root{--slide-bg:#fafafa;--slide-text:#37474f;--slide-title-color:#263238;--slide-subtitle-color:#546e7a;--slide-grade-color:#78909c;--slide-header-text:#ffffff;--slide-header-bg:#607d8b;--slide-card-bg:#ffffff;--slide-code-bg:#f5f5f5;--slide-primary:#607d8b;--slide-primary-light:#eceff1;--slide-primary-dark:#37474f;--slide-accent:#e65100;--slide-accent-light:#fff3e0;--slide-word-color:#263238;--slide-phonetic-color:#78909c;--slide-translation-color:#455a64;--slide-example-color:#78909c;--slide-rule-color:#37474f;--slide-explain-color:#546e7a;--slide-speaker-a-color:#607d8b;--slide-speaker-b-color:#e65100;--slide-label-color:#37474f;--slide-hint-color:#607d8b;--slide-prompt-color:#37474f;--slide-footer-text:#78909c;--slide-ai-question-bg:rgba(96,125,139,0.06);--slide-ai-question-text:#37474f;--slide-option-bg:#fafafa;--slide-warm:#fafafa;--slide-warm-border:#e0e0e0;--slide-border:#bdbdbd;--slide-shadow:0 1px 8px rgba(0,0,0,0.04);--slide-radius:4px;--slide-title-font:2.5vw;--slide-body-font:1.4vw;--slide-line-height:1.7}""",
        "css_content":""".ppt-presentation{font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:var(--slide-text);background:var(--slide-bg)}
.ppt-slide{padding:36px;display:flex;flex-direction:column;height:100%;box-sizing:border-box;overflow:hidden}
.slide-header{background:var(--slide-primary);padding:8px 20px;margin-bottom:16px}
.slide-header h2{margin:0;font-size:1.6vw;font-weight:600;color:#fff;text-transform:uppercase;letter-spacing:1px}
.main-title{font-size:var(--slide-title-font);font-weight:700;color:var(--slide-primary-dark);margin:0 0 6px}
.subtitle{font-size:1.6vw;color:#78909c}.grade{font-size:1.2vw;color:#b0bec5}
.word-card{background:var(--slide-card-bg);padding:10px 14px;margin-bottom:6px;border-bottom:1px solid var(--slide-border);display:flex;align-items:center;gap:8px}
.word-card .word{font-size:1.6vw;font-weight:600;color:var(--slide-primary-dark);min-width:100px}
.word-card .phonetic{font-size:1.2vw;color:#90a4ae}.word-card .translation{font-size:1.2vw;color:#546e7a;margin-left:auto}
.dialogue-bubble{padding:8px 14px;max-width:80%;margin-bottom:4px}
.dialogue-bubble.a{align-self:flex-start;border-left:3px solid var(--slide-primary);background:var(--slide-primary-light)}
.dialogue-bubble.b{align-self:flex-end;border-right:3px solid var(--slide-accent);background:#f5f5f5}
.grammar-card{padding:10px 14px;margin-bottom:6px;background:var(--slide-card-bg);border:1px solid var(--slide-border)}
.grammar-card .rule{font-size:1.3vw;font-weight:600;color:var(--slide-primary-dark)}
.question-card{background:var(--slide-card-bg);padding:10px 14px;margin-bottom:8px;border:1px solid var(--slide-border)}
.option-item{padding:4px 8px;font-size:1.2vw;color:#546e7a}
.objective-list{font-size:1.3vw;line-height:1.8;color:#546e7a}
.homework-box{background:var(--slide-card-bg);padding:10px;border:1px solid var(--slide-border)}""",
    },
]
