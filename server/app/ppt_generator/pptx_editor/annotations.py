# 注解与元素编辑工具
# 管理 SVG 元素的 data-edit-target / data-edit-annotation 标记及直接属性修改

import xml.etree.ElementTree as ET
import re
from copy import deepcopy
from typing import Optional

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def assign_temp_ids(root: ET.Element) -> None:
    """为没有 id 的元素分配 _edit_N 临时 id"""
    for elem in root.iter():
        eid = elem.get("id", "")
        if eid.startswith("_edit_"):
            elem.attrib.pop("id", None)
    counter = 0
    for elem in root.iter():
        if elem is root:
            continue
        if elem.get("id") is None:
            elem.set("id", f"_edit_{counter}")
            counter += 1


def _find_by_id(root: ET.Element, element_id: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if elem.get("id") == element_id:
            return elem
    return None


def _find_with_parent(root: ET.Element, element_id: str
                      ) -> tuple[Optional[ET.Element], Optional[ET.Element]]:
    for parent in root.iter():
        for child in list(parent):
            if child.get("id") == element_id:
                return child, parent
    return None, None


def _local_name(elem: ET.Element) -> str:
    return elem.tag.split("}", 1)[1] if "}" in elem.tag else elem.tag


def _first_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _format_number(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _tspan_baseline(text_el: ET.Element, tspan_el: ET.Element
                    ) -> Optional[tuple[float, float]]:
    cur_x = _first_number(text_el.get("x"))
    cur_y = _first_number(text_el.get("y"))
    for child in list(text_el):
        if _local_name(child) != "tspan":
            continue
        x_val = _first_number(child.get("x"))
        y_val = _first_number(child.get("y"))
        dx_val = _first_number(child.get("dx"))
        dy_val = _first_number(child.get("dy"))
        if x_val is not None:
            cur_x = x_val
        elif dx_val is not None:
            cur_x = (cur_x or 0.0) + dx_val
        if y_val is not None:
            cur_y = y_val
        elif dy_val is not None:
            cur_y = (cur_y or 0.0) + dy_val
        if child is tspan_el:
            break
    if cur_x is None or cur_y is None:
        return None
    return cur_x, cur_y


def _adjust_following_tspan_dy(text_el: ET.Element, target: ET.Element) -> None:
    children = list(text_el)
    try:
        idx = children.index(target)
    except ValueError:
        return
    if idx + 1 >= len(children):
        return
    next_el = children[idx + 1]
    if (_local_name(next_el) != "tspan" or next_el.get("y") is not None
            or next_el.get("dy") is None):
        return
    next_baseline = _tspan_baseline(text_el, next_el)
    if next_baseline is None:
        return
    prev_y: Optional[float] = None
    for prior in reversed(children[:idx]):
        if _local_name(prior) != "tspan":
            continue
        prior_baseline = _tspan_baseline(text_el, prior)
        if prior_baseline is not None:
            prev_y = prior_baseline[1]
            break
    if prev_y is None:
        prev_y = _first_number(text_el.get("y")) or 0.0
    next_el.set("dy", _format_number(next_baseline[1] - prev_y))


def _copy_text_attrs(src: ET.Element, dst: ET.Element, skip: set[str]) -> None:
    for key, value in src.attrib.items():
        if key not in skip:
            dst.set(key, value)


def promote_tspan_to_text(root: ET.Element, element_id: str, x: str, y: str
                          ) -> tuple[bool, Optional[str]]:
    """将 <text> 下的 <tspan> 升级为独立的 <text> 元素"""
    target, text_el = _find_with_parent(root, element_id)
    if target is None or text_el is None:
        return False, "not-found"
    if _local_name(target) != "tspan" or _local_name(text_el) != "text":
        return False, "not-tspan"
    grandparent: Optional[ET.Element] = None
    for candidate in root.iter():
        if text_el in list(candidate):
            grandparent = candidate
            break
    if grandparent is None:
        return False, "parent-not-found"
    _adjust_following_tspan_dy(text_el, target)
    new_text = ET.Element(f"{{{SVG_NS}}}text")
    _copy_text_attrs(text_el, new_text, {"id", "x", "y", "dx", "dy"})
    _copy_text_attrs(target, new_text, {"id", "x", "y", "dx", "dy", "transform"})
    new_text.set("id", element_id)
    new_text.set("x", x)
    new_text.set("y", y)
    if len(list(target)) == 0:
        new_text.text = "".join(target.itertext())
    else:
        new_text.text = target.text
        for child in list(target):
            new_text.append(deepcopy(child))
    target_index = list(text_el).index(target)
    tail = target.tail
    text_el.remove(target)
    if tail:
        if target_index == 0:
            text_el.text = (text_el.text or "") + tail
        else:
            prev = list(text_el)[target_index - 1]
            prev.tail = (prev.tail or "") + tail
    parent_index = list(grandparent).index(text_el)
    grandparent.insert(parent_index + 1, new_text)
    if not (text_el.text or "").strip() and len(list(text_el)) == 0:
        grandparent.remove(text_el)
    return True, None


def parse_annotations(root: ET.Element) -> list[dict]:
    """提取 SVG 中所有 data-edit-target 注解"""
    annotations = []
    for elem in root.iter():
        if elem.get("data-edit-target") == "true":
            annotations.append({
                "element_id": elem.get("id", ""),
                "tag": _local_name(elem),
                "annotation": elem.get("data-edit-annotation", ""),
            })
    return annotations


def set_annotation(root: ET.Element, element_id: str, annotation: str) -> bool:
    """设置元素注解标记"""
    elem = _find_by_id(root, element_id)
    if elem is None:
        return False
    elem.set("data-edit-target", "true")
    elem.set("data-edit-annotation", annotation)
    return True


def remove_annotation(root: ET.Element, element_id: str) -> bool:
    elem = _find_by_id(root, element_id)
    if elem is None:
        return False
    elem.attrib.pop("data-edit-target", None)
    elem.attrib.pop("data-edit-annotation", None)
    return True


# ---- 直接编辑（AI 免提）----

PROTECTED_ATTRS = frozenset({"id", "class", "data-edit-target", "data-edit-annotation"})
PROTECTED_ATTR_SUFFIXES = frozenset({"href"})


def is_editable_attr(key: str) -> bool:
    key_lower = key.lower()
    if key_lower in PROTECTED_ATTRS:
        return False
    if key_lower.startswith("on"):
        return False
    if key_lower in PROTECTED_ATTR_SUFFIXES or key_lower.endswith(":href"):
        return False
    return True


def set_text(root: ET.Element, element_id: str, text: str
             ) -> tuple[bool, Optional[str]]:
    elem = _find_by_id(root, element_id)
    if elem is None:
        return False, "not-found"
    for child in elem:
        ctag = _local_name(child)
        if ctag == "tspan":
            return False, "has-tspan-children"
    elem.text = text
    return True, None


def set_attributes(root: ET.Element, element_id: str, attrs: dict
                   ) -> tuple[bool, Optional[str]]:
    elem = _find_by_id(root, element_id)
    if elem is None:
        return False, "not-found"
    for key in attrs:
        if not is_editable_attr(key):
            return False, f"attr-not-allowed:{key}"
    for key, value in attrs.items():
        if value is None:
            elem.attrib.pop(key, None)
        else:
            elem.set(key, str(value))
    return True, None


def remove_attribute(root: ET.Element, element_id: str, key: str
                     ) -> tuple[bool, Optional[str]]:
    if not is_editable_attr(key):
        return False, f"attr-not-allowed:{key}"
    elem = _find_by_id(root, element_id)
    if elem is None:
        return False, "not-found"
    elem.attrib.pop(key, None)
    return True, None


def strip_unused_temp_ids(root: ET.Element, keep_ids: set) -> None:
    protected = set(keep_ids)
    for elem in root.iter():
        if elem.get("data-edit-target") == "true":
            eid = elem.get("id")
            if eid:
                protected.add(eid)
    for elem in root.iter():
        eid = elem.get("id", "")
        if eid.startswith("_edit_") and eid not in protected:
            elem.attrib.pop("id", None)
