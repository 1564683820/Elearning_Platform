"""EMU unit conversion constants and utilities.

All coordinate values in OOXML use EMU (English Metric Units).
This module provides constants and functions for converting to pixels.
"""

from __future__ import annotations

import math
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# XML Namespaces
# ---------------------------------------------------------------------------

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# ---------------------------------------------------------------------------
# EMU Conversion Factors
# ---------------------------------------------------------------------------

EMU_PER_PT = 12700          # 1 pt = 1/72 inch = 12700 EMU
EMU_PER_INCH = 914400       # 1 inch = 914400 EMU
EMU_PER_CM = 360000         # 1 cm = 360000 EMU
DEFAULT_DPI = 96.0           # PowerPoint's rendering DPI

# OOXML length units
HUNDREDTHS_PT_TO_PT = 0.01  # 100ths of a point -> points


def emu_to_pt(emu: float) -> float:
    """Convert EMU to points."""
    return emu / EMU_PER_PT


def emu_to_inch(emu: float) -> float:
    """Convert EMU to inches."""
    return emu / EMU_PER_INCH


def emu_to_cm(emu: float) -> float:
    """Convert EMU to centimetres."""
    return emu / EMU_PER_CM


def emu_to_px(emu: float) -> float:
    """Convert EMU to pixels at DEFAULT_DPI."""
    return emu / EMU_PER_INCH * DEFAULT_DPI


def hundredths_pt_to_px(val: float) -> float:
    """Convert hundredths of a point to pixels."""
    return val * HUNDREDTHS_PT_TO_PT / 72.0 * DEFAULT_DPI


def emu_attr_to_px(xfrm_elem: ET.Element | None, attr_x: str = "x", attr_y: str = "y") -> tuple[float, float]:
    """Read two EMU attributes and return as pixel values."""
    if xfrm_elem is None:
        return 0.0, 0.0
    try:
        x = emu_to_px(float(xfrm_elem.attrib.get(attr_x, "0")))
        y = emu_to_px(float(xfrm_elem.attrib.get(attr_y, "0")))
    except ValueError:
        return 0.0, 0.0
    return x, y


def fmt_num(val: float, decimals: int = 2) -> str:
    """Format a float to a short string suitable for SVG attributes.

    Strips trailing zeros and trailing decimal points.
    """
    if decimals < 0:
        decimals = 0
    formatted = f"{val:.{decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


# ---------------------------------------------------------------------------
# Xfrm — shape position / size / rotation
# ---------------------------------------------------------------------------


class Xfrm:
    """A shape's position, size, and transform, in slide-space pixels.

    All fields are float for sub-pixel precision; callers should format with
    fmt_num() for SVG output.
    """

    __slots__ = (
        "x", "y", "w", "h",
        "rot", "flip_h", "flip_v",
        "ch_x", "ch_y", "ch_w", "ch_h",
    )

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        w: float = 0.0,
        h: float = 0.0,
        rot: float = 0.0,
        flip_h: bool = False,
        flip_v: bool = False,
        ch_x: float | None = None,
        ch_y: float | None = None,
        ch_w: float | None = None,
        ch_h: float | None = None,
    ) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.rot = rot
        self.flip_h = flip_h
        self.flip_v = flip_v
        self.ch_x = ch_x
        self.ch_y = ch_y
        self.ch_w = ch_w
        self.ch_h = ch_h

    def __repr__(self) -> str:
        return (
            f"Xfrm(x={self.x:.1f}, y={self.y:.1f}, w={self.w:.1f}, "
            f"h={self.h:.1f}, rot={self.rot:.1f}, flip_h={self.flip_h}, "
            f"flip_v={self.flip_v})"
        )

    def to_svg_transform(self) -> str:
        """Return an SVG transform attribute string, or empty string if identity."""
        transforms: list[str] = []
        if self.flip_h or self.flip_v:
            cx = self.x + self.w / 2.0
            cy = self.y + self.h / 2.0
            sx = -1.0 if self.flip_h else 1.0
            sy = -1.0 if self.flip_v else 1.0
            transforms.append(f"translate({fmt_num(cx)},{fmt_num(cy)}) scale({sx},{sy}) translate({fmt_num(-cx)},{fmt_num(-cy)})")
        if self.rot:
            cx = self.x + self.w / 2.0
            cy = self.y + self.h / 2.0
            transforms.append(f"rotate({fmt_num(self.rot)} {fmt_num(cx)} {fmt_num(cy)})")
        return " ".join(transforms)


def parse_xfrm(xfrm_elem: ET.Element | None) -> Xfrm:
    """Parse an <a:xfrm> element into an Xfrm struct.

    Handles both simple shapes (off + ext) and group shapes (chOff + chExt).
    """
    if xfrm_elem is None:
        return Xfrm()

    # Rotation
    rot_str = xfrm_elem.attrib.get("rot") or "0"
    try:
        rot = float(rot_str) / 60000.0  # 1/60000 degree -> degrees
    except ValueError:
        rot = 0.0

    # Flip
    flip_h = xfrm_elem.attrib.get("flipH") == "1"
    flip_v = xfrm_elem.attrib.get("flipV") == "1"

    # off / ext
    off = xfrm_elem.find("a:off", NS)
    ext = xfrm_elem.find("a:ext", NS)
    x = y = w = h = 0.0
    if off is not None:
        try:
            x = emu_to_px(float(off.attrib.get("x", "0")))
            y = emu_to_px(float(off.attrib.get("y", "0")))
        except ValueError:
            pass
    if ext is not None:
        try:
            w = emu_to_px(float(ext.attrib.get("cx", "0")))
            h = emu_to_px(float(ext.attrib.get("cy", "0")))
        except ValueError:
            pass

    # chOff / chExt (group child coordinate frame)
    ch_off = xfrm_elem.find("a:chOff", NS)
    ch_ext = xfrm_elem.find("a:chExt", NS)
    ch_x = ch_y = None
    ch_w = ch_h = None
    if ch_off is not None:
        try:
            ch_x = emu_to_px(float(ch_off.attrib.get("x", "0")))
            ch_y = emu_to_px(float(ch_off.attrib.get("y", "0")))
        except ValueError:
            pass
    if ch_ext is not None:
        try:
            ch_w = emu_to_px(float(ch_ext.attrib.get("cx", "0")))
            ch_h = emu_to_px(float(ch_ext.attrib.get("cy", "0")))
        except ValueError:
            pass

    return Xfrm(
        x=x, y=y, w=w, h=h,
        rot=rot, flip_h=flip_h, flip_v=flip_v,
        ch_x=ch_x, ch_y=ch_y, ch_w=ch_w, ch_h=ch_h,
    )
