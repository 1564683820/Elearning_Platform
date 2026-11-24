"""验证正确的选项坐标 - 全面扫描所有题目

已知:
  左半选项中心: A=195, B=305, C=415, D=525, E=635, F=745, G=855
  右半选项中心: A=1346, B=1439, C=1532, D=1625, E=1718, F=1811, G=1904
  Q1 在 Y~1120, 行间距 ~82px

策略:
  1. 用正确坐标扫描 Y=1000~3000, 每3px
  2. 在每个Y采样左右各7个选项
  3. 找有填涂的行 -> 聚类 -> 映射题号
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

LEFT_CENTERS = [195, 305, 415, 525, 635, 745, 855]
RIGHT_CENTERS = [1346, 1439, 1532, 1625, 1718, 1811, 1904]

BOX_W = 40
BOX_H = 30


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

    # 扫描所有Y位置
    left_rows = []  # (y, best_opt, fills)
    right_rows = []

    for y in range(1000, 3000, 3):
        # 左半
        left_fills = [sample_fill(binary_inv, cx, y, BOX_W, BOX_H) for cx in LEFT_CENTERS]
        left_max = max(left_fills)
        if left_max > 0.4:
            best_idx = left_fills.index(left_max)
            left_rows.append((y, chr(65 + best_idx), left_max, left_fills))

        # 右半
        right_fills = [sample_fill(binary_inv, cx, y, BOX_W, BOX_H) for cx in RIGHT_CENTERS]
        right_max = max(right_fills)
        if right_max > 0.4:
            best_idx = right_fills.index(right_max)
            right_rows.append((y, chr(65 + best_idx), right_max, right_fills))

    # 聚类左半
    print("\n=== Left side filled rows ===")
    left_clusters = cluster_rows(left_rows, tol=30)
    print(f"{len(left_clusters)} clusters")

    left_answers = {}
    for ci, cluster in enumerate(left_clusters):
        best = max(cluster, key=lambda r: r[2])
        y, ans, fill, fills = best
        fills_str = " ".join(f"{chr(65+i)}:{f:.3f}" for i, f in enumerate(fills))
        print(f"  Row {ci}: Y={y} -> {ans} (fill={fill:.3f}) [{fills_str}]")
        left_answers[ci + 1] = (y, ans, fill)

    # 聚类右半
    print("\n=== Right side filled rows ===")
    right_clusters = cluster_rows(right_rows, tol=30)
    print(f"{len(right_clusters)} clusters")

    right_answers = {}
    for ci, cluster in enumerate(right_clusters):
        best = max(cluster, key=lambda r: r[2])
        y, ans, fill, fills = best
        fills_str = " ".join(f"{chr(65+i)}:{f:.3f}" for i, f in enumerate(fills))
        print(f"  Row {ci}: Y={y} -> {ans} (fill={fill:.3f}) [{fills_str}]")
        right_answers[21 + ci] = (y, ans, fill)

    # ═══ 对比预期答案 ═══
    print("\n=== Comparison with expected ===")
    print("\nLeft side (Q1-Q20):")
    correct = 0
    total = 0
    for qnum in range(1, 21):
        expected = EXPECTED['answers'].get(qnum, '')
        if qnum in left_answers:
            y, ans, fill = left_answers[qnum]
            match = "OK" if ans == expected else "XX"
            if expected:
                total += 1
                if ans == expected:
                    correct += 1
            print(f"  Q{qnum:2d}: detected={ans} expected={expected or 'empty':6s} {match} (Y={y}, fill={fill:.3f})")
        else:
            if expected:
                total += 1
                print(f"  Q{qnum:2d}: detected=??  expected={expected:6s} MISSING")
            else:
                print(f"  Q{qnum:2d}: detected=??  expected=empty  (empty)")

    print(f"\n  Left: {correct}/{total} correct")

    print("\nRight side (Q21-Q25):")
    correct_r = 0
    total_r = 0
    for qnum in range(21, 26):
        expected = EXPECTED['answers'].get(qnum, '')
        if qnum in right_answers:
            y, ans, fill = right_answers[qnum]
            match = "OK" if ans == expected else "XX"
            total_r += 1
            if ans == expected:
                correct_r += 1
            print(f"  Q{qnum:2d}: detected={ans} expected={expected:6s} {match} (Y={y}, fill={fill:.3f})")
        else:
            total_r += 1
            print(f"  Q{qnum:2d}: detected=??  expected={expected:6s} MISSING")

    print(f"\n  Right: {correct_r}/{total_r} correct")
    print(f"\n  TOTAL: {correct + correct_r}/{total + total_r} correct")

    # ═══ 输出坐标配置 ═══
    print("\n=== Coordinate Config ===")
    print("LEFT_CENTERS =", LEFT_CENTERS)
    print("RIGHT_CENTERS =", RIGHT_CENTERS)
    print("BOX_W =", BOX_W)
    print("BOX_H =", BOX_H)

    # 输出题目行Y坐标
    print("\nQuestion row Y positions:")
    all_ys = []
    for qnum, (y, ans, fill) in sorted(left_answers.items()):
        all_ys.append((qnum, y, ans, "left"))
    for qnum, (y, ans, fill) in sorted(right_answers.items()):
        all_ys.append((qnum, y, ans, "right"))

    for qnum, y, ans, side in all_ys:
        print(f"  Q{qnum}: Y={y} ans={ans} ({side})")


def cluster_rows(rows, tol=30):
    if not rows:
        return []
    clusters = []
    current = [rows[0]]
    for r in rows[1:]:
        if r[0] - current[-1][0] <= tol:
            current.append(r)
        else:
            clusters.append(current)
            current = [r]
    clusters.append(current)
    return clusters


if __name__ == '__main__':
    main()
