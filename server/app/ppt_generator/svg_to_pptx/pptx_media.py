"""PPTX 媒体嵌入工具"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def collect_media_from_svg(svg_content: str, base_dir: str) -> List[Dict]:
    """从 SVG 内容中收集所有引用的媒体文件

    Args:
        svg_content: SVG XML 内容
        base_dir: 基础目录（用于解析相对路径）

    Returns:
        媒体文件信息列表: [{"path": "...", "xlink": "..."}, ...]
    """
    import re
    media = []

    # 查找 xlink:href 和 href 属性
    # 匹配 <image ... href="..." .../>
    hrefs = re.findall(r'(?:xlink:href|href)\s*=\s*["\']([^"\']+)["\']', svg_content)
    for href in hrefs:
        # 排除 data: URI
        if href.startswith("data:"):
            continue
        # 解析路径
        abs_path = href if os.path.isabs(href) else os.path.join(base_dir, href)
        if os.path.exists(abs_path):
            media.append({"path": abs_path, "xlink": href})
        else:
            logger.warning(f"媒体文件未找到: {abs_path}")

    return media


def extract_base64_images(svg_content: str, output_dir: str) -> Dict[str, str]:
    """从 SVG 内容中提取 base64 图片并保存为文件

    Args:
        svg_content: SVG XML 内容
        output_dir: 输出目录

    Returns:
        href → 文件路径 的映射
    """
    import re
    import base64
    from mimetypes import guess_extension

    mapping = {}
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pattern = r'data:image/(\w+);base64,([^"\']+)'
    matches = re.findall(pattern, svg_content)
    for idx, (ext, b64_data) in enumerate(matches):
        try:
            img_bytes = base64.b64decode(b64_data)
            ext = ext or "png"
            if ext == "jpeg":
                ext = "jpg"
            file_name = f"embedded_img_{idx + 1}.{ext}"
            file_path = output_path / file_name
            file_path.write_bytes(img_bytes)
            mapping[f"data:image/{ext};base64,{b64_data}"] = str(file_path)
        except Exception as e:
            logger.error(f"提取 base64 图片 {idx} 失败: {e}")

    return mapping
