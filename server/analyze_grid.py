"""网格线检测 - 用 HoughLinesP 检测答题卡的横竖网格线

策略：
  1. 透视矫正
  2. 二值化 + 形态学提取横线/竖线
  3. HoughLinesP 检测线段
  4. 聚类线段 → 网格
  5. 在网格交叉点采样填涂比例
"""

import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.omr_scanner import _load_image, _rectify, _binary_inv
from app.services.printable_sheet_constants import A4_WIDTH, A4_HEIGHT

IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'tests', 'exam.jpg')

EXPECTED = {
    'exam_number': '0002603',
    'answers': {
        1: 'B', 2: 'C', 3: 'B', 4: 'C', 5: 'B',
        6: 'B', 7: 'C', 8: 'B', 9: 'C', 10: 'C',
        11: 'A', 12: 'D',
        21: 'E', 22: 'G', 23: 'D', 24: 'F', 25: 'C',
    }
}


def detect_lines(binary_inv, direction='horizontal', min_length=80):
    """检测水平或垂直线段"""
    if direction == 'horizontal':
        kernel_size = (40, 1)
    else:
        kernel_size = (1, 40)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
    detected = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, kernel)

    lines = cv2.HoughLinesP(
        detected, 1, np.pi / 180,
        threshold=30,
        minLineLength=min_length,
        maxLineGap=10
    )

    result = []
    if lines is not None:
        for line in lines:
            line = line.flatten()
            x1, y1, x2, y2 = int(line[0]), int(line[1]), int(line[2]), int(line[3])
            if direction == 'horizontal':
                result.append((y1 + y2) // 2)
            else:
                result.append((x1 + x2) // 2)

    return sorted(result)


def cluster_positions(positions, tol=20):
    """聚类相近的位置"""
    if not positions:
        return []
    sorted_pos = sorted(positions)
    clusters = []
    current = [sorted_pos[0]]
    for p in sorted_pos[1:]:
        if p - current[-1] <= tol:
            current.append(p)
        else:
            clusters.append(int(np.mean(current)))
            current = [p]
    clusters.append(int(np.mean(current)))
    return clusters


def sample_fill(binary_inv, cx, cy, w, h):
    """采样矩形区域填涂比例"""
    H, W = binary_inv.shape[:2]
    x1 = max(0, cx - w // 2)
    y1 = max(0, cy - h // 2)
    x2 = min(W, cx + w // 2)
    y2 = min(H, cy + h // 2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = binary_inv[y1:y2, x1:x2]
    return cv2.countNonZero(roi) / max(roi.size, 1)


def main():
    img = _load_image(IMAGE_PATH)
    if img is None:
        print("无法读取图像")
        return

    rectified, ok = _rectify(img)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    H, W = binary_inv.shape[:2]
    print(f"图像: {W}x{H}, 透视矫正: {'成功' if ok else '未矫正'}")

    # ═══ 检测水平线 ═══
    h_lines = detect_lines(binary_inv, 'horizontal', min_length=100)
    h_clusters = cluster_positions(h_lines, tol=25)
    print(f"\n水平线: {len(h_lines)}条 → 聚类为 {len(h_clusters)} 条")
    for i, y in enumerate(h_clusters):
        print(f"  H{i}: Y={y}")

    # ═══ 检测垂直线 ═══
    v_lines = detect_lines(binary_inv, 'vertical', min_length=100)
    v_clusters = cluster_positions(v_lines, tol=25)
    print(f"\n垂直线: {len(v_lines)}条 → 聚类为 {len(v_clusters)} 条")
    for i, x in enumerate(v_clusters):
        print(f"  V{i}: X={x}")

    # ═══ 分析网格 ═══
    # 题目区: Y=1000~3000
    q_h_lines = [y for y in h_clusters if 1000 <= y <= 3000]
    q_v_lines = [x for x in v_clusters if 50 <= x <= 2000]

    print(f"\n题目区水平线: {q_h_lines}")
    print(f"题目区垂直线: {q_v_lines}")

    # 计算网格间距
    if len(q_h_lines) > 1:
        h_gaps = [q_h_lines[i+1] - q_h_lines[i] for i in range(len(q_h_lines)-1)]
        print(f"水平间距: {h_gaps}")

    if len(q_v_lines) > 1:
        v_gaps = [q_v_lines[i+1] - q_v_lines[i] for i in range(len(q_v_lines)-1)]
        print(f"垂直间距: {v_gaps}")

    # ═══ 在网格中采样填涂 ═══
    # 如果有足够的线，构建网格
    if len(q_h_lines) >= 3 and len(q_v_lines) >= 3:
        print("\n══════ 网格采样 ══════")

        # 假设每两条水平线之间是一行题目
        # 每两条垂直线之间是一个选项
        for ri in range(len(q_h_lines) - 1):
            y_top = q_h_lines[ri]
            y_bot = q_h_lines[ri + 1]
            y_mid = (y_top + y_bot) // 2
            row_h = y_bot - y_top

            row_fills = []
            for ci in range(len(q_v_lines) - 1):
                x_left = q_v_lines[ci]
                x_right = q_v_lines[ci + 1]
                x_mid = (x_left + x_right) // 2
                col_w = x_right - x_left

                # 采样（缩小到内部70%避免边框干扰）
                fill = sample_fill(binary_inv, x_mid, y_mid,
                                   int(col_w * 0.7), int(row_h * 0.7))
                row_fills.append((ci, x_mid, fill))

            # 找最高填涂
            filled = [(ci, x, f) for ci, x, f in row_fills if f > 0.15]
            fills_str = " ".join(f"{f:.3f}" for _, _, f in row_fills)
            print(f"  行{ri} Y={y_mid}: [{fills_str}]")
            if filled:
                best = max(row_fills, key=lambda x: x[2])
                print(f"    → 最高: 列{best[0]} (X={best[1]}) fill={best[2]:.3f}")

    # ═══ 生成诊断图 ═══
    debug_img = rectified.copy()
    for y in h_clusters:
        cv2.line(debug_img, (0, y), (W, y), (255, 0, 0), 1)
    for x in v_clusters:
        cv2.line(debug_img, (x, 0), (x, H), (0, 0, 255), 1)

    debug_path = os.path.join(os.path.dirname(__file__), 'debug_grid_lines.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\n网格诊断图: {debug_path}")

    # ═══ 额外: 裁剪题目区第一行并保存 ═══
    if q_h_lines:
        crop = rectified[q_h_lines[0]-20:q_h_lines[0]+80, :]
        crop_path = os.path.join(os.path.dirname(__file__), 'debug_crop_row0.jpg')
        cv2.imwrite(crop_path, crop)
        print(f"第一行裁剪: {crop_path}")

    # 裁剪考号区
    exam_crop = rectified[150:600, :]
    exam_path = os.path.join(os.path.dirname(__file__), 'debug_crop_exam.jpg')
    cv2.imwrite(exam_path, exam_crop)
    print(f"考号区裁剪: {exam_path}")


if __name__ == '__main__':
    main()
