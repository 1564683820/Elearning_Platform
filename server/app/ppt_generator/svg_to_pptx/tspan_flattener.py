"""tspan 展平工具 — 将 <text> 内的 <tspan> 子元素展开为独立 <text> 元素"""
import xml.etree.ElementTree as ET


def flatten_tspans(svg_root: ET.Element) -> None:
    """将 SVG 文档中所有 <tspan> 展平为独立 <text> 元素

    遍历所有 <text> 元素，将内部的 <tspan> 子元素提升为独立的 <text>，
    保留各自的 x/y/dx/dy 偏移属性。

    Args:
        svg_root: SVG XML 根元素
    """
    ns = {"svg": "http://www.w3.org/2000/svg"}
    text_elements = svg_root.findall(".//svg:text", ns)

    for text_elem in text_elements:
        tspans = text_elem.findall("svg:tspan", ns)
        if not tspans:
            continue

        parent = text_elem.tag  # 可能是 {ns}text

        for i, tspan in enumerate(tspans):
            # 创建新的 text 元素
            new_text = ET.Element(text_elem.tag)
            # 复制 tspan 的属性和文本
            new_text.attrib.update(text_elem.attrib)
            # 用 tspan 的属性覆盖
            for key, val in tspan.attrib.items():
                new_text.set(key, val)
            new_text.text = tspan.text

            # 计算偏移
            dx = float(tspan.get("dx", 0))
            dy = float(tspan.get("dy", 0))
            if dx != 0 or dy != 0:
                x = float(text_elem.get("x", 0))
                y = float(text_elem.get("y", 0))
                new_text.set("x", str(x + dx))
                new_text.set("y", str(y + dy))

            # 在 text_elem 之后插入
            parent_elem = svg_root if "." in parent else svg_root

            if i == 0:
                # 第一个 tspan — 替换原 text 元素
                text_elem.tag = new_text.tag
                text_elem.attrib.clear()
                text_elem.attrib.update(new_text.attrib)
                text_elem.text = new_text.text
                # 清除子元素
                for child in list(text_elem):
                    text_elem.remove(child)
            else:
                # 后续 tspan — 在 text_elem 之后插入新的 text
                parent_elem = svg_root
                insert_idx = list(parent_elem).index(text_elem) + i
                parent_elem.insert(insert_idx, new_text)
