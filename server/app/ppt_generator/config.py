# PPT 生成器配置
# 画布格式 / 配色方案 / 字体系统 / SVG 约束

# ==================== 画布格式 ====================
CANVAS_FORMATS = {
    "ppt169":    {"name": "宽屏 16:9",  "viewBox": "0 0 1280 720",  "width_pt": 13.333, "height_pt": 7.5},
    "ppt43":     {"name": "标准 4:3",   "viewBox": "0 0 1024 768",  "width_pt": 10.0,   "height_pt": 7.5},
    "xhs":       {"name": "小红书 3:4", "viewBox": "0 0 720 960",   "width_pt": 7.5,    "height_pt": 10.0},
    "moment":    {"name": "朋友圈 1:1", "viewBox": "0 0 800 800",   "width_pt": 8.333,  "height_pt": 8.333},
    "douyin":    {"name": "抖音 9:16",  "viewBox": "0 0 720 1280",  "width_pt": 7.5,    "height_pt": 13.333},
    "wechat_oa": {"name": "公众号",     "viewBox": "0 0 1080 1920", "width_pt": 11.25,  "height_pt": 20.0},
    "a4":        {"name": "A4 竖版",    "viewBox": "0 0 794 1123",  "width_pt": 8.27,   "height_pt": 11.69},
    "a4_land":   {"name": "A4 横版",    "viewBox": "0 0 1123 794",  "width_pt": 11.69,  "height_pt": 8.27},
    "custom":    {"name": "自定义",     "viewBox": "0 0 1280 720",  "width_pt": 13.333, "height_pt": 7.5},
}
DEFAULT_CANVAS = "ppt169"

# ==================== 配色方案 ====================
COLOR_SCHEMES = {
    "professional": {
        "primary": "#1A56DB", "secondary": "#7E3AF2", "background": "#FFFFFF",
        "surface": "#F9FAFB", "text": "#111827", "text_secondary": "#6B7280",
        "accent": "#F59E0B", "success": "#10B981", "error": "#EF4444",
    },
    "warm": {
        "primary": "#D97706", "secondary": "#DC2626", "background": "#FFFBEB",
        "surface": "#FEF3C7", "text": "#1C1917", "text_secondary": "#78716C",
        "accent": "#2563EB", "success": "#16A34A", "error": "#DC2626",
    },
    "dark": {
        "primary": "#6366F1", "secondary": "#8B5CF6", "background": "#0F172A",
        "surface": "#1E293B", "text": "#F8FAFC", "text_secondary": "#94A3B8",
        "accent": "#F59E0B", "success": "#22C55E", "error": "#EF4444",
    },
    "nature": {
        "primary": "#15803D", "secondary": "#0D9488", "background": "#F0FDF4",
        "surface": "#DCFCE7", "text": "#052E16", "text_secondary": "#166534",
        "accent": "#EAB308", "success": "#16A34A", "error": "#DC2626",
    },
    "elegant": {
        "primary": "#1E293B", "secondary": "#475569", "background": "#FAFAFA",
        "surface": "#F1F5F9", "text": "#0F172A", "text_secondary": "#64748B",
        "accent": "#D946EF", "success": "#10B981", "error": "#EF4444",
    },
}
DEFAULT_COLOR_SCHEME = "professional"

# ==================== 字体系统 ====================
FONT_FAMILIES = {
    "system": {
        "heading": "Arial",
        "body": "Arial",
        "mono": "Courier New",
    },
    "elegant": {
        "heading": "Georgia",
        "body": "Calibri",
        "mono": "Consolas",
    },
    "modern": {
        "heading": "Segoe UI",
        "body": "Segoe UI",
        "mono": "Consolas",
    },
}
FONT_SIZES = {
    "title": 48,       # 封面大标题
    "heading1": 36,    # 一级标题
    "heading2": 28,    # 二级标题
    "heading3": 24,    # 三级标题
    "body": 18,        # 正文
    "small": 14,       # 小字
    "caption": 12,     # 注释
}
DEFAULT_FONT_FAMILY = "system"

# ==================== SVG 约束黑名单 ====================
# 禁止使用的 SVG 元素
FORBIDDEN_ELEMENTS = {
    "mask", "style", "foreignObject", "symbol", "use",
    "textPath", "animate", "animateTransform", "animateMotion",
    "set", "script", "iframe", "audio", "video",
}

# 禁止使用的 SVG 属性
FORBIDDEN_ATTRIBUTES = {
    "class", "style", "onclick", "onmouseover", "onmouseout",
}

# ==================== 路径单位转换 ====================
def px_to_pt(px_value: float) -> float:
    """像素转磅值 (1pt = 1px * 0.75)"""
    return px_value * 0.75

def emu_to_pt(emu_value: int) -> float:
    """EMU 转磅值 (1pt = 12700 EMU)"""
    return emu_value / 12700

def pt_to_emu(pt_value: float) -> int:
    """磅值转 EMU"""
    return int(pt_value * 12700)

# ==================== 默认 SVG 边距 ====================
CANVAS_MARGINS = {
    "ppt169":    {"top": 40, "bottom": 40, "left": 60, "right": 60},
    "ppt43":     {"top": 40, "bottom": 40, "left": 60, "right": 60},
    "xhs":       {"top": 40, "bottom": 40, "left": 40, "right": 40},
    "moment":    {"top": 40, "bottom": 40, "left": 40, "right": 40},
    "douyin":    {"top": 40, "bottom": 40, "left": 40, "right": 40},
    "wechat_oa": {"top": 50, "bottom": 50, "left": 50, "right": 50},
    "a4":        {"top": 50, "bottom": 50, "left": 50, "right": 50},
    "a4_land":   {"top": 50, "bottom": 50, "left": 50, "right": 50},
    "custom":    {"top": 40, "bottom": 40, "left": 60, "right": 60},
}
