"""DOCX → Markdown 转换器
使用 python-docx 提取段落、标题、列表、表格、图片。
"""
import logging
from pathlib import Path
from typing import Optional
from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)


class DOCXConverter:
    """Word 文档到 Markdown 的转换器"""

    def convert(self, docx_path: str, output_path: Optional[str] = None) -> str:
        """
        将 DOCX 文件转换为 Markdown 文本

        Args:
            docx_path: DOCX 文件路径
            output_path: 可选的输出文件路径

        Returns:
            Markdown 格式的文本内容
        """
        doc = Document(docx_path)
        md_parts = []
        in_table = False

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                # 段落
                para = self._find_paragraph(doc, element)
                if para is None:
                    continue
                md_parts.extend(self._paragraph_to_md(para))
                in_table = False

            elif tag == "tbl":
                # 表格
                table = self._find_table(doc, element)
                if table:
                    md_parts.append("\n" + self._table_to_markdown(table) + "\n")
                in_table = True

        md_text = "\n".join(md_parts)
        # 合并多余空行
        import re
        md_text = re.sub(r'\n{4,}', '\n\n\n', md_text)

        if output_path:
            Path(output_path).write_text(md_text, encoding="utf-8")

        return md_text

    def _find_paragraph(self, doc, element):
        """通过 oxml 元素找到对应的 Paragraph 对象"""
        for para in doc.paragraphs:
            if para._element is element:
                return para
        return None

    def _find_table(self, doc, element):
        """通过 oxml 元素找到对应的 Table 对象"""
        for table in doc.tables:
            if table._element is element:
                return table
        return None

    def _paragraph_to_md(self, para) -> list:
        """将段落转换为 Markdown 行"""
        lines = []
        text = para.text.strip()
        if not text:
            return lines

        style = para.style.name.lower() if para.style and para.style.name else ""

        if "heading 1" in style or "heading1" in style:
            lines.append(f"\n# {text}\n")
        elif "heading 2" in style or "heading2" in style:
            lines.append(f"\n## {text}\n")
        elif "heading 3" in style or "heading3" in style:
            lines.append(f"\n### {text}\n")
        elif "list" in style or para._element.find(qn('w:numPr')) is not None:
            lines.append(f"- {text}")
        else:
            lines.append(text)

        return lines

    def _table_to_markdown(self, table) -> str:
        """将 Word 表格转换为 Markdown 表格"""
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append("| " + " | ".join(cells) + " |")

        if not rows:
            return ""

        # 分隔行
        header_sep = "| " + " | ".join("---" for _ in table.rows[0].cells) + " |"
        return "\n".join([rows[0], header_sep] + rows[1:])

    def extract_images(self, docx_path: str, output_dir: str) -> list:
        """从 DOCX 中提取图片"""
        doc = Document(docx_path)
        image_paths = []
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_data = rel.target_part.blob
                ext = rel.target_ref.split(".")[-1] if "." in rel.target_ref else "png"
                img_path = output_dir / f"docx_img_{len(image_paths) + 1}.{ext}"
                img_path.write_bytes(image_data)
                image_paths.append(str(img_path))

        return image_paths
