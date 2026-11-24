"""分析真实答题卡 exam.jpg 的方块布局

目标：
  1. 透视矫正到 A4 (2480x3508)
  2. 检测所有方形选项框
  3. 聚类成行(题目)和列(选项)
  4. 输出布局信息，用于构建 coordinate_config
"""

import sys
import os
import cv2
import numpy as np

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.omr_scanner import _load_image, _rectify, _binary_inv
from app.services.printable_sheet_constants import A4_WIDTH, A4_HEIGHT

IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'tests', 'exam.jpg')


def detect_squares(binary_inv):
    """检测所有方形轮廓

    返回: [(cx, cy, w, h), ...] 每个方块的中心和尺寸
    """
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    squares = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)

        # 过滤太小或太大的
        if area < 200 or area > 50000:
            continue

        # 近似方形: 长宽比 0.5~2.0
        aspect = w / max(h, 1)
        if aspect < 0.5 or aspect > 2.0:
            continue

        # 4顶点近似
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) < 4 and len(approx) > 8:
            continue

        cx = x + w // 2
        cy = y + h // 2
        squares.append((cx, cy, w, h, area))

    return squares


def cluster_by_y(squares, tol=30):
    """按Y坐标聚类成行"""
    if not squares:
        return []

    sorted_sq = sorted(squares, key=lambda s: s[1])
    rows = []
    current_row = [sorted_sq[0]]
    current_y = sorted_sq[0][1]

    for sq in sorted_sq[1:]:
        if abs(sq[1] - current_y) <= tol:
            current_row.append(sq)
        else:
            rows.append(current_row)
            current_row = [sq]
            current_y = sq[1]
    rows.append(current_row)
    return rows


def cluster_by_x(squares, tol=30):
    """按X坐标聚类成列"""
    if not squares:
        return []

    sorted_sq = sorted(squares, key=lambda s: s[0])
    cols = []
    current_col = [sorted_sq[0]]
    current_x = sorted_sq[0][0]

    for sq in sorted_sq[1:]:
        if abs(sq[0] - current_x) <= tol:
            current_col.append(sq)
        else:
            cols.append(current_col)
            current_col = [sq]
            current_x = sq[0]
    cols.append(current_col)
    return cols


def main():
    img = _load_image(IMAGE_PATH)
    if img is None:
        print(f"无法读取图像: {IMAGE_PATH}")
        return

    print(f"原始尺寸: {img.shape[1]}x{img.shape[0]}")

    # 透视矫正
    rectified, ok = _rectify(img)
    print(f"透视矫正: {'成功' if ok else '未矫正'}")
    print(f"矫正后尺寸: {rectified.shape[1]}x{rectified.shape[0]}")

    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    white_pct = cv2.countNonZero(binary_inv) / binary_inv.size * 100
    print(f"二值化: {white_pct:.1f}% 白色像素(墨迹)")

    # 检测方块
    squares = detect_squares(binary_inv)
    print(f"\n检测到 {len(squares)} 个方块")

    if not squares:
        print("未检测到方块，尝试调整参数...")
        # 尝试不同参数
        for min_a in [100, 50, 20]:
            for max_a in [100000, 200000]:
                contours, _ = cv2.findContours(binary_inv, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
                count = 0
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    if area < min_a or area > max_a:
                        continue
                    x, y, w, h = cv2.boundingRect(cnt)
                    aspect = w / max(h, 1)
                    if 0.3 < aspect < 3.0:
                        count += 1
                print(f"  min_area={min_a}, max_area={max_a}: {count} 个候选")
        return

    # 打印方块尺寸分布
    sizes = [(s[2], s[3]) for s in squares]
    widths = [s[0] for s in sizes]
    heights = [s[1] for s in sizes]
    print(f"方块宽度: min={min(widths)}, max={max(widths)}, avg={np.mean(widths):.0f}")
    print(f"方块高度: min={min(heights)}, max={max(heights)}, avg={np.mean(heights):.0f}")

    # 按Y聚类成行
    rows = cluster_by_y(squares, tol=40)
    print(f"\n按Y聚类: {len(rows)} 行")
    for i, row in enumerate(rows):
        avg_y = np.mean([s[1] for s in row])
        xs = sorted([s[0] for s in row])
        print(f"  行{i}: Y={avg_y:.0f}, {len(row)}个方块, X范围={xs[0]}~{xs[-1]}")
        if i < 5 or i >= len(rows) - 3:
            for s in sorted(row, key=lambda x: x[0]):
                print(f"    ({s[0]:4d}, {s[1]:4d}) {s[2]}x{s[3]} area={s[4]:.0f}")

    # 按X聚类成列
    cols = cluster_by_x(squares, tol=40)
    print(f"\n按X聚类: {len(cols)} 列")
    for i, col in enumerate(cols):
        avg_x = np.mean([s[0] for s in col])
        ys = sorted([s[1] for s in col])
        print(f"  列{i}: X={avg_x:.0f}, {len(col)}个方块, Y范围={ys[0]}~{ys[-1]}")

    # 生成诊断图
    debug_img = rectified.copy()
    for s in squares:
        cx, cy, w, h = s[0], s[1], s[2], s[3]
        cv2.rectangle(debug_img, (cx - w//2, cy - h//2), (cx + w//2, cy + h//2), (0, 0, 255), 2)
    debug_path = os.path.join(os.path.dirname(__file__), 'debug_squares.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\n诊断图已保存: {debug_path}")


if __name__ == '__main__':
    main()
