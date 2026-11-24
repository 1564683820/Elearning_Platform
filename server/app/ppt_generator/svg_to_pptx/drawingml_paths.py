"""SVG path → DrawingML path 转换器"""
from typing import List, Tuple
import re


class SVGPathParser:
    """SVG path 数据解析器

    将 SVG d 属性解析为 DrawingML 可识别的路径命令。
    """

    def __init__(self):
        self.commands: List[str] = []

    def parse(self, d: str) -> List[str]:
        """解析 SVG path d 属性

        Args:
            d: SVG path 的 d 属性字符串

        Returns:
            DrawingML custGeom path XML 片段列表
        """
        if not d:
            return []

        tokens = self._tokenize(d)
        return self._convert_to_dml(tokens)

    def _tokenize(self, d: str) -> List[Tuple[str, List[float]]]:
        """将 SVG d 字符串拆分为命令和参数对"""
        tokens = []
        cmd_pattern = re.compile(r'([MLHVCSQTAZmlhvcsqtaz])\s*')
        float_pattern = re.compile(r'-?\d+(?:\.\d+)?(?:e-?\d+)?')

        i = 0
        while i < len(d):
            cmd_match = cmd_pattern.match(d, i)
            if cmd_match:
                cmd = cmd_match.group(1)
                i = cmd_match.end()
                params = []
                # 收集所有浮点数参数直到下一个命令或字符串结束
                while i < len(d):
                    # 跳过空白和逗号
                    while i < len(d) and (d[i] in ' ,\t\n\r'):
                        i += 1
                    if i < len(d) and d[i] in 'MLHVCSQTAZmlhvcsqtaz':
                        break
                    if i >= len(d):
                        break
                    float_match = float_pattern.match(d, i)
                    if float_match:
                        params.append(float(float_match.group()))
                        i = float_match.end()
                    else:
                        break
                tokens.append((cmd, params))
            else:
                i += 1

        return tokens

    def _convert_to_dml(self, tokens: List[Tuple[str, List[float]]]) -> List[str]:
        """将 SVG 路径 token 转换为 DrawingML path XML"""
        dml_commands = []
        current_x = 0.0
        current_y = 0.0

        for cmd, params in tokens:
            cmd_upper = cmd.upper()

            if cmd_upper == 'M':
                # MoveTo — 移到起点
                for i in range(0, len(params), 2):
                    x, y = params[i], params[i + 1]
                    if cmd.isupper():  # 绝对
                        pass
                    else:  # 相对
                        x += current_x
                        y += current_y
                    dml_commands.append(
                        f'<a:moveTo><a:pt x="{self._to_emu(x)}" y="{self._to_emu(y)}"/></a:moveTo>'
                    )
                    current_x, current_y = x, y

            elif cmd_upper == 'L':
                # LineTo — 画直线
                for i in range(0, len(params), 2):
                    x, y = params[i], params[i + 1]
                    if cmd.isupper():
                        pass
                    else:
                        x += current_x
                        y += current_y
                    dml_commands.append(
                        f'<a:lnTo><a:pt x="{self._to_emu(x)}" y="{self._to_emu(y)}"/></a:lnTo>'
                    )
                    current_x, current_y = x, y

            elif cmd_upper == 'H':
                # 水平线
                for px in params:
                    x = px if cmd.isupper() else current_x + px
                    dml_commands.append(
                        f'<a:lnTo><a:pt x="{self._to_emu(x)}" y="{self._to_emu(current_y)}"/></a:lnTo>'
                    )
                    current_x = x

            elif cmd_upper == 'V':
                # 垂直线
                for py in params:
                    y = py if cmd.isupper() else current_y + py
                    dml_commands.append(
                        f'<a:lnTo><a:pt x="{self._to_emu(current_x)}" y="{self._to_emu(y)}"/></a:lnTo>'
                    )
                    current_y = y

            elif cmd_upper == 'C':
                # 三次贝塞尔曲线
                for i in range(0, len(params), 6):
                    x1, y1, x2, y2, x, y = params[i:i+6]
                    if cmd.isupper():
                        pass
                    else:
                        x1 += current_x; y1 += current_y
                        x2 += current_x; y2 += current_y
                        x += current_x; y += current_y
                    dml_commands.append(
                        f'<a:cubicBezTo>'
                        f'<a:pt x="{self._to_emu(x1)}" y="{self._to_emu(y1)}"/>'
                        f'<a:pt x="{self._to_emu(x2)}" y="{self._to_emu(y2)}"/>'
                        f'<a:pt x="{self._to_emu(x)}" y="{self._to_emu(y)}"/>'
                        f'</a:cubicBezTo>'
                    )
                    current_x, current_y = x, y

            elif cmd_upper == 'S':
                # 平滑三次贝塞尔
                for i in range(0, len(params), 4):
                    x2, y2, x, y = params[i:i+4]
                    if cmd.isupper():
                        pass
                    else:
                        x2 += current_x; y2 += current_y
                        x += current_x; y += current_y
                    dml_commands.append(
                        f'<a:cubicBezTo>'
                        f'<a:pt x="{self._to_emu(x2)}" y="{self._to_emu(y2)}"/>'
                        f'<a:pt x="{self._to_emu(x)}" y="{self._to_emu(y)}"/>'
                        f'</a:cubicBezTo>'
                    )
                    current_x, current_y = x, y

            elif cmd_upper == 'Q':
                # 二次贝塞尔
                for i in range(0, len(params), 4):
                    x1, y1, x, y = params[i:i+4]
                    if cmd.isupper():
                        pass
                    else:
                        x1 += current_x; y1 += current_y
                        x += current_x; y += current_y
                    dml_commands.append(
                        f'<a:cubicBezTo>'
                        f'<a:pt x="{self._to_emu(x1)}" y="{self._to_emu(y1)}"/>'
                        f'<a:pt x="{self._to_emu(x1)}" y="{self._to_emu(y1)}"/>'
                        f'<a:pt x="{self._to_emu(x)}" y="{self._to_emu(y)}"/>'
                        f'</a:cubicBezTo>'
                    )
                    current_x, current_y = x, y

            elif cmd_upper == 'Z':
                # 闭合路径
                dml_commands.append('<a:close/>')

        return dml_commands

    def _to_emu(self, value: float) -> int:
        """SVG 坐标值转 EMU（假设 SVG 坐标 = 像素）"""
        return int(value * 0.75 * 12700)


def build_cust_geom_xml(d: str) -> str:
    """从 SVG path d 属性构建 DrawingML custGeom XML

    Args:
        d: SVG path 的 d 属性

    Returns:
        DrawingML custGeom XML 字符串
    """
    parser = SVGPathParser()
    path_commands = parser.parse(d)
    if not path_commands:
        return ""

    return (
        '<a:custGeom>'
        '<a:pathLst>'
        '<a:path w="12800" h="7200">'
        + "".join(path_commands) +
        '</a:path>'
        '</a:pathLst>'
        '</a:custGeom>'
    )
