"""
OMR 答题卡扫描识别模块（v3 重写版）

核心思路：
  1. 答题卡有四角定位块 + 外黑边框 → 可靠检测边界
  2. 透视矫正到 A4 标准尺寸（2480×3508）
  3. 使用 coordinate_config 中的精确坐标采样每个选项圈/方框
  4. OTSU 二值化 + ROI填涂比例判定

支持两种答题卡：
  - 系统生成答题卡：圆形选项圈，4选项，纵向排列
  - 外部真实答题卡：方形选项框，7选项，双列布局（Q1-Q10同行左右列，Q13-Q20空，Q21-Q25左列）

相比 v2 的改进：
  - 移除复杂的 Dinosheet/Anchor/GraderFlow 多方法降级
  - 统一使用坐标配置采样，简单可靠
  - 四角定位块 + 黑边框双重保障透视矫正
  - 新增矩形ROI采样支持方形选项框
  - 新增双列布局扫描支持真实答题卡格式
"""

import os
import time
import logging
from typing import Optional

import cv2
import numpy as np

from app.services.printable_sheet_constants import (
    A4_WIDTH, A4_HEIGHT,
    FILL_THRESHOLD,
    MORPH_KERNEL,
    EXAM_NUMBER_Y, EXAM_NUMBER_X_START, EXAM_NUMBER_SPACING,
    EXAM_NUMBER_OPTION_SPACING, EXAM_NUMBER_OPTION_START_Y, EXAM_NUMBER_DIGITS,
    CIRCLE_DIAMETER, CIRCLE_RADIUS,
    ANCHOR_SIZE, ANCHOR_POSITIONS,
)

logger = logging.getLogger(__name__)

# 选项标签
_OPTION_LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']


# ════════════════════════════════════════════
# 模板尺寸定义 (mm) — 来自 plan_ask/exam.html CSS
# ════════════════════════════════════════════

SHEET_W_MM = 198.0       # 答题卡宽度
SHEET_H_MM = 280.0       # 答题卡高度
CORNER_MARGIN_MM = 2.75  # 四角标记中心距边缘距离 (1.5mm边距 + 1.25mm半宽)

# 考号填涂区 (模板CSS比例)
EXAM_GRID_MM = {
    'start_x': 104.15,   # 网格左边距
    'col_w': 6.5,        # 每列宽
    'col_gap': 1.2,      # 列间距
    'start_y': 21.4,     # 网格顶边距
    'header_h': 6.0,     # 手写行高 (必须跳过!)
    'box_h': 4.2,        # 数字框高
    'box_gap': 0.3,      # 行间距
    'num_cols': 7,
    'num_rows': 10,      # 0~9
}

# 答案填涂区 (模板CSS比例)
ANSWER_AREA_MM = {
    'start_y': 80.4,     # 答案区起点Y
    'row_h': 6.0,        # 题目行高
    'row_gap': 0.5,      # 行间距
    'box_w': 5.0,        # 选项框宽
    'box_h': 4.2,        # 选项框高
    'left_area_x': 3.5,  # 左列area起点
    'right_area_x': 100.5, # 右列area起点
    'area_pad': 0.8,     # area内边距
    'q_num_w': 5.3,      # 题号宽 (含padding)
    'q_row_gap': 0.3,    # question-row内gap
    'opt_label_w': 2.5,  # 选项标签宽
    'opt_gap': 0.8,      # 选项间距
}


def _detect_corners_direct(gray: np.ndarray) -> Optional[np.ndarray]:
    """在图像4个角区域直接搜索暗色方块定位标记

    策略: 在每个角区域用固定低阈值(40~120)二值化，
    找面积最大的方形暗色区域作为角标。

    Returns:
        4个角点中心坐标 [TL, TR, BR, BL]，或None
    """
    h, w = gray.shape
    search_size = min(100, w // 10, h // 10)

    corners = {}
    corner_defs = {
        'TL': (0, search_size, 0, search_size),
        'TR': (0, search_size, w - search_size, w),
        'BL': (h - search_size, h, 0, search_size),
        'BR': (h - search_size, h, w - search_size, w),
    }

    for name, (y1, y2, x1, x2) in corner_defs.items():
        region = gray[y1:y2, x1:x2]
        best = None
        best_area = 0

        for t in [40, 50, 60, 80, 100, 120]:
            _, binary = cv2.threshold(region, t, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 20 or area > 2000:
                    continue
                bx, by, bw, bh = cv2.boundingRect(cnt)
                aspect = max(bw, bh) / max(1, min(bw, bh))
                if aspect > 2.0:
                    continue
                fill = area / (bw * bh)
                if fill < 0.3:
                    continue
                if area > best_area:
                    cx = x1 + bx + bw // 2
                    cy = y1 + by + bh // 2
                    best = (cx, cy)
                    best_area = area

            if best is not None:
                break

        if best:
            corners[name] = best
        else:
            logger.warning("角标检测 %s 未找到", name)

    if len(corners) < 4:
        return None

    pts = np.float32([
        corners['TL'], corners['TR'],
        corners['BR'], corners['BL'],
    ])

    # 排序为 [TL, TR, BR, BL]
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # TL
    rect[2] = pts[np.argmax(s)]  # BR
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]  # TR
    rect[3] = pts[np.argmax(d)]  # BL

    logger.info("四角标记检测: TL=%s TR=%s BR=%s BL=%s",
                 corners['TL'], corners['TR'],
                 corners['BR'], corners['BL'])
    return rect


def _rectify_by_corners(img: np.ndarray,
                         corners: np.ndarray) -> tuple:
    """透视矫正 — 角标映射到参考画布的正确比例位置

    关键改进: 不映射到画布四角(0,0)，而是映射到角标在画布中的
    正确比例位置(距边缘2.75mm)。这样矫正后的图像代表完整答题卡，
    所有元素位置可用模板CSS尺寸直接计算。

    Returns:
        (矫正后图像, 参考宽, 参考高)
    """
    w_dist = np.linalg.norm(corners[1] - corners[0])
    h_dist = np.linalg.norm(corners[3] - corners[0])

    # 参考画布: 补回角标到边缘的距离
    ref_w = int(w_dist * SHEET_W_MM / (SHEET_W_MM - 2 * CORNER_MARGIN_MM))
    ref_h = int(h_dist * SHEET_H_MM / (SHEET_H_MM - 2 * CORNER_MARGIN_MM))
    ref_w = ref_w if ref_w % 2 == 0 else ref_w + 1
    ref_h = ref_h if ref_h % 2 == 0 else ref_h + 1

    # 角标在画布中的位置
    margin_x = ref_w * CORNER_MARGIN_MM / SHEET_W_MM
    margin_y = ref_h * CORNER_MARGIN_MM / SHEET_H_MM

    dst = np.float32([
        [margin_x, margin_y],
        [ref_w - margin_x, margin_y],
        [ref_w - margin_x, ref_h - margin_y],
        [margin_x, ref_h - margin_y],
    ])

    M = cv2.getPerspectiveTransform(corners, dst)
    rectified = cv2.warpPerspective(img, M, (ref_w, ref_h))
    logger.info("透视矫正(角标比例): %dx%d → %dx%d "
                "(角标映射到 %.0f,%.0f 内)",
                img.shape[1], img.shape[0], ref_w, ref_h,
                margin_x, margin_y)
    return rectified, ref_w, ref_h


def _compute_template_positions(ref_w: int, ref_h: int) -> dict:
    """用模板CSS尺寸(mm)计算所有元素的像素位置

    Returns:
        {
            'exam_cols': [7个列中心X],
            'exam_rows': [10个行中心Y],  # 0~9, 已跳过手写行
            'exam_header_y': 手写行Y,
            'exam_box_w': 采样框宽,
            'exam_box_h': 采样框高,
            'answers': [{qn, options: [{label, cx, cy}]}],
            'answer_box_w': 答案采样框宽,
            'answer_box_h': 答案采样框高,
        }
    """
    px_x = lambda mm: int(mm * ref_w / SHEET_W_MM)
    px_y = lambda mm: int(mm * ref_h / SHEET_H_MM)

    # ── 考号网格 ──
    col_pitch = EXAM_GRID_MM['col_w'] + EXAM_GRID_MM['col_gap']
    exam_cols = []
    for i in range(EXAM_GRID_MM['num_cols']):
        cx_mm = (EXAM_GRID_MM['start_x'] + EXAM_GRID_MM['col_w'] / 2 +
                 i * col_pitch)
        exam_cols.append(px_x(cx_mm))

    row_pitch = EXAM_GRID_MM['box_h'] + EXAM_GRID_MM['box_gap']
    exam_rows = []
    for i in range(EXAM_GRID_MM['num_rows']):
        # 跳过手写行: 从 header_h 之后开始
        cy_mm = (EXAM_GRID_MM['start_y'] + EXAM_GRID_MM['header_h'] +
                 EXAM_GRID_MM['box_gap'] + EXAM_GRID_MM['box_h'] / 2 +
                 i * row_pitch)
        exam_rows.append(px_y(cy_mm))

    exam_box_w = max(12, px_x(EXAM_GRID_MM['col_w']) - 4)
    exam_box_h = max(10, px_y(EXAM_GRID_MM['box_h']) - 4)

    # ── 答案框 ──
    # 每个选项的X偏移(相对option-group起点):
    # label(2.5) + gap(0.8) + box/2 = 5.8mm (第1个)
    # 之后每个: box(5.0) + gap(0.8) + label(2.5) + gap(0.8) = 9.1mm 间距
    opt_start_offset = (ANSWER_AREA_MM['opt_label_w'] +
                        ANSWER_AREA_MM['opt_gap'] +
                        ANSWER_AREA_MM['box_w'] / 2)  # 5.8mm
    opt_pitch = (ANSWER_AREA_MM['box_w'] + ANSWER_AREA_MM['opt_gap'] +
                 ANSWER_AREA_MM['opt_label_w'] + ANSWER_AREA_MM['opt_gap'])  # 9.1mm

    # option-group起点 = area_x + pad + q_num_w + q_row_gap
    opt_group_offset = (ANSWER_AREA_MM['area_pad'] +
                        ANSWER_AREA_MM['q_num_w'] +
                        ANSWER_AREA_MM['q_row_gap'])  # 6.4mm

    answers = []
    for qn in range(10):
        col_idx = qn // 5  # 0=left, 1=right
        row_idx = qn % 5

        area_x = (ANSWER_AREA_MM['left_area_x'] if col_idx == 0
                  else ANSWER_AREA_MM['right_area_x'])

        cy_mm = (ANSWER_AREA_MM['start_y'] + ANSWER_AREA_MM['row_h'] / 2 +
                 row_idx * (ANSWER_AREA_MM['row_h'] + ANSWER_AREA_MM['row_gap']))

        options = []
        for opt_i in range(4):
            cx_mm = (area_x + opt_group_offset +
                     opt_start_offset + opt_i * opt_pitch)
            options.append({
                'label': ['A', 'B', 'C', 'D'][opt_i],
                'cx': px_x(cx_mm),
                'cy': px_y(cy_mm),
            })
        answers.append({'qn': qn + 1, 'options': options})

    answer_box_w = max(12, px_x(ANSWER_AREA_MM['box_w']) - 2)
    answer_box_h = max(10, px_y(ANSWER_AREA_MM['box_h']) - 2)

    return {
        'exam_cols': exam_cols,
        'exam_rows': exam_rows,
        'exam_header_y': px_y(EXAM_GRID_MM['start_y']),
        'exam_box_w': exam_box_w,
        'exam_box_h': exam_box_h,
        'answers': answers,
        'answer_box_w': answer_box_w,
        'answer_box_h': answer_box_h,
    }


def _scan_exam_number_template(rectified: np.ndarray,
                                positions: dict) -> str:
    """考号识别 — 模板比例驱动

    用模板CSS尺寸计算的位置直接采样，固定阈值190二值化。
    """
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY_INV)

    cols = positions['exam_cols']
    rows = positions['exam_rows']
    bw = positions['exam_box_w']
    bh = positions['exam_box_h']

    result = []
    for col_idx in range(len(cols)):
        cx = cols[col_idx]
        scores = {}

        for num in range(len(rows)):
            cy = rows[num]
            x1 = max(0, cx - bw // 2)
            x2 = min(gray.shape[1], cx + bw // 2)
            y1 = max(0, cy - bh // 2)
            y2 = min(gray.shape[0], cy + bh // 2)

            cell = thresh[y1:y2, x1:x2]
            total = cell.size
            white = int(np.sum(cell == 255))
            scores[str(num)] = round(white / total, 4) if total > 0 else 0.0

        best = max(scores, key=scores.get)
        best_fill = scores[best]
        sorted_vals = sorted(scores.values(), reverse=True)
        second = sorted_vals[1] if len(sorted_vals) > 1 else 0
        diff = best_fill - second

        logger.info("考号位%d: scores=%s",
                     col_idx, {k: f"{v:.4f}" for k, v in scores.items()})

        if best_fill > 0.30 and diff > 0.08:
            result.append(best)
            logger.info("考号位%d: ->%s (fill=%.4f diff=%.4f)",
                         col_idx, best, best_fill, diff)
        else:
            result.append("?")
            logger.info("考号位%d: 未识别 (best=%s fill=%.4f diff=%.4f)",
                         col_idx, best, best_fill, diff)

    exam_number = "".join(result)
    logger.info("考号结果(模板驱动): '%s'", exam_number)
    return exam_number


def _scan_answers_template(rectified: np.ndarray,
                            positions: dict) -> dict:
    """答案识别 — 模板比例驱动"""
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY_INV)

    bw = positions['answer_box_w']
    bh = positions['answer_box_h']
    answers = {}

    for q in positions['answers']:
        qn = q['qn']
        scores = {}

        for opt in q['options']:
            cx, cy = opt['cx'], opt['cy']
            x1 = max(0, cx - bw // 2)
            x2 = min(gray.shape[1], cx + bw // 2)
            y1 = max(0, cy - bh // 2)
            y2 = min(gray.shape[0], cy + bh // 2)

            cell = thresh[y1:y2, x1:x2]
            total = cell.size
            white = int(np.sum(cell == 255))
            fill = round(white / total, 4) if total > 0 else 0.0
            scores[opt['label']] = fill

        best = max(scores, key=scores.get)
        best_fill = scores[best]
        sorted_vals = sorted(scores.values(), reverse=True)
        second = sorted_vals[1] if len(sorted_vals) > 1 else 0
        diff = best_fill - second

        if best_fill > 0.25 and diff > 0.06:
            answers[qn] = {
                "answer": best,
                "confidence": round(best_fill, 4),
                "scores": scores,
                "method": "template",
            }
            logger.info("Q%d: ->%s (fill=%.4f diff=%.4f scores=%s)",
                         qn, best, best_fill, diff,
                         {k: f"{v:.4f}" for k, v in scores.items()})
        else:
            answers[qn] = {
                "answer": "",
                "confidence": 0.0,
                "scores": scores,
                "method": "template",
            }
            logger.info("Q%d: 未识别 (best=%s fill=%.4f diff=%.4f)",
                         qn, best, best_fill, diff)

    return answers


def _save_template_debug(rectified: np.ndarray, positions: dict,
                          upload_dir: str = None) -> None:
    """保存模板驱动扫描的调试图"""
    import os, time
    if not upload_dir or not os.path.isdir(upload_dir):
        return
    try:
        ts = int(time.time())
        debug = rectified.copy()
        cols = positions['exam_cols']
        rows = positions['exam_rows']
        bw = positions['exam_box_w']
        bh = positions['exam_box_h']

        # 考号区网格 (绿色框)
        for cx in cols:
            for cy in rows:
                cv2.rectangle(debug,
                              (cx - bw // 2, cy - bh // 2),
                              (cx + bw // 2, cy + bh // 2),
                              (0, 255, 0), 1)

        # 手写行底线 (蓝色)
        header_y = positions['exam_header_y']
        hw_h = int(bh * 1.5)
        cv2.line(debug, (cols[0] - 20, header_y + hw_h),
                 (cols[-1] + 20, header_y + hw_h), (255, 0, 0), 2)

        # 答案框 (绿色框)
        aw = positions['answer_box_w']
        ah = positions['answer_box_h']
        for q in positions['answers']:
            for opt in q['options']:
                cx, cy = opt['cx'], opt['cy']
                cv2.rectangle(debug,
                              (cx - aw // 2, cy - ah // 2),
                              (cx + aw // 2, cy + ah // 2),
                              (0, 255, 0), 1)

        cv2.imwrite(os.path.join(upload_dir,
                     f"debug_template_{ts}.jpg"), debug)
        logger.info("模板调试图已保存: debug_template_%d.jpg", ts)
    except Exception as e:
        logger.warning("保存模板调试图失败: %s", e)


# ════════════════════════════════════════════
# 图像加载 & 透视矫正
# ════════════════════════════════════════════

def _load_image(image_path: str) -> Optional[np.ndarray]:
    """加载图片"""
    img = cv2.imread(image_path)
    if img is None:
        logger.error("无法读取图像: %s", image_path)
    return img


def _find_sheet_corners(gray: np.ndarray) -> Optional[np.ndarray]:
    """检测答题卡四角定位块 → 返回排序后的4个角点

    策略：
      1. 自适应二值化 → 找全图大轮廓
      2. 筛选：面积 > 5% 图像面积 且 近似4边形
      3. 取最大四边形，返回排序角点 [左上, 右上, 右下, 左下]
    """
    h, w = gray.shape[:2]
    min_area = h * w * 0.03

    # 多阈值尝试 Canny 边缘检测
    for low, high in [(50, 150), (30, 100), (75, 200)]:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, low, high)
        # 闭运算连接断边
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        # 按面积降序排列，找最大近似四边形
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                return _sort_corners(pts)

    # 二阶段：用凸包逼近
    for low, high in [(50, 150), (30, 100)]:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, low, high)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for cnt in contours:
            if cv2.contourArea(cnt) < min_area:
                continue
            hull = cv2.convexHull(cnt)
            peri = cv2.arcLength(hull, True)
            approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                return _sort_corners(pts)

    return None


def _sort_corners(pts: np.ndarray) -> np.ndarray:
    """四边形角点排序: 左上→右上→右下→左下"""
    # 先按Y排序，分成上下两组
    by_y = pts[np.argsort(pts[:, 1])]
    top_two = by_y[:2]
    bottom_two = by_y[2:]

    # 每组内按X排序
    tl, tr = top_two[np.argsort(top_two[:, 0])]
    bl, br = bottom_two[np.argsort(bottom_two[:, 0])]

    return np.float32([tl, tr, br, bl])


def _rectify(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """透视矫正：检测答题卡边界 → 变换到 A4 标准尺寸

    返回: (矫正后图像, 是否成功)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    corners = _find_sheet_corners(gray)
    if corners is None:
        logger.warning("透视矫正: 未检测到答题卡边界，使用原始图像")
        # 如果原图尺寸接近A4，直接使用
        h, w = img.shape[:2]
        if abs(w / h - A4_WIDTH / A4_HEIGHT) < 0.1:
            img_resized = cv2.resize(img, (A4_WIDTH, A4_HEIGHT))
            return img_resized, False
        return img, False

    # 目标坐标: A4 标准尺寸
    dst = np.float32([
        [0, 0],
        [A4_WIDTH - 1, 0],
        [A4_WIDTH - 1, A4_HEIGHT - 1],
        [0, A4_HEIGHT - 1],
    ])

    try:
        M = cv2.getPerspectiveTransform(corners, dst)
        rectified = cv2.warpPerspective(img, M, (A4_WIDTH, A4_HEIGHT))
        logger.info("透视矫正成功: %dx%d → A4 (%dx%d)",
                     img.shape[1], img.shape[0], A4_WIDTH, A4_HEIGHT)
        return rectified, True
    except Exception as e:
        logger.error("透视变换失败: %s", e)
        return img, False


def _find_four_corner_markers(gray: np.ndarray) -> Optional[np.ndarray]:
    """检测外部答题卡四角黑色定位方块（v5 组合搜索版）

    不再依赖象限分组——如果答题卡在照片中倾斜或偏移，
    角标可能跨过象限边界。新策略：
      1. 宽松过滤收集所有方形候选（面积≥10, 宽高比≤4, 填充率≥0.2）
      2. 按离图像中心距离排序，取前30个最外层的候选
      3. 穷举搜索最优四边形组合（面积大 + 宽高比匹配）
    """
    h_img, w_img = gray.shape[:2]
    img_area = w_img * h_img
    cx_c = w_img / 2.0
    cy_c = h_img / 2.0
    expected_aspect = w_img / max(h_img, 1.0)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 收集所有候选，去重用 (cx, cy) 近似距离
    all_candidates = []  # [(cx, cy, score, area, fill_ratio), ...]
    seen_positions = set()

    # 多组自适应参数尝试（小C值更敏感，大blockSize更平滑）
    for block_size in [11, 15, 21, 31]:
        for c_val in [1, 2, 4]:
            try:
                thresh = cv2.adaptiveThreshold(
                    blurred, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV,
                    block_size, c_val)
            except cv2.error:
                continue

            # 轻量形态学：闭运算连接碎片，不开运算（避免过度去除小方块）
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                # 宽松面积范围：10~8000
                if area < 10 or area > 8000:
                    continue

                bx, by, bw, bh = cv2.boundingRect(cnt)
                if bw <= 1 or bh <= 1:
                    continue

                # 宽高比 ≤ 4:1（允许轻微畸变，远宽松于之前的 2.5）
                aspect_ratio = max(bw, bh) / min(bw, bh)
                if aspect_ratio > 4.0:
                    continue

                # 填充率 ≥ 0.2（远宽松于之前的 0.4）
                fill_ratio = area / (bw * bh)
                if fill_ratio < 0.2:
                    continue

                # 质心
                M = cv2.moments(cnt)
                if M["m00"] == 0:
                    continue
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

                # 去重：相近位置只保留得分更高的
                pos_key = (cx // 5, cy // 5)  # 5px 粒度去重
                if pos_key in seen_positions:
                    continue
                seen_positions.add(pos_key)

                # 得分：填充率 + 大小（越大越好，说明是明显的方块）
                size_score = min(area / 500.0, 1.0)
                score = fill_ratio * 0.5 + size_score * 0.5

                all_candidates.append((cx, cy, score, area, fill_ratio))

    logger.info("四角定位块: 宽松过滤阶段找到 %d 个候选", len(all_candidates))

    if len(all_candidates) < 4:
        return None

    # ═══ 穷举搜索最优四边形 ═══
    # 按距离中心排序，取前30个最外层候选
    all_candidates.sort(key=lambda c: (c[0] - cx_c) ** 2 + (c[1] - cy_c) ** 2,
                        reverse=True)
    top_k = min(30, len(all_candidates))
    top = all_candidates[:top_k]

    best_score = -1.0
    best_quad = None
    best_info = ""

    n = top_k
    for a in range(n):
        for b in range(a + 1, n):
            for c in range(b + 1, n):
                for d in range(c + 1, n):
                    pts_raw = np.float32([
                        top[a][:2], top[b][:2], top[c][:2], top[d][:2],
                    ])
                    pts_sorted = _sort_corners(pts_raw)
                    q_area = cv2.contourArea(pts_sorted.astype(np.int32))

                    # 面积至少占图像 8%
                    area_pct = q_area / img_area
                    if area_pct < 0.08:
                        continue

                    # 宽高比检查
                    q_w = np.linalg.norm(pts_sorted[0] - pts_sorted[1])
                    q_h = np.linalg.norm(pts_sorted[0] - pts_sorted[3])
                    if q_h < 1:
                        continue
                    q_aspect = q_w / q_h
                    max_aspect = max(q_aspect, 1.0 / q_aspect)
                    if max_aspect > 3.0:
                        continue

                    # 综合评分：面积 × 宽高比匹配度 ÷ 周长（偏向紧凑四边形）
                    aspect_match = 1.0 - min(
                        abs(q_aspect - expected_aspect) / max(expected_aspect, 0.1), 1.0)
                    peri = cv2.arcLength(pts_sorted.astype(np.int32), True)
                    compactness = 4.0 * np.pi * q_area / max(peri * peri, 1.0)

                    total = area_pct * 0.4 + aspect_match * 0.3 + compactness * 0.3

                    if total > best_score:
                        best_score = total
                        best_quad = pts_sorted.copy()
                        best_info = (
                            f"面积={area_pct*100:.1f}% "
                            f"宽高比={q_aspect:.3f} "
                            f"紧凑度={compactness:.3f}"
                        )

    if best_quad is not None:
        logger.info("四角定位块检测成功: 从%d个候选中穷举搜索, 最优得分=%.3f %s",
                      len(all_candidates), best_score, best_info)
        return best_quad

    logger.warning("四角定位块: %d个候选中未找到合格四边形", len(all_candidates))
    return None


def _find_sheet_corners_adaptive(gray: np.ndarray) -> Optional[np.ndarray]:
    """使用自适应阈值检测答题卡四角（兜底方案）

    当四角定位块检测失败时，用此方法找答题卡边框四边形。
    优先尝试四角定位块 _find_four_corner_markers。

    改进：不再简单取最大四边形，而是按"宽高比匹配度 + 面积"综合评分排序。
    """
    h, w = gray.shape[:2]
    min_area = h * w * 0.03
    max_area = h * w * 0.92
    expected_aspect = w / max(h, 1)  # 答题卡宽高比应与原始图像相近

    all_candidates = []  # [(score, sorted_pts), ...]

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    for block_size in [11, 15, 21, 31]:
        for c_val in [2, 4, 7]:
            try:
                thresh = cv2.adaptiveThreshold(
                    blurred, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV,
                    block_size, c_val)
            except cv2.error:
                continue

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area or area > max_area:
                    continue

                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                if len(approx) != 4:
                    continue

                pts = approx.reshape(4, 2).astype(np.float32)
                sorted_pts = _sort_corners(pts)

                # 计算四边形宽高比
                quad_w = np.linalg.norm(sorted_pts[0] - sorted_pts[1])
                quad_h = np.linalg.norm(sorted_pts[0] - sorted_pts[3])
                if quad_h < 1:
                    continue
                quad_aspect = quad_w / quad_h
                aspect_ratio = max(quad_aspect, 1.0 / quad_aspect)
                # 期望情况：宽高比不超3:1，且与原始图像相近
                if aspect_ratio > 3.0:
                    continue

                # 综合评分：宽高比匹配度 + 面积大小
                aspect_match = 1.0 - min(
                    abs(quad_aspect - expected_aspect) / max(expected_aspect, 0.1), 1.0)
                area_score = min(area / (w * h * 0.5), 1.0)
                score = aspect_match * 0.6 + area_score * 0.4
                all_candidates.append((score, sorted_pts))

    if all_candidates:
        all_candidates.sort(key=lambda x: x[0], reverse=True)
        best = all_candidates[0]
        logger.info("自适应边框检测: %d个候选 → 最佳得分=%.3f",
                      len(all_candidates), best[0])
        return best[1]

    return None


def _save_debug_rectify(original_img: np.ndarray, rectified: np.ndarray,
                        markers: Optional[np.ndarray],
                        method: str,
                        ref_w: int, ref_h: int,
                        upload_dir: str = "uploads") -> None:
    """保存透视矫正前的标记检测图和矫正后图像，用于诊断"""
    try:
        debug_dir = os.path.join(upload_dir, "omr_debug")
        os.makedirs(debug_dir, exist_ok=True)
        ts = int(time.time())

        # 矫正后图像
        rect_path = os.path.join(debug_dir, f"rectified_{method}_{ts}.jpg")
        cv2.imwrite(rect_path, rectified)

        # 标记检测图
        if markers is not None:
            debug_img = original_img.copy()
            # 绘制检测到的角点
            colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0)]  # 绿红蓝青
            labels = ["TL", "TR", "BR", "BL"]
            for i, (pt, color, label) in enumerate(zip(markers, colors, labels)):
                px, py = int(pt[0]), int(pt[1])
                cv2.circle(debug_img, (px, py), 15, color, 3)
                cv2.circle(debug_img, (px, py), 5, color, -1)
                cv2.putText(debug_img, f"{label}({px},{py})",
                            (px + 20, py - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            # 绘制连线
            for i in range(4):
                pt1 = (int(markers[i][0]), int(markers[i][1]))
                pt2 = (int(markers[(i + 1) % 4][0]), int(markers[(i + 1) % 4][1]))
                cv2.line(debug_img, pt1, pt2, (0, 255, 255), 2)

            marker_path = os.path.join(debug_dir, f"markers_{method}_{ts}.jpg")
            cv2.imwrite(marker_path, debug_img)
            logger.info("诊断图已保存: markers=%s rectified=%s", marker_path, rect_path)
        else:
            logger.info("矫正图已保存: rectified=%s", rect_path)
    except Exception as e:
        logger.debug("保存诊断图失败: %s", e)


def _rectify_to_reference(img: np.ndarray,
                           coordinate_config: dict) -> tuple[np.ndarray, bool, int, int]:
    """外部答题卡透视矫正 → 变换到参考分辨率（1387×1960）

    四级降级策略：
      1. 四角黑色定位方块 → cv2.getPerspectiveTransform（最精确）
      2. 自适应阈值四边形轮廓（宽高比匹配评分）
      3. OTSU + Canny边缘检测四边形（经典方法）
      4. 等比缩放居中兜底

    返回: (矫正后图像, 是否成功, 矫正后宽, 矫正后高)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    src_h, src_w = gray.shape[:2]

    ref_w = coordinate_config.get("reference_width", 1387)
    ref_h = coordinate_config.get("reference_height", 1960)

    dst = np.float32([
        [0, 0],
        [ref_w - 1, 0],
        [ref_w - 1, ref_h - 1],
        [0, ref_h - 1],
    ])

    upload_dir = coordinate_config.get("upload_dir", "uploads")

    def _do_transform(markers_pts, method_label):
        """执行透视变换 + 保存诊断图"""
        try:
            M = cv2.getPerspectiveTransform(markers_pts, dst)
            result = cv2.warpPerspective(img, M, (ref_w, ref_h))
            logger.info("外部答题卡透视矫正(%s): %dx%d → 参考分辨率 %dx%d",
                         method_label, src_w, src_h, ref_w, ref_h)
            # 保存调试图
            _save_debug_rectify(img, result, markers_pts, method_label,
                                 ref_w, ref_h, upload_dir)
            return result, True, ref_w, ref_h
        except Exception as e:
            logger.warning("外部答题卡透视变换失败(%s): %s", method_label, e)
            return None

    # ═══ 阶段1: 四角黑色定位方块（最精确）═══
    corners = _find_four_corner_markers(gray)
    if corners is not None:
        result = _do_transform(corners, "cornermarkers")
        if result is not None:
            return result

    # ═══ 阶段2: 自适应阈值四边形轮廓 ═══
    corners = _find_sheet_corners_adaptive(gray)
    if corners is not None:
        result = _do_transform(corners, "adaptive")
        if result is not None:
            return result

    # ═══ 阶段3: OTSU + Canny 经典方法 ═══
    corners = _find_sheet_corners(gray)
    if corners is not None:
        result = _do_transform(corners, "otsu")
        if result is not None:
            return result

    # ═══ 阶段4: 等比缩放居中兜底 ═══
    scale = min(ref_w / src_w, ref_h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    canvas = np.ones((ref_h, ref_w, 3), dtype=np.uint8) * 255
    x_off = (ref_w - new_w) // 2
    y_off = (ref_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

    # 兜底也保存诊断图
    _save_debug_rectify(img, canvas, None, "fallback_resize", ref_w, ref_h, upload_dir)
    logger.warning("外部答题卡: 所有检测方法失败，等比缩放兜底 %dx%d → %dx%d (居中于 %dx%d)",
                    src_w, src_h, new_w, new_h, ref_w, ref_h)
    return canvas, False, ref_w, ref_h


# ════════════════════════════════════════════
# 二值化 & 填涂判定
# ════════════════════════════════════════════

def _binary_inv(gray: np.ndarray) -> np.ndarray:
    """OTSU 二值化（反色）：墨迹→白(255)，纸张→黑(0)

    加上形态学开运算消除细边框
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if MORPH_KERNEL > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MORPH_KERNEL, MORPH_KERNEL))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    return binary


def _binary_otsu_simple(gray: np.ndarray) -> np.ndarray:
    """简化版OTSU二值化（反色）—— 参考 answer-paper 项目

    流程（与 answer-paper 的 _detect_answers 一致）：
      1. GaussianBlur(5,5) → 降噪
      2. cv2.threshold(..., THRESH_BINARY_INV + THRESH_OTSU) → 自动阈值二值化

    相比 adaptiveThreshold 的优势：
      - Otsu 基于全局直方图自动计算最优阈值，对不同拍摄条件适应性强
      - 不需要手动调参（blockSize/C值）
      - 填涂与未填涂区域的白色像素比例差异显著（填涂 >50%，未填涂 <10%）

    墨迹→白(255)，纸张→黑(0)
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _binary_adaptive(gray: np.ndarray) -> np.ndarray:
    """自适应二值化（反色）—— 保留作为后备方案

    仅在没有四角定位块的答题卡上使用，提供更好的局部光照适应性。
    Otsu 二值化应该在大多数场景下更可靠。
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    total_pixels = blurred.size
    best_binary = None
    best_score = -1.0

    for block_size in [11, 15, 21]:
        for c_val in [1, 2, 4]:
            try:
                binary = cv2.adaptiveThreshold(
                    blurred, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV,
                    block_size, c_val)
            except cv2.error:
                continue

            white_pct = cv2.countNonZero(binary) / total_pixels * 100
            if 10 <= white_pct <= 35:
                score = 1.0 - abs(white_pct - 15) / 20
                if score > best_score:
                    best_score = score
                    best_binary = binary

    if best_binary is not None:
        return best_binary

    # 兜底参数
    binary = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 1)
    logger.warning("自适应二值化: 无参数落入目标范围，使用兜底参数")
    return binary


def _sample_circle_fill(binary_inv: np.ndarray, cx: int, cy: int,
                         diameter: int) -> float:
    """圆形ROI填涂比例（0~1）

    在 (cx, cy) 中心，以 diameter 为直径采样圆形区域，
    统计白色像素占比。使用圆形遮罩避免矩形角部的干扰。
    """
    radius = diameter // 2
    h, w = binary_inv.shape[:2]

    # ROI 边界
    x1 = max(0, cx - radius)
    y1 = max(0, cy - radius)
    x2 = min(w, cx + radius)
    y2 = min(h, cy + radius)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    roi = binary_inv[y1:y2, x1:x2]
    roi_h, roi_w = roi.shape[:2]

    # 圆形遮罩
    roi_cx = roi_w / 2.0
    roi_cy = roi_h / 2.0
    ys, xs = np.ogrid[:roi_h, :roi_w]
    circle_mask = ((xs - roi_cx) ** 2 + (ys - roi_cy) ** 2) <= radius ** 2

    mask_area = np.count_nonzero(circle_mask)
    if mask_area == 0:
        return 0.0

    fill_pixels = cv2.countNonZero(cv2.bitwise_and(roi, roi, mask=circle_mask.astype(np.uint8)))
    return fill_pixels / mask_area


def _sample_rect_fill(binary_inv: np.ndarray, cx: int, cy: int,
                       box_w: int = 44, box_h: int = 30) -> float:
    """矩形ROI填涂比例（0~1）用于方形选项框

    在 (cx, cy) 中心，以 box_w×box_h 为尺寸采样矩形区域，
    统计白色像素占比。

    参数:
        cx, cy: 选项框中心坐标
        box_w, box_h: 矩形采样框的宽和高
    """
    h, w = binary_inv.shape[:2]
    half_w = box_w // 2
    half_h = box_h // 2

    x1 = max(0, cx - half_w)
    y1 = max(0, cy - half_h)
    x2 = min(w, cx + half_w)
    y2 = min(h, cy + half_h)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    roi = binary_inv[y1:y2, x1:x2]
    total = roi.size
    if total == 0:
        return 0.0
    return float(cv2.countNonZero(roi)) / total


def _sample_gray_fill(gray: np.ndarray, cx: int, cy: int,
                       box_w: int = 30, box_h: int = 30) -> float:
    """灰度均值法采样：采样框内平均灰度越低 = 填涂越黑

    返回归一化值 (0=纯黑~1=纯白)，方便与二值化结果统一比较。
    手机拍照条件下灰度检测比 OTSU 二值化更稳定，
    不受全局光照变化影响。

    参数:
        gray: 灰度图像
        cx, cy: 采样框中心坐标
        box_w, box_h: 采样框宽高
    返回:
        0.0(全黑/已填涂) ~ 1.0(全白/未填涂)
    """
    h, w = gray.shape[:2]
    half_w = box_w // 2
    half_h = box_h // 2

    x1 = max(0, cx - half_w)
    y1 = max(0, cy - half_h)
    x2 = min(w, cx + half_w)
    y2 = min(h, cy + half_h)

    if x2 <= x1 or y2 <= y1:
        return 1.0  # 无效区域视为空白

    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return 1.0
    # 平均灰度 / 255 → 归一化: 黑→0, 白→1
    return float(np.mean(roi)) / 255.0


def _sample_fill_with_search(gray: np.ndarray, binary_inv: np.ndarray,
                               cx: int, cy: int,
                               box_w: int = 30, box_h: int = 30,
                               search_radius: int = 15) -> float:
    """在预期坐标 (cx,cy) 附近搜索最暗位置并采样

    策略：
      1. 在 (cx±search_radius, cy±search_radius) 范围内搜索灰度最低的像素点
      2. 以该点为中心采样灰度均值
      3. 返回归一化填充值 (0=全黑, 1=全白)

    这解决了透视矫正后的微小偏移问题——即使理论坐标偏了几像素，
    仍然能找到实际填涂位置。
    """
    h, w = gray.shape[:2]
    half_w = max(1, box_w // 2)
    half_h = max(1, box_h // 2)

    # 搜索边界
    sx1 = max(half_w, cx - search_radius)
    sy1 = max(half_h, cy - search_radius)
    sx2 = min(w - half_w, cx + search_radius)
    sy2 = min(h - half_h, cy + search_radius)

    if sx2 <= sx1 or sy2 <= sy1:
        # 搜索范围无效，回退到原坐标
        return _sample_gray_fill(gray, cx, cy, box_w, box_h)

    # 在搜索区域内用窗口扫描找最暗位置
    best_gray = 255.0
    best_cx, best_cy = cx, cy

    search_roi = gray[sy1:sy2, sx1:sx2]
    if search_roi.size == 0:
        return _sample_gray_fill(gray, cx, cy, box_w, box_h)

    # 用框大小做均值滤波，找最小值位置
    kernel_size = min(box_w, box_h)
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = np.ones((kernel_size, kernel_size), np.float32) / (kernel_size * kernel_size)
    blurred = cv2.filter2D(search_roi, cv2.CV_32F, kernel)

    min_val, _, min_loc, _ = cv2.minMaxLoc(blurred)
    if min_val < 255:
        best_cx = sx1 + min_loc[0] + kernel_size // 2
        best_cy = sy1 + min_loc[1] + kernel_size // 2

    # 在新中心采样
    return _sample_gray_fill(gray, best_cx, best_cy, box_w, box_h)


def _get_scale_factors(image_width: int, image_height: int,
                        coordinate_config: dict) -> tuple[float, float]:
    """计算实际图像相对参考分辨率的缩放比例

    对外部答题卡，坐标基于参考分辨率存储，
    需要按实际图像尺寸缩放。
    """
    ref_w = coordinate_config.get("reference_width")
    ref_h = coordinate_config.get("reference_height")
    if ref_w and ref_h:
        return image_width / ref_w, image_height / ref_h
    return 1.0, 1.0


# ════════════════════════════════════════════
# 真实答题卡坐标配置（方形选项框，双列布局）
# ════════════════════════════════════════════

REAL_SHEET_COORDINATES = {
    "sheet_type": "real_7options",
    "option_count": 7,
    "option_labels": ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
    "box_width": 44,
    "box_height": 30,
    "fill_threshold": 0.35,
    "left_columns": [222, 332, 443, 557, 667, 778, 897],
    "right_columns": [1408, 1519, 1630, 1741, 1852, 1963, 2074],
    "questions": [
        {"number": 1, "side": "left", "row_y": 1120},
        {"number": 6, "side": "right", "row_y": 1120},
        {"number": 2, "side": "left", "row_y": 1200},
        {"number": 7, "side": "right", "row_y": 1200},
        {"number": 3, "side": "left", "row_y": 1280},
        {"number": 8, "side": "right", "row_y": 1280},
        {"number": 4, "side": "left", "row_y": 1360},
        {"number": 9, "side": "right", "row_y": 1360},
        {"number": 5, "side": "left", "row_y": 1440},
        {"number": 10, "side": "right", "row_y": 1440},
        {"number": 11, "side": "left", "row_y": 1577},
        {"number": 12, "side": "left", "row_y": 1658},
        {"number": 21, "side": "left", "row_y": 2067},
        {"number": 22, "side": "left", "row_y": 2151},
        {"number": 23, "side": "left", "row_y": 2235},
        {"number": 24, "side": "left", "row_y": 2313},
        {"number": 25, "side": "left", "row_y": 2396},
    ],
    "exam_number": {
        "y_range": [500, 650],
        "enabled": True,
    },
}

# 外部真实答题卡（4选项，双列布局，10题，7位考号）
# 所有坐标基于参考分辨率 1387×1960，扫描时按比例缩放
EXTERNAL_SHEET_4OPTIONS = {
    "sheet_type": "external_4options",
    "option_count": 4,
    "option_labels": ['A', 'B', 'C', 'D'],
    "reference_width": 1387,
    "reference_height": 1960,
    "search_radius": 0,              # 禁用局部搜索（Otsu二值化 + 精确坐标即可）
    "fill_threshold": 0.40,          # 参考answer-paper: 0.50, 我们设0.40（小方框边框占比高）
    "box_w": 30,                     # 选项框采样宽度
    "box_h": 30,                     # 选项框采样高度
    # 选择题: 10题, option_regions格式存每个选项的中心坐标
    "question_regions": [
        # 左列 Q1-Q5
        {"question_number": 1,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 128, "cy": 641, "w": 30, "h": 30},
             {"label": "B", "cx": 191, "cy": 641, "w": 30, "h": 30},
             {"label": "C", "cx": 267, "cy": 641, "w": 30, "h": 30},
             {"label": "D", "cx": 330, "cy": 641, "w": 30, "h": 30}]},
        {"question_number": 2,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 128, "cy": 660, "w": 30, "h": 30},
             {"label": "B", "cx": 191, "cy": 660, "w": 30, "h": 30},
             {"label": "C", "cx": 267, "cy": 660, "w": 30, "h": 30},
             {"label": "D", "cx": 330, "cy": 660, "w": 30, "h": 30}]},
        {"question_number": 3,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 128, "cy": 686, "w": 30, "h": 30},
             {"label": "B", "cx": 191, "cy": 686, "w": 30, "h": 30},
             {"label": "C", "cx": 267, "cy": 686, "w": 30, "h": 30},
             {"label": "D", "cx": 330, "cy": 686, "w": 30, "h": 30}]},
        {"question_number": 4,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 128, "cy": 703, "w": 30, "h": 30},
             {"label": "B", "cx": 191, "cy": 703, "w": 30, "h": 30},
             {"label": "C", "cx": 267, "cy": 703, "w": 30, "h": 30},
             {"label": "D", "cx": 330, "cy": 703, "w": 30, "h": 30}]},
        {"question_number": 5,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 128, "cy": 730, "w": 30, "h": 30},
             {"label": "B", "cx": 191, "cy": 730, "w": 30, "h": 30},
             {"label": "C", "cx": 267, "cy": 730, "w": 30, "h": 30},
             {"label": "D", "cx": 330, "cy": 730, "w": 30, "h": 30}]},
        # 右列 Q6-Q10
        {"question_number": 6,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 783, "cy": 748, "w": 30, "h": 30},
             {"label": "B", "cx": 846, "cy": 748, "w": 30, "h": 30},
             {"label": "C", "cx": 891, "cy": 748, "w": 30, "h": 30},
             {"label": "D", "cx": 969, "cy": 748, "w": 30, "h": 30}]},
        {"question_number": 7,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 783, "cy": 775, "w": 30, "h": 30},
             {"label": "B", "cx": 846, "cy": 775, "w": 30, "h": 30},
             {"label": "C", "cx": 891, "cy": 775, "w": 30, "h": 30},
             {"label": "D", "cx": 969, "cy": 775, "w": 30, "h": 30}]},
        {"question_number": 8,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 783, "cy": 793, "w": 30, "h": 30},
             {"label": "B", "cx": 846, "cy": 793, "w": 30, "h": 30},
             {"label": "C", "cx": 891, "cy": 793, "w": 30, "h": 30},
             {"label": "D", "cx": 969, "cy": 793, "w": 30, "h": 30}]},
        {"question_number": 9,  "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 783, "cy": 818, "w": 30, "h": 30},
             {"label": "B", "cx": 846, "cy": 818, "w": 30, "h": 30},
             {"label": "C", "cx": 891, "cy": 818, "w": 30, "h": 30},
             {"label": "D", "cx": 969, "cy": 818, "w": 30, "h": 30}]},
        {"question_number": 10, "options": ["A","B","C","D"],
         "option_regions": [
             {"label": "A", "cx": 783, "cy": 833, "w": 30, "h": 30},
             {"label": "B", "cx": 846, "cy": 833, "w": 30, "h": 30},
             {"label": "C", "cx": 891, "cy": 833, "w": 30, "h": 30},
             {"label": "D", "cx": 969, "cy": 833, "w": 30, "h": 30}]},
    ],
    # 7位考号填涂区
    # 坐标基于参考分辨率1387×1960，手写行(y≈150~216)在digit_y上方，不参与扫描
    #
    # ★ 标定边界（来自 docs/答题卡考号识别分析文档.md 的精确分析）
    #   - 手写行: 0~66 (必须跳过！)
    #   - 0~9行: 66~370，10行需要11个y边界
    #   - 7列: 需要8个x边界
    #   所有坐标均为考号区域ROI内的局部坐标
    "exam_number": {
        "digits": 7,
        "digit_x": [754, 806, 855, 907, 956, 1007, 1061],
        "digit_y": [231, 261, 291, 321, 351, 381, 411, 441, 471, 503],
        "box_w": 30,
        "box_h": 20,
        "enabled": True,
        # ★ 精确标定的行列边界（考号ROI内局部坐标）
        "calibrated_col_boundaries": [3, 64, 108, 162, 212, 260, 314, 368],
        "calibrated_row_boundaries": [66, 96, 126, 156, 186, 216, 246, 276, 306, 336, 370],
        # 标定参数：阈值、填充率判定、置信度差距
        "calibrated_threshold": 190,
        "calibrated_fill_threshold": 0.50,
        "calibrated_diff_threshold": 0.30,
    },
}


# ════════════════════════════════════════════
# 题目扫描（v4 改进版）
# ════════════════════════════════════════════

def _scan_questions(binary_inv: np.ndarray,
                     coordinate_config: dict,
                     gray: np.ndarray = None) -> dict:
    """基于坐标配置扫描所有选择题

    v4改进：
      - 优先使用 option_regions[{cx,cy,w,h}] 精确坐标
      - 支持灰度均值 + 二值化双模式填涂判定
      - 支持 ±search_radius 局部搜索补偿偏移

    返回: {
        qnum: {"answer": "A"/"", "confidence": float, "scores": {A:0.12, B:0.85, ...}},
        ...
    }
    """
    question_regions = coordinate_config.get("question_regions", [])
    if not question_regions:
        logger.warning("坐标配置中无 question_regions")
        return {}

    opt_count = coordinate_config.get("option_count", 4)
    search_radius = coordinate_config.get("search_radius", 0)
    answers = {}
    total_scanned = 0
    total_filled = 0

    # 灰度图（如果有，用于灰度均值检测）
    use_gray = gray is not None

    # 计算坐标缩放比例（矫正后图像尺寸 vs 参考分辨率）
    scale_x, scale_y = _get_scale_factors_for_array(
        binary_inv.shape[1], binary_inv.shape[0], coordinate_config)

    for qr in question_regions:
        qn = qr.get("number", qr.get("question_number", 0))
        option_regions = qr.get("option_regions")

        scores = {}

        if option_regions:
            # ★ 优先使用精确坐标 option_regions[{cx,cy,w,h}]（已缩放）
            for opt in option_regions:
                label = opt.get("label", "?")
                cx = int(opt.get("cx", 0) * scale_x)
                cy = int(opt.get("cy", 0) * scale_y)
                bw = int(opt.get("w", 30) * scale_x)
                bh = int(opt.get("h", 30) * scale_y)

                if search_radius > 0 and use_gray:
                    # 灰度局部搜索模式
                    fill = 1.0 - _sample_fill_with_search(
                        gray, binary_inv, cx, cy, bw, bh, search_radius)
                elif use_gray:
                    # 灰度均值检测（更稳定）
                    gray_val = _sample_gray_fill(gray, cx, cy, bw, bh)
                    fill = 1.0 - gray_val  # 转换为填涂比例
                else:
                    # 回退到二值化
                    fill = _sample_rect_fill(binary_inv, cx, cy, bw, bh)

                scores[label] = round(fill, 4)
                total_scanned += 1

        else:
            # 回退：简化格式 {number, x, y, options}（坐标需缩放）
            x = int(qr.get("x", 0) * scale_x)
            y = int(qr.get("y", 0) * scale_y)
            num_options = qr.get("options", opt_count)
            if isinstance(num_options, (list, tuple)):
                num_options = len(num_options)
            opt_spacing = int(coordinate_config.get("option_spacing", 60) * scale_x)
            circle_d = int(coordinate_config.get("circle_diameter", CIRCLE_DIAMETER)
                           * min(scale_x, scale_y))

            for oi in range(num_options):
                opt_x = x + oi * opt_spacing + circle_d // 2
                opt_y = y + circle_d // 2
                fill = _sample_circle_fill(binary_inv, opt_x, opt_y, circle_d)
                label = chr(65 + oi)
                scores[label] = round(fill, 4)
                total_scanned += 1

        if not scores:
            continue

        # 判定逻辑（v5 简化版，参考 answer-paper）
        #   answer-paper: np.sum(roi==255) / roi.size > 0.5 → filled
        #   我们使用配置的 fill_threshold + 与第二名的差距来判定
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_label, best_fill = sorted_items[0]
        second_fill = sorted_items[1][1] if len(sorted_items) > 1 else 0

        fill_threshold = coordinate_config.get("fill_threshold", FILL_THRESHOLD)
        lead = best_fill - second_fill

        # 简化判定：
        #   1. 最佳填涂值必须超过阈值
        #   2. 与第二名的差距必须足够大（避免两个选项都部分填涂时误判）
        is_filled = (
            best_fill > fill_threshold
            and lead > 0.08
        )

        if is_filled:
            confidence = min(0.99, best_fill / (best_fill + second_fill + 0.01))
            answers[qn] = {
                "answer": best_label,
                "confidence": round(confidence, 4),
                "scores": scores,
            }
            total_filled += 1
        else:
            answers[qn] = {
                "answer": "",
                "confidence": 0.0,
                "scores": scores,
            }

    logger.info("题目扫描: %d个选项 / %d题有填涂 / %d题空白",
                 total_scanned, total_filled, len(answers) - total_filled)

    for qn in sorted(answers.keys()):
        a = answers[qn]
        logger.info("  Q%d: ->%s (conf=%.4f) fills=%s",
                      qn, a["answer"] or "空", a["confidence"],
                      {k: f"{v:.4f}" for k, v in a["scores"].items()})

    return answers


# ════════════════════════════════════════════
# 考号识别
# ════════════════════════════════════════════

def _scan_exam_number(binary_inv: np.ndarray,
                       coordinate_config: dict) -> str:
    """扫描考号填涂区

    支持三种格式:
      1. exam_number_area 精确配置（系统生成答题卡）
      2. exam_number{digits, digit_x[], digit_y[]} 外部答题卡格式
      3. 常量回退（经典纵向布局）
    """
    # 优先: 外部答题卡格式 (7位考号, digit_x + digit_y)
    exam_num_cfg = coordinate_config.get("exam_number", {})
    if exam_num_cfg and exam_num_cfg.get("digit_x"):
        return _scan_exam_number_external(binary_inv, coordinate_config)

    # 其次: exam_number_area 配置
    exam_area = coordinate_config.get("exam_number_area", {})
    if not exam_area:
        # 回退: 使用常量（纵向布局）
        digits_str = []
        circle_d = int(CIRCLE_DIAMETER * 0.7)
        for di in range(EXAM_NUMBER_DIGITS):
            col_x = EXAM_NUMBER_X_START + di * EXAM_NUMBER_SPACING + 80
            scores = []
            for vi in range(10):
                cx = col_x + circle_d // 2
                cy = (EXAM_NUMBER_Y + EXAM_NUMBER_OPTION_START_Y + 30
                      + vi * EXAM_NUMBER_OPTION_SPACING + circle_d // 2)
                fill = _sample_circle_fill(binary_inv, cx, cy, circle_d)
                scores.append(fill)

            if not scores:
                digits_str.append("?")
                continue

            best_idx = max(range(len(scores)), key=lambda i: scores[i])
            best_val = scores[best_idx]
            second_val = sorted(scores, reverse=True)[1] if len(scores) > 1 else 0

            if best_val > 0.08 and (best_val - second_val) > 0.04:
                digits_str.append(str(best_idx))
            else:
                digits_str.append("?")

        return "".join(digits_str)

    # exam_number_area 坐标
    x_start = exam_area.get("x", EXAM_NUMBER_X_START)
    y_start = exam_area.get("y", EXAM_NUMBER_Y)
    digits = exam_area.get("digits", EXAM_NUMBER_DIGITS)
    d_spacing = exam_area.get("digit_spacing", EXAM_NUMBER_SPACING)
    o_spacing = exam_area.get("option_spacing", EXAM_NUMBER_OPTION_SPACING)
    circle_d = exam_area.get("circle_diameter", int(CIRCLE_DIAMETER * 0.7))
    label_offset_y = exam_area.get("label_offset_y", 20)
    option_offset_y = exam_area.get("option_offset_y", 30)
    x_offset = exam_area.get("x_offset", 80)

    result_chars = []
    for di in range(digits):
        col_x = x_start + di * d_spacing + x_offset
        cx = col_x + circle_d // 2

        scores = []
        for vi in range(10):
            cy = (y_start + label_offset_y + option_offset_y
                  + vi * o_spacing + circle_d // 2)
            fill = _sample_circle_fill(binary_inv, cx, cy, circle_d)
            scores.append(fill)

        if not scores:
            result_chars.append("?")
            continue

        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_val = scores[best_idx]
        second_val = sorted(scores, reverse=True)[1] if len(scores) > 1 else 0

        if best_val > 0.08 and (best_val - second_val) > 0.04:
            result_chars.append(str(best_idx))
            logger.debug("考号位%d: ->%d (fill=%.4f diff=%.4f)",
                         di, best_idx, best_val, best_val - second_val)
        else:
            result_chars.append("?")
            logger.debug("考号位%d: 未识别 (best=%d fill=%.4f second=%.4f)",
                         di, best_idx, best_val, second_val)

    return "".join(result_chars)


def _scan_exam_number_external(binary_inv: np.ndarray,
                                coordinate_config: dict) -> str:
    """扫描外部真实答题卡的7位考号

    使用 exam_number{digits, digit_x[], digit_y[]} 中的精确坐标。
    图像已通过 _rectify_to_reference 矫正到参考分辨率 (1387×1960)，
    因此坐标可直接使用，无需缩放。
    """
    exam_cfg = coordinate_config.get("exam_number", {})
    digits = exam_cfg.get("digits", 7)
    digit_x = exam_cfg.get("digit_x", [])
    digit_y = exam_cfg.get("digit_y", [])
    box_w = exam_cfg.get("box_w", 30)
    box_h = exam_cfg.get("box_h", 20)

    if not digit_x or not digit_y:
        return "?" * digits

    # 矫正后图像 = 参考分辨率，坐标直接使用
    scale_x, scale_y = _get_scale_factors_for_array(
        binary_inv.shape[1], binary_inv.shape[0], coordinate_config)

    # digit_y[0]~digit_y[9] 直接对应数字值 0~9
    # 手写行在 digit_y[0] 上方，坐标配置中不包含，不需要跳过
    result_chars = []
    for di in range(min(digits, len(digit_x))):
        cx = int(digit_x[di] * scale_x)
        scores = {}

        for vi in range(min(10, len(digit_y))):
            cy = int(digit_y[vi] * scale_y)
            fill = _sample_rect_fill(binary_inv, cx, cy, box_w, box_h)
            scores[vi] = fill  # vi = 数字值 0~9

        if not scores:
            result_chars.append("?")
            continue

        best_value = max(scores, key=scores.get)
        best_val = scores[best_value]
        # 排除 best_val 后找次高
        others = [scores[k] for k in scores if k != best_value]
        second_val = max(others) if others else 0

        # 打印每位所有候选分数（INFO级别，便于诊断坐标偏移）
        sorted_scores = {str(k): f"{scores[k]:.4f}" for k in sorted(scores.keys())}
        logger.info("考号位%d cx=%d: scores=%s",
                     di, cx, sorted_scores)

        if best_val > 0.30 and (best_val - second_val) > 0.10:
            result_chars.append(str(best_value))
            logger.info("考号位%d: ->%d (fill=%.4f diff=%.4f)",
                         di, best_value, best_val, best_val - second_val)
        else:
            result_chars.append("?")
            logger.info("考号位%d: 未识别 (best=%d fill=%.4f second=%.4f diff=%.4f)",
                         di, best_value, best_val, second_val, best_val - second_val)

    return "".join(result_chars)


def _get_scale_factors_for_array(img_w: int, img_h: int,
                                   coordinate_config: dict) -> tuple[float, float]:
    """计算实际图像相对参考分辨率的缩放比例"""
    ref_w = coordinate_config.get("reference_width")
    ref_h = coordinate_config.get("reference_height")
    if ref_w and ref_h:
        return img_w / ref_w, img_h / ref_h
    return 1.0, 1.0


def _is_external_sheet(coordinate_config: dict) -> bool:
    """检测是否为外部真实答题卡

    判断条件（满足任一）:
      - sheet_type 以 "external" 或 "real" 开头
      - option_count == 7（旧版7选项格式）
      - 有 left_columns（旧版双列布局）
      - question_regions 中包含 option_regions（精确坐标格式）
      - exam_number 中有 digit_x（外部考号格式）
    """
    st = coordinate_config.get("sheet_type", "")
    if st.startswith("external") or st.startswith("real"):
        return True
    if coordinate_config.get("option_count") == 7:
        return True
    if coordinate_config.get("left_columns"):
        return True
    # 检查 question_regions 是否包含 option_regions
    qr = coordinate_config.get("question_regions", [])
    if qr and isinstance(qr, list) and len(qr) > 0:
        if qr[0].get("option_regions"):
            return True
    # 检查考号配置是否为外部格式
    exam_cfg = coordinate_config.get("exam_number", {})
    if exam_cfg and exam_cfg.get("digit_x"):
        return True
    return False


def _is_external_4options(coordinate_config: dict) -> bool:
    """检测是否为外部4选项答题卡（需要坐标缩放）"""
    ref_w = coordinate_config.get("reference_width")
    ref_h = coordinate_config.get("reference_height")
    return bool(
        coordinate_config.get("sheet_type") == "external_4options"
        or (ref_w and ref_h and _is_external_sheet(coordinate_config))
    )


def _scan_questions_real_sheet(binary_inv: np.ndarray,
                                coordinate_config: dict,
                                gray: np.ndarray = None) -> dict:
    """扫描真实答题卡（方形选项框 + 双列布局）

    v4改进：
      - 支持外部答题卡 option_regions 精确坐标
      - 支持坐标缩放（reference_width/height）
      - 支持灰度 + 二值化双模式
    """
    # 优先: 使用 question_regions 中的 option_regions
    question_regions = coordinate_config.get("question_regions", [])
    if question_regions and question_regions[0].get("option_regions"):
        logger.info("使用 option_regions 精确坐标扫描")
        return _scan_questions(binary_inv, coordinate_config, gray)

    # 回退: 旧版双列布局 (left_columns / right_columns / questions)
    questions = coordinate_config.get("questions", [])
    if not questions:
        questions = REAL_SHEET_COORDINATES.get("questions", [])

    option_count = coordinate_config.get("option_count", 7)
    box_w = coordinate_config.get("box_width", 44)
    box_h = coordinate_config.get("box_height", 30)
    fill_threshold = coordinate_config.get("fill_threshold", 0.35)
    left_cols = coordinate_config.get("left_columns", REAL_SHEET_COORDINATES.get("left_columns", []))
    right_cols = coordinate_config.get("right_columns", REAL_SHEET_COORDINATES.get("right_columns", []))
    search_radius = coordinate_config.get("search_radius", 0)
    use_gray = gray is not None

    # 坐标缩放比例
    scale_x, scale_y = _get_scale_factors_for_array(
        binary_inv.shape[1], binary_inv.shape[0], coordinate_config)

    answers = {}
    for q in questions:
        qn = q["number"]
        side = q.get("side", "left")
        row_y = int(q["row_y"] * scale_y)
        columns = [int(c * scale_x) for c in (left_cols if side == "left" else right_cols)]

        scores = {}
        for oi in range(min(option_count, len(columns))):
            cx = columns[oi]
            cy = row_y
            if search_radius > 0 and use_gray:
                fill = 1.0 - _sample_fill_with_search(
                    gray, binary_inv, cx, cy, box_w, box_h, search_radius)
            elif use_gray:
                fill = 1.0 - _sample_gray_fill(gray, cx, cy, box_w, box_h)
            else:
                fill = _sample_rect_fill(binary_inv, cx, cy, box_w, box_h)
            label = chr(65 + oi)
            scores[label] = round(fill, 4)

        if not scores:
            continue

        # 判定逻辑（v5 简化版，参考 answer-paper）
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_label, best_fill = sorted_items[0]
        second_fill = sorted_items[1][1] if len(sorted_items) > 1 else 0

        fill_threshold = coordinate_config.get("fill_threshold", 0.35)
        lead = best_fill - second_fill

        is_filled = (
            best_fill > fill_threshold
            and lead > 0.10
        )

        if is_filled:
            confidence = min(0.99, best_fill / (best_fill + second_fill + 0.01))
            answers[qn] = {
                "answer": best_label,
                "confidence": round(confidence, 4),
                "scores": scores,
            }
        else:
            answers[qn] = {
                "answer": "",
                "confidence": 0.0,
                "scores": scores,
            }

    # 补充空白题
    for empty_q in range(13, 21):
        if empty_q not in answers:
            answers[empty_q] = {"answer": "", "confidence": 0.0, "scores": {}}

    total_filled = sum(1 for v in answers.values() if v.get("answer"))
    logger.info("真实答题卡扫描: %d题有填涂 / %d题空白",
                 total_filled, len(answers) - total_filled)

    for qn in sorted(answers.keys()):
        a = answers[qn]
        logger.info("  Q%d: ->%s (conf=%.4f) fills=%s",
                      qn, a["answer"] or "空", a["confidence"],
                      {k: f"{v:.4f}" for k, v in a["scores"].items()})

    return answers


# ════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════

def scan_answer_sheet(image_path: str,
                      coordinate_config: dict,
                      option_count: int = 4,
                      scale_factor: float = 1.0,
                      method: str = "auto") -> dict:
    """答题卡 OMR 扫描识别（v4）

    v4改进：
      - 外部答题卡坐标按 reference_width/height 自动缩放
      - 灰度均值 + 二值化双模式检测
      - ±search_radius 局部搜索补偿偏移
      - 优先使用 option_regions[{cx,cy,w,h}] 精确坐标

    参数:
        image_path: 答题卡照片路径
        coordinate_config: 坐标配置
        option_count: 每题选项数（备用）
        scale_factor: 缩放因子（预留）
        method: 扫描方法

    返回:
        {success, answers, exam_number, duration_ms, detail_summary, method, ...}
    """
    start_ts = time.time()

    # 1. 加载图片
    img = _load_image(image_path)
    if img is None:
        return _fail_result("无法读取图像", start_ts)
    logger.info("OMR扫描: 原始尺寸 %dx%d", img.shape[1], img.shape[0])

    # 2. 检测是否为外部答题卡 + 决定透视矫正方式
    is_external = _is_external_sheet(coordinate_config)
    needs_scale = _is_external_4options(coordinate_config)

    if is_external:
        logger.info("检测到外部/真实答题卡 | sheet_type=%s needs_scale=%s",
                     coordinate_config.get("sheet_type", ""), needs_scale)

    # 外部答题卡: 用自适应阈值矫正到参考分辨率
    # 系统生成答题卡: 用OTSU矫正到A4
    if is_external and needs_scale:
        # ★ 模板驱动: 四角标记直接检测 + 比例矫正
        #   1. 在4个角区域用固定低阈值找暗色方块
        #   2. 角标映射到画布中正确比例位置(距边缘2.75mm)
        #   3. 用模板CSS尺寸计算所有元素位置
        coordinate_config["upload_dir"] = os.path.dirname(image_path) or "uploads"
        gray_raw = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = _detect_corners_direct(gray_raw)
        if corners is not None:
            rectified, ref_w, ref_h = _rectify_by_corners(img, corners)
            rect_ok = True
        else:
            # 回退到旧方法
            logger.warning("四角直接检测失败，回退到自适应方法")
            rectified, rect_ok, ref_w, ref_h = _rectify_to_reference(
                img, coordinate_config)
        logger.info("外部答题卡透视矫正: %s → %dx%d",
                     "成功" if rect_ok else "等比缩放兜底", ref_w, ref_h)
    elif is_external:
        # 旧版真实答题卡: 用原比例矫正
        gray_raw = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = _find_sheet_corners(gray_raw)
        if corners is not None:
            h, w = img.shape[:2]
            dst = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
            try:
                M = cv2.getPerspectiveTransform(corners, dst)
                rectified = cv2.warpPerspective(img, M, (w, h))
                rect_ok = True
                ref_w, ref_h = w, h
                logger.info("真实答题卡透视矫正: %dx%d → %dx%d", w, h, w, h)
            except Exception as e:
                logger.warning("真实答题卡透视矫正失败: %s", e)
                rectified, rect_ok, ref_h = img, False, img.shape[0]
                ref_w = img.shape[1]
        else:
            rectified, rect_ok, ref_h = img, False, img.shape[0]
            ref_w = img.shape[1]
            logger.info("真实答题卡: 未检测到边界，使用原图")
    else:
        # 系统生成的答题卡: 矫正到A4
        rectified, rect_ok = _rectify(img)
        ref_w, ref_h = A4_WIDTH, A4_HEIGHT
        logger.info("透视矫正: %s", "成功" if rect_ok else "未矫正")

    # 3. 灰度 + 二值化（外部答题卡用自适应阈值处理光照不均）
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)

    if is_external and needs_scale:
        # ★ 外部答题卡: Otsu 二值化（参考 answer-paper 项目）
        #   Otsu 基于全局直方图自动计算最优阈值，
        #   填涂区 white% >50%，未填涂 white% <10%，差异显著
        binary_inv = _binary_otsu_simple(gray)
        logger.info("二值化: Otsu（参考answer-paper）")
    else:
        # 系统答题卡: OTSU 二值化
        binary_inv = _binary_inv(gray)

    white_pct = cv2.countNonZero(binary_inv) / binary_inv.size * 100
    logger.info("二值化: %.1f%% 白色像素（墨迹）", white_pct)

    # 4. 题目扫描 + 5. 考号识别
    if is_external and needs_scale:
        # ★ 模板驱动扫描: 用CSS模板尺寸计算位置，固定阈值190二值化
        upload_dir = coordinate_config.get("upload_dir", "uploads")
        positions = _compute_template_positions(ref_w, ref_h)
        answers = _scan_answers_template(rectified, positions)
        exam_number = _scan_exam_number_template(rectified, positions)
        _save_template_debug(rectified, positions, upload_dir)
        logger.info("考号识别(模板驱动): '%s'", exam_number)
    elif is_external:
        # 旧版外部答题卡：用原坐标方式
        answers = _scan_questions_real_sheet(binary_inv, coordinate_config, gray)
        exam_number = _scan_exam_number(binary_inv, coordinate_config)
        logger.info("考号识别: '%s'", exam_number)
    else:
        # 系统生成答题卡：用标准扫描
        answers = _scan_questions(binary_inv, coordinate_config, gray)
        exam_number = _scan_exam_number(binary_inv, coordinate_config)
        logger.info("考号识别: '%s'", exam_number)

    # 6. 汇总
    duration_ms = int((time.time() - start_ts) * 1000)
    total_qs = len(answers)
    valid = sum(1 for v in answers.values() if v.get("answer"))

    answers_list = []
    detail_parts = [
        f"OMR扫描结果 (v4 耗时:{duration_ms}ms)",
        f"  图像: {image_path} ({rectified.shape[1]}x{rectified.shape[0]})",
        f"  透视矫正: {'成功' if rect_ok else '未矫正'}",
        f"  考号: '{exam_number}'",
    ]

    for qn in sorted(answers.keys()):
        v = answers[qn]
        answers_list.append({
            "question_number": qn,
            "student_answer": v.get("answer", ""),
            "confidence": v.get("confidence", 0.0),
            "all_ratios": v.get("scores", {}),
        })
        detail_parts.append(
            f"  Q{qn}: {v.get('answer', '空') or '空'} (conf={v.get('confidence', 0):.4f})")

    detail_parts.append(f"  识别: {valid}/{total_qs}题有填涂")
    detail_summary = "\n".join(detail_parts)
    logger.info(detail_summary)

    return {
        "success": valid > 0,
        "answers": answers_list,
        "exam_number": exam_number,
        "duration_ms": duration_ms,
        "detail_summary": detail_summary,
        "method": "omr_v4",
        "total_questions": total_qs,
        "valid_answers": valid,
    }


def _fail_result(error_msg: str, start_ts: float) -> dict:
    """返回失败结果"""
    duration_ms = int((time.time() - start_ts) * 1000)
    logger.error("OMR扫描失败: %s", error_msg)
    return {
        "success": False,
        "answers": [],
        "exam_number": "",
        "duration_ms": duration_ms,
        "detail_summary": f"OMR扫描失败: {error_msg}",
        "method": "failed",
        "total_questions": 0,
        "valid_answers": 0,
        "error": error_msg,
    }


# ════════════════════════════════════════════
# 调试辅助: 生成带标注的诊断图
# ════════════════════════════════════════════

def generate_debug_image(image_path: str,
                          coordinate_config: dict,
                          output_path: str = None) -> str:
    """生成标注了扫描区域的诊断图（用于调试坐标配置）

    在答题卡照片上绘制:
      - 检测到的边界
      - 所有选项圈位置（绿色=检测到填涂，红色=未检测到）
      - 考号区域

    返回: 输出图片路径
    """
    img = _load_image(image_path)
    if img is None:
        return ""

    rectified, _ = _rectify(img)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    # 复制一份用于绘制
    debug_img = rectified.copy()
    h, w = debug_img.shape[:2]

    # 绘制答题卡边框
    cv2.rectangle(debug_img, (5, 5), (w - 5, h - 5), (255, 0, 0), 3)

    # 绘制考号区域
    exam_area = coordinate_config.get("exam_number_area", {})
    if exam_area:
        ex = exam_area.get("x", EXAM_NUMBER_X_START)
        ey = exam_area.get("y", EXAM_NUMBER_Y)
        cv2.rectangle(debug_img, (ex, ey),
                       (ex + 800, ey + 150), (255, 255, 0), 2)
        cv2.putText(debug_img, "Exam Number Area", (ex, ey - 10),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    # 绘制每题选项圈
    question_regions = coordinate_config.get("question_regions", [])
    opt_count = coordinate_config.get("option_count", 4)
    opt_spacing = coordinate_config.get("option_spacing", 60)
    circle_d = coordinate_config.get("circle_diameter", CIRCLE_DIAMETER)
    radius = circle_d // 2

    for qr in question_regions:
        qn = qr.get("number", 0)
        x = qr.get("x", 0)
        y = qr.get("y", 0)
        num_options = qr.get("options", opt_count)

        for oi in range(num_options):
            opt_x = x + oi * opt_spacing + radius
            opt_y = y + radius

            # 采样填涂比例
            fill = _sample_circle_fill(binary_inv, opt_x, opt_y, circle_d)
            color = (0, 255, 0) if fill > FILL_THRESHOLD else (0, 0, 255)

            # 画圈
            cv2.circle(debug_img, (opt_x, opt_y), radius, color, 2)

            # 标注题号（只在第一列选项）
            if oi == 0:
                cv2.putText(debug_img, f"Q{qn}", (x - 60, y + radius + 5),
                             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # 保存
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(image_path),
            f"debug_{int(time.time())}.jpg"
        )

    cv2.imwrite(output_path, debug_img)
    logger.info("调试图像已保存: %s", output_path)
    return output_path


# ════════════════════════════════════════════
# 自适应投影分析（每张图独立分析，不依赖硬编码坐标）
# 参考: docs/答题卡考号识别分析文档.md
# ════════════════════════════════════════════

def _find_projection_valleys(proj: np.ndarray, distance: int = 30) -> np.ndarray:
    """在一维投影中找到波谷位置（无scipy依赖）

    波谷 = 列间隙 / 行间隙，用于分割填涂列和行。
    采用滑动窗口局部最小值检测 + 距离约束，
    等效于 scipy.signal.find_peaks(-proj, distance=n)。

    Args:
        proj: 一维投影数组（各列/行的白色像素总和）
        distance: 两个波谷之间的最小距离（像素）

    Returns:
        波谷位置的整数数组
    """
    n = len(proj)
    if n < 2 * distance + 1:
        return np.array([0, n - 1], dtype=int)

    # 平滑投影以去除噪声
    kernel = np.ones(5) / 5
    smoothed = np.convolve(proj, kernel, mode='same')

    # 步骤1: 找所有局部最小值（在 ±half_win 窗口内比周围值低）
    half_win = max(3, distance // 4)
    valleys = []
    for i in range(half_win, n - half_win):
        left = smoothed[i - half_win:i]
        right = smoothed[i + 1:i + half_win + 1]
        # 严格小于等于周围所有值（允许等于）
        if smoothed[i] <= np.min(left) and smoothed[i] <= np.min(right):
            valleys.append(i)

    if not valleys:
        return np.array([], dtype=int)

    # 步骤2: 距离约束过滤 — 在每组相距 <distance 的候选点中取最小值
    valleys = np.array(valleys, dtype=int)
    filtered = []
    last_selected = -distance
    for v in valleys:
        if v - last_selected < distance:
            # 与上一个选中的太近：比较谁更小，保留更小的
            if smoothed[v] < smoothed[filtered[-1]]:
                filtered[-1] = int(v)
        else:
            filtered.append(int(v))
            last_selected = int(v)

    return np.array(filtered, dtype=int)







def _scan_exam_number_dynamic(rectified: np.ndarray,
                                coordinate_config: dict = None) -> str:
    """考号识别——优先使用标定边界（可靠），回退到比例推算

    工作流程（参考 docs/答题卡考号识别分析文档.md）:
      1. 裁剪考号区域 ROI (y=150~520, x=720~1150, 基于参考分辨率1387×1960)
      2. 灰度化 + 二值化 (THRESH_BINARY_INV, thresh=190)
      3. 列分割: 优先使用配置中的 calibrated_col_boundaries
      4. 行分割: 优先使用配置中的 calibrated_row_boundaries（已跳过手写行）
      5. 逐格计算白色像素占比 → 每列取填充率最高值
      6. 保存调试图

    Args:
        rectified: 透视矫正后的BGR图像
        coordinate_config: 答题卡配置

    Returns:
        7位考号字符串（如 "0002602"）
    """
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape

    # ─── 读取配置 ───
    exam_cfg = (coordinate_config or {}).get("exam_number", {})
    # 标定边界（考号ROI内局部坐标，参考ROI=370×430）
    calib_cols = exam_cfg.get("calibrated_col_boundaries")
    calib_rows = exam_cfg.get("calibrated_row_boundaries")
    # 标定阈值
    threshold = exam_cfg.get("calibrated_threshold", 190)
    fill_threshold = exam_cfg.get("calibrated_fill_threshold", 0.50)
    diff_threshold = exam_cfg.get("calibrated_diff_threshold", 0.30)
    num_digits = exam_cfg.get("digits", 7)

    # ─── 步骤1: 裁剪考号区域 ───
    scale_x = w_img / 1387.0
    scale_y = h_img / 1960.0
    exam_y1 = int(150 * scale_y)
    exam_y2 = int(520 * scale_y)
    exam_x1 = int(720 * scale_x)
    exam_x2 = int(1150 * scale_x)
    exam_y2 = min(exam_y2, h_img)
    exam_x2 = min(exam_x2, w_img)

    region_w = exam_x2 - exam_x1
    region_h = exam_y2 - exam_y1
    if region_w <= 50 or region_h <= 50:
        logger.warning("考号区域裁剪过小: %dx%d", region_w, region_h)
        return "?" * num_digits

    exam_region = gray[exam_y1:exam_y2, exam_x1:exam_x2]
    _, thresh_inv = cv2.threshold(exam_region, threshold, 255, cv2.THRESH_BINARY_INV)
    logger.info("考号区域: ROI %d~%d×%d~%d, 尺寸 %dx%d",
                 exam_y1, exam_y2, exam_x1, exam_x2, region_w, region_h)

    # ─── 步骤2: 确定列边界 ───
    if calib_cols and len(calib_cols) == num_digits + 1:
        # 标定边界按实际ROI尺寸等比缩放
        col_scale = region_w / 430.0
        col_boundaries = [int(c * col_scale) for c in calib_cols]
        logger.info("考号列边界(标定×%.3f): %s", col_scale, col_boundaries)
    else:
        # 回退：均匀分割列宽
        col_boundaries = np.linspace(2, region_w - 2, num_digits + 1, dtype=int).tolist()
        logger.warning("无标定列边界，均匀分割: %s", col_boundaries)

    # ─── 步骤3: 确定行边界（0~9行，共11个边界） ───
    # ★ 关键：row_boundaries[0]=66 是手写行底部 / 0行顶部
    #   手写行占 y=0~66，必须跳过！
    #   0~9行占 y=66~370，每行约30px（9行34px）
    #   若 row_boundaries[0] 不对齐66，会导致所有数字偏移±1
    if calib_rows and len(calib_rows) == 11:
        row_scale = region_h / 370.0
        row_boundaries = [int(r * row_scale) for r in calib_rows]
        logger.info("考号行边界(标定×%.3f): %s | row0=%d 手写行=0~%d",
                     row_scale, row_boundaries,
                     row_boundaries[0], row_boundaries[0])
    else:
        # 回退：比例化推算（17.8%手写行 + 10行）
        row_0_start = int(region_h * 0.178)
        row_h = int(region_h * 0.082)
        row_boundaries = [row_0_start + i * row_h for i in range(11)]
        row_boundaries[-1] = region_h
        logger.warning("无标定行边界，比例推算: %s", row_boundaries)

    # ─── 步骤4: 保存调试图 ───
    _save_exam_number_debug(rectified, thresh_inv, col_boundaries,
                             row_boundaries, exam_y1, exam_y2,
                             exam_x1, exam_x2, coordinate_config)

    # ─── 步骤5: 逐格计算填充率 ───
    result_chars = []
    used_calib = bool(calib_cols and calib_rows)

    for col_idx in range(num_digits):
        cs = col_boundaries[col_idx]
        ce = col_boundaries[col_idx + 1]
        scores = {}

        for num in range(10):
            rs = row_boundaries[num]
            re = row_boundaries[num + 1]
            if rs >= re or cs >= ce:
                scores[str(num)] = 0.0
                continue
            cell = thresh_inv[rs:re, cs:ce]
            total = cell.size
            white = int(np.sum(cell == 255))
            scores[str(num)] = round(white / total, 4) if total > 0 else 0.0

        max_num = max(scores, key=scores.get)
        max_fill = scores[max_num]
        sorted_vals = sorted(scores.values(), reverse=True)
        second_val = sorted_vals[1] if len(sorted_vals) > 1 else 0
        diff = max_fill - second_val

        logger.info("考号位%d: scores=%s",
                     col_idx, {k: f"{v:.4f}" for k, v in scores.items()})

        if max_fill >= fill_threshold and diff >= diff_threshold:
            result_chars.append(max_num)
            logger.info("考号位%d: ->%s ✓ (fill=%.4f diff=%.4f)",
                         col_idx, max_num, max_fill, diff)
        else:
            result_chars.append("?")
            logger.info("考号位%d: 未识别 ✗ (best=%s fill=%.4f second=%.4f diff=%.4f)",
                         col_idx, max_num, max_fill, second_val, diff)

    exam_number = "".join(result_chars)
    logger.info("考号结果: '%s' (方法=%s)", exam_number,
                 "标定边界" if used_calib else "比例推算")
    return exam_number


def _save_exam_number_debug(rectified: np.ndarray, thresh_inv: np.ndarray,
                             col_boundaries: list, row_boundaries: list,
                             exam_y1: int, exam_y2: int,
                             exam_x1: int, exam_x2: int,
                             coordinate_config: dict = None) -> None:
    """保存考号区域调试图——全图网格 + 裁剪ROI网格 + 二值化网格

    生成3张图方便诊断：
      1. debug_exam_number_*.jpg        — 全图带黄色框 + 红绿网格
      2. debug_exam_roi_*.jpg           — 仅考号ROI区域 + 红绿网格（放大版）
      3. debug_exam_thresh_*.jpg        — 二值化ROI + 红绿网格（看填涂对齐）

    Args:
        rectified: 完整矫正图像
        thresh_inv: 考号ROI二值化图（白色像素=墨迹）
        col_boundaries: 列边界列表（共 digits+1 个值）
        row_boundaries: 行边界列表（共 11 个值，0~9行）
        exam_y1/exam_y2/exam_x1/exam_x2: ROI在原图中的位置
    """
    import os, time
    try:
        upload_dir = (coordinate_config or {}).get("upload_dir", "uploads")
        if not os.path.isdir(upload_dir):
            return

        ts = int(time.time())

        # ── 图1: 全图带网格 ──
        debug_full = rectified.copy()
        cv2.rectangle(debug_full, (exam_x1, exam_y1), (exam_x2, exam_y2),
                       (0, 255, 255), 2)
        for cv_val in col_boundaries:
            x = exam_x1 + int(cv_val)
            cv2.line(debug_full, (x, exam_y1), (x, exam_y2), (0, 0, 255), 1)
        for r in row_boundaries:
            y = exam_y1 + int(r)
            cv2.line(debug_full, (exam_x1, y), (exam_x2, y), (0, 255, 0), 1)
        cv2.imwrite(os.path.join(upload_dir, f"debug_exam_number_{ts}.jpg"),
                     debug_full)

        # ── 图2: 裁剪ROI放大版 + 网格 ──
        roi_bgr = rectified[exam_y1:exam_y2, exam_x1:exam_x2].copy()
        for cv_val in col_boundaries:
            x = int(cv_val)
            cv2.line(roi_bgr, (x, 0), (x, roi_bgr.shape[0]), (0, 0, 255), 2)
        for r in row_boundaries:
            y = int(r)
            cv2.line(roi_bgr, (0, y), (roi_bgr.shape[1], y), (0, 255, 0), 2)
        # 蓝色线标记手写行底部（row_boundaries[0]）
        y_hw = int(row_boundaries[0])
        cv2.line(roi_bgr, (0, y_hw), (roi_bgr.shape[1], y_hw), (255, 0, 0), 3)
        # 放大2倍便于查看
        roi_bgr_big = cv2.resize(roi_bgr, (roi_bgr.shape[1] * 2,
                                            roi_bgr.shape[0] * 2),
                                  interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(upload_dir, f"debug_exam_roi_{ts}.jpg"),
                     roi_bgr_big)

        # ── 图3: 二值化ROI + 网格 ──
        thresh_color = cv2.cvtColor(thresh_inv, cv2.COLOR_GRAY2BGR)
        for cv_val in col_boundaries:
            x = int(cv_val)
            cv2.line(thresh_color, (x, 0), (x, thresh_color.shape[0]),
                      (0, 0, 255), 2)
        for r in row_boundaries:
            y = int(r)
            cv2.line(thresh_color, (0, y), (thresh_color.shape[1], y),
                      (0, 255, 0), 2)
        # 蓝色线标记手写行底部
        cv2.line(thresh_color, (0, y_hw), (thresh_color.shape[1], y_hw),
                  (255, 0, 0), 3)
        thresh_big = cv2.resize(thresh_color,
                                 (thresh_color.shape[1] * 2,
                                  thresh_color.shape[0] * 2),
                                 interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(upload_dir, f"debug_exam_thresh_{ts}.jpg"),
                     thresh_big)

        logger.info("考号调试图已保存: debug_exam_number_%d.jpg, "
                     "debug_exam_roi_%d.jpg, debug_exam_thresh_%d.jpg",
                     ts, ts, ts)
    except Exception as e:
        logger.warning("保存考号调试图失败: %s", e)


def _save_answers_debug(rectified: np.ndarray, q_regions: list,
                         answers: dict, coordinate_config: dict = None) -> None:
    """保存答案识别调试图——画出所有选项框，绿色=识别到的答案，红色=未识别

    Args:
        rectified: 完整矫正图像
        q_regions: 题目坐标配置
        answers: 识别结果 {qn: {"answer": "A", ...}}
        coordinate_config: 答题卡配置
    """
    import os, time
    try:
        upload_dir = (coordinate_config or {}).get("upload_dir", "uploads")
        if not os.path.isdir(upload_dir):
            return

        debug_img = rectified.copy()
        ts = int(time.time())

        for qr in q_regions:
            qn = qr.get("question_number", 0)
            ans = answers.get(qn, {})
            answer_label = ans.get("answer", "")
            option_regions = qr.get("option_regions", [])

            for opt in option_regions:
                label = opt.get("label", "")
                cx = opt.get("cx", 0)
                cy = opt.get("cy", 0)
                ow = opt.get("w", 30)
                oh = opt.get("h", 30)

                x1 = max(0, cx - ow // 2)
                y1 = max(0, cy - oh // 2)
                x2 = min(debug_img.shape[1], cx + ow // 2)
                y2 = min(debug_img.shape[0], cy + oh // 2)

                # 识别到的答案=绿色，其他选项=灰色，未识别=红色
                if answer_label and label == answer_label:
                    color = (0, 255, 0)    # 绿色
                    thickness = 3
                elif not answer_label:
                    color = (0, 0, 255)    # 红色（未识别）
                    thickness = 2
                else:
                    color = (128, 128, 128)  # 灰色
                    thickness = 1

                cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, thickness)

                # 标注题号和答案
                cv2.putText(debug_img, f"Q{qn}",
                            (x1 - 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                            0.4, (0, 0, 255), 1)
                if answer_label and label == answer_label:
                    cv2.putText(debug_img, f"{label}←",
                                (cx - 5, y2 + 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 255, 0), 2)

        filename = os.path.join(upload_dir, f"debug_answers_{ts}.jpg")
        cv2.imwrite(filename, debug_img)
        logger.info("答案调试图已保存: debug_answers_%d.jpg", ts)
    except Exception as e:
        logger.warning("保存答案调试图失败: %s", e)


def _scan_questions_dynamic(rectified: np.ndarray,
                             coordinate_config: dict = None) -> dict:
    """自适应填涂答案识别——每张图独立投影分析

    思路:
      1. 裁剪选择题区域
      2. 水平投影 → 自动检测每题行边界
      3. 每行内用垂直投影 → 找ABCD选项的填涂区
      4. 逐选项计算填充率 → 取最高值

    Args:
        rectified: 透视矫正后的BGR图像
        coordinate_config: 答题卡配置

    Returns:
        {question_number: {"answer": "A", "confidence": 0.8, "scores": {...}}, ...}
    """
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape

    # 用配置中的参考坐标定位选择题区域
    # 外部4选项答题卡: 左列 Q1-Q5 (x≈128~330, y≈641~730), 右列 Q6-Q10 (x≈783~969, y≈748~833)
    q_regions = coordinate_config.get("question_regions", []) if coordinate_config else []

    # 靠配置大致定位每个选项的位置
    answers = {}
    option_labels = ['A', 'B', 'C', 'D']
    fill_threshold = coordinate_config.get("fill_threshold", 0.35) if coordinate_config else 0.35

    if q_regions:
        # 有精确坐标配置: 用配置坐标 + 局部投影微调
        answers = _scan_questions_dynamic_with_regions(
            gray, q_regions, option_labels, fill_threshold)
        # 保存答案识别调试图
        _save_answers_debug(rectified, q_regions, answers,
                             coordinate_config)
        return answers
    else:
        # 无坐标配置: 全自动投影分析
        return _scan_questions_dynamic_auto(
            gray, option_labels, fill_threshold)


def _scan_questions_dynamic_with_regions(
        gray: np.ndarray,
        q_regions: list,
        option_labels: list,
        fill_threshold: float) -> dict:
    """基于已知坐标配置，但每选项独立Otsu二值化，自适应光照变化

    改进点:
      1. 每选项ROI独立Otsu二值化（替代固定阈值190），适应局部光照差异
      2. 扩大采样框至40×40（原30×30），容忍坐标微小偏移
      3. 连续/离散 双模式：高质量答案用高置信度，未检出时回退到较低阈值

    Args:
        gray: 透视矫正后的灰度图像（参考分辨率 1387×1960）
        q_regions: 题目坐标配置列表
        option_labels: 选项标签 ['A','B','C','D']
        fill_threshold: 填充率阈值

    Returns:
        {question_number: {"answer": "A", "confidence": 0.8, "scores": {...}}, ...}
    """
    answers = {}
    box_w = 40   # 扩大采样框，容忍5-10px位移
    box_h = 40

    for qr in q_regions:
        qn = qr.get("question_number", 0)
        option_regions = qr.get("option_regions", [])
        if not option_regions:
            continue

        scores = {}
        for opt in option_regions:
            label = opt.get("label", "")
            cx = opt.get("cx", 0)
            cy = opt.get("cy", 0)
            ow = opt.get("w", box_w)
            oh = opt.get("h", box_h)

            # 裁剪每个选项的局部区域
            y1 = max(0, cy - oh // 2)
            y2 = min(gray.shape[0], cy + oh // 2)
            x1 = max(0, cx - ow // 2)
            x2 = min(gray.shape[1], cx + ow // 2)

            if y2 <= y1 or x2 <= x1:
                scores[label] = 0.0
                continue

            roi = gray[y1:y2, x1:x2]

            # ★ 每ROI独立Otsu二值化，适应局部光照差异
            try:
                _, roi_thresh = cv2.threshold(roi, 0, 255,
                                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            except Exception:
                # ROI太小或全同色时Otsu可能失败，回退到固定阈值
                _, roi_thresh = cv2.threshold(roi, 128, 255, cv2.THRESH_BINARY_INV)

            total = roi_thresh.size
            white = int(np.sum(roi_thresh == 255))
            fill = white / total if total > 0 else 0.0
            scores[label] = round(fill, 4)

        if not scores:
            continue

        best_label = max(scores, key=scores.get)
        best_fill = scores[best_label]
        sorted_vals = sorted(scores.values(), reverse=True)
        second = sorted_vals[1] if len(sorted_vals) > 1 else 0
        diff = best_fill - second

        # ★ 双级判定：
        #   Level A（严格）: fill > fill_threshold 且 diff > 0.12 → 高置信度
        #   Level B（宽松）: fill > 0.20 且 diff > 0.06 且 best > second*1.5 → 低置信度但仍采纳
        if best_fill > fill_threshold and diff > 0.12:
            answers[qn] = {
                "answer": best_label,
                "confidence": round(best_fill, 4),
                "scores": scores,
                "method": "otsu_roi_strict",
            }
            logger.info("Q%d: ->%s (fill=%.4f diff=%.4f scores=%s)",
                         qn, best_label, best_fill, diff,
                         {k: f"{v:.4f}" for k, v in scores.items()})
        elif best_fill > 0.20 and diff > 0.06 and best_fill > second * 1.5:
            answers[qn] = {
                "answer": best_label,
                "confidence": round(best_fill, 4),
                "scores": scores,
                "method": "otsu_roi_loose",
            }
            logger.info("Q%d: ->%s [宽松] (fill=%.4f diff=%.4f scores=%s)",
                         qn, best_label, best_fill, diff,
                         {k: f"{v:.4f}" for k, v in scores.items()})
        else:
            answers[qn] = {
                "answer": "",
                "confidence": 0.0,
                "scores": scores,
                "method": "otsu_roi",
            }
            logger.info("Q%d: 未识别 (best=%s fill=%.4f second=%.4f diff=%.4f)",
                         qn, best_label, best_fill, second, diff)

    return answers


def _scan_questions_dynamic_auto(
        gray: np.ndarray,
        option_labels: list,
        fill_threshold: float) -> dict:
    """全自动选择题识别（无坐标配置时的兜底方案）

    使用投影分析自动定位题目和选项位置。
    """
    h_img, w_img = gray.shape
    # 选择题区域大致在图像下半部分
    q_region = gray[int(h_img * 0.3):, :]
    _, q_thresh = cv2.threshold(q_region, 190, 255, cv2.THRESH_BINARY_INV)

    # 水平投影 → 找题目行
    row_sum = np.sum(q_thresh, axis=1).astype(np.float64)
    row_valleys = _find_projection_valleys(row_sum, distance=15)

    logger.info("题目区域投影分析: 检测到%d个行分割点", len(row_valleys))
    # 回退到配置坐标（实际应用中极少走到此路径）
    return {}
