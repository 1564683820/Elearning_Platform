"""PPTX 母版/主题注入器

通过解包 .pptx 修改其中的 theme1.xml 来注入自定义配色和字体方案。
无需自行构建完整母版 XML。
"""

import os
import zipfile
import tempfile
import shutil
import logging
from typing import Optional, Dict
from lxml import etree

logger = logging.getLogger(__name__)

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

# 默认配色 12 色
DEFAULT_COLOR_MAP: Dict[str, str] = {
    "dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6",
    "accent1": "1A56DB", "accent2": "7E3AF2", "accent3": "F59E0B",
    "accent4": "10B981", "accent5": "EF4444", "accent6": "6366F1",
    "hlink": "0563C1", "folHlink": "954F72",
}


def inject_theme(
    pptx_path: str,
    color_map: Optional[Dict[str, str]] = None,
    font_major: str = "Arial",
    font_minor: str = "Calibri",
    font_east_asia: str = "Microsoft YaHei",
) -> str:
    """注入自定义配色和字体到现有 .pptx 的 theme 中

    解包 → 修改 theme/theme1.xml → 重新打包。
    保留原文件结构不变。

    Args:
        pptx_path: 源 .pptx 路径
        color_map: 12 色映射 {dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink}
        font_major: 标题字体
        font_minor: 正文字体
        font_east_asia: 东亚字体

    Returns:
        修改后的 .pptx 路径（同路径覆盖）
    """
    if not os.path.exists(pptx_path):
        logger.warning(f"PPTX 文件不存在: {pptx_path}")
        return pptx_path

    cm = color_map or DEFAULT_COLOR_MAP
    temp_dir = tempfile.mkdtemp(prefix="pptx_theme_")
    try:
        # 解包
        with zipfile.ZipFile(pptx_path, "r") as z:
            z.extractall(temp_dir)

        # 查找 theme1.xml
        theme_path = None
        for root, _dirs, files in os.walk(temp_dir):
            for f in files:
                if f == "theme1.xml":
                    theme_path = os.path.join(root, f)
                    break

        if not theme_path:
            logger.warning("未找到 theme1.xml")
            return pptx_path

        # 修改配色
        tree = etree.parse(theme_path)
        root_elem = tree.getroot()

        # 查找 clrScheme
        clr_scheme = root_elem.find(f".//{{{NS_A}}}clrScheme")
        if clr_scheme is not None:
            for tag_name, hex_val in cm.items():
                tag = clr_scheme.find(f"{{{NS_A}}}{tag_name}")
                if tag is not None:
                    srgb = tag.find(f"{{{NS_A}}}srgbClr")
                    if srgb is not None:
                        srgb.set("val", hex_val)

        # 查找 fontScheme
        font_scheme = root_elem.find(f".//{{{NS_A}}}fontScheme")
        if font_scheme is not None:
            for scheme_type in ("majorFont", "minorFont"):
                scheme = font_scheme.find(f"{{{NS_A}}}{scheme_type}")
                if scheme is not None:
                    latin = scheme.find(f"{{{NS_A}}}latin")
                    if latin is not None:
                        latin.set("typeface", font_major if scheme_type == "majorFont" else font_minor)
                    ea = scheme.find(f"{{{NS_A}}}ea")
                    if ea is not None:
                        ea.set("typeface", font_east_asia)

        tree.write(theme_path, xml_declaration=True, encoding="UTF-8", standalone=True)

        # 重新打包
        os.remove(pptx_path)
        with zipfile.ZipFile(pptx_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _dirs, files in os.walk(temp_dir):
                for f in files:
                    file_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_path, temp_dir)
                    z.write(file_path, arcname)

        logger.info(f"主题配色已注入: {pptx_path}")
        return pptx_path

    except Exception as e:
        logger.error(f"注入主题失败: {e}")
        return pptx_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
