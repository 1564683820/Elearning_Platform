"""DrawingML color resolution.

Reads <a:solidFill>/<a:gradFill>/... color elements and resolves them using
the slide master's clrMap and the theme's clrScheme, producing hex color values.

Supported color types:
- <a:srgbClr val="RRGGBB"/>          (direct RGB)
- <a:schemeClr val="dk1"/>           (theme color reference)
- <a:sysClr val="window"/>           (system color)
- <a:prstClr val="black"/>           (preset named color)
- <a:hslClr hue="..." sat="..." lum="..."/> (HSL)
- <a:scrgbClr r="..." g="..." b="..."/>     (percentage RGB)
"""

from __future__ import annotations

import colorsys
import re
from xml.etree import ElementTree as ET

from .emu_units import NS


# ---------------------------------------------------------------------------
# ColorPalette
# ---------------------------------------------------------------------------

# ECMA-376 20.1.4.1.17: fixed mapping of system colours. We only need the
# most common ones that PowerPoint actually emits.
_SYSTEM_COLORS: dict[str, str] = {
    "window": "#FFFFFF",
    "windowText": "#000000",
    "scrollBar": "#C0C0C0",
    "menu": "#F0F0F0",
    "menuText": "#000000",
    "activeCaption": "#000080",
    "captionText": "#FFFFFF",
    "inactiveCaption": "#808080",
    "inactiveCaptionText": "#C0C0C0",
    "highlight": "#000080",
    "highlightText": "#FFFFFF",
    "hotLight": "#0000FF",
    "btnFace": "#F0F0F0",
    "btnShadow": "#808080",
    "btnHighlight": "#FFFFFF",
    "btnText": "#000000",
    "grayText": "#808080",
}

# ECMA-376 20.1.10.48 — preset colours. Complete enough for all common shapes.
_PRESET_COLORS: dict[str, str] = {
    "aliceBlue": "#F0F8FF",
    "antiqueWhite": "#FAEBD7",
    "aqua": "#00FFFF",
    "aquamarine": "#7FFFD4",
    "azure": "#F0FFFF",
    "beige": "#F5F5DC",
    "bisque": "#FFE4C4",
    "black": "#000000",
    "blanchedAlmond": "#FFEBCD",
    "blue": "#0000FF",
    "blueViolet": "#8A2BE2",
    "brown": "#A52A2A",
    "burlyWood": "#DEB887",
    "cadetBlue": "#5F9EA0",
    "chartreuse": "#7FFF00",
    "chocolate": "#D2691E",
    "coral": "#FF7F50",
    "cornflowerBlue": "#6495ED",
    "cornsilk": "#FFF8DC",
    "crimson": "#DC143C",
    "cyan": "#00FFFF",
    "darkBlue": "#00008B",
    "darkCyan": "#008B8B",
    "darkGoldenrod": "#B8860B",
    "darkGray": "#A9A9A9",
    "darkGreen": "#006400",
    "darkGrey": "#A9A9A9",
    "darkKhaki": "#BDB76B",
    "darkMagenta": "#8B008B",
    "darkOliveGreen": "#556B2F",
    "darkOrange": "#FF8C00",
    "darkOrchid": "#9932CC",
    "darkRed": "#8B0000",
    "darkSalmon": "#E9967A",
    "darkSeaGreen": "#8FBC8F",
    "darkSlateBlue": "#483D8B",
    "darkSlateGray": "#2F4F4F",
    "darkSlateGrey": "#2F4F4F",
    "darkTurquoise": "#00CED1",
    "darkViolet": "#9400D3",
    "deepPink": "#FF1493",
    "deepSkyBlue": "#00BFFF",
    "dimGray": "#696969",
    "dimGrey": "#696969",
    "dodgerBlue": "#1E90FF",
    "firebrick": "#B22222",
    "floralWhite": "#FFFAF0",
    "forestGreen": "#228B22",
    "fuchsia": "#FF00FF",
    "gainsboro": "#DCDCDC",
    "ghostWhite": "#F8F8FF",
    "gold": "#FFD700",
    "goldenrod": "#DAA520",
    "gray": "#808080",
    "green": "#008000",
    "greenYellow": "#ADFF2F",
    "grey": "#808080",
    "honeydew": "#F0FFF0",
    "hotPink": "#FF69B4",
    "indianRed": "#CD5C5C",
    "indigo": "#4B0082",
    "ivory": "#FFFFF0",
    "khaki": "#F0E68C",
    "lavender": "#E6E6FA",
    "lavenderBlush": "#FFF0F5",
    "lawnGreen": "#7CFC00",
    "lemonChiffon": "#FFFACD",
    "lightBlue": "#ADD8E6",
    "lightCoral": "#F08080",
    "lightCyan": "#E0FFFF",
    "lightGoldenrodYellow": "#FAFAD2",
    "lightGray": "#D3D3D3",
    "lightGreen": "#90EE90",
    "lightGrey": "#D3D3D3",
    "lightPink": "#FFB6C1",
    "lightSalmon": "#FFA07A",
    "lightSeaGreen": "#20B2AA",
    "lightSkyBlue": "#87CEFA",
    "lightSlateGray": "#778899",
    "lightSlateGrey": "#778899",
    "lightSteelBlue": "#B0C4DE",
    "lightYellow": "#FFFFE0",
    "lime": "#00FF00",
    "limeGreen": "#32CD32",
    "linen": "#FAF0E6",
    "magenta": "#FF00FF",
    "maroon": "#800000",
    "mediumAquamarine": "#66CDAA",
    "mediumBlue": "#0000CD",
    "mediumOrchid": "#BA55D3",
    "mediumPurple": "#9370DB",
    "mediumSeaGreen": "#3CB371",
    "mediumSlateBlue": "#7B68EE",
    "mediumSpringGreen": "#00FA9A",
    "mediumTurquoise": "#48D1CC",
    "mediumVioletRed": "#C71585",
    "midnightBlue": "#191970",
    "mintCream": "#F5FFFA",
    "mistyRose": "#FFE4E1",
    "moccasin": "#FFE4B5",
    "navajoWhite": "#FFDEAD",
    "navy": "#000080",
    "oldLace": "#FDF5E6",
    "olive": "#808000",
    "oliveDrab": "#6B8E23",
    "orange": "#FFA500",
    "orangeRed": "#FF4500",
    "orchid": "#DA70D6",
    "paleGoldenrod": "#EEE8AA",
    "paleGreen": "#98FB98",
    "paleTurquoise": "#AFEEEE",
    "paleVioletRed": "#DB7093",
    "papayaWhip": "#FFEFD5",
    "peachPuff": "#FFDAB9",
    "peru": "#CD853F",
    "pink": "#FFC0CB",
    "plum": "#DDA0DD",
    "powderBlue": "#B0E0E6",
    "purple": "#800080",
    "red": "#FF0000",
    "rosyBrown": "#BC8F8F",
    "royalBlue": "#4169E1",
    "saddleBrown": "#8B4513",
    "salmon": "#FA8072",
    "sandyBrown": "#F4A460",
    "seaGreen": "#2E8B57",
    "seaShell": "#FFF5EE",
    "sienna": "#A0522D",
    "silver": "#C0C0C0",
    "skyBlue": "#87CEEB",
    "slateBlue": "#6A5ACD",
    "slateGray": "#708090",
    "slateGrey": "#708090",
    "snow": "#FFFAFA",
    "springGreen": "#00FF7F",
    "steelBlue": "#4682B4",
    "tan": "#D2B48C",
    "teal": "#008080",
    "thistle": "#D8BFD8",
    "tomato": "#FF6347",
    "turquoise": "#40E0D0",
    "violet": "#EE82EE",
    "wheat": "#F5DEB3",
    "white": "#FFFFFF",
    "whiteSmoke": "#F5F5F5",
    "yellow": "#FFFF00",
    "yellowGreen": "#9ACD32",
}


class ColorPalette:
    """Resolves DrawingML colors using a slide master's clrMap and theme's clrScheme.

    Usage:
        palette = ColorPalette(slide_master_part, theme_part)
        hex_color, alpha = resolve_color(color_elem, palette)
    """

    def __init__(
        self,
        master_part: ET.Element | None,  # SlideMaster XML root (or None)
        theme_part: ET.Element | None,   # Theme XML root (or None)
    ) -> None:
        self._clr_scheme: dict[str, str] = {}
        self._clr_map: dict[str, str] = {}

        if theme_part is not None:
            scheme = theme_part.find(".//a:clrScheme", NS)
            if scheme is not None:
                for child in list(scheme):
                    if not isinstance(child.tag, str):
                        continue
                    name = child.tag.split("}", 1)[-1]
                    color_elem = find_color_elem(child)
                    if color_elem is not None:
                        hex_, _ = resolve_color(color_elem, ColorPalette(None, None))
                        if hex_:
                            self._clr_scheme[name] = hex_

        if master_part is not None:
            clr_map = master_part.find("p:clrMap", NS)
            if clr_map is not None:
                for attr_name in clr_map.attrib:
                    val = clr_map.attrib[attr_name]
                    if val:
                        self._clr_map[attr_name] = val

    def resolve_scheme_color(self, scheme_name: str) -> str | None:
        """Resolve a theme colour name via clrMap then clrScheme.

        Examples: "dk1", "accent1", "tx1".
        """
        mapped = self._clr_map.get(scheme_name, scheme_name)
        return self._clr_scheme.get(mapped)

    def resolve_scheme_color_direct(self, scheme_name: str) -> str | None:
        """Resolve directly from clrScheme, bypassing clrMap."""
        return self._clr_scheme.get(scheme_name)

    @property
    def clr_scheme(self) -> dict[str, str]:
        return dict(self._clr_scheme)

    @property
    def clr_map(self) -> dict[str, str]:
        return dict(self._clr_map)


# ---------------------------------------------------------------------------
# Color element detection
# ---------------------------------------------------------------------------


def find_color_elem(parent: ET.Element | None) -> ET.Element | None:
    """Find the first DrawingML colour specification child element.

    Looks for children like a:solidFill/a:srgbClr, a:solidFill/a:schemeClr,
    etc. Returns the innermost leaf that carries the colour value.
    """
    if parent is None:
        return None
    for child in list(parent):
        if not isinstance(child.tag, str):
            continue
        # These are the colour tag names OOXML uses as leaf values.
        local = child.tag.split("}", 1)[-1]
        if local in ("srgbClr", "schemeClr", "sysClr", "prstClr", "hslClr", "scrgbClr"):
            return child
        # Some parents wrap: a:solidFill -> a:srgbClr
        inner = find_color_elem(child)
        if inner is not None:
            return inner
    return None


def resolve_color(
    color_elem: ET.Element | None,
    palette: ColorPalette | None,
) -> tuple[str, float]:
    """Resolve a DrawingML colour element to (hex, alpha).

    Returns (hex_string, alpha_float) where alpha is in [0, 1].
    Default alpha is 1.0 (fully opaque).
    """
    if color_elem is None:
        return "#000000", 1.0

    local = color_elem.tag.split("}", 1)[-1]
    alpha = _read_alpha(color_elem)

    if local == "srgbClr":
        val = color_elem.attrib.get("val", "000000")
        return f"#{val.strip().upper()}", alpha

    if local == "schemeClr":
        scheme_val = color_elem.attrib.get("val", "dk1")
        if palette is not None:
            resolved = palette.resolve_scheme_color(scheme_val)
            if resolved:
                return resolved, alpha
        return "#000000", alpha

    if local == "sysClr":
        sys_val = color_elem.attrib.get("lastClr")
        if sys_val:
            return f"#{sys_val.strip().upper()}", alpha
        sys_name = color_elem.attrib.get("val", "")
        return _SYSTEM_COLORS.get(sys_name, "#000000"), alpha

    if local == "prstClr":
        prst_val = color_elem.attrib.get("val", "black")
        return _PRESET_COLORS.get(prst_val, "#000000"), alpha

    if local == "hslClr":
        try:
            hue = float(color_elem.attrib.get("hue", "0")) / 60000.0
            sat = float(color_elem.attrib.get("sat", "0")) / 1000.0 / 255.0 * 100.0
            lum = float(color_elem.attrib.get("lum", "0")) / 1000.0 / 255.0 * 100.0
        except ValueError:
            return "#000000", alpha
        r, g, b = colorsys.hls_to_rgb(hue / 360.0, lum / 100.0, sat / 100.0)
        return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}", alpha

    if local == "scrgbClr":
        try:
            r = float(color_elem.attrib.get("r", "0"))
            g = float(color_elem.attrib.get("g", "0"))
            b = float(color_elem.attrib.get("b", "0"))
        except ValueError:
            return "#000000", alpha
        return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}", alpha

    return "#000000", alpha


def _read_alpha(color_elem: ET.Element) -> float:
    """Read <a:alpha val="N"/> child from a colour element.

    The val is in 1/1000ths of a percent (so 100000 = 100%).
    """
    alpha_elem = color_elem.find("a:alpha", NS)
    if alpha_elem is None:
        return 1.0
    try:
        return float(alpha_elem.attrib.get("val", "100000")) / 100000.0
    except (ValueError, ZeroDivisionError):
        return 1.0
