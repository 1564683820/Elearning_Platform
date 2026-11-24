"""DrawingML fill -> SVG fill attributes conversion.

Handles:
- <a:solidFill>       -> fill="{color}"
- <a:gradFill>        -> <linearGradient>/<radialGradient> + fill="url(#id)"
- <a:blipFill>        -> referenced via slide_to_svg.py (image fill)
- <a:pattFill>        -> v1 approximation via solid fill
- <a:noFill>          -> fill="none"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .color_resolver import ColorPalette, find_color_elem, resolve_color
from .emu_units import NS, fmt_num


@dataclass
class FillResult:
    """Resolved fill output.

    ``attrs`` maps directly to SVG attributes (e.g. {"fill": "#FF0000"}).
    ``defs`` carries any gradient/marker defs the caller should merge.
    """

    attrs: dict[str, str] = field(default_factory=dict)
    defs: list[str] = field(default_factory=list)


def resolve_fill(
    parent: ET.Element | None,
    palette: ColorPalette | None,
    *,
    id_prefix: str = "g",
    id_seq: list[int] | None = None,
    placeholder_hex: str | None = None,
) -> FillResult:
    """Inspect *parent* for a DrawingML fill element and return SVG fill attrs.

    ``parent`` is typically a ``<p:spPr>`` or ``<p:bgPr>`` element.
    """
    if parent is None:
        return FillResult()

    fill_elem = _find_fill_element(parent)
    if fill_elem is None:
        return _default_fill(parent, placeholder_hex)

    local = fill_elem.tag.split("}", 1)[-1]

    if local == "noFill":
        return FillResult(attrs={"fill": "none"})

    if local == "solidFill":
        color_elem = find_color_elem(fill_elem)
        hex_, alpha = resolve_color(color_elem, palette)
        attrs = {"fill": hex_}
        if alpha < 1.0:
            attrs["fill-opacity"] = fmt_num(alpha, 4)
        return FillResult(attrs=attrs)

    if local == "gradFill":
        return _resolve_gradient(fill_elem, palette, id_prefix=id_prefix, id_seq=id_seq)

    if local == "pattFill":
        return _resolve_pattern(fill_elem, palette)

    if local == "blipFill":
        # Image fills on generic shapes (e.g. Canva exports) are handled by
        # slide_to_svg._convert_shape, which checks for blipFill directly.
        # Here we return no fill so the geometry doesn't collide with the image.
        return FillResult()

    return FillResult()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


_FILL_TAGS = {
    "a:noFill",
    "a:solidFill",
    "a:gradFill",
    "a:blipFill",
    "a:pattFill",
    "a:grpFill",
}


def _find_fill_element(parent: ET.Element) -> ET.Element | None:
    for tag in _FILL_TAGS:
        child = parent.find(tag, NS)
        if child is not None:
            return child
    return None


def _default_fill(parent: ET.Element, placeholder_hex: str | None) -> FillResult:
    if placeholder_hex:
        return FillResult(attrs={"fill": placeholder_hex})
    return FillResult()


def _resolve_gradient(
    grad_fill: ET.Element,
    palette: ColorPalette | None,
    *,
    id_prefix: str,
    id_seq: list[int] | None,
) -> FillResult:
    if id_seq is None:
        id_seq = [0]
    id_seq[0] += 1
    gid = f"{id_prefix}{id_seq[0]}"

    gs_lst = grad_fill.find("a:gsLst", NS)
    if gs_lst is None:
        return FillResult()

    stops: list[tuple[float, str, float]] = []
    for gs in gs_lst.findall("a:gs", NS):
        pos_str = gs.attrib.get("pos", "0")
        try:
            pos = float(pos_str) / 100000.0
        except ValueError:
            pos = 0.0
        color_elem = find_color_elem(gs)
        hex_, alpha = resolve_color(color_elem, palette)
        stops.append((pos, hex_, alpha))

    if not stops:
        return FillResult()

    # Determine gradient type and geometry
    lin = grad_fill.find("a:lin", NS)
    path = grad_fill.find("a:path", NS)

    if lin is not None:
        # Linear gradient
        try:
            angle = float(lin.attrib.get("ang", "0")) / 60000.0
        except ValueError:
            angle = 0.0
        # SVG: 0 = right, 90 = down; OOXML: 0 = up, 90 = right. Convert.
        svg_angle = angle - 90.0
        # Flip: OOXML is counterclockwise, SVG clockwise for gradient
        svg_angle = -svg_angle
        x1, y1, x2, y2 = _linear_endpoints(svg_angle)

        stops_xml = _build_stops_xml(stops)
        defs = [
            f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            + stops_xml + "</linearGradient>"
        ]
        return FillResult(attrs={"fill": f"url(#{gid})"}, defs=defs)

    if path is not None:
        path_type = path.attrib.get("pathType", "shape")
        if path_type == "circle":
            fill_to_rect = path.find("a:fillToRect", NS)
            cx, cy = 0.5, 0.5
            if fill_to_rect is not None:
                try:
                    cx = float(fill_to_rect.attrib.get("l", "50000")) / 100000.0
                    cy = float(fill_to_rect.attrib.get("t", "50000")) / 100000.0
                except ValueError:
                    pass
            stops_xml = _build_stops_xml(stops)
            defs = [
                f'<radialGradient id="{gid}" cx="{cx:.2f}" cy="{cy:.2f}" r="1">'
                + stops_xml + "</radialGradient>"
            ]
            return FillResult(attrs={"fill": f"url(#{gid})"}, defs=defs)
        # rect path -> linear fallback
        stops_xml = _build_stops_xml(stops)
        defs = [
            f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
            + stops_xml + "</linearGradient>"
        ]
        return FillResult(attrs={"fill": f"url(#{gid})"}, defs=defs)

    # No lin/path -> fallback linear
    stops_xml = _build_stops_xml(stops)
    defs = [
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
        + stops_xml + "</linearGradient>"
    ]
    return FillResult(attrs={"fill": f"url(#{gid})"}, defs=defs)


def _build_stops_xml(stops: list[tuple[float, str, float]]) -> str:
    parts: list[str] = []
    for pos, hex_, alpha in stops:
        alpha_attr = f' stop-opacity="{fmt_num(alpha, 4)}"' if alpha < 1.0 else ""
        parts.append(f'<stop offset="{fmt_num(pos * 100, 1)}%"'
                     f' stop-color="{hex_}"{alpha_attr}/>')
    return "".join(parts)


def _linear_endpoints(angle_deg: float) -> tuple[str, str, str, str]:
    """Convert an SVG-style angle to linearGradient x1/y1/x2/y2 in [0,1]."""
    import math
    rad = math.radians(angle_deg % 360.0)
    x = math.cos(rad)
    y = math.sin(rad)
    x1 = max(0.0, -x)
    y1 = max(0.0, -y)
    x2 = max(0.0, x)
    y2 = max(0.0, y)
    norm = max(abs(x) + abs(y), 1e-10)
    return f"{x1 / norm:.2f}", f"{y1 / norm:.2f}", f"{x2 / norm:.2f}", f"{y2 / norm:.2f}"


def _resolve_pattern(patt_fill: ET.Element, palette: ColorPalette | None) -> FillResult:
    """Pattern fill: v1 renders as a solid colour approximation."""
    fg = patt_fill.find("a:fgClr", NS)
    if fg is not None:
        color_elem = find_color_elem(fg)
        hex_, _ = resolve_color(color_elem, palette)
        return FillResult(attrs={"fill": hex_ or "#CCCCCC"})
    bg = patt_fill.find("a:bgClr", NS)
    if bg is not None:
        color_elem = find_color_elem(bg)
        hex_, _ = resolve_color(color_elem, palette)
        return FillResult(attrs={"fill": hex_ or "#FFFFFF"})
    return FillResult()
