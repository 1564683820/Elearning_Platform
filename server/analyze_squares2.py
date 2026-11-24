"""精确分析真实答题卡的方块布局 - 第二版

改进：
  1. 按尺寸精确过滤选项框（去除文字、边框噪声）
  2. 去重（同一位置多个检测）
  3. 识别题目网格和考号区
  4. 采样填涂比例，验证识别结果
"""

import sys
import os
import cv2
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.omr_scanner import _load_image, _rectify, _binary_inv
from app.services.printable_sheet_constants import A4_WIDTH, A4_HEIGHT

IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'tests', 'exam.jpg')

# 预期答案
EXPECTED = {
    'exam_number': '0002603',
    'answers': {
        1: 'B', 2: 'C', 3: 'B', 4: 'C', 5: 'B',
        6: 'B', 7: 'C', 8: 'B', 9: 'C', 10: 'C',
        11: 'A', 12: 'D',
        21: 'E', 22: 'G', 23: 'D', 24: 'F', 25: 'C',
    }
}


def detect_squares_filtered(binary_inv, min_w=25, max_w=55, min_h=25, max_h=55):
    """检测方形选项框，按尺寸精确过滤"""
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    raw = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < min_w or w > max_w:
            continue
        if h < min_h or h > max_h:
            continue
        aspect = w / max(h, 1)
        if aspect < 0.7 or aspect > 1.4:
            continue
        area = cv2.contourArea(cnt)
        rect_area = w * h
        fill_ratio = area / max(rect_area, 1)
        if fill_ratio < 0.3:  # 轮廓填充率太低，可能是噪声
            continue
        cx = x + w // 2
        cy = y + h // 2
        raw.append((cx, cy, w, h, x, y))

    # 去重：同一位置(±15px)只保留一个
    deduped = []
    for s in raw:
        cx, cy = s[0], s[1]
        is_dup = False
        for d in deduped:
            if abs(cx - d[0]) < 15 and abs(cy - d[1]) < 15:
                is_dup = True
                break
        if not is_dup:
            deduped.append(s)

    return deduped


def sample_rect_fill(binary_inv, cx, cy, w, h):
    """方形ROI填涂比例"""
    H, W = binary_inv.shape[:2]
    x1 = max(0, cx - w // 2)
    y1 = max(0, cy - h // 2)
    x2 = min(W, cx + w // 2)
    y2 = min(H, cy + h // 2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = binary_inv[y1:y2, x1:x2]
    return cv2.countNonZero(roi) / max(roi.size, 1)


def cluster_rows(squares, tol=50):
    """按Y聚类成行"""
    if not squares:
        return []
    sorted_sq = sorted(squares, key=lambda s: s[1])
    rows = []
    current_row = [sorted_sq[0]]
    current_y = sorted_sq[0][1]
    for sq in sorted_sq[1:]:
        if abs(sq[1] - current_y) <= tol:
            current_row.append(sq)
            current_y = np.mean([s[1] for s in current_row])
        else:
            rows.append(current_row)
            current_row = [sq]
            current_y = sq[1]
    rows.append(current_row)
    return rows


def main():
    img = _load_image(IMAGE_PATH)
    if img is None:
        print(f"无法读取图像: {IMAGE_PATH}")
        return

    rectified, ok = _rectify(img)
    print(f"透视矫正: {'成功' if ok else '未矫正'}, 尺寸: {rectified.shape[1]}x{rectified.shape[0]}")

    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    # 检测方块
    squares = detect_squares_filtered(binary_inv)
    print(f"\n检测到 {len(squares)} 个方块（过滤后）")

    if len(squares) < 10:
        print("方块太少，尝试更宽的尺寸范围...")
        squares = detect_squares_filtered(binary_inv, min_w=20, max_w=65, min_h=20, max_h=65)
        print(f"放宽后: {len(squares)} 个方块")

    # 尺寸统计
    if squares:
        ws = [s[2] for s in squares]
        hs = [s[3] for s in squares]
        print(f"宽度: min={min(ws)}, max={max(ws)}, avg={np.mean(ws):.0f}, median={np.median(ws):.0f}")
        print(f"高度: min={min(hs)}, max={max(hs)}, avg={np.mean(hs):.0f}, median={np.median(hs):.0f}")

    # 按Y聚类
    rows = cluster_rows(squares, tol=50)
    print(f"\n=== 按Y聚类: {len(rows)} 行 ===")

    # 分析每行
    for i, row in enumerate(rows):
        avg_y = np.mean([s[1] for s in row])
        row_sorted = sorted(row, key=lambda s: s[0])
        xs = [s[0] for s in row_sorted]
        x_gaps = [xs[j+1] - xs[j] for j in range(len(xs)-1)] if len(xs) > 1 else []

        # 采样填涂比例
        fills = []
        for s in row_sorted:
            f = sample_rect_fill(binary_inv, s[0], s[1], s[2], s[3])
            fills.append(f)

        filled_count = sum(1 for f in fills if f > 0.15)

        print(f"\n行{i}: Y={avg_y:.0f}, {len(row)}个方块, X={xs[0]}~{xs[-1]}, 填涂={filled_count}")
        if x_gaps:
            # 检测间距模式
            unique_gaps = sorted(set(g // 10 * 10 for g in x_gaps))
            print(f"  X间距: {x_gaps[:10]}... (去量化: {unique_gaps[:5]})")

        # 打印每个方块的详情
        for j, s in enumerate(row_sorted):
            f = fills[j]
            marker = "★" if f > 0.15 else " "
            print(f"  {marker} X={s[0]:4d} Y={s[1]:4d} {s[2]}x{s[3]} fill={f:.4f}")

    # 生成诊断图（标注填涂状态）
    debug_img = rectified.copy()
    for s in squares:
        cx, cy, w, h = s[0], s[1], s[2], s[3]
        f = sample_rect_fill(binary_inv, cx, cy, w, h)
        color = (0, 0, 255) if f > 0.15 else (0, 255, 0)  # 红=填涂, 绿=空白
        cv2.rectangle(debug_img, (cx - w//2, cy - h//2), (cx + w//2, cy + h//2), color, 2)
        if f > 0.15:
            cv2.putText(debug_img, f"{f:.2f}", (cx - 15, cy - h//2 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    debug_path = os.path.join(os.path.dirname(__file__), 'debug_squares2.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\n诊断图: {debug_path}")


if __name__ == '__main__':
    main()
