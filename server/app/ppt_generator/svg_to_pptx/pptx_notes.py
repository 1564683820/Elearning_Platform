"""PPTX 备注写入工具"""
import logging
from lxml import etree
from typing import List

logger = logging.getLogger(__name__)

# 备注幻灯片 XML 模板
NOTES_SLIDE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
         xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name="Notes"/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Notes Text"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="0" y="0"/>
            <a:ext cx="6858000" cy="4572000"/>
          </a:xfrm>
          <a:prstGeom prst="rect"/>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" rtlCol="0"/>
          {paragraphs}
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:notes>"""


def build_notes_xml(notes_text: str) -> str:
    """构建备注幻灯片 XML

    Args:
        notes_text: 备注文本（支持换行分割为多个段落）

    Returns:
        备注幻灯片 XML 字符串
    """
    if not notes_text:
        return ""

    paragraphs = []
    for line in notes_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        from .drawingml_utils import escape_xml
        safe_text = escape_xml(line)
        para_xml = (
            f'<a:p>'
            f'<a:r><a:rPr lang="en-US" sz="1400"/>'
            f'<a:t>{safe_text}</a:t></a:r>'
            f'</a:p>'
        )
        paragraphs.append(para_xml)

    if not paragraphs:
        return ""

    return NOTES_SLIDE_TEMPLATE.format(paragraphs="\n".join(paragraphs))


def add_notes_to_slide(slide_element, notes_text: str):
    """向现有的幻灯片 XML 元素添加备注

    Args:
        slide_element: python-pptx Slide 的 _element
        notes_text: 备注文本
    """
    from pptx.oxml.ns import qn

    if not notes_text:
        return

    try:
        notes_xml = build_notes_xml(notes_text)
        if notes_xml:
            notes_elem = etree.fromstring(notes_xml.encode("utf-8"))
            slide_element.addnext(notes_elem)
    except Exception as e:
        logger.warning(f"添加备注失败: {e}")
