"""DrawingML 上下文：颜色表、字体表、样式状态管理"""
from typing import Optional, Dict


class DrawingMLContext:
    """SVG→PPTX 转换的上下文管理器

    维护颜色映射表、字体映射表和全局样式状态。
    """

    def __init__(self):
        # 颜色映射: SVG 颜色 → 主题色/HSL 引用
        self.color_map: Dict[str, str] = {}

        # 字体映射: SVG font-family → PPTX 字体
        self.font_map: Dict[str, str] = {
            "serif": "Times New Roman",
            "sans-serif": "Microsoft YaHei",      # 默认非衬线用 YaHei（支持中文）
            "monospace": "Courier New",
            "Arial": "Microsoft YaHei",            # Arial 无中文字形 → 映射到 YaHei
            "Helvetica": "Microsoft YaHei",        # 同上
            "Calibri": "Microsoft YaHei",          # Calibri 也无中文
            "Microsoft YaHei": "Microsoft YaHei",
            "SimSun": "SimSun",
            "SimHei": "SimHei",
            "PingFang SC": "PingFang SC",
            "Noto Sans SC": "Microsoft YaHei",     # Linux 通用 → Windows 映射
            "Noto Serif SC": "Microsoft YaHei",
        }

        # 当前样式状态
        self.current_fill = None
        self.current_stroke = None
        self.current_stroke_width = 0
        self.current_opacity = 1.0

        # 形状 ID 计数器
        self._shape_id = 1

    def get_next_shape_id(self) -> str:
        """获取下一个形状 ID"""
        sid = self._shape_id
        self._shape_id += 1
        return f"shape_{sid}"

    def map_color(self, svg_color: str) -> str:
        """将 SVG 颜色映射为 DrawingML 颜色值"""
        if not svg_color or svg_color == "none":
            return "none"

        # 已映射
        if svg_color in self.color_map:
            return self.color_map[svg_color]

        # 命名颜色简单映射
        named = {
            "red": "FF0000", "green": "00FF00", "blue": "0000FF",
            "white": "FFFFFF", "black": "000000", "gray": "808080",
            "grey": "808080", "yellow": "FFFF00", "orange": "FFA500",
            "purple": "800080", "pink": "FFC0CB", "brown": "A52A2A",
            "transparent": "none",
        }
        if svg_color.lower() in named:
            return named[svg_color.lower()]

        # #RRGGBB 格式
        if svg_color.startswith("#"):
            hex_val = svg_color[1:]
            if len(hex_val) == 3:
                hex_val = "".join(c * 2 for c in hex_val)
            return hex_val.upper()

        # rgb(r,g,b) 格式
        if svg_color.startswith("rgb("):
            import re
            m = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', svg_color)
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return f"{r:02X}{g:02X}{b:02X}"

        # rgba 格式 — 取前三个通道
        if svg_color.startswith("rgba("):
            import re
            m = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', svg_color)
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return f"{r:02X}{g:02X}{b:02X}"

        # 默认返回黑色
        return "000000"

    def map_font(self, font_family: str) -> str:
        """映射字体族到 PowerPoint 字体"""
        if not font_family:
            return "Calibri"
        for key, value in self.font_map.items():
            if key.lower() in font_family.lower():
                return value
        return font_family

    def parse_opacity(self, opacity_str: Optional[str]) -> float:
        """解析 SVG 透明度"""
        if not opacity_str:
            return 1.0
        try:
            return float(opacity_str)
        except ValueError:
            return 1.0

    def opacity_to_transparency(self, opacity: float) -> int:
        """透明度转 PPTX transparency (0-100000)"""
        return int((1.0 - opacity) * 100000)
