"""SVG 质量检查器 — 检查禁用元素/属性/viewBox/图片引用/文本溢出"""
import re
import logging
from typing import List, Dict, Tuple
import xml.etree.ElementTree as ET
from ..config import FORBIDDEN_ELEMENTS, FORBIDDEN_ATTRIBUTES

logger = logging.getLogger(__name__)


class QualityIssue:
    """质量检查发现的问题"""

    def __init__(self, severity: str, message: str, line: int = 0, element: str = ""):
        self.severity = severity  # "error" | "warning"
        self.message = message
        self.line = line
        self.element = element

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] L{self.line}: {self.message}"


class SVGQualityChecker:
    """SVG 质量检查器

    检查项:
    - error: 禁用元素、禁用属性、缺少 viewBox
    - warning: 外部图片引用、文本溢出、tspan 嵌入
    """

    SVG_NS = "http://www.w3.org/2000/svg"

    def __init__(self, viewbox_w: float = 1280, viewbox_h: float = 720):
        self.viewbox_w = viewbox_w
        self.viewbox_h = viewbox_h

    def check(self, svg_content: str) -> List[QualityIssue]:
        """执行质量检查

        Args:
            svg_content: SVG XML 内容

        Returns:
            检查出的问题列表
        """
        issues = []

        # 1. 基础 XML 解析检查
        try:
            root = ET.fromstring(svg_content)
        except ET.ParseError as e:
            issues.append(QualityIssue("error", f"XML 解析失败: {e}"))
            return issues

        # 2. 检查 viewBox
        self._check_viewbox(root, issues)

        # 3. 递归检查禁用元素和属性
        self._check_element(root, issues, svg_content)

        # 4. 检查图片引用
        self._check_images(root, svg_content, issues)

        # 5. 检查文本溢出
        self._check_text_overflow(root, issues)

        return issues

    def _check_viewbox(self, root: ET.Element, issues: List[QualityIssue]):
        """检查 viewBox 属性"""
        vb = root.get("viewBox")
        if not vb:
            issues.append(QualityIssue("error", "缺少 viewBox 属性", element="svg"))
        else:
            parts = vb.strip().split()
            if len(parts) != 4:
                issues.append(QualityIssue("error", f"viewBox 格式无效: {vb}", element="svg"))
            else:
                try:
                    w, h = float(parts[2]), float(parts[3])
                    if w <= 0 or h <= 0:
                        issues.append(QualityIssue("error", f"viewBox 尺寸无效: {w}x{h}", element="svg"))
                except ValueError:
                    issues.append(QualityIssue("error", f"viewBox 包含非数字值: {vb}", element="svg"))

    def _check_element(self, elem: ET.Element, issues: List[QualityIssue], raw_svg: str):
        """递归检查元素"""
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        # 检查禁用元素
        if tag in FORBIDDEN_ELEMENTS:
            line = self._find_line_number(raw_svg, tag)
            issues.append(QualityIssue("error", f"禁用元素: <{tag}>", line, tag))

        # 检查禁用属性
        for attr in elem.attrib:
            attr_name = attr.split("}")[-1] if "}" in attr else attr
            if attr_name.lower() in FORBIDDEN_ATTRIBUTES:
                line = self._find_line_number(raw_svg, attr)
                issues.append(QualityIssue("error", f"禁用属性: {attr_name}", line, f"<{tag}>"))

        # 检查 use 元素
        if tag == "use":
            issues.append(QualityIssue("error", "<use> 元素禁止使用", element="use"))

        # 递归子元素
        for child in elem:
            self._check_element(child, issues, raw_svg)

    def _check_images(self, root: ET.Element, raw_svg: str, issues: List[QualityIssue]):
        """检查图片引用"""
        ns = {"svg": self.SVG_NS}
        images = root.findall(".//svg:image", ns)
        for img in images:
            href = img.get("{http://www.w3.org/1999/xlink}href") or img.get("href", "")
            if href and not href.startswith("data:"):
                line = self._find_line_number(raw_svg, href[:30])
                issues.append(QualityIssue("warning", f"外部图片引用: {href[:50]}...", line, "image"))

    def _check_text_overflow(self, root: ET.Element, issues: List[QualityIssue]):
        """检查文本是否可能溢出"""
        ns = {"svg": self.SVG_NS}
        texts = root.findall(".//svg:text", ns)
        for text in texts:
            x = float(text.get("x", 0))
            y = float(text.get("y", 0))
            content = (text.text or "") + "".join(
                (child.text or "") + (child.tail or "")
                for child in text
            )
            if content and len(content) > 50:
                # 粗略估计：中文字符约 1em，英文字符约 0.6em
                font_size = float(text.get("font-size", "18").replace("px", ""))
                estimated_w = len(content) * font_size * 0.6
                remaining_w = self.viewbox_w - x
                if estimated_w > remaining_w:
                    issues.append(QualityIssue(
                        "warning", f"文本可能溢出: \"{content[:30]}...\" 估计宽{estimated_w:.0f}px > 剩余{remaining_w:.0f}px",
                        element="text",
                    ))

    def _find_line_number(self, content: str, target: str) -> int:
        """在内容中查找目标字符串的大致行号"""
        idx = content.find(target)
        if idx == -1:
            return 0
        return content[:idx].count("\n") + 1

    def has_errors(self, issues: List[QualityIssue]) -> bool:
        """检查是否存在 error 级别的问题"""
        return any(i.severity == "error" for i in issues)

    def has_warnings(self, issues: List[QualityIssue]) -> bool:
        """检查是否存在 warning 级别的问题"""
        return any(i.severity == "warning" for i in issues)

    def print_report(self, issues: List[QualityIssue]):
        """打印质量报告"""
        if not issues:
            logger.info("✓ SVG 质量检查通过，无问题")
            return

        for issue in issues:
            prefix = "✗" if issue.severity == "error" else "⚠"
            logger.info(f"{prefix} {issue}")

        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        logger.info(f"总计: {error_count} 个错误, {warning_count} 个警告")

    def check_and_report(self, svg_content: str) -> Tuple[bool, List[QualityIssue]]:
        """检查并报告结果

        Args:
            svg_content: SVG XML 内容

        Returns:
            (是否通过, 问题列表)
        """
        issues = self.check(svg_content)
        self.print_report(issues)
        return not self.has_errors(issues), issues
