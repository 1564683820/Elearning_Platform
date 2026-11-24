"""PPTX 动画 XML 构建器 — 幻灯片切换 + 元素动画

为 PPTX 生成 Open XML（p:transition + p:timing）动画定义。
支持 6 种切换效果和 4 种元素动画类型。
"""

from typing import Optional, List, Dict
from lxml import etree

# 命名空间
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

# ========== 幻灯片切换效果 ==========

TRANSITION_TYPES = {
    "fade":       "fade",
    "push":       "push",
    "wipe":       "wipe",
    "split":      "split",
    "uncover":    "uncover",
    "cover":      "cover",
    "dissolve":   "dissolve",
    "randomBar":  "randomBar",
    "plus":       "plus",
    "circle":     "circle",
    "fadeSmoothly": "fadeSmoothly",
}

# 方向映射 (push/wipe/split/uncover/cover)
DIR_MAP = {
    "left":    "l",
    "right":   "r",
    "up":      "u",
    "down":    "d",
    "lu":      "lu",
    "ru":      "ru",
    "ld":      "ld",
    "rd":      "rd",
}

# 速度映射
SPEED_MAP = {
    "slow":    "slow",
    "medium":  "med",
    "fast":    "fast",
}

# ========== 元素动画类型 ==========

ANIMATION_TYPES = {
    "fade":       None,     # p:animEffect, transition=fade
    "fly-in":     None,     # p:animEffect, transition=inFromLeft/Right/Top/Bottom
    "zoom":       None,     # p:animEffect, scale=200
    "bounce":     None,     # p:animEffect
    "float-in":   None,     # 类似 fly-in 但带弹性
}


def build_slide_transition(
    style: str = "fade",
    speed: str = "medium",
    direction: Optional[str] = None,
    auto_advance_ms: int = 0,
) -> str:
    """构建幻灯片切换 XML (p:transition)

    Args:
        style: 切换效果名 — fade/push/wipe/split/uncover/cover/dissolve/randomBar
        speed: 速度 — slow/medium/fast
        direction: 方向 — left/right/up/down/lu/ru/ld/rd (仅 push/wipe/split/uncover/cover 有效)
        auto_advance_ms: 自动翻页间隔（毫秒，0=手动翻页）

    Returns:
        p:transition XML 字符串（空字符串表示无切换）
    """
    trans_type = TRANSITION_TYPES.get(style, "fade")
    spd = SPEED_MAP.get(speed, "med")

    attrs = {
        "spd": spd,
        "xmlns:p": NS_P,
    }
    if auto_advance_ms > 0:
        attrs["advTm"] = str(auto_advance_ms)

    if direction:
        dir_val = DIR_MAP.get(direction, "l")
        attrs["dir"] = dir_val

    # 构建 inner element（不同的切换效果使用不同的标签名）
    if trans_type == "fade":
        inner = f'<p:fade xmlns:p="{NS_P}"/>'
    elif trans_type == "push":
        inner = f'<p:push xmlns:p="{NS_P}" dir="{attrs.get("dir","l")}"/>'
    elif trans_type == "wipe":
        inner = f'<p:wipe xmlns:p="{NS_P}" dir="{attrs.get("dir","l")}"/>'
    elif trans_type == "split":
        inner = f'<p:split xmlns:p="{NS_P}" dir="{attrs.get("dir","l")}"/>'
    elif trans_type == "uncover":
        inner = f'<p:uncover xmlns:p="{NS_P}" dir="{attrs.get("dir","l")}"/>'
    elif trans_type == "cover":
        inner = f'<p:cover xmlns:p="{NS_P}" dir="{attrs.get("dir","l")}"/>'
    elif trans_type == "dissolve":
        inner = f'<p:dissolve xmlns:p="{NS_P}"/>'
    elif trans_type == "randomBar":
        inner = f'<p:randomBar xmlns:p="{NS_P}"/>'
    elif trans_type == "plus":
        inner = f'<p:plus xmlns:p="{NS_P}"/>'
    elif trans_type == "circle":
        inner = f'<p:circle xmlns:p="{NS_P}"/>'
    elif trans_type == "fadeSmoothly":
        inner = f'<p:fadeSmoothly xmlns:p="{NS_P}"/>'
    else:
        inner = f'<p:fade xmlns:p="{NS_P}"/>'

    # 移除 dir 属性（如果 inner 已包含）避免重复
    if "dir" in attrs and trans_type in ("fade","dissolve","randomBar","plus","circle","fadeSmoothly"):
        del attrs["dir"]

    # 构建外层 transition 元素
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items() if k != "dir" or "dir" in attrs)
    return f'<p:transition {attr_str}>{inner}</p:transition>'


def build_common_timing(
    duration_sec: float = 0.5,
    trigger: str = "onClick",
    delay_sec: float = 0.0,
) -> str:
    """构建幻灯片级时间线 (p:timing) — 控制整体动画时机

    Args:
        duration_sec: 整页动画总时长（秒）
        trigger: 触发方式 — onClick/afterPrevious/withPrevious
        delay_sec: 延迟（秒）

    Returns:
        p:timing XML 字符串
    """
    dur_str = f"{duration_sec:.3f}" if delay_sec > 0 else "indefinite"

    timing = (
        f'<p:timing xmlns:p="{NS_P}">'
        f'<p:tnLst>'
        f'<p:par dur="{dur_str}" repeatCount="1">'
        f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
        f'<p:stCondLst>'
        f'<p:cond delay="{delay_sec:.3f}"/>'
        f'</p:stCondLst>'
        f'</p:cTn>'
        f'</p:par>'
        f'</p:tnLst>'
        f'</p:timing>'
    )
    return timing


def build_element_animation_xml(
    element_id: str,
    anim_type: str = "fade",
    trigger: str = "onClick",
    duration_sec: float = 0.5,
    delay_sec: float = 0.0,
    direction: str = "bottom",
) -> str:
    """为单个元素构建动画 XML (p:animEffect / p:animMotion)

    封装在 p:timing > p:tnLst > p:par > p:cTn > p:childTnLst > p:set/p:animEffect 中。

    Args:
        element_id: 元素的唯一标识（可多选，用逗号分隔）
        anim_type: 动画类型 — fade/fly-in/zoom/bounce/float-in
        trigger: 触发方式 — onClick/afterPrevious/withPrevious
        duration_sec: 动画时长（秒）
        delay_sec: 延迟（秒）
        direction: 进入方向 — top/bottom/left/right (仅 fly-in 有用)

    Returns:
        动画定义 XML 片段或空字符串
    """
    # 时间换算
    dur_str = f"{duration_sec:.3f}"
    delay_str = f"{delay_sec:.3f}"
    prev_attr = ""

    if trigger == "afterPrevious":
        prev_attr = ' nodeType="afterEffect"'
    elif trigger == "withPrevious":
        prev_attr = ' nodeType="clickEffect"'

    if anim_type == "fade":
        # 淡入/淡出
        return (
            f'<p:animEffect{prev_attr}>'
            f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
            f'<p:stCondLst>'
            f'<p:cond delay="{delay_str}"/>'
            f'</p:stCondLst>'
            f'</p:cTn>'
            f'<p:tgtEl>'
            f'<p:spTgt spid="{element_id}"/>'
            f'</p:tgtEl>'
            f'<p:attributeName>style.visibility</p:attributeName>'
            f'</p:animEffect>'
        )
    elif anim_type == "fly-in":
        # 飞入
        dir_transition = {
            "top": "inFromTop",
            "bottom": "inFromBottom",
            "left": "inFromLeft",
            "right": "inFromRight",
        }
        transition = dir_transition.get(direction, "inFromBottom")
        return (
            f'<p:animEffect{prev_attr} transition="{transition}">'
            f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
            f'<p:stCondLst>'
            f'<p:cond delay="{delay_str}"/>'
            f'</p:stCondLst>'
            f'</p:cTn>'
            f'<p:tgtEl>'
            f'<p:spTgt spid="{element_id}"/>'
            f'</p:tgtEl>'
            f'<p:attributeName>ppt_x</p:attributeName>'
            f'</p:animEffect>'
        )
    elif anim_type == "zoom":
        # 缩放
        return (
            f'<p:animEffect{prev_attr} scale="200">'
            f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
            f'<p:stCondLst>'
            f'<p:cond delay="{delay_str}"/>'
            f'</p:stCondLst>'
            f'</p:cTn>'
            f'<p:tgtEl>'
            f'<p:spTgt spid="{element_id}"/>'
            f'</p:tgtEl>'
            f'<p:attributeName>ppt_h</p:attributeName>'
            f'</p:animEffect>'
        )
    elif anim_type == "bounce":
        # 弹跳（使用动画 motion 模拟弹性效果）
        return (
            f'<p:animEffect{prev_attr}>'
            f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
            f'<p:stCondLst>'
            f'<p:cond delay="{delay_str}"/>'
            f'</p:stCondLst>'
            f'</p:cTn>'
            f'<p:tgtEl>'
            f'<p:spTgt spid="{element_id}"/>'
            f'</p:tgtEl>'
            f'<p:attributeName>ppt_y</p:attributeName>'
            f'</p:animEffect>'
        )
    elif anim_type == "float-in":
        # 浮动进入（从下方缓慢飞入 + 淡入）
        return (
            f'<p:animEffect{prev_attr} transition="inFromBottom">'
            f'<p:cTn id="1" dur="{dur_str}" fill="hold">'
            f'<p:stCondLst>'
            f'<p:cond delay="{delay_str}"/>'
            f'</p:stCondLst>'
            f'</p:cTn>'
            f'<p:tgtEl>'
            f'<p:spTgt spid="{element_id}"/>'
            f'</p:tgtEl>'
            f'<p:attributeName>style.visibility</p:attributeName>'
            f'</p:animEffect>'
        )

    return ""


def build_page_animation_set(
    page_animation: Optional[Dict] = None,
) -> str:
    """构建完整页面的动画配置（切换 + 元素动画）

    处理 pages_json 中新增的 animation 字段：
    {
        "transition": {"style": "fade", "speed": "medium", "direction": "left"},
        "elements": [
            {"id": "2", "type": "fly-in", "trigger": "afterPrevious",
             "duration": 0.5, "delay": 0.0, "direction": "bottom"},
            ...
        ],
        "auto_advance_ms": 5000,
    }

    Args:
        page_animation: 页面动画配置 dict

    Returns:
        (transition_xml, timing_xml) 元组
    """
    if not page_animation:
        return "", ""

    # 幻灯片切换
    transition_config = page_animation.get("transition", {})
    transition_xml = build_slide_transition(
        style=transition_config.get("style", "fade"),
        speed=transition_config.get("speed", "medium"),
        direction=transition_config.get("direction"),
        auto_advance_ms=page_animation.get("auto_advance_ms", 0),
    )

    # 元素动画
    element_anims = page_animation.get("elements", [])
    if not element_anims:
        return transition_xml, ""

    # 构建元素动画 XML
    anim_parts = []
    for idx, elem in enumerate(element_anims):
        xml = build_element_animation_xml(
            element_id=str(elem.get("id", str(idx + 1))),
            anim_type=elem.get("type", "fade"),
            trigger=elem.get("trigger", "onClick"),
            duration_sec=elem.get("duration", 0.5),
            delay_sec=elem.get("delay", 0.0),
            direction=elem.get("direction", "bottom"),
        )
        if xml:
            anim_parts.append(xml)

    if not anim_parts:
        return transition_xml, ""

    # 包裹在 p:timing 中
    timing_xml = (
        f'<p:timing xmlns:p="{NS_P}">'
        f'<p:tnLst>'
        f'<p:par dur="indefinite" repeatCount="1">'
        f'<p:cTn id="1" dur="indefinite" fill="hold">'
        f'<p:childTnLst>'
        f'{" ".join(anim_parts)}'
        f'</p:childTnLst>'
        f'</p:cTn>'
        f'</p:par>'
        f'</p:tnLst>'
        f'</p:timing>'
    )

    return transition_xml, timing_xml
