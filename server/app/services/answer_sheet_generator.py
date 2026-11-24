"""动态答题卡 HTML / PDF 生成器

根据试卷题目数据或参数动态生成可打印/导出为 PDF 的答题卡。
使用 CSS Flexbox 布局，分为顶部（左右并排）和底部（题目区）两行。
与教师端摄像头扫描批卷功能相通：生成的答题卡同时输出坐标配置供扫描定位。

用法:
    from app.services.answer_sheet_generator import generate_answer_sheet_html

    html = generate_answer_sheet_html(
        question_count=80,
        options=["A", "B", "C", "D", "E", "F", "G"],
        id_digits=6,
        id_options=["1","2","3","4","5","6","7","8","9"],
    )
"""

import os
from app.core.paths import UPLOADS_DIR
from typing import List, Optional, Dict, Any

# 答题卡文件存储目录（对应 main.py 中 StaticFiles mount 的 /uploads 路径）
_ANSWER_SHEETS_DIR = str(UPLOADS_DIR / "answer_sheets")


def _make_option_letters(count: int) -> List[str]:
    """生成选项字母列表，例如 5 -> ['A','B','C','D','E']"""
    return [chr(65 + i) for i in range(count)]


def _make_digit_labels(limit: int, start: int = 1) -> List[str]:
    """生成考号数字列表 start..limit，如 0..9"""
    return [str(i) for i in range(start, limit + 1)]


# 不同纸张对应的容器宽度（CSS px，留边距）
_CONTAINER_WIDTHS = {"A5": "520px", "A4": "750px"}

# A5 缩小比例（框大小*字号*考号格）
_A5_SCALE = 0.75


def _build_styles(
    page_size: str,
    id_digits: int,
    id_option_count: int,
) -> str:
    """生成动态 CSS 样式（Flexbox 布局，匹配用户模板风格）"""
    # 考号格大小
    id_box_size = max(28, min(38, int(200 / id_option_count)))
    container_width = _CONTAINER_WIDTHS.get(page_size.upper(), "520px")
    # A5 缩小考号格
    if page_size.upper() == "A5":
        id_box_size = max(20, int(id_box_size * _A5_SCALE))
    # 选项框大小
    if page_size.upper() == "A5":
        opt_w, opt_h, opt_fs = "3.8mm", "2.2mm", "10pt"
        qrow_g, group_gap = "0.2mm", "1.5mm"
    else:
        opt_w, opt_h, opt_fs = "4.5mm", "2.5mm", "10pt"
        qrow_g, group_gap = "0.5mm", "2.5mm"
    css_page_size = page_size.lower() if page_size else "a5"

    return f"""@page{{size:{css_page_size} portrait;margin:0;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{
  font-family:'SimSun','STSong','SimHei','Microsoft YaHei',serif;
  color:#000;background:#f0f0f0;
  -webkit-print-color-adjust:exact;print-color-adjust:exact;
}}
/* ── 答题卡主容器（固定大小，用于扫描定位） ── */
.exam-container{{
  width:{container_width};min-height:800px;
  background:#fff;border:3px solid #000;
  box-sizing:border-box;
  display:flex;flex-direction:column;
  margin:0 auto;
}}
/* ── 标题 ── */
.title{{
  text-align:center;font-size:16pt;font-weight:700;
  letter-spacing:3pt;padding-bottom:2mm;
  border-bottom:2px solid #000;margin-bottom:3mm;
}}
/* ── 上区：左右并排，底部分隔线 ── */
.top-section{{
  display:flex;
  border-bottom:3px solid #000;
}}
/* 左上：学生信息区 */
.left-info-area{{
  width:35%;padding:3mm;
  border-right:3px solid #000;
  box-sizing:border-box;
  display:flex;flex-direction:column;
}}
.tl-title{{
  font-size:9pt;font-weight:700;text-align:center;
  margin-bottom:2.5mm;padding-bottom:1.5mm;border-bottom:1px solid #999;
}}
.tl-row{{
  display:flex;align-items:flex-end;margin-bottom:3mm;font-size:10pt;
}}
.tl-label{{font-weight:700;white-space:nowrap;min-width:18mm;}}
.tl-line{{flex:1;border-bottom:1.5px solid #000;height:5mm;margin-left:1.5mm;}}
.tl-instructions{{
  font-size:7.5pt;margin-top:2mm;line-height:1.7;color:#333;
}}
.tl-example{{
  display:flex;align-items:center;margin-top:2mm;font-size:9pt;font-weight:700;gap:2mm;
}}
.tl-example-block{{
  display:inline-block;width:8mm;height:8mm;background:#000;border:1px solid #000;
}}
/* 右上：考号填涂区 */
.right-id-area{{
  flex:1;padding:2mm 3mm;
}}
.tr-title{{
  font-size:9pt;font-weight:700;text-align:center;
  margin-bottom:1.5mm;letter-spacing:2pt;
}}
.tr-hint{{
  font-size:7pt;color:#666;text-align:center;margin-bottom:2mm;
}}
.id-grid{{
  display:flex;gap:2mm;justify-content:center;
}}
.id-col{{
  display:flex;flex-direction:column;align-items:center;gap:0.5mm;
}}
.id-header{{
  width:{id_box_size}px;height:{id_box_size}px;
  border:1.5px solid #666;display:flex;
  align-items:center;justify-content:center;
  font-size:8pt;font-weight:700;margin-bottom:1mm;
}}
.id-row{{
  display:flex;flex-direction:column;align-items:center;gap:1mm;
}}
.id-box{{
  display:inline-flex;justify-content:center;align-items:center;
  width:{id_box_size}px;height:{id_box_size}px;
  border:1.5px solid #000;font-weight:700;
  font-size:8pt;background:#fff;
}}
/* ── CSDN 锚点（四角 + 行列网格锚点） ── */
/* 锚点必须位于答题卡内部可见区域，供 OMR 扫描器定位 */
.anchor-corner{{
  position:absolute;width:2.5mm;height:2.5mm;
  background:#000;border:0.3mm solid #000;
}}
.anchor-row-marker{{
  display:inline-block;width:3mm;height:3mm;
  background:#000;border:0.3mm solid #000;
  flex-shrink:0;margin-right:0.5mm;
}}
.anchor-col-marker{{
  display:inline-block;width:3mm;height:3mm;
  background:#000;border:0.3mm solid #000;
  flex-shrink:0;margin-bottom:0.5mm;
}}
/* ── 行锚点列容器 ── */
.anchor-row-col{{
  display:flex;flex-direction:column;gap:{qrow_g};
  flex-shrink:0;width:3.5mm;
  justify-content:flex-start;
  padding-top:2.5mm; /* 对齐第一行的 question-number */
}}
/* ── 列锚点行容器 ── */
.anchor-col-row{{
  display:none; /* 列锚点暂时不用，从四角锚点推算 */
}}
/* ── 下区：题目填涂区（4列×5行列主布局，等宽均匀分布） ── */
.bottom-questions-area{{
  padding:2mm 3mm;
  flex:1;position:relative;
}}
.qs-area{{
  display:flex;flex-direction:column;gap:2.5mm;
}}
.qs-group{{
  display:flex;gap:{group_gap};
  page-break-inside:avoid;
  margin-bottom:2mm;position:relative;
}}
.qs-col{{
  display:flex;flex-direction:column;gap:0.5mm;
  flex:1;min-width:0;
}}
.qs-qrow{{
  display:flex;align-items:center;gap:{qrow_g};
  justify-content:flex-start;
}}
.question-number{{
  font-size:7pt;font-weight:700;min-width:5mm;text-align:right;
  padding-right:0.8mm;
}}
.option-box{{
  display:inline-flex;align-items:center;justify-content:center;
  width:5mm;height:5mm;
  border:1.2px solid #000;
  font-size:7pt;font-weight:700;background:#fff;
  flex-shrink:0;margin:0 0.3mm;
}}
/* ── 图例说明 ── */
.legend{{
  display:flex;justify-content:center;gap:2mm;margin-top:1mm;
  font-size:6pt;align-items:center;flex-wrap:wrap;
}}
.lg-item{{display:flex;align-items:center;gap:0.5mm;}}
.lg-box{{
  border:1px solid #000;padding:0.3mm 1mm;font-weight:700;font-size:6pt;
}}
.lg-box-fill{{
  border:1px solid #000;padding:0.3mm 1mm;font-weight:700;font-size:6pt;
  background:#000;color:#fff;
}}
/* ── 页脚 ── */
.footer{{
  display:flex;justify-content:space-between;align-items:center;
  padding-top:1mm;margin-top:1mm;border-top:1.5px solid #000;font-size:6pt;
}}
/* ── 打印优化：保持固定宽度不缩放 ── */
@media print{{
  body{{background:#fff;padding:0;}}
  .exam-container{{width:{container_width};border:3px solid #000;margin:0 auto;position:relative;}}
}}
"""


def _build_student_info_section(show_student_id: bool) -> str:
    """生成左上方学生信息区（姓名、班级、考号填写、说明、示例）"""
    parts = [
        '<div class="left-info-area">',
        '<div class="tl-title">▼ 请用黑色签字笔填写</div>',
        '<div class="tl-row"><span class="tl-label">姓　名</span><span class="tl-line"></span></div>',
        '<div class="tl-row"><span class="tl-label">班　级</span><span class="tl-line"></span></div>',
    ]
    if show_student_id:
        parts.append(
            '<div class="tl-row"><span class="tl-label">考　号</span><span class="tl-line"></span></div>'
        )
    parts.extend([
        '<div class="tl-instructions">',
        '1. 用2B铅笔涂黑对应选项<br>',
        '2. 保持卡面平整清洁，不做多余填涂<br>',
        '3. 修改请用橡皮擦干净',
        '</div>',
        '<div class="tl-example">',
        '填涂示例 <span class="tl-example-block"></span>',
        '</div>',
        '</div>',
    ])
    return "\n".join(parts)


def _build_id_fill_section(
    id_digits: int,
    id_options: List[str],
) -> str:
    """生成右上方考号填涂区（每列对应一位数，每位有 id_options 个可涂选项）"""
    cols_html = []
    for _col_idx in range(1, id_digits + 1):
        cells = []
        for opt in id_options:
            cells.append(
                f'<span class="id-box">{opt}</span>'
            )
        cols_html.append(
            f'<div class="id-col">'
            f'<div class="id-header"></div>'
            f'<div class="id-row">{"".join(cells)}</div>'
            f'</div>'
        )
    id_grid = "\n".join(cols_html)

    return (
        '<div class="right-id-area">\n'
        '  <div class="tr-title">考 号 填 涂 区</div>\n'
        '  <div class="tr-hint">（用2B铅笔涂黑，位数不够在前面补0）</div>\n'
        f'  <div class="id-grid">\n{id_grid}\n  </div>\n'
        '</div>'
    )


def _build_question_area(
    question_count: int,
    options: List[str],
) -> str:
    """生成题目填涂区：4列×5行列主布局，7选项每列占2个组位（2列布局）"""
    # 7选项时每列占2个组位，只能排2列；4选项占1个组位，排4列
    has_7opt = len(options[:7]) > 4
    COLS = 2 if has_7opt else 4
    ROWS = 5
    GROUP_SIZE = COLS * ROWS  # 7选项时10题一组，4选项时20题一组

    groups = []
    start = 1
    while start <= question_count:
        # CSDN 行锚点：左侧每行一个可见小黑块（inline-block在专用列中）
        row_anchors_html = "".join(
            f'<div class="anchor-row-marker"></div>'
            for _ in range(ROWS)
        )
        row_anchors_col = f'<div class="anchor-row-col">{row_anchors_html}</div>'
        # CSDN 四角锚点（每组外框四个角各一个小黑块，视觉参考）
        corner_anchors_html = (
            f'<div class="anchor-corner" style="top:-3mm;left:-3mm;"></div>'
            f'<div class="anchor-corner" style="top:-3mm;right:-3mm;"></div>'
            f'<div class="anchor-corner" style="bottom:-3mm;left:-3mm;"></div>'
            f'<div class="anchor-corner" style="bottom:-3mm;right:-3mm;"></div>'
        )

        cols_html = []
        for col in range(COLS):
            qs = []
            for row in range(ROWS):
                qn = start + col * ROWS + row
                if qn > question_count:
                    break
                # 以7选项为标准，不足7个的留空
                col_opts = options[:7]
                opt_s = "".join(
                    f'<span class="option-box">{o[0] if o else "?"}</span>'
                    for o in col_opts
                )
                qs.append(
                    f'<div class="qs-qrow">'
                    f'<span class="question-number">{qn}.</span>{opt_s}</div>'
                )
            if qs:
                cols_html.append(f'<div class="qs-col">{"".join(qs)}</div>')
        if cols_html:
            groups.append(
                f'<div class="qs-group">'
                f'{row_anchors_col}{corner_anchors_html}{"".join(cols_html)}'
                f'</div>'
            )
        start += GROUP_SIZE
    return "\n".join(groups)


def _build_question_area_from_json(
    questions: List[Dict[str, Any]],
) -> str:
    """基于选择题JSON生成题目填涂区（4列×5行列主布局）

    每题为 {"question_number":1, "options":["A","B","C","D"], ...}
    全局统一按题号排入 4列×5行 的网格中（列主序），不按选项数分组。
    包含7选项题的列占flex:2（占2个组位），只有4选项的列占flex:1。
    """
    COLS = 4
    ROWS = 5
    GROUP_SIZE = COLS * ROWS

    q_by_num: Dict[int, dict] = {}
    for q in questions:
        qn = q.get("question_number", q.get("number"))
        if qn is not None:
            q_by_num[int(qn)] = q
    if not q_by_num:
        return ""

    all_qns = sorted(q_by_num.keys())
    first_qn, last_qn = all_qns[0], all_qns[-1]

    groups = []
    start = first_qn
    while start <= last_qn:
        # 先检查每列是否有7选项题，决定flex权重
        col_flex = []
        for col in range(COLS):
            has_7opt = False
            for row in range(ROWS):
                qn = start + col * ROWS + row
                if qn > last_qn or qn not in q_by_num:
                    continue
                opts = q_by_num[qn].get("options", ["A", "B", "C", "D"])
                if len(opts) > 4:
                    has_7opt = True
                    break
            col_flex.append(2 if has_7opt else 1)

        # CSDN 行锚点：左侧每行一个可见小黑块（inline-block在专用列中）
        row_anchors_html = "".join(
            f'<div class="anchor-row-marker"></div>'
            for _ in range(ROWS)
        )
        row_anchors_col = f'<div class="anchor-row-col">{row_anchors_html}</div>'
        # CSDN 四角锚点（每组外框四个角各一个小黑块，视觉参考）
        corner_anchors_html = (
            f'<div class="anchor-corner" style="top:-3mm;left:-3mm;"></div>'
            f'<div class="anchor-corner" style="top:-3mm;right:-3mm;"></div>'
            f'<div class="anchor-corner" style="bottom:-3mm;left:-3mm;"></div>'
            f'<div class="anchor-corner" style="bottom:-3mm;right:-3mm;"></div>'
        )

        cols_html = []
        for col in range(COLS):
            qs = []
            for row in range(ROWS):
                qn = start + col * ROWS + row
                if qn > last_qn or qn not in q_by_num:
                    continue
                opts = q_by_num[qn].get("options", ["A", "B", "C", "D"])
                opt_s = "".join(
                    f'<span class="option-box">{o[0] if o else "?"}</span>'
                    for o in opts
                )
                qs.append(
                    f'<div class="qs-qrow">'
                    f'<span class="question-number">{qn}.</span>{opt_s}</div>'
                )
            if qs:
                cols_html.append(
                    f'<div class="qs-col" style="flex:{col_flex[col]}">'
                    f'{"".join(qs)}</div>'
                )
        if cols_html:
            groups.append(
                f'<div class="qs-group">'
                f'{row_anchors_col}{corner_anchors_html}{"".join(cols_html)}'
                f'</div>'
            )
        start += GROUP_SIZE
    return "\n".join(groups)


def _build_section_title(section_name: str, question_range: str, option_count: int) -> str:
    """生成答题卡分区标题"""
    return (
        f'<div class="section-title">'
        f'<span class="section-name">{section_name}</span>'
        f'<span class="section-range">{question_range}</span>'
        f'<span class="section-opts">共{option_count}个选项</span>'
        f'</div>'
    )


def _build_json_styles(
    page_size: str,
    id_digits: int,
    id_option_count: int,
) -> str:
    """生成动态CSS样式（选项框固定4mm×2mm，行优先布局）"""
    id_box_size = max(28, min(38, int(200 / id_option_count)))
    container_width = _CONTAINER_WIDTHS.get(page_size.upper(), "520px")
    # A5 缩小考号格
    if page_size.upper() == "A5":
        id_box_size = max(20, int(id_box_size * _A5_SCALE))
    # 选项框大小
    if page_size.upper() == "A5":
        opt_w, opt_h, opt_fs = "3.8mm", "2.2mm", "10pt"
        qrow_g, group_gap = "0.2mm", "1.5mm"
    else:
        opt_w, opt_h, opt_fs = "4.5mm", "2.5mm", "10pt"
        qrow_g, group_gap = "0.5mm", "2.5mm"
    css_page_size = page_size.lower() if page_size else "a5"

    return f"""@page{{size:{css_page_size} portrait;margin:0;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{
  font-family:'SimSun','STSong','SimHei','Microsoft YaHei',serif;
  color:#000;background:#f0f0f0;
  -webkit-print-color-adjust:exact;print-color-adjust:exact;
}}
/* ── 答题卡主容器（固定大小，用于扫描定位） ── */
.exam-container{{
  width:{container_width};min-height:800px;
  background:#fff;border:3px solid #000;
  box-sizing:border-box;
  display:flex;flex-direction:column;
  margin:0 auto;
}}
.title{{
  text-align:center;font-size:16pt;font-weight:700;
  letter-spacing:3pt;padding-bottom:2mm;
  border-bottom:2px solid #000;margin-bottom:3mm;
}}
.top-section{{
  display:flex;
  border-bottom:3px solid #000;
}}
.top-left{{
  width:30%;border:2px solid #000;padding:3mm;display:flex;flex-direction:column;
}}
.left-info-area{{
  width:35%;padding:3mm;
  border-right:3px solid #000;
  box-sizing:border-box;
  display:flex;flex-direction:column;
}}
.tl-title{{
  font-size:9pt;font-weight:700;text-align:center;
  margin-bottom:2.5mm;padding-bottom:1.5mm;border-bottom:1px solid #999;
}}
.tl-row{{
  display:flex;align-items:flex-end;margin-bottom:3mm;font-size:10pt;
}}
.tl-label{{font-weight:700;white-space:nowrap;min-width:18mm;}}
.tl-line{{flex:1;border-bottom:1.5px solid #000;height:5mm;margin-left:1.5mm;}}
.tl-instructions{{
  font-size:7.5pt;margin-top:2mm;line-height:1.7;color:#333;
}}
.tl-example{{
  display:flex;align-items:center;margin-top:2mm;font-size:9pt;font-weight:700;gap:2mm;
}}
.tl-example-block{{
  display:inline-block;width:8mm;height:8mm;background:#000;border:1px solid #000;
}}
/* ── CSDN 锚点（四角 + 行列网格锚点） ── */
/* 锚点必须位于答题卡内部可见区域，供 OMR 扫描器定位 */
.anchor-corner{{
  position:absolute;width:2.5mm;height:2.5mm;
  background:#000;border:0.3mm solid #000;
}}
.anchor-row-marker{{
  display:inline-block;width:3mm;height:3mm;
  background:#000;border:0.3mm solid #000;
  flex-shrink:0;margin-right:0.5mm;
}}
.anchor-col-marker{{
  display:inline-block;width:3mm;height:3mm;
  background:#000;border:0.3mm solid #000;
  flex-shrink:0;margin-bottom:0.5mm;
}}
/* ── 行锚点列容器 ── */
.anchor-row-col{{
  display:flex;flex-direction:column;gap:{qrow_g};
  flex-shrink:0;width:3.5mm;
  justify-content:flex-start;
  padding-top:2.5mm;
}}
.right-id-area{{
  flex:1;padding:2mm 3mm;
}}
.tr-title{{
  font-size:9pt;font-weight:700;text-align:center;
  margin-bottom:1.5mm;letter-spacing:2pt;
}}
.tr-hint{{
  font-size:7pt;color:#666;text-align:center;margin-bottom:2mm;
}}
.id-grid{{
  display:flex;gap:2mm;justify-content:center;
}}
.id-col{{
  display:flex;flex-direction:column;align-items:center;gap:0.5mm;
}}
.id-header{{
  width:{id_box_size}px;height:{id_box_size}px;
  border:1.5px solid #666;display:flex;
  align-items:center;justify-content:center;
  font-size:8pt;font-weight:700;margin-bottom:1mm;
}}
.id-row{{
  display:flex;flex-direction:column;align-items:center;gap:1mm;
}}
.id-box{{
  display:inline-flex;justify-content:center;align-items:center;
  width:{id_box_size}px;height:{id_box_size}px;
  border:1.5px solid #000;
  font-size:7pt;font-weight:700;background:#fff;
}}
.bottom-questions-area{{
  padding:2mm 3mm;
  flex:1;position:relative;
}}
.qs-area{{
  display:flex;flex-direction:column;gap:2.5mm;
}}
.qs-group{{
  display:flex;gap:{group_gap};
  page-break-inside:avoid;
  margin-bottom:2mm;position:relative;
}}
.qs-col{{
  display:flex;flex-direction:column;gap:0.5mm;
  flex:1;min-width:0;
}}
.qs-qrow{{
  display:flex;align-items:center;gap:{qrow_g};
  justify-content:flex-start;
}}
.question-number{{
  font-size:7pt;font-weight:700;min-width:5mm;text-align:right;
  padding-right:0.8mm;
}}
.option-box{{
  display:inline-flex;align-items:center;justify-content:center;
  width:5mm;height:5mm;
  border:1.2px solid #000;
  font-size:7pt;font-weight:700;background:#fff;
  flex-shrink:0;margin:0 0.3mm;
}}
.legend{{
  display:flex;justify-content:center;gap:2mm;margin-top:1mm;
  font-size:6pt;align-items:center;flex-wrap:wrap;
}}
.lg-item{{display:flex;align-items:center;gap:0.5mm;}}
.lg-box{{
  border:1px solid #000;padding:0.3mm 1mm;font-weight:700;font-size:6pt;
}}
.lg-box-fill{{
  border:1px solid #000;padding:0.3mm 1mm;font-weight:700;font-size:6pt;
  background:#000;color:#fff;
}}
.footer{{
  display:flex;justify-content:space-between;align-items:center;
  padding-top:1mm;margin-top:1mm;border-top:1.5px solid #000;font-size:6pt;
}}
/* ── 打印优化：保持固定宽度不缩放 ── */
@media print{{
  body{{background:#fff;padding:0;}}
  .exam-container{{width:{container_width};border:3px solid #000;margin:0 auto;position:relative;}}
}}
"""


def _build_computed_regions(
    question_count: int,
    options: List[str],
    id_digits: int,
    id_options: List[str],
    page_width_mm: float = 210,
    page_height_mm: float = 297,
) -> Dict[str, Any]:
    """基于给出参数计算答题卡上各选项的坐标区域（供摄像头扫描定位用）

    返回:
        {
            "canvas_width": 800,
            "canvas_height": 1100,
            "id_regions": [...],     # 考号涂区坐标
            "question_regions": [...], # 题目选项坐标
        }
    """
    import math
    num_options = len(options)
    canvas_w, canvas_h = 800, int(1100 * (page_height_mm / page_width_mm))

    # 顶部考号区估算坐标（实际扫描时以四角定位标记为准）
    id_regions = []
    id_area_top = 60
    id_area_left = 300
    id_area_width = canvas_w - id_area_left - 20
    id_col_w = id_area_width / max(id_digits, 1)
    id_row_h = (180 - id_area_top) / max(len(id_options), 1)

    for col in range(id_digits):
        for row, opt_val in enumerate(id_options):
            id_regions.append({
                "digit_index": col,
                "label": opt_val,
                "x": round(id_area_left + col * id_col_w + id_col_w * 0.3),
                "y": round(id_area_top + row * id_row_h + id_row_h * 0.3),
                "w": round(id_col_w * 0.4),
                "h": round(id_row_h * 0.4),
                "cx": round(id_area_left + col * id_col_w + id_col_w / 2),
                "cy": round(id_area_top + row * id_row_h + id_row_h / 2),
            })

    # 题目区估算坐标（4列×5行列主布局）
    question_regions = []
    q_area_top = 200
    q_area_left = 30
    q_area_width = canvas_w - q_area_left - 30

    COLS = 4
    ROWS = 5
    GROUP_SIZE = COLS * ROWS

    # 列宽：4列等宽均匀分布
    col_widths = [
        q_area_width * 0.25,
        q_area_width * 0.25,
        q_area_width * 0.25,
        q_area_width * 0.25,
    ]
    cell_h = max(24, min(54, (canvas_h - q_area_top - 40) / (math.ceil(question_count / GROUP_SIZE) * ROWS)))

    for i in range(question_count):
        # 列主序: 列号 = (i % GROUP_SIZE) // ROWS, 行号 = (i % GROUP_SIZE) % ROWS
        group_idx = i % GROUP_SIZE
        col = group_idx // ROWS
        row = group_idx % ROWS
        group_start = (i // GROUP_SIZE) * GROUP_SIZE

        # 首列 x 偏移
        x_offset = sum(col_widths[:col]) if col > 0 else 0
        x0 = q_area_left + x_offset
        y0 = q_area_top + row * cell_h

        # 该题选项数（以7选项为标准布局）
        this_opt_count = min(num_options, 7)
        opt_w = (col_widths[col] - 24) / max(this_opt_count, 1)

        opt_regions = []
        for j, opt in enumerate(options[:this_opt_count]):
            opt_regions.append({
                "label": opt,
                "x": round(x0 + 24 + j * opt_w + opt_w * 0.2),
                "y": round(y0 + cell_h * 0.1),
                "w": round(opt_w * 0.6),
                "h": round(cell_h * 0.7),
                "cx": round(x0 + 24 + j * opt_w + opt_w / 2),
                "cy": round(y0 + cell_h / 2),
            })
        question_regions.append({
            "question_number": (i + 1),
            "options": options,
            "option_regions": opt_regions,
        })

    # 扫描布局元数据
    total_groups = math.ceil(question_count / GROUP_SIZE)

    # CSDN 锚点位置: 左侧行锚点坐标 (每组每行一个)
    row_anchors = [
        {"row": r, "y": round(q_area_top + r * cell_h + cell_h / 2)}
        for r in range(ROWS)
    ]
    # CSDN 锚点位置: 顶部列锚点坐标 (每组每列一个)
    col_anchors = []
    for col in range(COLS):
        x_offset = sum(col_widths[:col]) if col > 0 else 0
        col_anchors.append({
            "col": col,
            "x": round(q_area_left + x_offset + col_widths[col] / 2),
        })

    scan_layout = {
        "cols": COLS,
        "rows": ROWS,
        "groups": total_groups,
        "group_size": GROUP_SIZE,
        "margin_x": q_area_left,
        "margin_y": q_area_top,
        "col_widths": col_widths,
        "cell_h": cell_h,
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "corner_markers": [
            {"x": 15, "y": 15, "size": 30},
            {"x": canvas_w - 45, "y": 15, "size": 30},
            {"x": 15, "y": canvas_h - 45, "size": 30},
            {"x": canvas_w - 45, "y": canvas_h - 45, "size": 30},
        ],
        # CSDN 动态锚点定位
        "csdn_anchors": {
            "row_anchors": row_anchors,
            "col_anchors": col_anchors,
        },
    }

    return {
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "id_regions": id_regions,
        "question_regions": question_regions,
        "id_digits": id_digits,
        "id_options": id_options,
        "total_questions": question_count,
        "option_count": num_options,
        "scan_layout": scan_layout,
    }


def generate_answer_sheet_html(
    *,
    title: str = "标准答题卡",
    page_size: str = "A4",
    page_width: str = "210mm",
    page_height: str = "297mm",
    question_count: int = 100,
    options: Optional[List[str]] = None,
    id_digits: int = 6,
    id_options: Optional[List[str]] = None,
    show_student_id: bool = True,
    questions_per_row: int = 5,
    show_answer_key: bool = False,
) -> str:
    """动态生成答题卡 HTML（Flexbox 布局，匹配 docs/序号.html 模板风格）

    参数:
        title: 试卷标题
        page_size: 纸张尺寸 (A4 / A5)
        page_width/page_height: 纸张宽高
        question_count: 题目总数
        options: 选项字母列表，默认 ['A','B','C','D']
        id_digits: 考号位数（几列）
        id_options: 考号每位可选数字，默认 0-9
        show_student_id: 是否显示考号填写栏
        questions_per_row: 每列几道题（固定5，保持 ROWS=5 不变）
        show_answer_key: 是否生成参考答案页（暂未实现）
    """
    if options is None:
        options = ["A", "B", "C", "D"]
    if id_options is None:
        id_options = _make_digit_labels(9, start=0)

    styles = _build_styles(page_size, id_digits, len(id_options))
    top_left = _build_student_info_section(show_student_id)
    top_right = _build_id_fill_section(id_digits, id_options)
    question_area = _build_question_area(question_count, options)

    # 图例说明
    legend_items = [
        f'<span class="lg-item"><span class="lg-box">[A]</span> 正确填涂</span>',
        '<span class="lg-item"><span class="lg-box-fill">[▣]</span> 涂黑填涂</span>',
        '<span class="lg-item"><span class="lg-box">[ ]</span> 错误填涂</span>',
        '<span class="lg-item">修改请用橡皮擦干净</span>',
    ]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>{styles}</style>
</head>
<body>

<!-- ══════ 答题卡 ══════ -->
<div class="exam-container">
  <div class="title">{title}</div>

  <!-- 上区：左右并排，底部分隔线 -->
  <div class="top-section">
    {top_left}
    {top_right}
  </div>

  <!-- 下区：题目填涂（4列×5行列主布局） -->
  <div class="bottom-questions-area">
    <div class="qs-area">
      {question_area}
    </div>
  </div>

  <!-- 图例 -->
  <div class="legend">
    {"\n    ".join(legend_items)}
  </div>

  <div class="footer">
    <span>请用2B铅笔填涂 · 黑色签字笔书写</span>
    <span>{title}</span>
  </div>
</div>

</body>
</html>"""


def generate_answer_sheet_from_exam(
    *,
    title: str = "标准答题卡",
    questions: List[Dict[str, Any]],
    page_size: str = "A4",
    page_width: str = "210mm",
    page_height: str = "297mm",
    id_digits: int = 6,
    id_options: Optional[List[str]] = None,
) -> str:
    """基于实际试卷题目数据生成答题卡 HTML

    参数:
        title: 试卷标题
        questions: 题目列表，每题为 {"number":1, "type":"single", "options":["A","B","C","D"], "score":5}
        page_size: 纸张尺寸
        page_width/page_height: 纸张宽高
        id_digits: 考号位数
        id_options: 考号可选数字
    """
    if id_options is None:
        id_options = _make_digit_labels(9, start=0)

    question_count = len(questions)

    # 取第一道题的选项数作为统一选项数，始终生成字母标签
    first_opts = questions[0].get("options", ["A", "B", "C", "D"]) if questions else ["A", "B", "C", "D"]
    unified_options = _make_option_letters(len(first_opts))

    return generate_answer_sheet_html(
        title=title,
        page_size=page_size,
        page_width=page_width,
        page_height=page_height,
        question_count=question_count,
        options=unified_options,
        id_digits=id_digits,
        id_options=id_options,
        show_student_id=True,
    )


def generate_answer_sheet_from_json(
    *,
    title: str = "标准答题卡",
    choice_questions: List[Dict[str, Any]],
    page_size: str = "A4",
    page_width: str = "210mm",
    page_height: str = "297mm",
    id_digits: int = 6,
    id_options: Optional[List[str]] = None,
    show_student_id: bool = True,
) -> str:
    """基于选择题JSON生成答题卡HTML（支持每题不同选项数）

    参数:
        title: 试卷标题
        choice_questions: 选择题JSON列表，每题为 {
            "question_number": 1,        # 全局题号
            "section": "语法选择",        # 所属板块
            "question_type": "single_choice",  # 题型
            "correct_answer": "A",        # 正确答案
            "option_count": 4,            # 选项数量
            "options": ["A","B","C","D"],  # 选项字母列表
            "score": 1.0,                 # 分值
        }
        page_size: 纸张尺寸
        page_width/page_height: 纸张宽高
        id_digits: 考号位数
        id_options: 考号可选数字
        show_student_id: 是否显示考号填写栏

    所有选择题统一连续排列，不按选项数分组。每题可有不同选项数。
    """
    if not choice_questions:
        return generate_answer_sheet_html(
            title=title, page_size=page_size,
            page_width=page_width, page_height=page_height,
            question_count=0, id_digits=id_digits,
            id_options=id_options or _make_digit_labels(9, start=0),
        )

    if id_options is None:
        id_options = _make_digit_labels(9, start=0)

    # 生成样式
    styles = _build_json_styles(page_size, id_digits, len(id_options))

    # 学生信息区
    top_left = _build_student_info_section(show_student_id)

    # 考号填涂区
    top_right = _build_id_fill_section(id_digits, id_options)

    # 所有题目统一连续排列（不按选项数分组）
    question_rows = _build_question_area_from_json(choice_questions)

    # 图例说明
    legend_items = [
        f'<span class="lg-item"><span class="lg-box">[A]</span> 正确填涂</span>',
        '<span class="lg-item"><span class="lg-box-fill">[▣]</span> 涂黑填涂</span>',
        '<span class="lg-item"><span class="lg-box">[ ]</span> 错误填涂</span>',
        '<span class="lg-item">修改请用橡皮擦干净</span>',
    ]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>{styles}</style>
</head>
<body>

<!-- ══════ 答题卡 ══════ -->
<div class="exam-container">
  <div class="title">{title}</div>

  <!-- 上区：左右并排，底部分隔线 -->
  <div class="top-section">
    {top_left}
    {top_right}
  </div>

  <!-- 下区：选择题填涂（4列×5行列主布局） -->
  <div class="bottom-questions-area">
    <div class="qs-area">
      {question_rows}
    </div>
  </div>

  <!-- 图例 -->
  <div class="legend">
    {"\n    ".join(legend_items)}
  </div>

  <div class="footer">
    <span>请用2B铅笔填涂 · 黑色签字笔书写</span>
    <span>{title}</span>
  </div>
</div>

</body>
</html>"""


def _build_computed_regions_from_json(
    choice_questions: List[Dict[str, Any]],
    id_digits: int,
    id_options: List[str],
    page_width_mm: float = 210,
    page_height_mm: float = 297,
) -> Dict[str, Any]:
    """基于选择题JSON计算答题卡坐标区域

    ★ 2026-07-06 重构: 坐标系改为匹配 printable_sheet_generator 布局
       - Canvas: A4_WIDTH×A4_HEIGHT (2480×3508)，与透视矫正后一致
       - 题目: ITEMS_PER_ROW=5 列布局，START_X=400, START_Y=400
       - 选项: CIRCLE_DIAMETER=40 圆形，OPTION_SPACING=60 间距
       - 考号: EXAM_NUMBER_X_START=400, EXAM_NUMBER_Y=200
    """
    from app.services.printable_sheet_constants import (
        A4_WIDTH, A4_HEIGHT,
        START_X, START_Y, ROW_SPACING, OPTION_SPACING, CIRCLE_DIAMETER,
        ITEMS_PER_ROW, EXAM_NUMBER_X_START, EXAM_NUMBER_Y,
        EXAM_NUMBER_SPACING, EXAM_NUMBER_OPTION_SPACING,
        EXAM_NUMBER_OPTION_START_Y, EXAM_NUMBER_DIGITS,
    )
    import math

    # Canvas = A4 标准尺寸（与 rectify_perspective 输出一致）
    canvas_w, canvas_h = A4_WIDTH, A4_HEIGHT

    # ── 考号区坐标（匹配 printable_sheet_generator 的实际绘制位置） ──
    id_regions = []
    exam_x_base = EXAM_NUMBER_X_START  # 400
    exam_y_base = EXAM_NUMBER_Y  # 200
    digit_spacing = EXAM_NUMBER_SPACING  # 80
    opt_spacing = EXAM_NUMBER_OPTION_SPACING  # 50
    opt_start_y_offset = EXAM_NUMBER_OPTION_START_Y  # 20
    exam_circle_r = int(CIRCLE_DIAMETER * 0.7 / 2)  # 14, 考号圆圈半径
    exam_circle_d = int(CIRCLE_DIAMETER * 0.7)  # 28, 考号圆圈直径

    for col in range(id_digits):
        # 每位考号的X起始（匹配生成器: dx = exam_x + col*digit_spacing + 80）
        digit_x = exam_x_base + col * digit_spacing + 80
        # 选项圈起始Y（匹配生成器: oy = digit_label_y + 30）
        opt_y = exam_y_base + opt_start_y_offset + 30
        for row_idx, opt_val in enumerate(id_options):
            ox = digit_x + row_idx * opt_spacing
            id_regions.append({
                "digit_index": col,
                "label": opt_val,
                "cx": round(ox + exam_circle_r),
                "cy": round(opt_y + exam_circle_r),
                "w": max(24, exam_circle_d),  # 检测窗口略大于圆圈
                "h": max(24, exam_circle_d),
            })

    # ── 题目区坐标（匹配 printable_sheet_generator 的 5列×N行 布局） ──
    question_regions = []
    step_x = OPTION_SPACING * 4 + 40  # 280, 每道题+X偏移量
    step_y = ROW_SPACING  # 120, 行间距
    option_count = 4  # 统一4个选项 (A/B/C/D)

    sorted_qs = sorted(choice_questions,
                       key=lambda q: q.get("question_number", q.get("number", 0)))
    q_count = len(sorted_qs)
    total_rows = math.ceil(q_count / ITEMS_PER_ROW)

    for i, q in enumerate(sorted_qs):
        row = i // ITEMS_PER_ROW
        col = i % ITEMS_PER_ROW
        x0 = START_X + col * step_x
        y0 = START_Y + row * step_y
        qn = q.get("question_number", i + 1)

        opts = q.get("options", _make_option_letters(q.get("option_count", option_count)))
        opt_regions = []
        for oi, opt_label in enumerate(opts[:option_count]):
            ox = x0 + oi * OPTION_SPACING
            oy = y0
            opt_regions.append({
                "label": opt_label,
                "cx": round(ox + CIRCLE_DIAMETER / 2),
                "cy": round(oy + CIRCLE_DIAMETER / 2),
                "w": CIRCLE_DIAMETER,  # 检测窗口 = 圆圈直径
                "h": CIRCLE_DIAMETER,
            })
        question_regions.append({
            "question_number": qn,
            "options": opts[:option_count],
            "option_regions": opt_regions,
        })

    # 最大选项数
    max_oc = max(
        (q.get("option_count", len(q.get("options", ["A","B","C","D"]))) for q in choice_questions),
        default=4,
    )

    # 扫描布局元数据
    COLS = ITEMS_PER_ROW  # 5
    ROWS = 5  # 锚点扫描最多5行一组
    GROUP_SIZE = COLS * ROWS  # 25
    total_groups = math.ceil(q_count / GROUP_SIZE)

    row_anchors = [
        {"row": r, "y": round(START_Y + r * step_y + CIRCLE_DIAMETER / 2)}
        for r in range(ROWS)
    ]
    col_anchors = [
        {"col": c, "x": round(START_X + c * step_x + step_x / 2)}
        for c in range(COLS)
    ]

    scan_layout = {
        "cols": COLS,
        "rows": ROWS,
        "groups": total_groups,
        "group_size": GROUP_SIZE,
        "margin_x": START_X,
        "margin_y": START_Y,
        "col_widths": [step_x] * COLS,
        "cell_h": step_y,
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "corner_markers": [
            {"x": 50, "y": 50, "size": 50},
            {"x": 2230, "y": 50, "size": 50},
            {"x": 50, "y": 3258, "size": 50},
            {"x": 2230, "y": 3258, "size": 50},
        ],
        "csdn_anchors": {
            "row_anchors": row_anchors,
            "col_anchors": col_anchors,
        },
    }

    first_qn = sorted_qs[0].get("question_number", 1) if sorted_qs else 1

    return {
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "id_regions": id_regions,
        "question_regions": question_regions,
        "id_digits": id_digits,
        "id_options": id_options,
        "total_questions": q_count,
        "option_count": max_oc,
        "start_question": first_qn,
        "scan_layout": scan_layout,
    }


def save_answer_sheet_html_to_file(exam_id: int, html_content: str) -> str:
    """将答题卡HTML内容保存到磁盘文件，返回公开访问的相对URL路径

    文件存储在 uploads/answer_sheets/{exam_id}/answer-sheet.html，
    由 main.py 中的 StaticFiles mount 提供公开访问（无需认证）。
    """
    exam_dir = os.path.join(_ANSWER_SHEETS_DIR, str(exam_id))
    os.makedirs(exam_dir, exist_ok=True)
    filepath = os.path.join(exam_dir, "answer-sheet.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return f"/uploads/answer_sheets/{exam_id}/answer-sheet.html"


def save_graderflow_sheet_html_to_file(exam_id: int, html_content: str) -> str:
    """将 GraderFlow 答题卡HTML保存到磁盘文件，返回公开访问的相对URL路径

    文件存储在 uploads/answer_sheets/{exam_id}/graderflow-sheet.html，
    与标准答题卡 answer-sheet.html 区分，避免互相覆盖。
    由 main.py 中的 StaticFiles mount 提供公开访问（无需认证）。
    """
    exam_dir = os.path.join(_ANSWER_SHEETS_DIR, str(exam_id))
    os.makedirs(exam_dir, exist_ok=True)
    filepath = os.path.join(exam_dir, "graderflow-sheet.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return f"/uploads/answer_sheets/{exam_id}/graderflow-sheet.html"


def save_answer_sheet_html(exam_id: int, title: str, questions: List[Dict[str, Any]]) -> str:
    """基于题目列表生成答题卡HTML并保存到磁盘

    返回公开访问的相对URL路径。
    """
    html = generate_answer_sheet_from_exam(
        title=title,
        questions=questions,
    )
    return save_answer_sheet_html_to_file(exam_id, html)


def save_answer_sheet_html_from_json(
    exam_id: int, title: str, choice_questions: List[Dict[str, Any]],
) -> str:
    """基于选择题JSON生成答题卡HTML并保存到磁盘

    支持每题不同选项数。返回公开访问的相对URL路径。
    """
    html = generate_answer_sheet_from_json(
        title=title,
        choice_questions=choice_questions,
    )
    return save_answer_sheet_html_to_file(exam_id, html)


# ===================================================================
# GraderFlow 兼容答题卡生成（适配 YOLOv5 + OMR 识别管线）
# ===================================================================
# 与标准答题卡的区别：
#   - 4列 answerArea 网格布局（匹配 YOLO B-mode 检测模式）
#   - 每组 area 内 5题 × 4选项 row 布局（匹配 group_size=5）
#   - 矩形填涂框 5.0mm×4.2mm（满足 contour 检测: area>300, w>8, h>8）
#   - area 间 4mm 白色间距（确保 YOLO 区域分离）
#   - 四角定位标记 + 条形码粘贴区 + 7位考号填涂
# ===================================================================

def _build_graderflow_styles(
    id_digits: int = 7,
    id_option_count: int = 10,
) -> str:
    """生成 GraderFlow 兼容的 CSS 样式表"""
    return """@page{size:A4 portrait;margin:5mm;}
*{margin:0;padding:0;box-sizing:border-box;}
body{
  font-family:'SimHei','Microsoft YaHei','SimSun',sans-serif;
  color:#000;background:#fff;
  -webkit-print-color-adjust:exact;print-color-adjust:exact;
}
.sheet-container{
  width:198mm;min-height:280mm;
  background:#fff;border:2.5px solid #000;
  margin:0 auto;padding:4mm 3.5mm;
  position:relative;display:flex;flex-direction:column;
}
.sheet-title{
  text-align:center;font-size:17pt;font-weight:700;
  letter-spacing:4pt;margin-bottom:2mm;
  padding-bottom:1.5mm;border-bottom:2px solid #000;
}
/* 顶部区域：学生信息(左) + 考号填涂(右) */
.top-section{
  display:flex;gap:3mm;margin-bottom:2mm;
  padding-bottom:2mm;border-bottom:2px solid #000;
}
.left-info{width:60mm;min-width:55mm;display:flex;flex-direction:column;gap:2mm;}
.left-info .info-title{font-size:8pt;font-weight:700;text-align:center;padding-bottom:0.5mm;border-bottom:1px solid #999;}
.info-row{display:flex;align-items:flex-end;font-size:9pt;gap:1mm;}
.info-label{font-weight:700;white-space:nowrap;min-width:14mm;text-align:right;}
.info-line{flex:1;border-bottom:1.5px solid #000;height:5mm;margin-bottom:0.5mm;}
.info-hint{font-size:6.5pt;color:#555;margin-top:0.5mm;line-height:1.5;}
.barcode-area{
  margin-top:1mm;border:1.5px dashed #999;height:12mm;
  display:flex;align-items:center;justify-content:center;
  font-size:6.5pt;color:#999;
}
/* 考号填涂区 */
.right-id-area{flex:1;display:flex;flex-direction:column;align-items:center;}
.id-title{font-size:8pt;font-weight:700;text-align:center;margin-bottom:1mm;letter-spacing:2pt;}
.id-hint{font-size:6pt;color:#666;text-align:center;margin-bottom:1.5mm;}
.id-grid{display:flex;gap:1.2mm;justify-content:center;}
.id-digit-col{display:flex;flex-direction:column;align-items:center;gap:0.3mm;}
.id-digit-header{
  width:6.5mm;height:6mm;border:1.5px solid #666;
  display:flex;align-items:center;justify-content:center;
  font-size:7pt;font-weight:700;background:#f8f8f8;margin-bottom:0.3mm;
}
.id-digit-options{display:flex;flex-direction:column;gap:0.3mm;}
.id-box{
  width:6.5mm;height:4.2mm;border:1.3px solid #000;
  display:flex;align-items:center;justify-content:center;
  font-size:7pt;font-weight:700;background:#fff;
}
/* 题目填涂区 - answerArea 网格 */
.questions-section{flex:1;display:flex;flex-direction:column;gap:4mm;}
.area-row{display:flex;gap:3mm;justify-content:space-between;}
.answer-area{
  flex:1;min-width:0;overflow:hidden;
  border:1px solid #ccc;background:#fcfcfc;
  padding:0.8mm 0.8mm;display:flex;flex-direction:column;gap:0.5mm;
}
.question-row{display:flex;align-items:center;gap:0.3mm;height:6mm;}
.q-number{font-size:7pt;font-weight:700;min-width:5mm;text-align:right;padding-right:0.3mm;color:#333;flex-shrink:0;}
.q-option-label{font-size:6pt;font-weight:700;color:#555;min-width:2.5mm;text-align:center;}
.fill-box{
  width:5mm;height:4.2mm;border:1.5px solid #000;
  background:#fff;flex-shrink:0;
}
.option-group{display:flex;gap:0.8mm;align-items:center;}
/* 四角定位标记 */
.corner-mark{position:absolute;width:2.5mm;height:2.5mm;background:#000;border:0.3mm solid #000;}
.corner-tl{top:1.5mm;left:1.5mm;}
.corner-tr{top:1.5mm;right:1.5mm;}
.corner-bl{bottom:1.5mm;left:1.5mm;}
.corner-br{bottom:1.5mm;right:1.5mm;}
/* 图例 */
.legend{
  display:flex;justify-content:center;gap:2.5mm;
  margin-top:2mm;font-size:6pt;align-items:center;
}
.legend-item{display:flex;align-items:center;gap:0.5mm;}
.legend-box{width:3.5mm;height:3mm;border:1.5px solid #000;background:#fff;display:inline-block;}
.legend-box-fill{width:3.5mm;height:3mm;border:1.5px solid #000;background:#000;display:inline-block;}
.footer{
  display:flex;justify-content:space-between;align-items:center;
  padding-top:0.5mm;margin-top:1.5mm;border-top:1px solid #000;
  font-size:5.5pt;color:#666;
}
@media print{
  body{background:#fff;}
  .sheet-container{border:2.5px solid #000;}
}"""


def _build_graderflow_student_info_section() -> str:
    """生成 GraderFlow 风格的左上方学生信息区（姓名、班级、学校 + 条形码粘贴区）"""
    return (
        '<div class="left-info">\n'
        '  <div class="info-title">▼ 请用黑色签字笔填写</div>\n'
        '  <div class="info-row">'
        '<span class="info-label">姓　名</span>'
        '<span class="info-line"></span></div>\n'
        '  <div class="info-row">'
        '<span class="info-label">班　级</span>'
        '<span class="info-line"></span></div>\n'
        '  <div class="info-row">'
        '<span class="info-label">学　校</span>'
        '<span class="info-line"></span></div>\n'
        '  <div style="font-size:7pt;font-weight:700;margin-top:1mm;">条形码粘贴区 ▼</div>\n'
        '  <div class="barcode-area">条形码粘贴处（由监考老师粘贴）</div>\n'
        '  <div class="info-hint">'
        '1. 用 2B 铅笔将对应选项矩形框涂黑<br>'
        '2. 修改答案请用橡皮擦干净<br>'
        '3. 保持卡面平整、清洁'
        '</div>\n'
        '</div>'
    )


def _build_graderflow_id_fill_section(
    id_digits: int = 7,
    id_options: Optional[List[str]] = None,
) -> str:
    """生成 GraderFlow 风格的右上方考号填涂区（每列一位数，0-9 可涂选）"""
    if id_options is None:
        id_options = [str(i) for i in range(10)]

    cols_html = []
    for _ in range(id_digits):
        cells = []
        for opt in id_options:
            cells.append(f'<span class="id-box">{opt}</span>')
        cols_html.append(
            f'<div class="id-digit-col">'
            f'<div class="id-digit-header"></div>'
            f'<div class="id-digit-options">{"".join(cells)}</div>'
            f'</div>'
        )
    id_grid_html = "\n".join(cols_html)

    # 考号位次标签
    pos_labels = "".join(
        f'<span style="width:6.5mm;text-align:center;">{i+1}</span>'
        for i in range(id_digits)
    )

    return (
        '<div class="right-id-area">\n'
        '  <div class="id-title">考 号 填 涂 区</div>\n'
        '  <div class="id-hint">'
        '（用 2B 铅笔涂黑对应数字，位数不足在前面补0）'
        '</div>\n'
        f'  <div class="id-grid">\n{id_grid_html}\n  </div>\n'
        f'  <div style="margin-top:2mm;text-align:center;">\n'
        f'    <div style="display:flex;gap:1.2mm;justify-content:center;font-size:6.5pt;font-weight:700;color:#555;">\n'
        f'      {pos_labels}\n'
        f'    </div>\n'
        f'    <div style="font-size:5.5pt;color:#999;margin-top:0.5mm;">← 考号位数（从左到右）</div>\n'
        f'  </div>\n'
        '</div>'
    )


def _build_graderflow_question_area(
    question_count: int = 40,
    options_per_question: int = 4,
    questions_per_area: int = 5,
    columns_per_row: int = 4,
    questions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """生成 GraderFlow 兼容的题目填涂区

    布局: N行 × 4列 answerArea 网格，每个 area 内含 questions_per_area 题
    遍历顺序: B-mode 列优先 [1,5,9,13,2,6,10,14,...]

    参数:
        question_count: 总题数
        options_per_question: 统一选项数（当 questions 为 None 时使用）
        questions_per_area: 每个 answerArea 包含的题数（匹配 group_size）
        columns_per_row: 每行 answerArea 数量（匹配 YOLO 4列网格）
        questions: 可选题目列表，提供每题不同的选项数（支持4选项+7选项混合试卷）
    """
    total_areas = (question_count + questions_per_area - 1) // questions_per_area
    rows_needed = (total_areas + columns_per_row - 1) // columns_per_row

    area_rows = []
    for row in range(rows_needed):
        areas = []
        for col in range(columns_per_row):
            area_index = row * columns_per_row + col
            if area_index >= total_areas:
                break

            start_q = area_index * questions_per_area + 1
            end_q = min(start_q + questions_per_area - 1, question_count)

            q_rows = []
            for q in range(start_q, end_q + 1):
                # 确定当前题目的选项数：优先从 questions 列表获取，否则使用统一值
                q_opts_count = options_per_question
                if questions and (q - 1) < len(questions):
                    q_data = questions[q - 1]
                    q_opts = q_data.get("options", [])
                    if q_opts:
                        q_opts_count = len(q_opts)
                q_option_labels = [chr(65 + i) for i in range(q_opts_count)]

                opt_items = []
                for opt_label in q_option_labels:
                    opt_items.append(
                        f'<span class="q-option-label">{opt_label}</span>'
                        f'<span class="fill-box" data-q="{q}" data-opt="{opt_label}"'
                        f' data-area="{area_index + 1}"></span>'
                    )
                q_rows.append(
                    f'<div class="question-row">'
                    f'<span class="q-number">{q}.</span>'
                    f'<span class="option-group">{"".join(opt_items)}</span>'
                    f'</div>'
                )

            areas.append(
                f'<div class="answer-area">{"".join(q_rows)}</div>'
            )
        area_rows.append(
            f'<div class="area-row">{"".join(areas)}</div>'
        )

    return "\n".join(area_rows)


def generate_graderflow_sheet_html(
    *,
    title: str = "答  题  卡",
    question_count: int = 40,
    options_per_question: int = 4,
    questions_per_area: int = 5,
    columns_per_row: int = 4,
    id_digits: int = 7,
    id_options: Optional[List[str]] = None,
    questions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """生成 GraderFlow 兼容的答题卡 HTML

    参数:
        title: 答题卡标题
        question_count: 总题数（默认40）
        options_per_question: 每题统一选项数（当 questions 为 None 时使用，默认4即A/B/C/D）
        questions_per_area: 每个 answerArea 内题数（默认5，匹配 group_size）
        columns_per_row: 每行 answerArea 数量（默认自动：4选项→4列，>4选项→2列）
        id_digits: 考号位数（默认7）
        id_options: 考号可选数字列表（默认0-9）
        questions: 可选题目列表，支持每题不同选项数（如4选项+7选项混合试卷）
    """
    if id_options is None:
        id_options = [str(i) for i in range(10)]

    # 自动检测列数：超过4个选项时切换为2列布局，确保选项行不超出area
    _columns = columns_per_row
    if _columns == 4 and options_per_question > 4:
        _columns = 2

    styles = _build_graderflow_styles(id_digits, len(id_options))
    student_info = _build_graderflow_student_info_section()
    id_fill = _build_graderflow_id_fill_section(id_digits, id_options)
    question_area = _build_graderflow_question_area(
        question_count=question_count,
        options_per_question=options_per_question,
        questions_per_area=questions_per_area,
        columns_per_row=_columns,
        questions=questions,
    )

    total_areas = (question_count + questions_per_area - 1) // questions_per_area
    rows_needed = (total_areas + _columns - 1) // _columns

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title} - GraderFlow 兼容格式</title>
<style>{styles}</style>
</head>
<body>

<div class="sheet-container">

  <!-- 四角定位标记 -->
  <div class="corner-mark corner-tl"></div>
  <div class="corner-mark corner-tr"></div>
  <div class="corner-mark corner-bl"></div>
  <div class="corner-mark corner-br"></div>

  <!-- 标题 -->
  <div class="sheet-title">{title}</div>

  <!-- 顶部：学生信息 + 考号填涂 -->
  <div class="top-section">
    {student_info}
    {id_fill}
  </div>

  <!-- 题目填涂区 -->
  <div class="questions-section">
    {question_area}
  </div>

  <!-- 图例说明 -->
  <div class="legend">
    <div class="legend-item">
      <span>正确填涂：</span>
      <span class="legend-box-fill"></span>
    </div>
    <div class="legend-item">
      <span>错误填涂：</span>
      <span class="legend-box"></span>
      <span style="margin-left:1mm;font-size:7pt;color:#888;">✗</span>
    </div>
    <div class="legend-item">
      <span style="color:#888;">|</span>
    </div>
    <div class="legend-item">
      <span>缺考标记：</span>
      <span class="legend-box" style="margin-left:1mm;"></span>
      <span style="font-size:5pt;color:#999;">监考员填涂</span>
    </div>
  </div>

</div>

</body>
</html>"""


def generate_graderflow_sheet_from_exam(
    *,
    title: str = "答  题  卡",
    questions: List[Dict[str, Any]],
    id_digits: int = 7,
    id_options: Optional[List[str]] = None,
) -> str:
    """基于实际试卷数据生成 GraderFlow 兼容答题卡

    参数:
        title: 答题卡标题
        questions: 题目列表
        id_digits: 考号位数
        id_options: 考号可选数字
    """
    question_count = len(questions)
    # 取所有题的最大选项数（处理混合选项如4选项+7选项的试卷）
    max_opts = 4
    for q in questions:
        opts = q.get("options", ["A", "B", "C", "D"])
        if len(opts) > max_opts:
            max_opts = len(opts)
    options_per_question = max_opts

    return generate_graderflow_sheet_html(
        title=title,
        question_count=question_count,
        options_per_question=options_per_question,
        questions_per_area=5,
        columns_per_row=4,  # 内部自动检测: >4选项→2列
        id_digits=id_digits,
        id_options=id_options,
        questions=questions,
    )


def save_graderflow_sheet_html(
    exam_id: int, title: str, questions: List[Dict[str, Any]],
    id_digits: int = 7,
) -> str:
    """基于题目列表生成 GraderFlow 答题卡并保存到磁盘

    保存到 graderflow-sheet.html，与标准 answer-sheet.html 区分。
    返回公开访问的相对URL路径。
    """
    html = generate_graderflow_sheet_from_exam(
        title=title,
        questions=questions,
        id_digits=id_digits,
    )
    return save_graderflow_sheet_html_to_file(exam_id, html)


def save_graderflow_sheet_html_from_json(
    exam_id: int, title: str, choice_questions: List[Dict[str, Any]],
    id_digits: int = 7,
) -> str:
    """基于选择题JSON生成 GraderFlow 答题卡并保存到磁盘

    保存到 graderflow-sheet.html，与标准 answer-sheet.html 区分。
    返回公开访问的相对URL路径。
    """
    html = generate_graderflow_sheet_from_exam(
        title=title,
        questions=choice_questions,
        id_digits=id_digits,
    )
    return save_graderflow_sheet_html_to_file(exam_id, html)


def _build_graderflow_regions(
    question_count: int,
    options_per_question: int,
    id_digits: int,
    id_options: List[str],
    questions_per_area: int = 5,
    columns_per_row: int = 4,
    page_width_mm: float = 210,
    page_height_mm: float = 297,
    question_option_counts: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """基于 GraderFlow 答题卡布局计算各选项的坐标区域（供扫描定位用）

    Canvas 坐标系基于 A4 标准尺寸，匹配透视矫正后的输出。

    参数:
        question_option_counts: 可选，每题的实际选项数列表，支持混合选项试卷（如4选项+7选项）
                                为 None 时所有题使用统一的 options_per_question

    返回:
        {
            "canvas_width": int,
            "canvas_height": int,
            "id_regions": [...],
            "question_regions": [...],
            "scan_layout": {...},
        }
    """
    import math

    # Canvas = A4 标准尺寸
    dpi_scale = 8.5  # mm → pixel 转换系数（约 216 dpi 对应 A4=2480×3508）
    canvas_w = int(page_width_mm * dpi_scale)
    canvas_h = int(page_height_mm * dpi_scale)

    # ── 考号区坐标 ──
    # 考号区位于答题卡右上角，top-section 的 right-id-area 内
    id_area_top = int(30 * dpi_scale)       # 约 255px @ 216dpi
    id_area_left = int(75 * dpi_scale)      # 约 638px（左侧学生信息区占 65mm）
    id_area_width = canvas_w - id_area_left - int(10 * dpi_scale)
    id_col_w = id_area_width / max(id_digits, 1)
    id_box_w_mm, id_box_h_mm = 7, 5

    id_regions = []
    for col in range(id_digits):
        col_cx = id_area_left + col * id_col_w + id_col_w / 2
        # 考号头部占位 + 选项行
        id_header_h = int(8 * dpi_scale)  # id-digit-header + gap
        for row_idx, opt_val in enumerate(id_options):
            id_regions.append({
                "digit_index": col,
                "label": opt_val,
                "cx": round(col_cx),
                "cy": round(id_area_top + id_header_h + row_idx * (id_box_h_mm + 0.5) * dpi_scale + id_box_h_mm * dpi_scale / 2),
                "w": round(id_box_w_mm * dpi_scale),
                "h": round(id_box_h_mm * dpi_scale),
            })

    # ── 题目区坐标 ──
    # 布局: columns_per_row 列 × N 行 answerArea 网格
    # 每个 area 内 questions_per_area 题垂直排列
    q_area_top = int(55 * dpi_scale)         # 顶部区域后
    q_area_left = int(4 * dpi_scale)         # 左边距 4mm
    q_area_width = canvas_w - 2 * int(4 * dpi_scale)  # 去掉左右边距
    q_area_height = canvas_h - q_area_top - int(10 * dpi_scale)

    # 区域尺寸
    area_gap = int(4 * dpi_scale)  # area 间距 4mm
    total_gaps_w = area_gap * (columns_per_row - 1)
    area_w = (q_area_width - total_gaps_w) / columns_per_row
    area_padding = int(1 * dpi_scale)  # area 内边距

    total_areas = math.ceil(question_count / questions_per_area)
    rows_needed = math.ceil(total_areas / columns_per_row)

    q_row_h = int(6.5 * dpi_scale)    # question-row 高度 6.5mm
    area_inner_gap = int(0.8 * dpi_scale)  # question-row 间距
    total_inner_h = questions_per_area * q_row_h + (questions_per_area - 1) * area_inner_gap
    area_h = total_inner_h + 2 * area_padding

    total_gaps_h = area_gap * (rows_needed - 1)
    # 自适应计算行高
    if rows_needed > 0:
        available_h = q_area_height - total_gaps_h
        area_h = min(area_h, available_h / rows_needed)

    question_regions = []
    for i in range(question_count):
        area_idx = i // questions_per_area
        q_in_area = i % questions_per_area

        area_row = area_idx // columns_per_row
        area_col = area_idx % columns_per_row

        # area 左上角坐标
        area_x0 = q_area_left + area_col * (area_w + area_gap)
        area_y0 = q_area_top + area_row * (area_h + area_gap)

        # 题号行在 area 内的偏移
        q_x0 = area_x0 + area_padding + int(5.3 * dpi_scale)  # 题号标签占 5.3mm
        q_y0 = area_y0 + area_padding + q_in_area * (q_row_h + area_inner_gap)

        opt_label_w = int(2.5 * dpi_scale)    # 选项字母标签 2.5mm
        opt_gap = int(0.8 * dpi_scale)        # 选项间距 0.8mm
        fill_w = int(5 * dpi_scale)           # 填涂框 5mm
        fill_h = int(4.2 * dpi_scale)         # 填涂框 4.2mm

        # 每题的实际选项数：优先使用 question_option_counts，回退到统一值
        q_opts_count = options_per_question
        if question_option_counts and i < len(question_option_counts):
            q_opts_count = question_option_counts[i]
        option_labels = [chr(65 + j) for j in range(q_opts_count)]

        opt_regions = []
        for o_idx, label in enumerate(option_labels):
            opt_x0 = q_x0 + o_idx * (opt_label_w + opt_gap + fill_w + opt_gap)
            opt_regions.append({
                "label": label,
                "cx": round(opt_x0 + opt_label_w + opt_gap + fill_w / 2),
                "cy": round(q_y0 + fill_h / 2),
                "w": fill_w,
                "h": fill_h,
            })

        question_regions.append({
            "question_number": i + 1,
            "options": option_labels,
            "option_regions": opt_regions,
        })

    # 扫描布局元数据
    scan_layout = {
        "format": "graderflow",
        "columns_per_row": columns_per_row,
        "questions_per_area": questions_per_area,
        "total_areas": total_areas,
        "area_rows": rows_needed,
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "page_width_mm": page_width_mm,
        "page_height_mm": page_height_mm,
        "fill_box": {"w_mm": 5.0, "h_mm": 4.2},
        "area_gap_mm": 4,
        "traversal_order": "b_mode",  # [1,5,9,13,2,6,10,14,...]
        "corner_markers": [
            {"x": int(2 * dpi_scale), "y": int(2 * dpi_scale), "size": int(3 * dpi_scale)},
            {"x": canvas_w - int(5 * dpi_scale), "y": int(2 * dpi_scale), "size": int(3 * dpi_scale)},
            {"x": int(2 * dpi_scale), "y": canvas_h - int(5 * dpi_scale), "size": int(3 * dpi_scale)},
            {"x": canvas_w - int(5 * dpi_scale), "y": canvas_h - int(5 * dpi_scale), "size": int(3 * dpi_scale)},
        ],
    }

    return {
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "id_regions": id_regions,
        "question_regions": question_regions,
        "id_digits": id_digits,
        "id_options": id_options,
        "total_questions": question_count,
        "option_count": options_per_question,
        "scan_layout": scan_layout,
    }
