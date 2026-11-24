"""
答题卡 PNG 生成器（Pillow）— v3 重写版

核心改进:
  1. 绘制粗黑色外边框（用于拍照后的透视矫正检测）
  2. 移除 Dinosheet 行/列标记块（v3扫描器不需要）
  3. 坐标配置输出与 omr_scanner.py 完全对齐
  4. 保留四角定位块作为辅助
"""

import os
from app.core.paths import UPLOADS_DIR
import json
import logging
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.services.printable_sheet_constants import (
    ITEMS_PER_ROW, OPTION_SPACING, CIRCLE_DIAMETER, CIRCLE_RADIUS,
    START_X, START_Y, ROW_SPACING, OPTION_LABEL_OFFSET_X, OPTION_LABEL_OFFSET_Y,
    QUESTION_NUM_OFFSET_Y,
    ANCHOR_SIZE, ANCHOR_POSITIONS, A4_WIDTH, A4_HEIGHT,
    EXAM_NUMBER_Y, EXAM_NUMBER_DIGITS, EXAM_NUMBER_SPACING, EXAM_NUMBER_X_START,
    EXAM_NUMBER_OPTION_SPACING, EXAM_NUMBER_OPTION_START_Y,
)

logger = logging.getLogger(__name__)

# 字体路径（按优先级查找）
_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    None,  # 回退到默认字体
]

# 黑色外边框宽度（px），用于透视矫正检测
BORDER_WIDTH = 8


def _get_font(size: int = 24):
    """获取适合文本绘制的字体"""
    for path in _FONT_PATHS:
        if path is None:
            try:
                return ImageFont.load_default()
            except Exception:
                return None
        try:
            return ImageFont.truetype(path, size, encoding="unic")
        except Exception:
            continue
    return None


def generate_printable_sheet(
    exam_id: int,
    choice_questions: list,
    option_count: int = 4,
    page_size: str = "A4",
    dpi: int = 200,
    title: str = "答题卡",
    class_name: str = "",
) -> dict:
    """生成可打印的答题卡PNG图片

    参数:
        exam_id: 试卷ID
        choice_questions: 选择题列表
        option_count: 每道题的选项数（默认4: A/B/C/D）
        page_size: 纸张大小 "A4" 或 "A5"
        dpi: 分辨率
        title: 试卷标题
        class_name: 班级名称（可选）

    返回:
        dict: {image_url, coordinate_config, total_questions, option_count}
    """
    total_questions = len(choice_questions)

    # 根据DPI调整尺寸
    scale = dpi / 200  # 以200dpi为基准
    width = int(2480 * scale * (0.5 if page_size == "A5" else 1))
    height = int(3508 * scale * (0.5 if page_size == "A5" else 1))

    # 缩放坐标参数
    s = scale * (0.5 if page_size == "A5" else 1)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    font_title = _get_font(int(36 * s))
    font_text = _get_font(int(20 * s))
    font_small = _get_font(int(16 * s))

    # ═══ 1. 绘制粗黑色外边框（用于透视矫正检测） ═══
    bw = int(BORDER_WIDTH * s)
    draw.rectangle([0, 0, width - 1, height - 1], outline="black", width=bw)

    # ═══ 2. 绘制四角定位块（辅助定位） ═══
    scale_func = lambda pos: (int(pos[0] * s), int(pos[1] * s))
    anchor_size = int(ANCHOR_SIZE * s)
    for name, (ax, ay) in ANCHOR_POSITIONS.items():
        pos = scale_func((ax, ay))
        draw.rectangle([pos[0], pos[1], pos[0] + anchor_size, pos[1] + anchor_size], fill="black")

    # ═══ 3. 绘制标题 ═══
    title_y = int(30 * s)
    if font_title:
        draw.text((width // 2, title_y), title, fill="black", font=font_title, anchor="mt")

    # ═══ 4. 绘制班级名 ═══
    if class_name:
        name_y = int(80 * s)
        if font_text:
            draw.text((int(50 * s), name_y), f"班级: {class_name}", fill="black", font=font_text)

    # ═══ 5. 绘制考号填涂区（每位数字一列，0-9纵向排列） ═══
    exam_x = int(EXAM_NUMBER_X_START * s)
    exam_y = int(EXAM_NUMBER_Y * s)
    spacing = int(EXAM_NUMBER_SPACING * s)           # 水平方向：数字列间距
    opt_spacing = int(EXAM_NUMBER_OPTION_SPACING * s) # 垂直方向：0-9选项间距
    opt_start_y = int(EXAM_NUMBER_OPTION_START_Y * s)

    if font_text:
        draw.text((exam_x, exam_y), "考号:", fill="black", font=font_text)
    digit_label_y = exam_y + opt_start_y
    exam_circle_d = int(CIRCLE_DIAMETER * s * 0.7)
    exam_radius = exam_circle_d // 2

    for digit_idx in range(EXAM_NUMBER_DIGITS):
        # 每位数字的列X坐标
        col_x = exam_x + digit_idx * spacing + int(80 * s)
        # 列标题（第几位）
        if font_small:
            draw.text((col_x, digit_label_y), str(digit_idx + 1),
                       fill="black", font=font_small)
        # 0-9选项纵向排列
        for opt_idx in range(10):
            ox = col_x
            oy = digit_label_y + int(30 * s) + opt_idx * opt_spacing
            draw.ellipse([ox, oy, ox + exam_circle_d, oy + exam_circle_d],
                         outline="black", width=int(2 * s))
            # 选项标签（0-9）画在圆圈左侧
            if font_small:
                draw.text((ox - int(18 * s), oy + int(OPTION_LABEL_OFFSET_Y * s * 0.7)),
                          str(opt_idx), fill="black", font=font_small)

    # ═══ 6. 逐题绘制选择题区域 ═══
    rows = (total_questions + ITEMS_PER_ROW - 1) // ITEMS_PER_ROW
    cur_x = int(START_X * s)
    cur_y = int(START_Y * s)
    step_x = int(OPTION_SPACING * option_count + int(40 * s))
    step_y = int(ROW_SPACING * s)

    question_regions = []

    for i in range(total_questions):
        row = i // ITEMS_PER_ROW
        col = i % ITEMS_PER_ROW
        x = cur_x + col * step_x
        y = cur_y + row * step_y

        qnum = choice_questions[i].get("number", i + 1)
        if font_text:
            draw.text((x, y - int(QUESTION_NUM_OFFSET_Y * s)), str(qnum), fill="black", font=font_text)

        q_options = choice_questions[i].get("options", option_count)
        cur_options = q_options if isinstance(q_options, int) else len(q_options) if isinstance(q_options, list) else option_count

        for opt_idx in range(cur_options):
            ox = x + opt_idx * int(OPTION_SPACING * s)
            oy = y
            draw.ellipse([ox, oy, ox + int(CIRCLE_DIAMETER * s), oy + int(CIRCLE_DIAMETER * s)],
                         outline="black", width=int(2 * s))
            if font_text:
                label = chr(65 + opt_idx)
                draw.text((ox + int(OPTION_LABEL_OFFSET_X * s),
                           oy + int(OPTION_LABEL_OFFSET_Y * s)),
                          label, fill="black", font=font_text)

        question_regions.append({
            "number": qnum,
            "x": int(x),
            "y": int(y),
            "options": cur_options,
        })

    # ═══ 7. 保存图片 ═══
    upload_dir = str(UPLOADS_DIR / "answer_sheets")
    os.makedirs(upload_dir, exist_ok=True)

    ext = "png"
    filename = f"{exam_id}_{page_size.lower()}.{ext}"
    save_path = os.path.join(upload_dir, filename)
    img.save(save_path, quality=95)

    # ═══ 8. 构建坐标配置（与 omr_scanner.py 完全对齐） ═══
    coord_config = {
        # 画布尺寸
        "canvas_width": width,
        "canvas_height": height,
        # 题目布局参数
        "items_per_row": ITEMS_PER_ROW,
        "start_x": int(START_X * s),
        "start_y": int(START_Y * s),
        "row_spacing": int(ROW_SPACING * s),
        "option_spacing": int(OPTION_SPACING * s),
        "circle_diameter": int(CIRCLE_DIAMETER * s),
        "option_count": option_count,
        # 四角定位块
        "anchor_size": int(ANCHOR_SIZE * s),
        "anchor_positions": {k: (int(v[0] * s), int(v[1] * s)) for k, v in ANCHOR_POSITIONS.items()},
        # 考号区域（包含扫描器所需的全部坐标参数）
        "exam_number_area": {
            "x": exam_x,
            "y": exam_y,
            "digits": EXAM_NUMBER_DIGITS,
            "digit_spacing": spacing,               # 水平方向：数字列间距
            "option_spacing": opt_spacing,           # 垂直方向：0-9选项间距
            "circle_diameter": exam_circle_d,        # 考号选项圈直径
            "label_offset_y": opt_start_y,           # y → 数字标签的Y偏移
            "option_offset_y": int(30 * s),          # 数字标签 → 第一个选项圈(0)的Y偏移
            "x_offset": int(80 * s),                 # x → 第一位数字列的X偏移
            "layout": "vertical",                    # 布局：选项纵向排列
        },
        # 题目区域列表
        "question_regions": question_regions,
        # 元数据
        "page_size": page_size,
        "dpi": dpi,
        "border_width": bw,
    }

    image_url = f"/static/answer_sheets/{filename}"

    logger.info("答题卡生成完成 | exam_id=%d 题数=%d 尺寸=%dx%d dpi=%d",
                exam_id, total_questions, width, height, dpi)

    return {
        "image_url": image_url,
        "coordinate_config": coord_config,
        "total_questions": total_questions,
        "option_count": option_count,
    }


def save_answer_sheet_config_to_db(
    db_session,
    exam_id: int,
    sheet_data: dict,
):
    """将答题卡配置保存到 teacher_exam.answer_sheet_config

    在API层调用此函数，避免在服务层引入db依赖
    """
    from app.models.exam_models import TeacherExam
    from sqlalchemy.orm.attributes import flag_modified

    exam = db_session.query(TeacherExam).filter(TeacherExam.id == exam_id).first()
    if not exam:
        logger.error("保存答题卡配置: 试卷不存在 (id=%d)", exam_id)
        return False

    if not exam.answer_sheet_config:
        exam.answer_sheet_config = {}

    exam.answer_sheet_config.update(sheet_data)
    flag_modified(exam, "answer_sheet_config")
    db_session.commit()

    logger.info("答题卡配置已保存到数据库 | exam_id=%d", exam_id)
    return True
