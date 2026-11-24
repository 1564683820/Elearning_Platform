"""DrawingML <a:ln> -> SVG stroke attributes conversion.

Handles:
- <a:noFill>          -> stroke="none"
- <a:solidFill>       -> stroke={color}
- <a:gradFill>        -> stroke="url(#id)" (reuses gradient defs from fill_to_svg)
- <a:prstDash>        -> stroke-dasharray
- Arrowhead markers   -> marker-start / marker-end
- <a:round> / <a:bevel> -> stroke-linejoin
- <a:tailEnd> / <a:headEnd> -> arrow markers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .color_resolver import ColorPalette, find_color_elem, resolve_color
from .emu_units import NS, emu_to_px, fmt_num
from .fill_to_svg import _find_fill_element, _resolve_gradient


@dataclass
class StrokeResult:
    """Resolved stroke output."""

    attrs: dict[str, str] = field(default_factory=dict)
    defs: list[str] = field(default_factory=list)


# Standard SVG dasharray values for DrawingML presets.
_DASH_MAP: dict[str, str] = {
    "solid": "",
    "dot": "2 4",
    "dash": "6 4",
    "lgDash": "12 6",
    "dashDot": "6 4 2 4",
    "lgDashDot": "12 6 2 4",
    "lgDashDotDot": "12 6 2 4 2 4",
    "sysDash": "16 6",
    "sysDot": "2 6",
    "sysDashDot": "16 6 2 6",
    "sysDashDotDot": "16 6 2 6 2 6",
}


def resolve_stroke(
    parent: ET.Element | None,
    palette: ColorPalette | None,
    *,
    id_prefix: str = "m",
    id_seq: list[int] | None = None,
    style_stroke_default: str | None = None,
) -> StrokeResult:
    """Inspect *parent* for an <a:ln> element and return SVG stroke attrs.

    ``parent`` is typically ``<p:spPr>``. ``style_stroke_default`` is
    the colour resolved from ``<p:style><a:lnRef>``, used when ``<a:ln>``
    doesn't specify an explicit fill.
    """
    ln = parent.find("a:ln", NS) if parent is not None else None
    if ln is None:
        return StrokeResult()

    # noFill
    if ln.find("a:noFill", NS) is not None:
        return StrokeResult(attrs={"stroke": "none"})

    # Width
    w_emu = ln.attrib.get("w")
    stroke_width: float | None = None
    if w_emu:
        try:
            stroke_width = emu_to_px(float(w_emu))
        except ValueError:
            pass

    # Fill
    fill_elem = _find_fill_element(ln)
    stroke_color: str | None = None
    stroke_opacity: float | None = None
    defs: list[str] = []

    if fill_elem is not None:
        local = fill_elem.tag.split("}", 1)[-1]
        if local == "solidFill":
            color_elem = find_color_elem(fill_elem)
            hex_, alpha = resolve_color(color_elem, palette)
            stroke_color = hex_
            if alpha < 1.0:
                stroke_opacity = alpha
        elif local == "gradFill":
            result = _resolve_gradient(fill_elem, palette, id_prefix=id_prefix, id_seq=id_seq)
            if result.attrs.get("fill", "").startswith("url("):
                stroke_color = result.attrs["fill"]
            defs.extend(result.defs)

    if stroke_color is None:
        stroke_color = style_stroke_default

    if stroke_color is None and fill_elem is None:
        # No fill and no style default -> no visible stroke (PowerPoint
        # draws a default 1px dark line, but SVG should not).
        return StrokeResult()

    # Dash
    dash_elem = ln.find("a:prstDash", NS)
    dasharray = ""
    if dash_elem is not None:
        dash_name = dash_elem.attrib.get("val", "solid")
        dasharray = _DASH_MAP.get(dash_name, "")

    # Cap
    cap = ln.attrib.get("cap", "flat")
    cap_map = {"rnd": "round", "sq": "square", "flat": "butt"}

    # Join
    join = None
    for join_tag in ("a:round", "a:bevel", "a:miter"):
        if ln.find(join_tag, NS) is not None:
            join = join_tag.split(":")[1]
            break

    # Arrow markers
    tail = ln.find("a:tailEnd", NS)
    head = ln.find("a:headEnd", NS)

    attrs: dict[str, str] = {}
    if stroke_color:
        attrs["stroke"] = stroke_color
    if stroke_width is not None and stroke_width > 0:
        attrs["stroke-width"] = fmt_num(stroke_width)
    elif stroke_color:
        attrs["stroke-width"] = "1"
    if stroke_opacity is not None:
        attrs["stroke-opacity"] = fmt_num(stroke_opacity, 4)
    if dasharray:
        attrs["stroke-dasharray"] = dasharray
    if cap in cap_map:
        attrs["stroke-linecap"] = cap_map[cap]
    if join:
        attrs["stroke-linejoin"] = join

    # Arrow markers
    if tail is not None and id_seq is not None:
        _add_marker_def("tail", tail, stroke_color, stroke_width, palette,
                        id_prefix, id_seq, attrs, defs)
    if head is not None and id_seq is not None:
        _add_marker_def("head", head, stroke_color, stroke_width, palette,
                        id_prefix, id_seq, attrs, defs)

    return StrokeResult(attrs=attrs, defs=defs)


def _add_marker_def(
    end_type: str,
    end_elem: ET.Element,
    stroke_color: str | None,
    stroke_width: float | None,
    palette: ColorPalette | None,
    id_prefix: str,
    id_seq: list[int],
    attrs: dict[str, str],
    defs: list[str],
) -> None:
    """Generate a marker <defs> entry and add the marker-* reference."""
    svg_ref = "marker-end" if end_type == "tail" else "marker-start"

    # Get arrowhead type
    arrow_type = end_elem.attrib.get("type", "triangle")
    sz = end_elem.attrib.get("sz", "med")
    len_map = {"sm": 4, "med": 6, "lg": 8}
    marker_len = len_map.get(sz, 6) * (stroke_width or 1)

    # Build a simple arrowhead path
    if arrow_type == "triangle":
        path = "M 0 0 L 10 5 L 0 10 Z"
    elif arrow_type in ("stealth", "diamond", "oval"):
        path = "M 0 0 L 10 5 L 0 10 Z"
    elif arrow_type == "arrow":
        path = "M 0 0 L 10 5 L 0 10 Z"
    elif arrow_type == "triangleStealth":
        path = "M 0 0 L 10 5 L 0 10 Z"
    else:
        path = "M 0 0 L 10 5 L 0 10 Z"

    color = stroke_color or "#000000"
    id_seq[0] += 1
    marker_id = f"{id_prefix}{id_seq[0]}"
    defs.append(
        f'<marker id="{marker_id}" viewBox="0 0 10 10" '
        f'refX="10" refY="5" markerWidth="{fmt_num(marker_len)}" '
        f'markerHeight="{fmt_num(marker_len)}" orient="auto">'
        f'<path d="{path}" fill="{color}"/></marker>'
    )
    attrs[svg_ref] = f"url(#{marker_id})"
