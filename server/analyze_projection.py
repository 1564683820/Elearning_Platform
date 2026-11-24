"""投影分析法 - 通过行/列墨迹密度定位题目和选项

策略：
  1. 透视矫正到 A4
  2. OTSU 二值化
  3. 水平投影（每行墨迹量）→ 找题目行Y坐标
  4. 垂直投影（每列墨迹量）→ 找选项列X坐标
  5. 构建网格，采样每个交叉点的填涂比例
  6. 与预期答案对比验证
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


def find_peaks(profile, min_val=None, min_dist=50):
    """找投影曲线的峰值（局部极大值）"""
    if min_val is None:
        min_val = np.max(profile) * 0.1 if profile.max() > 0 else 0

    peaks = []
    for i in range(1, len(profile) - 1):
        if profile[i] > min_val and profile[i] >= profile[i-1] and profile[i] >= profile[i+1]:
            if not peaks or i - peaks[-1] >= min_dist:
                peaks.append(i)
            elif profile[i] > profile[peaks[-1]]:
                peaks[-1] = i
    return peaks


def main():
    img = _load_image(IMAGE_PATH)
    if img is None:
        print("无法读取图像")
        return

    rectified, ok = _rectify(img)
    print(f"透视矫正: {'成功' if ok else '未矫正'}, {rectified.shape[1]}x{rectified.shape[0]}")

    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    H, W = binary_inv.shape[:2]

    # ═══ 水平投影：每行的墨迹像素数 ═══
    row_proj = np.sum(binary_inv > 0, axis=1)  # shape: (H,)

    # 打印水平投影的峰值区域
    print("\n══════ 水平投影（行墨迹密度）══════")
    print(f"最大值: {row_proj.max():.0f}, 均值: {row_proj.mean():.0f}")

    # 找高密度行（题目行）
    threshold = row_proj.max() * 0.15
    high_rows = np.where(row_proj > threshold)[0]

    # 聚类连续的高密度行
    if len(high_rows) > 0:
        clusters = []
        start = high_rows[0]
        prev = high_rows[0]
        for r in high_rows[1:]:
            if r - prev > 20:  # 间隔>20px → 新簇
                clusters.append((start, prev))
                start = r
            prev = r
        clusters.append((start, prev))

        print(f"\n高密度行簇 (阈值={threshold:.0f}):")
        for i, (s, e) in enumerate(clusters):
            center = (s + e) // 2
            height = e - s
            peak_val = row_proj[center]
            print(f"  簇{i}: Y={s}~{e} (中心={center}, 高度={height}px, 峰值={peak_val:.0f})")

    # ═══ 垂直投影：每列的墨迹像素数 ═══
    col_proj = np.sum(binary_inv > 0, axis=0)  # shape: (W,)

    print(f"\n══════ 垂直投影（列墨迹密度）══════")
    print(f"最大值: {col_proj.max():.0f}, 均值: {col_proj.mean():.0f}")

    # 找高密度列
    col_threshold = col_proj.max() * 0.1
    high_cols = np.where(col_proj > col_threshold)[0]

    if len(high_cols) > 0:
        col_clusters = []
        start = high_cols[0]
        prev = high_cols[0]
        for c in high_cols[1:]:
            if c - prev > 30:
                col_clusters.append((start, prev))
                start = c
            prev = c
        col_clusters.append((start, prev))

        print(f"\n高密度列簇 (阈值={col_threshold:.0f}):")
        for i, (s, e) in enumerate(col_clusters):
            center = (s + e) // 2
            width = e - s
            peak_val = col_proj[center]
            print(f"  簇{i}: X={s}~{e} (中心={center}, 宽度={width}px, 峰值={peak_val:.0f})")

    # ═══ 分区域分析 ═══
    # 将图像分成几个区域来分析
    print("\n══════ 分区域分析 ═════")

    # 考号区 (Y < 600)
    exam_region = binary_inv[0:600, :]
    exam_row_proj = np.sum(exam_region > 0, axis=1)
    exam_col_proj = np.sum(exam_region > 0, axis=0)

    print("\n考号区 (Y=0~600):")
    print(f"  行峰值: {exam_row_proj.max():.0f}")
    # 找考号区的列簇
    exam_high_cols = np.where(exam_col_proj > exam_col_proj.max() * 0.1)[0]
    if len(exam_high_cols) > 0:
        ec = []
        start = exam_high_cols[0]
        prev = exam_high_cols[0]
        for c in exam_high_cols[1:]:
            if c - prev > 20:
                ec.append((start, prev))
                start = c
            prev = c
        ec.append((start, prev))
        print(f"  列簇:")
        for i, (s, e) in enumerate(ec):
            print(f"    簇{i}: X={s}~{e} (中心={(s+e)//2}, 宽={e-s}px)")

    # 题目区 (Y=1000~3000)
    q_region = binary_inv[1000:3000, :]

    # 题目区水平投影
    q_row_proj = np.sum(q_region > 0, axis=1)
    q_threshold = q_row_proj.max() * 0.15
    q_high_rows = np.where(q_row_proj > q_threshold)[0]

    print(f"\n题目区 (Y=1000~3000):")
    print(f"  行峰值: {q_row_proj.max():.0f}")

    if len(q_high_rows) > 0:
        qrc = []
        start = q_high_rows[0]
        prev = q_high_rows[0]
        for r in q_high_rows[1:]:
            if r - prev > 30:
                qrc.append((start + 1000, prev + 1000))
                start = r
            prev = r
        qrc.append((start + 1000, prev + 1000))

        print(f"  题目行 (阈值={q_threshold:.0f}):")
        for i, (s, e) in enumerate(qrc):
            center = (s + e) // 2
            print(f"    行{i}: Y={s}~{e} (中心={center})")

    # 题目区垂直投影
    q_col_proj = np.sum(q_region > 0, axis=0)
    q_col_threshold = q_col_proj.max() * 0.1
    q_high_cols = np.where(q_col_proj > q_col_threshold)[0]

    if len(q_high_cols) > 0:
        qcc = []
        start = q_high_cols[0]
        prev = q_high_cols[0]
        for c in q_high_cols[1:]:
            if c - prev > 30:
                qcc.append((start, prev))
                start = c
            prev = c
        qcc.append((start, prev))

        print(f"\n  选项列 (阈值={q_col_threshold:.0f}):")
        for i, (s, e) in enumerate(qcc):
            center = (s + e) // 2
            print(f"    列{i}: X={s}~{e} (中心={center}, 宽={e-s}px)")

    # ═══ 生成投影可视化 ═══
    viz = rectified.copy()
    # 在右侧画水平投影
    max_r = row_proj.max()
    for y in range(0, H, 2):
        val = int(row_proj[y] / max_r * 200)
        cv2.line(viz, (W, y), (W - val, y), (0, 0, 255), 1)
    # 在底部画垂直投影
    max_c = col_proj.max()
    for x in range(0, W, 2):
        val = int(col_proj[x] / max_c * 200)
        cv2.line(viz, (x, H), (x, H - val), (0, 0, 255), 1)

    viz_path = os.path.join(os.path.dirname(__file__), 'debug_projection.jpg')
    cv2.imwrite(viz_path, viz)
    print(f"\n投影可视化: {viz_path}")


if __name__ == '__main__':
    main()
