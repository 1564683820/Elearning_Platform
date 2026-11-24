"""DrawingML <p:txBody> -> SVG <text> conversion.

Strategy (v1):
- Each <a:p> paragraph emits one <text> element (one line of baseline).
  Multiple <a:r> runs in one paragraph become <tspan>s sharing the text element's x.
- Vertical layout: y of first paragraph is determined by anchor (t/ctr/b)
  and tIns/bIns. Subsequent paragraphs stack downward with line height
  derived from the largest font in the paragraph * 1.2 (default leading).
- Horizontal layout: text-anchor follows pPr@algn. x is computed from the
  text frame plus lIns/rIns and the alignment.
- No automatic word wrap (PPT's wrap is layout-time; v1 trusts the existing
  text frame width and emits text as-is). a:br produces an explicit linebreak.
- Bullet points (a:buChar / a:buAutoNum) are rendered as literal prefixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .color_resolver import ColorPalette, find_color_elem, resolve_color
from .emu_units import (
    NS, Xfrm, fmt_num, emu_to_px, hundredths_pt_to_px,
)
from .fill_to_svg import resolve_fill


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_INSETS_EMU = {"l": 91440, "t": 45720, "r": 91440, "b": 45720}
DEFAULT_FONT_SIZE_PX = 24.0
DEFAULT_LINE_HEIGHT_RATIO = 1.2
DEFAULT_FILL_HEX = "#000000"


@dataclass
class TextRun:
    """A single run with resolved style + text."""
    text: str
    font_size_px: float
    font_family: str
    fill: str
    fill_opacity: float = 1.0
    defs: list[str] = field(default_factory=list)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    letter_spacing_px: float = 0.0
    is_break: bool = False


@dataclass
class TextParagraph:
    """One <a:p>: a list of runs sharing alignment + level."""
    runs: list[TextRun] = field(default_factory=list)
    align: str = "l"
    level: int = 0
    indent_px: float = 0.0
    margin_left_px: float = 0.0
    line_height_ratio: float = DEFAULT_LINE_HEIGHT_RATIO
    space_before_px: float = 0.0
    space_after_px: float = 0.0
    bullet_prefix: str = ""


@dataclass
class TextResult:
    """Resolved text body ready for SVG emission."""
    svg: str = ""
    defs: list[str] = field(default_factory=list)


VERTICAL_TEXT_MODES = {"eaVert", "vert", "wordArtVert", "wordArtVertRtl"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_txbody(
    tx_body: ET.Element | None,
    xfrm: Xfrm,
    palette: ColorPalette | None,
    *,
    theme_fonts: dict[str, str] | None = None,
    default_fill: str = DEFAULT_FILL_HEX,
    default_font_size_px: float = DEFAULT_FONT_SIZE_PX,
    fallback_lst_styles: tuple[ET.Element, ...] = (),
    id_prefix: str = "txt",
    id_seq: list[int] | None = None,
) -> TextResult:
    """Convert <p:txBody> under the given shape geometry to SVG <text>(s)."""
    if tx_body is None:
        return TextResult()
    body_pr = tx_body.find("a:bodyPr", NS)
    paragraphs = _parse_paragraphs(
        tx_body, palette, theme_fonts or {}, default_fill=default_fill,
        default_font_size_px=default_font_size_px,
        fallback_lst_styles=fallback_lst_styles,
        id_prefix=id_prefix, id_seq=id_seq,
    )
    if not paragraphs or not _has_visible_text(paragraphs):
        return TextResult()
    lins = _read_emu_attr(body_pr, "lIns", DEFAULT_INSETS_EMU["l"])
    tins = _read_emu_attr(body_pr, "tIns", DEFAULT_INSETS_EMU["t"])
    rins = _read_emu_attr(body_pr, "rIns", DEFAULT_INSETS_EMU["r"])
    bins = _read_emu_attr(body_pr, "bIns", DEFAULT_INSETS_EMU["b"])
    anchor = body_pr.attrib.get("anchor", "t") if body_pr is not None else "t"
    wrap_mode = body_pr.attrib.get("wrap", "square") if body_pr is not None else "square"
    inner_x = xfrm.x + lins
    inner_y = xfrm.y + tins
    inner_w = max(xfrm.w - lins - rins, 1.0)
    inner_h = max(xfrm.h - tins - bins, 1.0)
    wrap_width = inner_w if wrap_mode == "square" else float("inf")
    para_lines: list[list[list[TextRun]]] = [
        _wrap_paragraph_into_lines(p, wrap_width) for p in paragraphs
    ]
    para_heights = [
        _paragraph_height_from_lines(p, lines)
        for p, lines in zip(paragraphs, para_lines)
    ]
    total_h = sum(para_heights)
    if anchor == "ctr":
        cursor_y = inner_y + max(0.0, (inner_h - total_h) / 2.0)
    elif anchor == "b":
        cursor_y = inner_y + max(0.0, inner_h - total_h)
    else:
        cursor_y = inner_y
    bottom_y = inner_y + inner_h
    text_blocks: list[str] = []
    for para, lines, height in zip(paragraphs, para_lines, para_heights):
        cursor_y += para.space_before_px
        visible_lines = _clip_lines_to_bottom(para, lines, cursor_y, bottom_y)
        if visible_lines:
            text_blocks.append(
                _emit_paragraph(para, visible_lines, inner_x, inner_w, cursor_y)
            )
        cursor_y += height + para.space_after_px
        if cursor_y >= bottom_y:
            break
    return TextResult(svg="\n".join(text_blocks), defs=_collect_text_defs(paragraphs))


def is_vertical_txbody(tx_body: ET.Element | None, xfrm: Xfrm | None = None) -> bool:
    if tx_body is None:
        return False
    body_pr = tx_body.find("a:bodyPr", NS)
    if body_pr is None:
        return False
    if body_pr.attrib.get("vert") in VERTICAL_TEXT_MODES:
        return True
    return _looks_like_auto_stacked_cjk(tx_body, body_pr, xfrm)


def convert_vertical_txbody(
    tx_body: ET.Element | None,
    xfrm: Xfrm,
    palette: ColorPalette | None,
    *,
    theme_fonts: dict[str, str] | None = None,
    default_fill: str = DEFAULT_FILL_HEX,
    default_font_size_px: float = DEFAULT_FONT_SIZE_PX,
    fallback_lst_styles: tuple[ET.Element, ...] = (),
    id_prefix: str = "txt",
    id_seq: list[int] | None = None,
) -> TextResult:
    """Render East Asian vertical text as upright stacked glyphs."""
    if tx_body is None:
        return TextResult()
    paragraphs = _parse_paragraphs(
        tx_body, palette, theme_fonts or {}, default_fill=default_fill,
        default_font_size_px=default_font_size_px,
        fallback_lst_styles=fallback_lst_styles,
        id_prefix=id_prefix, id_seq=id_seq,
    )
    runs = [
        run for para in paragraphs
        for run in para.runs
        if not run.is_break and run.text
    ]
    if not runs:
        return TextResult()
    box_x, box_y, box_w, box_h = _rotated_bbox(xfrm)
    center_x = box_x + box_w / 2.0
    glyphs: list[tuple[str, TextRun]] = []
    for run in runs:
        for char in run.text:
            if char in "\r\n":
                continue
            if char == " ":
                continue
            glyphs.append((char, run))
    if not glyphs:
        return TextResult()
    advances = [glyph_run.font_size_px * 1.05 for _, glyph_run in glyphs]
    total_h = sum(advances)
    top_y = box_y + max(0.0, (box_h - total_h) / 2.0)
    bottom_y = box_y + box_h
    spans: list[str] = []
    cursor_y = top_y
    first_run: TextRun | None = None
    first_baseline: float | None = None
    previous_baseline: float | None = None
    for (char, run), advance in zip(glyphs, advances):
        if cursor_y + advance > bottom_y:
            break
        baseline_y = cursor_y + run.font_size_px * 0.85
        tspan_attrs = _run_tspan_attrs(run)
        if first_run is None:
            first_run = run
            first_baseline = baseline_y
            spans.append(f"<tspan{tspan_attrs}>{_xml_escape(char)}</tspan>")
        else:
            dy = baseline_y - (previous_baseline or baseline_y)
            spans.append(
                f'<tspan x="{fmt_num(center_x)}" dy="{fmt_num(dy)}"'
                f"{tspan_attrs}>{_xml_escape(char)}</tspan>"
            )
        previous_baseline = baseline_y
        cursor_y += advance
    if first_run is None or first_baseline is None:
        return TextResult()
    attrs = _text_base_attrs(first_run, center_x, first_baseline, "middle")
    return TextResult(
        svg=f"<text{attrs}>{''.join(spans)}</text>",
        defs=_collect_text_defs(paragraphs),
    )


def _rotated_bbox(xfrm: Xfrm) -> tuple[float, float, float, float]:
    rot = round(xfrm.rot) % 360
    cx = xfrm.x + xfrm.w / 2.0
    cy = xfrm.y + xfrm.h / 2.0
    if rot in (90, 270):
        return cx - xfrm.h / 2.0, cy - xfrm.w / 2.0, xfrm.h, xfrm.w
    return xfrm.x, xfrm.y, xfrm.w, xfrm.h


def _looks_like_auto_stacked_cjk(
    tx_body: ET.Element, body_pr: ET.Element, xfrm: Xfrm | None,
) -> bool:
    if xfrm is None or xfrm.w <= 0 or xfrm.h <= 0:
        return False
    if body_pr.attrib.get("wrap", "square") != "square":
        return False
    if xfrm.w > 64 or xfrm.h < xfrm.w * 2.4:
        return False
    text = _plain_text(tx_body)
    chars = [ch for ch in text if not ch.isspace()]
    if len(chars) < 3 or len(chars) > 16:
        return False
    cjk_count = sum(1 for ch in chars if _is_cjk(ch))
    if cjk_count / len(chars) < 0.8:
        return False
    lins = _read_emu_attr(body_pr, "lIns", DEFAULT_INSETS_EMU["l"])
    rins = _read_emu_attr(body_pr, "rIns", DEFAULT_INSETS_EMU["r"])
    inner_w = max(xfrm.w - lins - rins, 1.0)
    return inner_w <= DEFAULT_FONT_SIZE_PX


def _plain_text(tx_body: ET.Element) -> str:
    parts: list[str] = []
    for text_elem in tx_body.findall(".//a:t", NS):
        if text_elem.text:
            parts.append(text_elem.text)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _read_emu_attr(elem: ET.Element | None, attr: str, default_emu: int) -> float:
    if elem is None:
        return emu_to_px(default_emu)
    val = elem.attrib.get(attr)
    if val is None:
        return emu_to_px(default_emu)
    try:
        return emu_to_px(int(val))
    except ValueError:
        return emu_to_px(default_emu)


def _parse_paragraphs(
    tx_body: ET.Element, palette: ColorPalette | None,
    theme_fonts: dict[str, str],
    *,
    default_fill: str = DEFAULT_FILL_HEX,
    default_font_size_px: float = DEFAULT_FONT_SIZE_PX,
    fallback_lst_styles: tuple[ET.Element, ...] = (),
    id_prefix: str = "txt", id_seq: list[int] | None = None,
) -> list[TextParagraph]:
    paragraphs: list[TextParagraph] = []
    autonum_state: dict[int, int] = {}
    lst_style = tx_body.find("a:lstStyle", NS)
    lst_styles = (
        (lst_style,) + fallback_lst_styles
        if lst_style is not None else fallback_lst_styles
    )
    for p_elem in tx_body.findall("a:p", NS):
        para = _parse_paragraph(
            p_elem, palette, theme_fonts, autonum_state,
            lst_styles=lst_styles, default_fill=default_fill,
            default_font_size_px=default_font_size_px,
            id_prefix=id_prefix, id_seq=id_seq,
        )
        paragraphs.append(para)
    return paragraphs


def _parse_paragraph(
    p_elem: ET.Element,
    palette: ColorPalette | None,
    theme_fonts: dict[str, str],
    autonum_state: dict[int, int],
    *,
    lst_styles: tuple[ET.Element, ...] = (),
    default_fill: str = DEFAULT_FILL_HEX,
    default_font_size_px: float = DEFAULT_FONT_SIZE_PX,
    id_prefix: str = "txt",
    id_seq: list[int] | None = None,
) -> TextParagraph:
    para = TextParagraph()
    p_pr = p_elem.find("a:pPr", NS)
    if p_pr is not None:
        try:
            para.level = int(p_pr.attrib.get("lvl", "0"))
        except ValueError:
            para.level = 0
    para_style_chain = (p_pr,) + _lst_style_level_prs(lst_styles, para.level)
    para.align = _attr_chain(para_style_chain, "algn") or "l"
    para.margin_left_px = _emu_px_attr_chain(para_style_chain, "marL", 0.0)
    para.indent_px = _emu_px_attr_chain(para_style_chain, "indent", 0.0)
    para.line_height_ratio = _line_height_ratio(para_style_chain)
    para.space_before_px = _spacing_points_px(para_style_chain, "a:spcBef/a:spcPts")
    para.space_after_px = _spacing_points_px(para_style_chain, "a:spcAft/a:spcPts")
    para.bullet_prefix = _resolve_bullet_prefix(para_style_chain, para.level, autonum_state)
    end_rpr = p_elem.find("a:endParaRPr", NS)
    def_rpr = p_pr.find("a:defRPr", NS) if p_pr is not None else None
    list_def_rpr = _child_chain(para_style_chain[1:], "a:defRPr")
    for child in list(p_elem):
        if not isinstance(child.tag, str):
            continue
        local = child.tag.split("}", 1)[-1]
        if local == "r":
            rpr = child.find("a:rPr", NS)
            text_elem = child.find("a:t", NS)
            text = text_elem.text or "" if text_elem is not None else ""
            run = _build_run(text, rpr, end_rpr, palette, theme_fonts,
                def_rpr=def_rpr, list_def_rpr=list_def_rpr,
                default_fill=default_fill, default_font_size_px=default_font_size_px,
                id_prefix=id_prefix, id_seq=id_seq)
            para.runs.append(run)
        elif local == "br":
            para.runs.append(TextRun(text="", font_size_px=default_font_size_px,
                font_family="sans-serif", fill=default_fill, is_break=True))
        elif local == "fld":
            rpr = child.find("a:rPr", NS)
            text_elem = child.find("a:t", NS)
            text = text_elem.text or "" if text_elem is not None else ""
            if text:
                run = _build_run(text, rpr, end_rpr, palette, theme_fonts,
                    def_rpr=def_rpr, list_def_rpr=list_def_rpr,
                    default_fill=default_fill, default_font_size_px=default_font_size_px,
                    id_prefix=id_prefix, id_seq=id_seq)
                para.runs.append(run)
    return para


def _build_run(text, rpr, end_rpr, palette, theme_fonts, *,
               def_rpr=None, list_def_rpr=None,
               default_fill=DEFAULT_FILL_HEX, default_font_size_px=DEFAULT_FONT_SIZE_PX,
               id_prefix="txt", id_seq=None):
    style_chain = (rpr, def_rpr, list_def_rpr, end_rpr)
    sz = _attr_chain(style_chain, "sz")
    font_size_px = hundredths_pt_to_px(int(sz)) if sz else default_font_size_px
    bold = _attr_chain(style_chain, "b") == "1"
    italic = _attr_chain(style_chain, "i") == "1"
    u_val = _attr_chain(style_chain, "u")
    underline = u_val not in (None, "", "none")
    strike_val = _attr_chain(style_chain, "strike")
    strikethrough = strike_val in ("sngStrike", "dblStrike")
    spc = _attr_chain(style_chain, "spc")
    letter_spacing_px = 0.0
    if spc is not None:
        try:
            letter_spacing_px = float(spc) / 100.0 * 4.0 / 3.0
        except ValueError:
            pass
    fill = default_fill
    fill_opacity = 1.0
    defs = []
    color_source = None
    for src in style_chain:
        if src is None:
            continue
        grad = src.find("a:gradFill", NS)
        if grad is not None:
            grad_fill = resolve_fill(grad, palette, id_prefix=id_prefix, id_seq=id_seq)
            if grad_fill.attrs.get("fill"):
                fill = grad_fill.attrs["fill"]
                fill_opacity = 1.0
                defs.extend(grad_fill.defs)
                color_source = None
                break
        solid = src.find("a:solidFill", NS)
        if solid is not None:
            color_source = solid
            break
    if color_source is not None:
        color_elem = find_color_elem(color_source)
        hex_, alpha = resolve_color(color_elem, palette)
        if hex_:
            fill = hex_
            fill_opacity = alpha
    latin_face = _typeface_chain(style_chain, "latin")
    ea_face = _typeface_chain(style_chain, "ea")
    cs_face = _typeface_chain(style_chain, "cs")
    latin_face = _resolve_theme_typeface(latin_face, theme_fonts)
    ea_face = _resolve_theme_typeface(ea_face, theme_fonts)
    cs_face = _resolve_theme_typeface(cs_face, theme_fonts)
    font_family = _build_font_stack(latin_face, ea_face, cs_face)
    return TextRun(text=text, font_size_px=font_size_px, font_family=font_family,
        fill=fill, fill_opacity=fill_opacity, defs=defs,
        bold=bold, italic=italic, underline=underline, strikethrough=strikethrough,
        letter_spacing_px=letter_spacing_px)


def _lst_style_level_prs(lst_styles, level):
    level_idx = min(max(level, 0), 8) + 1
    level_prs = []
    for lst_style in lst_styles:
        lvl_pr = lst_style.find(f"a:lvl{level_idx}pPr", NS)
        if lvl_pr is not None:
            level_prs.append(lvl_pr)
    return tuple(level_prs)


def _child_chain(sources, path):
    for src in sources:
        if src is None:
            continue
        child = src.find(path, NS)
        if child is not None:
            return child
    return None


def _emu_px_attr_chain(sources, attr, default):
    value = _attr_chain(sources, attr)
    if value is None:
        return default
    try:
        return emu_to_px(int(value))
    except ValueError:
        return default


def _line_height_ratio(sources):
    ln_spc = _child_chain(sources, "a:lnSpc")
    if ln_spc is None:
        return DEFAULT_LINE_HEIGHT_RATIO
    spc_pct = ln_spc.find("a:spcPct", NS)
    if spc_pct is None:
        return DEFAULT_LINE_HEIGHT_RATIO
    try:
        return float(spc_pct.attrib.get("val", "100000")) / 100000.0
    except ValueError:
        return DEFAULT_LINE_HEIGHT_RATIO


def _spacing_points_px(sources, path):
    spacing = _child_chain(sources, path)
    if spacing is None:
        return 0.0
    try:
        return hundredths_pt_to_px(int(spacing.attrib.get("val", "0")))
    except ValueError:
        return 0.0


def _attr_chain(sources, attr):
    for src in sources:
        if src is None:
            continue
        v = src.attrib.get(attr)
        if v is not None:
            return v
    return None


def _typeface(rpr, child_tag):
    if rpr is None:
        return None
    elem = rpr.find(f"a:{child_tag}", NS)
    if elem is None:
        return None
    val = elem.attrib.get("typeface")
    return val or None


def _typeface_chain(sources, child_tag):
    for src in sources:
        face = _typeface(src, child_tag)
        if face:
            return face
    return None


def _resolve_theme_typeface(face, theme_fonts):
    if not face or not face.startswith("+"):
        return face
    code = face[1:]
    if code == "mj-lt":
        return theme_fonts.get("majorLatin") or face
    if code == "mn-lt":
        return theme_fonts.get("minorLatin") or face
    if code == "mj-ea":
        return theme_fonts.get("majorEastAsia") or theme_fonts.get("majorLatin") or face
    if code == "mn-ea":
        return theme_fonts.get("minorEastAsia") or theme_fonts.get("minorLatin") or face
    return face


def _build_font_stack(latin, ea, cs):
    parts = []
    seen = set()
    for face in (latin, ea, cs):
        if face and face not in seen:
            parts.append(_quote_font(face))
            seen.add(face)
    parts.append("sans-serif")
    return ", ".join(parts)


def _quote_font(name):
    if any(c.isspace() or ord(c) > 127 for c in name):
        return f"&quot;{name}&quot;"
    return name


def _resolve_bullet_prefix(sources, level, autonum_state):
    bu_none = _child_chain(sources, "a:buNone")
    if bu_none is not None:
        autonum_state.pop(level, None)
        return ""
    bu_char = _child_chain(sources, "a:buChar")
    if bu_char is not None:
        ch = bu_char.attrib.get("char", "\u2022")
        return f"{ch} "
    bu_auto = _child_chain(sources, "a:buAutoNum")
    if bu_auto is not None:
        start_at = bu_auto.attrib.get("startAt")
        if start_at is not None:
            try:
                autonum_state[level] = int(start_at)
            except ValueError:
                autonum_state[level] = 1
        else:
            autonum_state[level] = autonum_state.get(level, 0) + 1
        return _format_auto_number(autonum_state[level], bu_auto.attrib.get("type", "arabicPeriod"))
    return ""


def _format_auto_number(value, kind):
    lower = kind.lower()
    if "alphalc" in lower:
        token = _alpha_number(value, uppercase=False)
    elif "alphauc" in lower:
        token = _alpha_number(value, uppercase=True)
    elif "romanlc" in lower:
        token = _roman_number(value).lower()
    elif "romanuc" in lower:
        token = _roman_number(value).upper()
    else:
        token = str(value)
    if "parenboth" in lower:
        return f"({token}) "
    if "parenr" in lower:
        return f"{token}) "
    if "period" in lower:
        return f"{token}. "
    return f"{token} "


def _alpha_number(value, *, uppercase):
    value = max(1, value)
    chars = []
    while value:
        value -= 1
        chars.append(chr(ord("A") + (value % 26)))
        value //= 26
    text = "".join(reversed(chars))
    return text if uppercase else text.lower()


def _roman_number(value):
    value = max(1, min(value, 3999))
    parts = []
    for n, token in ((1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),
        (100,"C"),(90,"XC"),(50,"L"),(40,"XL"),
        (10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")):
        while value >= n:
            parts.append(token)
            value -= n
    return "".join(parts)


def _has_visible_text(paragraphs):
    for p in paragraphs:
        for r in p.runs:
            if r.text.strip():
                return True
    return False


def _collect_text_defs(paragraphs):
    defs = []
    seen = set()
    for para in paragraphs:
        for run in para.runs:
            for item in run.defs:
                if item not in seen:
                    defs.append(item)
                    seen.add(item)
    return defs


def _is_cjk(ch):
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x2E80 <= cp <= 0x2EFF or 0x3000 <= cp <= 0x303F or
            0xFF00 <= cp <= 0xFFEF or 0xF900 <= cp <= 0xFAFF or
            0x20000 <= cp <= 0x2A6DF)


def _char_width(ch, font_size, bold):
    """改进的字宽估算 — 区分 CJK、拉丁字母、数字和标点"""
    if _is_cjk(ch):
        w = font_size
    elif ch == ' ':
        w = font_size * 0.28
    elif ch in 'mMwWOQ%':
        w = font_size * 0.72
    elif ch in 'iIlj!|':
        w = font_size * 0.28
    elif ch in '.,:;':
        w = font_size * 0.25
    elif ch.isdigit():
        w = font_size * 0.55
    elif ch.isalpha():
        # 小写字母稍窄，大写稍宽
        if ch.isupper():
            w = font_size * 0.62
        else:
            w = font_size * 0.48
    else:
        w = font_size * 0.5
    if bold and not _is_cjk(ch):
        w *= 1.08
    return w


def _estimate_run_width(text, run):
    glyph_width = sum(_char_width(c, run.font_size_px, run.bold) for c in text)
    tracking_width = run.letter_spacing_px * max(len(text) - 1, 0)
    return (glyph_width + tracking_width) * 1.05


def _advance_width(ch, index_in_segment, run):
    tracking = run.letter_spacing_px if index_in_segment > 0 else 0.0
    return _char_width(ch, run.font_size_px, run.bold) + tracking


def _find_break_point(text, start, max_width, run):
    """改进的断点查找 — 在 CJK/拉丁混合文本中智能断开"""
    cur_w = 0.0
    last_break = start
    last_break_w = 0.0
    # 识别当前段落的文字类型上下文
    in_latin_word = False
    for i in range(start, len(text)):
        ch = text[i]
        ch_w = _advance_width(ch, i - start, run)
        is_latin_char = ch.isalpha() and not _is_cjk(ch)

        # 检测拉丁词边界（从CJK/标点进入拉丁字母）
        if is_latin_char and not in_latin_word:
            in_latin_word = True
            # 在进入新拉丁词时标记可能的断点（保留当前词不跨行）
            if cur_w > 0:
                last_break = i
                last_break_w = cur_w

        # 检测拉丁词结束
        if in_latin_word and not is_latin_char:
            in_latin_word = False
            if ch.isspace():
                last_break = i + 1
                last_break_w = cur_w + ch_w

        if cur_w + ch_w > max_width:
            if last_break > start:
                return last_break, last_break_w
            # 实在找不到合适的断点，强制在当前字符后断开
            if cur_w > max_width * 0.5:
                return i, cur_w
            return start, 0.0
        cur_w += ch_w

        # 标记可断点：空格 / CJK字符 / 中英文标点 / 连字符
        if ch.isspace():
            last_break = i + 1
            last_break_w = cur_w
        elif _is_cjk(ch):
            last_break = i + 1
            last_break_w = cur_w
        elif ch in "-\u2014\u2013\u3001\u3002\uff01\uff1f\uff1a\uff1b\u2018\u2019\u201c\u201d":
            last_break = i + 1
            last_break_w = cur_w
    return len(text), cur_w


def _wrap_paragraph_into_lines(para, max_width):
    lines = [[]]
    cur_w = 0.0
    if _should_keep_single_line(para, max_width):
        return [[_copy_run(run, text=run.text) for run in para.runs if not run.is_break and run.text]]
    if para.bullet_prefix and para.runs:
        first_run = next((r for r in para.runs if not r.is_break), None)
        if first_run is not None:
            bullet_run = _copy_run(first_run, text=para.bullet_prefix)
            lines[-1].append(bullet_run)
            cur_w = _estimate_run_width(para.bullet_prefix, bullet_run)
    for run in para.runs:
        if run.is_break:
            lines.append([])
            cur_w = 0.0
            continue
        if not run.text:
            continue
        text = run.text
        i = 0
        while i < len(text):
            avail = max_width - cur_w
            if avail <= 0 and lines[-1]:
                lines.append([])
                cur_w = 0.0
                avail = max_width
            end, used = _find_break_point(text, i, avail, run)
            if end == i:
                if lines[-1]:
                    lines.append([])
                    cur_w = 0.0
                    continue
                end = i + 1
                used = _advance_width(text[i], 0, run)
            chunk = text[i:end]
            lines[-1].append(_copy_run(run, text=chunk))
            cur_w += used
            i = end
            if i < len(text):
                lines.append([])
                cur_w = 0.0
    return lines


def _should_keep_single_line(para, max_width):
    """判断是否保持单行 — 对短文本（≤18非空字符）或刚好能放入的文本保持单行"""
    if max_width == float("inf"):
        return False
    if any(run.is_break for run in para.runs):
        return False
    text_runs = [run for run in para.runs if run.text]
    if not text_runs:
        return False
    text = "".join(run.text for run in text_runs)
    non_space_count = sum(1 for ch in text if not ch.isspace())
    if non_space_count <= 18:
        return True
    # 考虑 bullet 前缀的宽度占用
    bullet_extra = _estimate_run_width(para.bullet_prefix, text_runs[0]) if para.bullet_prefix else 0
    estimated = sum(_estimate_run_width(run.text, run) for run in text_runs) + bullet_extra
    return estimated <= max_width * 1.15


def _copy_run(run, *, text):
    return TextRun(text=text, font_size_px=run.font_size_px,
        font_family=run.font_family, fill=run.fill,
        fill_opacity=run.fill_opacity, defs=list(run.defs),
        bold=run.bold, italic=run.italic, underline=run.underline,
        strikethrough=run.strikethrough, letter_spacing_px=run.letter_spacing_px)


def _paragraph_height_from_lines(p, lines):
    if not lines:
        return DEFAULT_FONT_SIZE_PX * p.line_height_ratio
    height = 0.0
    for line in lines:
        height += _line_height(p, line)
    return height


def _line_height(p, line):
    max_font = max((r.font_size_px for r in line), default=DEFAULT_FONT_SIZE_PX)
    return max_font * p.line_height_ratio


def _clip_lines_to_bottom(para, lines, top_y, bottom_y):
    visible = []
    cursor_y = top_y
    for line in lines:
        line_h = _line_height(para, line)
        if cursor_y >= bottom_y:
            break
        visible.append(line)
        cursor_y += line_h
    return visible


def _emit_paragraph(para, lines, inner_x, inner_w, top_y):
    align = para.align
    if align == "ctr":
        anchor_x = inner_x + inner_w / 2.0
        text_anchor = "middle"
    elif align == "r":
        anchor_x = inner_x + inner_w
        text_anchor = "end"
    else:
        anchor_x = inner_x + para.indent_px + para.margin_left_px
        text_anchor = "start"
    if not lines or all(not line for line in lines):
        return ""
    first_line_idx = next((i for i, ln in enumerate(lines) if ln), 0)
    first_line = lines[first_line_idx]
    first_run = first_line[0] if first_line else None
    first_font = first_run.font_size_px if first_run else DEFAULT_FONT_SIZE_PX
    first_baseline = top_y + 0.85 * first_font
    base_font_family = first_run.font_family if first_run else "sans-serif"
    spans = []
    for line_idx, line in enumerate(lines):
        if not line:
            spans.append(f'<tspan x="{fmt_num(anchor_x)}" dy="{fmt_num(first_font * para.line_height_ratio)}"></tspan>')
            continue
        line_font = max(r.font_size_px for r in line)
        for run_idx, run in enumerate(line):
            attrs = _run_tspan_attrs(run, base_font_family=base_font_family)
            if run_idx == 0 and line_idx > 0:
                spans.append(f'<tspan x="{fmt_num(anchor_x)}" dy="{fmt_num(line_font * para.line_height_ratio)}"{attrs}>{_xml_escape(run.text)}</tspan>')
            else:
                spans.append(f"<tspan{attrs}>{_xml_escape(run.text)}</tspan>")
    base_attrs = _text_base_attrs(first_run, anchor_x, first_baseline, text_anchor)
    return f"<text{base_attrs}>{''.join(spans)}</text>"


def _text_base_attrs(run, x, y, text_anchor):
    parts = [f'x="{fmt_num(x)}"', f'y="{fmt_num(y)}"', f'text-anchor="{text_anchor}"', 'xml:space="preserve"']
    if run is None:
        return " " + " ".join(parts)
    parts.append(f'font-family="{run.font_family}"')
    parts.append(f'font-size="{fmt_num(run.font_size_px)}"')
    parts.append(f'fill="{run.fill}"')
    if run.fill_opacity < 1.0:
        parts.append(f'fill-opacity="{fmt_num(run.fill_opacity, 4)}"')
    if run.bold:
        parts.append('font-weight="bold"')
    if run.italic:
        parts.append('font-style="italic"')
    if run.underline and run.strikethrough:
        parts.append('text-decoration="underline line-through"')
    elif run.underline:
        parts.append('text-decoration="underline"')
    elif run.strikethrough:
        parts.append('text-decoration="line-through"')
    if run.letter_spacing_px:
        parts.append(f'letter-spacing="{fmt_num(run.letter_spacing_px)}"')
    return " " + " ".join(parts)


def _run_tspan_attrs(run, base_font_family: str | None = None):
    """改进的 tspan 属性 — 加入 font-family 当与父元素不同时"""
    parts = [f'fill="{run.fill}"', f'font-size="{fmt_num(run.font_size_px)}"']
    if run.font_family != (base_font_family or "") and base_font_family is not None:
        parts.append(f'font-family="{run.font_family}"')
    if run.fill_opacity < 1.0:
        parts.append(f'fill-opacity="{fmt_num(run.fill_opacity, 4)}"')
    if run.bold:
        parts.append('font-weight="bold"')
    if run.italic:
        parts.append('font-style="italic"')
    if run.underline and run.strikethrough:
        parts.append('text-decoration="underline line-through"')
    elif run.underline:
        parts.append('text-decoration="underline"')
    elif run.strikethrough:
        parts.append('text-decoration="line-through"')
    if run.letter_spacing_px:
        parts.append(f'letter-spacing="{fmt_num(run.letter_spacing_px)}"')
    return " " + " ".join(parts)


def _xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
