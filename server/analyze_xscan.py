"""精确扫描X轴 - 在已知有填涂的Y位置找选项列X坐标

从之前分析知道:
  - Y=1098 附近有 B 选项填涂 (4列测试中 X=280 fill=0.259)
  - Y=1206 附近有 C 选项填涂 (4列测试中 X=390 fill=0.384)
  - 右半 Q23=D 在 Y=1195, Q25=C 在 Y=1285

策略:
  1. 在这些Y位置扫描X=50~1200 (左半), 每5px采样
  2. 找填涂峰值 → 确定选项列精确X坐标
  3. 同时扫描右半验证
"""

import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.omr_scanner import _load_image, _rectify, _binary_inv

IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'tests', 'exam.jpg')


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

    print(f"Image: {rectified.shape[1]}x{rectified.shape[0]}")

    W_SMALL, H_SMALL = 35, 25

    # ═══ 1. 在多个Y位置扫描左半X轴 ═══
    print("\n=== Left side X scan at various Y ===")

    # 测试多个Y位置
    test_ys = [1098, 1148, 1206, 1286, 1369, 1450]

    for y in test_ys:
        print(f"\nY={y}:")
        fills = []
        for x in range(50, 1200, 5):
            f = sample_fill(binary_inv, x, y, W_SMALL, H_SMALL)
            fills.append((x, f))

        # 找峰值 (局部极大值 > 0.25)
        peaks = []
        for i in range(1, len(fills) - 1):
            x, f = fills[i]
            _, f_prev = fills[i - 1]
            _, f_next = fills[i + 1]
            if f > 0.25 and f >= f_prev and f >= f_next:
                peaks.append((x, f))

        # 去重相近的峰值
        unique_peaks = []
        for x, f in peaks:
            if not unique_peaks or x - unique_peaks[-1][0] > 30:
                unique_peaks.append((x, f))
            elif f > unique_peaks[-1][1]:
                unique_peaks[-1] = (x, f)

        if unique_peaks:
            for x, f in unique_peaks:
                print(f"  X={x:4d}: fill={f:.4f}")
        else:
            # 打印最高的几个
            top = sorted(fills, key=lambda x: x[1], reverse=True)[:5]
            print(f"  No peaks > 0.25. Top 5:")
            for x, f in top:
                print(f"  X={x:4d}: fill={f:.4f}")

    # ═══ 2. 在右半验证Y位置扫描X轴 ═══
    print("\n=== Right side X scan at Y=1195 (Q23=D) ===")
    y = 1195
    fills = []
    for x in range(1200, 2100, 5):
        f = sample_fill(binary_inv, x, y, W_SMALL, H_SMALL)
        fills.append((x, f))

    peaks = []
    for i in range(1, len(fills) - 1):
        x, f = fills[i]
        _, f_prev = fills[i - 1]
        _, f_next = fills[i + 1]
        if f > 0.3 and f >= f_prev and f >= f_next:
            peaks.append((x, f))

    unique_peaks = []
    for x, f in peaks:
        if not unique_peaks or x - unique_peaks[-1][0] > 30:
            unique_peaks.append((x, f))
        elif f > unique_peaks[-1][1]:
            unique_peaks[-1] = (x, f)

    for x, f in unique_peaks:
        print(f"  X={x:4d}: fill={f:.4f}")

    # ═══ 3. 在整个题目区做Y-X热图扫描 ═══
    print("\n=== Dense Y scan for left side (X=100~1000) ===")
    print("Finding all filled positions in left question area...")

    # 扫描 Y=1000~2000, X=100~1000
    filled_positions = []
    for y in range(1000, 2000, 5):
        for x in range(100, 1000, 10):
            f = sample_fill(binary_inv, x, y, W_SMALL, H_SMALL)
            if f > 0.35:
                filled_positions.append((x, y, f))

    print(f"Found {len(filled_positions)} high-fill positions (>0.35)")

    # 按Y聚类
    if filled_positions:
        filled_positions.sort(key=lambda p: p[1])
        clusters = []
        current = [filled_positions[0]]
        for p in filled_positions[1:]:
            if p[1] - current[-1][1] <= 30:
                current.append(p)
            else:
                clusters.append(current)
                current = [p]
        clusters.append(current)

        print(f"\n{len(clusters)} Y clusters:")
        for ci, cluster in enumerate(clusters):
            ys = [p[1] for p in cluster]
            xs = [p[0] for p in cluster]
            avg_y = int(np.mean(ys))
            print(f"\n  Cluster {ci}: Y={min(ys)}~{max(ys)} (center={avg_y})")
            # 按X排序
            cluster.sort(key=lambda p: p[0])
            for x, y, f in cluster:
                print(f"    X={x:4d} Y={y}: fill={f:.4f}")

    # ═══ 4. 右半密集扫描 ═══
    print("\n=== Dense scan for right side (X=1200~2000, Y=1000~3000) ===")
    right_filled = []
    for y in range(1000, 3000, 5):
        for x in range(1200, 2000, 10):
            f = sample_fill(binary_inv, x, y, W_SMALL, H_SMALL)
            if f > 0.35:
                right_filled.append((x, y, f))

    print(f"Found {len(right_filled)} high-fill positions")

    if right_filled:
        right_filled.sort(key=lambda p: p[1])
        clusters = []
        current = [right_filled[0]]
        for p in right_filled[1:]:
            if p[1] - current[-1][1] <= 30:
                current.append(p)
            else:
                clusters.append(current)
                current = [p]
        clusters.append(current)

        print(f"\n{len(clusters)} Y clusters:")
        for ci, cluster in enumerate(clusters):
            ys = [p[1] for p in cluster]
            avg_y = int(np.mean(ys))
            cluster.sort(key=lambda p: p[0])
            print(f"\n  Cluster {ci}: Y={min(ys)}~{max(ys)} (center={avg_y})")
            for x, y, f in cluster:
                print(f"    X={x:4d} Y={y}: fill={f:.4f}")


if __name__ == '__main__':
    main()
