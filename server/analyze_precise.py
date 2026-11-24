"""精确定位每题Y坐标 - 用预期答案反向定位

策略:
  1. 对每个预期答案，在对应选项列扫描Y范围
  2. 找填涂比例最高的Y位置
  3. 确定每题的精确Y坐标
  4. 用小窗口(40x30)避免边框干扰
"""

import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.omr_scanner import _load_image, _rectify, _binary_inv

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

# 选项列中心 (A-G)
LEFT_CENTERS = [149, 256, 368, 483, 596, 706, 821]
RIGHT_CENTERS = [1350, 1443, 1538, 1634, 1730, 1827, 1920]


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

    # 用小窗口采样
    W_SMALL, H_SMALL = 40, 30

    # ═══ 1. 用预期答案反向定位Y坐标 ═══
    print("\n=== Reverse locate Y positions ===")

    # 左半 Q1-Q12
    print("\nLeft side (Q1-Q12):")
    left_q_ys = {}
    for qnum, ans in sorted(EXPECTED['answers'].items()):
        if qnum > 20:
            continue
        opt_idx = ord(ans) - 65  # A=0, B=1, ...
        cx = LEFT_CENTERS[opt_idx]

        best_y, best_fill = 0, 0
        for y in range(1000, 2000, 3):
            f = sample_fill(binary_inv, cx, y, W_SMALL, H_SMALL)
            if f > best_fill:
                best_fill = f
                best_y = y

        left_q_ys[qnum] = (best_y, best_fill, ans)
        print(f"  Q{qnum:2d} ans={ans}: Y={best_y} fill={best_fill:.4f}")

    # 右半 Q21-Q25
    print("\nRight side (Q21-Q25):")
    right_q_ys = {}
    for qnum, ans in sorted(EXPECTED['answers'].items()):
        if qnum < 21:
            continue
        opt_idx = ord(ans) - 65
        cx = RIGHT_CENTERS[opt_idx]

        best_y, best_fill = 0, 0
        for y in range(1000, 3000, 3):
            f = sample_fill(binary_inv, cx, y, W_SMALL, H_SMALL)
            if f > best_fill:
                best_fill = f
                best_y = y

        right_q_ys[qnum] = (best_y, best_fill, ans)
        print(f"  Q{qnum:2d} ans={ans}: Y={best_y} fill={best_fill:.4f}")

    # ═══ 2. 确定题目行Y坐标 ═══
    print("\n=== Question row Y positions ===")

    # 收集所有Y坐标，聚类
    all_ys = []
    for qnum, (y, _, _) in left_q_ys.items():
        all_ys.append((y, f"Q{qnum}", "left"))
    for qnum, (y, _, _) in right_q_ys.items():
        all_ys.append((y, f"Q{qnum}", "right"))

    all_ys.sort()
    print("\nAll located Y positions (sorted):")
    for y, q, side in all_ys:
        print(f"  Y={y}: {q} ({side})")

    # ═══ 3. 在每个定位的Y位置，采样所有选项 ═══
    print("\n=== Full option scan at each located Y ===")

    # 聚类Y坐标 (tolerance=50)
    clusters = []
    if all_ys:
        current = [all_ys[0]]
        for item in all_ys[1:]:
            if item[0] - current[-1][0] <= 50:
                current.append(item)
            else:
                clusters.append(current)
                current = [item]
        clusters.append(current)

    print(f"\n{len(clusters)} Y clusters:")
    for ci, cluster in enumerate(clusters):
        avg_y = int(np.mean([item[0] for item in cluster]))
        labels = [item[1] for item in cluster]
        print(f"\n  Cluster {ci}: Y={avg_y} ({', '.join(labels)})")

        # 在这个Y位置采样所有选项
        left_fills = [sample_fill(binary_inv, cx, avg_y, W_SMALL, H_SMALL) for cx in LEFT_CENTERS]
        right_fills = [sample_fill(binary_inv, cx, avg_y, W_SMALL, H_SMALL) for cx in RIGHT_CENTERS]

        left_str = " ".join(f"{chr(65+i)}:{f:.3f}" for i, f in enumerate(left_fills))
        right_str = " ".join(f"{chr(65+i)}:{f:.3f}" for i, f in enumerate(right_fills))
        print(f"  Left:  [{left_str}]")
        print(f"  Right: [{right_str}]")

        # 找最高
        left_best = max(range(7), key=lambda i: left_fills[i])
        right_best = max(range(7), key=lambda i: right_fills[i])
        print(f"  Left best: {chr(65+left_best)} ({left_fills[left_best]:.3f})")
        print(f"  Right best: {chr(65+right_best)} ({right_fills[right_best]:.3f})")

    # ═══ 4. 确定行间距和起始Y ═══
    print("\n=== Layout analysis ===")
    if len(all_ys) >= 2:
        ys = [item[0] for item in all_ys]
        gaps = [ys[i+1] - ys[i] for i in range(len(ys)-1)]
        print(f"Y gaps: {gaps}")
        print(f"Min gap: {min(gaps)}, Max gap: {max(gaps)}, Avg: {np.mean(gaps):.0f}")

    # ═══ 5. 考号区分析 ═══
    print("\n=== Exam number area ===")
    # 7位考号 0002603
    # 扫描 Y=150~600, 找填涂位置
    exam_expected = '0002603'
    print(f"Expected: {exam_expected}")

    # 扫描考号区，找所有高填涂位置
    for y in range(150, 600, 5):
        fills = []
        for x in range(50, 2000, 10):
            f = sample_fill(binary_inv, x, y, 30, 25)
            if f > 0.3:
                fills.append((x, f))
        if fills:
            # 去重相近的X
            unique_x = []
            for x, f in fills:
                if not unique_x or x - unique_x[-1][0] > 30:
                    unique_x.append((x, f))
                elif f > unique_x[-1][1]:
                    unique_x[-1] = (x, f)

            if len(unique_x) > 0:
                xs_str = ", ".join(f"X={x}:{f:.2f}" for x, f in unique_x[:10])
                print(f"  Y={y}: {xs_str}")

    # ═══ 6. 生成诊断图 ═══
    debug_img = rectified.copy()
    for qnum, (y, fill, ans) in {**left_q_ys, **right_q_ys}.items():
        centers = LEFT_CENTERS if qnum <= 20 else RIGHT_CENTERS
        color = (0, 0, 255) if qnum <= 20 else (255, 0, 0)
        cv2.line(debug_img, (0, y), (rectified.shape[1], y), color, 1)
        cv2.putText(debug_img, f"Q{qnum}={ans}", (10, y - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    debug_path = os.path.join(os.path.dirname(__file__), 'debug_precise.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\nDebug image: {debug_path}")


if __name__ == '__main__':
    main()
