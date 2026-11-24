"""左右分区分析 - 分别检测左半和右半的网格线

发现：
  - 右半 (X>1200): 7个选项列，间距~93px
  - 左半 (X<1200): 需要更短线段检测

策略：
  1. 分别对左右半检测垂直线
  2. 用更短的 min_length 和不同核大小
  3. 采样填涂比例验证
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


def detect_lines_region(binary_inv, x_start, x_end, direction='vertical',
                         min_length=50, kernel_size=30):
    """在指定X范围内检测线段"""
    region = binary_inv[:, x_start:x_end]

    if direction == 'horizontal':
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_size))

    detected = cv2.morphologyEx(region, cv2.MORPH_OPEN, kernel)
    lines = cv2.HoughLinesP(detected, 1, np.pi / 180, threshold=20,
                            minLineLength=min_length, maxLineGap=10)

    result = []
    if lines is not None:
        for line in lines:
            line = line.flatten()
            x1, y1, x2, y2 = int(line[0]), int(line[1]), int(line[2]), int(line[3])
            if direction == 'horizontal':
                result.append((y1 + y2) // 2)
            else:
                result.append(x1 + x_start)  # 转换回全局坐标
    return sorted(result)


def cluster_positions(positions, tol=20):
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
    rectified, ok = _rectify(img)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)
    H, W = binary_inv.shape[:2]

    print(f"图像: {W}x{H}")

    # ═══ 右半垂直线 (已知: X=1304~1964, 7个选项) ═══
    print("\n══════ 右半垂直线 ══════")
    for ks in [30, 20, 15]:
        v_lines = detect_lines_region(binary_inv, 1200, 2100, 'vertical',
                                       min_length=50, kernel_size=ks)
        v_clusters = cluster_positions(v_lines, tol=20)
        print(f"  kernel={ks}: {len(v_lines)}条 → {len(v_clusters)}簇: {v_clusters}")

    # 使用 kernel=30 的结果
    v_lines_r = detect_lines_region(binary_inv, 1200, 2100, 'vertical',
                                     min_length=50, kernel_size=30)
    v_clusters_r = cluster_positions(v_lines_r, tol=20)
    print(f"\n右半垂直线: {v_clusters_r}")
    if len(v_clusters_r) > 1:
        gaps = [v_clusters_r[i+1] - v_clusters_r[i] for i in range(len(v_clusters_r)-1)]
        print(f"间距: {gaps}")

    # ═══ 左半垂直线 ═══
    print("\n══════ 左半垂直线 ══════")
    for ks in [30, 20, 15, 10]:
        for ml in [50, 30, 20]:
            v_lines = detect_lines_region(binary_inv, 50, 1200, 'vertical',
                                           min_length=ml, kernel_size=ks)
            v_clusters = cluster_positions(v_lines, tol=20)
            if len(v_clusters) > 2:
                print(f"  kernel={ks}, min_len={ml}: {len(v_lines)}条 → {len(v_clusters)}簇: {v_clusters}")

    # ═══ 题目区水平线 ═══
    print("\n══════ 题目区水平线 ══════")
    for ks in [40, 30, 20]:
        h_lines = detect_lines_region(binary_inv, 50, 2100, 'horizontal',
                                       min_length=100, kernel_size=ks)
        h_clusters = cluster_positions(h_lines, tol=25)
        print(f"  kernel={ks}: {len(h_lines)}条 → {len(h_clusters)}簇")
        if len(h_clusters) > 3:
            print(f"    位置: {h_clusters}")

    # ═══ 用投影法找题目行 ═══
    print("\n══════ 题目行检测（投影法）══════")
    q_region = binary_inv[1000:3000, 50:2100]
    row_proj = np.sum(q_region > 0, axis=1)

    # 找局部峰值
    threshold = np.max(row_proj) * 0.12
    high_rows = np.where(row_proj > threshold)[0]

    if len(high_rows) > 0:
        clusters = []
        start = high_rows[0]
        prev = high_rows[0]
        for r in high_rows[1:]:
            if r - prev > 25:
                clusters.append((start + 1000, prev + 1000))
                start = r
            prev = r
        clusters.append((start + 1000, prev + 1000))

        print(f"题目行 (阈值={threshold:.0f}): {len(clusters)}行")
        for i, (s, e) in enumerate(clusters):
            center = (s + e) // 2
            print(f"  行{i}: Y={s}~{e} (中心={center}, 高度={e-s}px)")

    # ═══ 右半采样验证 ═══
    print("\n══════ 右半选项采样 ══════")
    # 右半7个选项的列中心
    if len(v_clusters_r) >= 8:
        opt_centers_r = []
        for i in range(len(v_clusters_r) - 1):
            cx = (v_clusters_r[i] + v_clusters_r[i+1]) // 2
            opt_centers_r.append(cx)
        print(f"选项列中心: {opt_centers_r}")

        # 在每行采样
        question_rows = [(s, e) for s, e in clusters if 1000 <= s <= 3000]
        for ri, (ys, ye) in enumerate(question_rows):
            ymid = (ys + ye) // 2
            fills = []
            for ci, cx in enumerate(opt_centers_r):
                f = sample_fill(binary_inv, cx, ymid, 70, 60)
                fills.append(f)

            filled_idx = [i for i, f in enumerate(fills) if f > 0.15]
            labels = [chr(65 + i) for i in filled_idx]  # A, B, C...
            fills_str = " ".join(f"{f:.3f}" for f in fills)
            print(f"  行{ri} Y={ymid}: [{fills_str}] → {labels if labels else '空'}")

    # ═══ 左半采样 ═══
    print("\n══════ 左半选项采样 ══════")
    # 尝试不同的列位置
    # 从投影分析知道左半有簇在 X=142~576
    # 假设4个选项，间距约110px
    left_starts = [170, 280, 390, 500]  # 猜测的4列
    # 也尝试5列
    left_starts_5 = [170, 260, 350, 440, 530]

    question_rows = [(s, e) for s, e in clusters if 1000 <= s <= 3000]

    print("  尝试4列 (间距110):")
    for ri, (ys, ye) in enumerate(question_rows[:10]):
        ymid = (ys + ye) // 2
        fills = [sample_fill(binary_inv, cx, ymid, 80, 60) for cx in left_starts]
        filled_idx = [i for i, f in enumerate(fills) if f > 0.15]
        labels = [chr(65 + i) for i in filled_idx]
        fills_str = " ".join(f"{f:.3f}" for f in fills)
        print(f"  行{ri} Y={ymid}: [{fills_str}] → {labels if labels else '空'}")

    # ═══ 生成诊断图 ═══
    debug_img = rectified.copy()
    # 画右半垂直线
    for x in v_clusters_r:
        cv2.line(debug_img, (x, 0), (x, H), (0, 0, 255), 1)
    # 画题目行
    for s, e in clusters:
        if 1000 <= s <= 3000:
            ymid = (s + e) // 2
            cv2.line(debug_img, (0, ymid), (W, ymid), (255, 0, 0), 1)

    debug_path = os.path.join(os.path.dirname(__file__), 'debug_grid2.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\n诊断图: {debug_path}")


if __name__ == '__main__':
    main()
