"""SVG 后处理管线 — 7 步严格顺序处理

1. embed_icons       — 图标引用 → 内联 SVG 路径
2. flatten_tspan     — tspan 子元素 → 独立 text 元素
3. embed_images      — 外部图片引用 → Base64 内嵌
4. align_images      — 对齐图片坐标
5. fix_aspect        — 修复图片宽高比
6. crop_images       — 裁剪图片到边界
7. rect2path         — rect 元素 → path 元素
"""
import os
import re
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


class SVGFinalizer:
    """SVG 后处理器 — 7 步严格顺序"""

    def __init__(self, icon_dir: Optional[str] = None):
        self.icon_dir = icon_dir

    def process(self, svg_content: str, images_dir: Optional[str] = None) -> str:
        """完整处理 SVG 内容

        Args:
            svg_content: SVG XML 内容
            images_dir: 图片目录（用于内嵌图片路径解析）

        Returns:
            处理后的 SVG XML 内容
        """
        root = ET.fromstring(svg_content)

        # Step 1: 嵌入图标
        root = self.embed_icons(root)

        # Step 2: 展平 tspan
        root = self.flatten_tspan(root)

        # Step 3: 嵌入图片
        root = self.embed_images(root, images_dir)

        # Step 4: 对齐图片坐标（取整到像素边界防模糊）
        root = self.align_images(root)

        # Step 5: 修复图片宽高比
        root = self.fix_aspect(root)

        # Step 6: 裁剪图片到边界
        root = self.crop_images(root)

        # Step 7: rect → path（如圆角 rect 需要精确转换）
        root = self.rect2path(root)

        # 转回字符串
        processed = ET.tostring(root, encoding="unicode", method="xml")
        return processed

    def embed_icons(self, root: ET.Element) -> ET.Element:
        """Step 1: 嵌入图标 — 用内联路径替换图标引用"""
        # 查找所有使用 'icon-' 类名或特定属性标记的图标
        ns = {"svg": SVG_NS}
        icons = root.findall(".//*[@class]", ns)
        for elem in icons:
            classes = elem.get("class", "").split()
            icon_classes = [c for c in classes if c.startswith("icon-")]
            if icon_classes and self.icon_dir:
                icon_name = icon_classes[0].replace("icon-", "")
                icon_path = os.path.join(self.icon_dir, f"{icon_name}.svg")
                if os.path.exists(icon_path):
                    try:
                        icon_svg = ET.parse(icon_path)
                        icon_root = icon_svg.getroot()
                        # 将图标路径复制到当前位置
                        for path_elem in icon_root.findall(".//svg:path", ns):
                            elem.append(path_elem)
                    except Exception as e:
                        logger.warning(f"嵌入图标 {icon_name} 失败: {e}")

        return root

    def flatten_tspan(self, root: ET.Element) -> ET.Element:
        """Step 2: 展平 tspan — 将 <text> 内的 <tspan> 子元素提升为独立 <text>"""
        ns = {"svg": SVG_NS}
        text_elements = list(root.findall(".//svg:text", ns))

        for text_elem in text_elements:
            tspans = text_elem.findall("svg:tspan", ns)
            if not tspans:
                continue

            parent = root
            text_idx = list(root).index(text_elem)

            for i, tspan in enumerate(tspans):
                # 创建新的 text 元素
                new_text = ET.Element(f"{{{SVG_NS}}}text")
                # 复制父 text 的属性
                new_text.attrib.update(text_elem.attrib)
                # 用 tspan 属性覆盖
                for key, val in tspan.attrib.items():
                    new_text.set(key, val)
                new_text.text = tspan.text

                if i == 0:
                    # 替换原 text 元素
                    text_elem.tag = new_text.tag
                    text_elem.attrib.clear()
                    text_elem.attrib.update(new_text.attrib)
                    text_elem.text = new_text.text
                    for child in list(text_elem):
                        text_elem.remove(child)
                else:
                    # 在 text_elem 后插入
                    insert_idx = list(parent).index(text_elem) + i - 1
                    parent.insert(insert_idx + 1, new_text)

        return root

    def embed_images(self, root: ET.Element, images_dir: Optional[str] = None) -> ET.Element:
        """Step 3: 嵌入图片 — 将外部图片引用转为 Base64 内嵌"""
        import base64

        ns = {"svg": SVG_NS, "xlink": XLINK_NS}
        images = root.findall(".//svg:image", ns)

        for img in images:
            href = img.get(f"{{{XLINK_NS}}}href") or img.get("href", "")
            if not href or href.startswith("data:"):
                continue

            # 解析图片路径
            img_path = None
            if images_dir and not os.path.isabs(href):
                candidate = os.path.join(images_dir, href)
                if os.path.exists(candidate):
                    img_path = candidate
            elif os.path.exists(href):
                img_path = href

            if img_path:
                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()
                    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
                    if ext in ("jpg", "jpeg"):
                        ext = "jpeg"
                    b64_str = base64.b64encode(img_bytes).decode("ascii")
                    data_uri = f"data:image/{ext};base64,{b64_str}"

                    # 替换 href 属性
                    if f"{{{XLINK_NS}}}href" in img.attrib:
                        img.set(f"{{{XLINK_NS}}}href", data_uri)
                    else:
                        img.set("href", data_uri)

                    logger.info(f"已嵌入图片: {href}")
                except Exception as e:
                    logger.warning(f"嵌入图片 {href} 失败: {e}")

        return root

    def align_images(self, root: ET.Element) -> ET.Element:
        """Step 4: 对齐图片坐标 — 取整到像素边界防止渲染模糊"""
        ns = {"svg": SVG_NS}
        images = root.findall(".//svg:image", ns)
        for img in images:
            for attr in ("x", "y", "width", "height"):
                val = img.get(attr)
                if val:
                    try:
                        rounded = round(float(val))
                        img.set(attr, str(rounded))
                    except ValueError:
                        pass
        return root

    def fix_aspect(self, root: ET.Element) -> ET.Element:
        """Step 5: 修复图片宽高比 — 确保 preserveAspectRatio 正确处理"""
        ns = {"svg": SVG_NS}
        images = root.findall(".//svg:image", ns)
        for img in images:
            # 已有 preserveAspectRatio 则跳过
            if img.get("preserveAspectRatio"):
                continue
            w_str = img.get("width", "0")
            h_str = img.get("height", "0")
            try:
                w = float(w_str)
                h = float(h_str)
            except ValueError:
                continue
            if w > 0 and h > 0:
                # 对非正方形的图片设置合理的缩放策略
                ratio = w / h
                if abs(ratio - 1.0) > 0.05:
                    img.set("preserveAspectRatio", "xMidYMid meet")
        return root

    def crop_images(self, root: ET.Element) -> ET.Element:
        """Step 6: 裁剪图片到边界 — 用 clipPath 包裹超出 viewBox 的图片"""
        ns = {"svg": SVG_NS}
        svg_elem = root
        vb = svg_elem.get("viewBox", "")
        if not vb:
            return root
        try:
            parts = vb.split()
            vb_x, vb_y, vb_w, vb_h = map(float, parts[:4])
        except (ValueError, IndexError):
            return root

        images = root.findall(".//svg:image", ns)
        clipped = []
        for img in images:
            try:
                ix = float(img.get("x", "0"))
                iy = float(img.get("y", "0"))
                iw = float(img.get("width", "0"))
                ih = float(img.get("height", "0"))
            except ValueError:
                continue
            # 只在图片明显超出 viewBox 时才裁剪
            if (ix < vb_x - 5 or iy < vb_y - 5 or
                    ix + iw > vb_x + vb_w + 5 or iy + ih > vb_y + vb_h + 5):
                clip_id = f"img-clip-{len(clipped) + 1}"
                clip_x = max(ix, vb_x)
                clip_y = max(iy, vb_y)
                clip_w = min(ix + iw, vb_x + vb_w) - clip_x
                clip_h = min(iy + ih, vb_y + vb_h) - clip_y
                if clip_w > 0 and clip_h > 0:
                    clipped.append((img, clip_id, clip_x, clip_y, clip_w, clip_h))

        if not clipped:
            return root

        defs = root.find("svg:defs", ns)
        if defs is None:
            defs = ET.SubElement(root, f"{{{SVG_NS}}}defs")
            # 将 defs 移到最前面
            root.remove(defs)
            root.insert(0, defs)

        for img, clip_id, cx, cy, cw, ch in clipped:
            clip_path = ET.SubElement(
                defs, f"{{{SVG_NS}}}clipPath",
                attrib={"id": clip_id, "clipPathUnits": "userSpaceOnUse"},
            )
            ET.SubElement(clip_path, f"{{{SVG_NS}}}rect",
                          attrib={"x": str(cx), "y": str(cy),
                                  "width": str(cw), "height": str(ch)})
            # 更新图片 x/y（对齐裁剪区域）
            img.set("x", str(cx))
            img.set("y", str(cy))
            img.set("clip-path", f"url(#{clip_id})")
            logger.info(f"裁剪图片到 viewBox 边界: {clip_id}")

        return root

    def rect2path(self, root: ET.Element) -> ET.Element:
        """Step 7: 带 rx/ry 的 rect → path 元素，以确保精确圆角"""
        ns = {"svg": SVG_NS}
        rects = list(root.findall(".//svg:rect", ns))
        for rect in rects:
            rx_str = rect.get("rx")
            ry_str = rect.get("ry")
            if rx_str is None and ry_str is None:
                continue
            try:
                x = float(rect.get("x", "0"))
                y = float(rect.get("y", "0"))
                w = float(rect.get("width", "0"))
                h = float(rect.get("height", "0"))
                rx = float(rx_str) if rx_str else (float(ry_str) if ry_str else 0)
                ry = float(ry_str) if ry_str else rx
            except (ValueError, TypeError):
                continue
            if w <= 0 or h <= 0:
                continue
            # 限制圆角半径不超过边长的 50%
            rx = min(rx, w / 2)
            ry = min(ry, h / 2)
            if rx <= 0 and ry <= 0:
                continue
            # 收集 rect 的其他属性（fill, stroke 等）
            other_attrs = {k: v for k, v in rect.attrib.items()
                           if k not in ("x", "y", "width", "height", "rx", "ry")}

            # 构造圆角矩形 path: M x+rx y → A rx ry 0 0 1 x+w y → ... 闭合
            d = (f"M{x + rx},{y} "
                 f"L{x + w - rx},{y} "
                 f"A{rx},{ry} 0 0,1 {x + w},{y + ry} "
                 f"L{x + w},{y + h - ry} "
                 f"A{rx},{ry} 0 0,1 {x + w - rx},{y + h} "
                 f"L{x + rx},{y + h} "
                 f"A{rx},{ry} 0 0,1 {x},{y + h - ry} "
                 f"L{x},{y + ry} "
                 f"A{rx},{ry} 0 0,1 {x + rx},{y} Z")

            path = ET.Element(f"{{{SVG_NS}}}path", attrib={"d": d, **other_attrs})
            parent = root
            idx = list(root).index(rect)
            parent.remove(rect)
            parent.insert(idx, path)

        return root


def process_svg_file(
    input_path: str,
    output_path: Optional[str] = None,
    icon_dir: Optional[str] = None,
    images_dir: Optional[str] = None,
) -> str:
    """处理单个 SVG 文件

    Args:
        input_path: 输入 SVG 文件路径
        output_path: 可选的输出文件路径（默认覆盖原文件）
        icon_dir: 图标目录
        images_dir: 图片目录

    Returns:
        处理后的 SVG 内容
    """
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    finalizer = SVGFinalizer(icon_dir=icon_dir)
    processed = finalizer.process(content, images_dir=images_dir)

    output = output_path or input_path
    with open(output, "w", encoding="utf-8") as f:
        f.write(processed)

    logger.info(f"SVG 处理后保存: {output}")
    return processed


def process_svg_batch(
    input_dir: str,
    output_dir: Optional[str] = None,
    icon_dir: Optional[str] = None,
    images_dir: Optional[str] = None,
) -> List[str]:
    """批量处理 SVG 文件

    Args:
        input_dir: 输入 SVG 目录
        output_dir: 可选的输出目录
        icon_dir: 图标目录
        images_dir: 图片目录

    Returns:
        处理后的文件路径列表
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir) if output_dir else input_path
    output_path.mkdir(parents=True, exist_ok=True)

    processed_files = []
    for svg_file in sorted(input_path.glob("slide_*.svg")):
        out_file = output_path / svg_file.name
        process_svg_file(
            str(svg_file),
            str(out_file),
            icon_dir=icon_dir,
            images_dir=images_dir,
        )
        processed_files.append(str(out_file))

    return processed_files
