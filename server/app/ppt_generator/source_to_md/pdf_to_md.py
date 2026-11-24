"""PDF → Markdown 转换器
使用 pdfplumber + pypdf 提取文本、表格、图片，支持 OCR 回退。
"""
import re
import logging
from pathlib import Path
from typing import Optional
import pdfplumber
from PIL import Image
import io

logger = logging.getLogger(__name__)


class PDFConverter:
    """PDF 到 Markdown 的转换器"""

    def __init__(self, ocr_fallback: bool = False):
        self.ocr_fallback = ocr_fallback

    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        将 PDF 文件转换为 Markdown 文本

        Args:
            pdf_path: PDF 文件路径
            output_path: 可选的输出文件路径

        Returns:
            Markdown 格式的文本内容
        """
        md_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                md_parts.append(f"\n\n## 第 {page_num} 页\n")
                md_parts.extend(self._extract_page_content(page, page_num))

        md_text = "".join(md_parts)
        md_text = self._clean_text(md_text)

        if output_path:
            Path(output_path).write_text(md_text, encoding="utf-8")

        return md_text

    def _extract_page_content(self, page, page_num: int) -> list:
        """提取单页内容"""
        parts = []

        # 1. 提取表格
        tables = page.extract_tables()
        if tables:
            for table in tables:
                md_table = self._table_to_markdown(table)
                if md_table:
                    parts.append(md_table)

        # 2. 提取文本
        text = page.extract_text()
        if text:
            # 过滤页眉页脚噪声
            lines = text.split("\n")
            clean_lines = [l for l in lines if not self._is_header_footer(l, page_num)]
            parts.append("\n".join(clean_lines))

        # 3. 提取图片
        images = page.images
        if images:
            for img in images:
                parts.append(f"\n![图片_{page_num}_{img.get('name', '')}]({img.get('name', '')})\n")

        return parts

    def _table_to_markdown(self, table: list) -> str:
        """将表格数据转换为 Markdown 表格格式"""
        if not table or not table[0]:
            return ""

        rows = []
        for row in table:
            rows.append("| " + " | ".join(cell.replace("\n", " ") if cell else "" for cell in row) + " |")

        if not rows:
            return ""

        # 分隔行
        header_sep = "| " + " | ".join("---" for _ in table[0]) + " |"
        return "\n".join([rows[0], header_sep] + rows[1:]) + "\n\n"

    def _is_header_footer(self, line: str, page_num: int) -> bool:
        """判断是否为页眉页脚噪声行"""
        line = line.strip()
        if not line:
            return True
        # 页码行
        if re.match(r'^\d+$', line):
            return True
        if f"- {page_num} -" in line or f"{page_num}" == line:
            return True
        return False

    def _clean_text(self, text: str) -> str:
        """清理提取的文本"""
        # 合并多余空行
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        # 移除孤立的页码
        text = re.sub(r'\n\d+\n', '\n', text)
        return text.strip()

    def extract_images(self, pdf_path: str, output_dir: str) -> list:
        """从 PDF 中提取图片"""
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        image_paths = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images()
            for idx, img in enumerate(images):
                xref = img[0]
                base = doc.extract_image(xref)
                image_bytes = base["image"]
                ext = base["ext"]
                img_path = Path(output_dir) / f"img_p{page_num + 1}_{idx + 1}.{ext}"
                img_path.write_bytes(image_bytes)
                image_paths.append(str(img_path))

        doc.close()
        return image_paths
