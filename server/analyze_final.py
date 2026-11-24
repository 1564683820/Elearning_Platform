"""最终版分析 - 全面扫描左右两半的所有选项

已知：
  左半选项列中心: 149, 256, 368, 483, 596, 706, 821 (A-G)
  右半选项列中心: 1350, 1443, 1538, 1634, 1730, 1827, 1920 (A-G)
  题目区: Y=1000~3000

策略:
  1. 每10px扫描一行
  2. 采样左右各7个选项
  3. 找有填涂的Y位置 → 聚类为题目行
  4. 映射到题号
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

# 选项列中心
LEFT_CENTERS = [149, 256, 368, 483, 596, 706, 821]   # A-G
RIGHT_CENTERS = [1350, 1443, 1538, 1634, 1730, 1827, 1920]  # A-G

BOX_W = 70  # 采样宽度
BOX_H = 50  # 采样高度


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


def scan_all_rows(binary_inv):
    """扫描所有行，返回每行的填涂情况"""
    results = []
    for y in range(1000, 3000, 10):
        left_fills = [sample_fill(binary_inv, cx, y, BOX_W, BOX_H) for cx in LEFT_CENTERS]
        right_fills = [sample_fill(binary_inv, cx, y, BOX_W, BOX_H) for cx in RIGHT_CENTERS]

        left_max = max(left_fills) if left_fills else 0
        right_max = max(right_fills) if right_fills else 0

        if left_max > 0.15 or right_max > 0.15:
            results.append({
                'y': y,
                'left': left_fills,
                'right': right_fills,
                'left_max': left_max,
                'right_max': right_max,
            })
    return results


def cluster_rows(results, tol=40):
    """将有填涂的行聚类"""
    if not results:
        return []
    clusters = []
    current = [results[0]]
    for r in results[1:]:
        if r['y'] - current[-1]['y'] <= tol:
            current.append(r)
        else:
            clusters.append(current)
            current = [r]
    clusters.append(current)
    return clusters


def main():
    img = _load_image(IMAGE_PATH)
    rectified, ok = _rectify(img)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    binary_inv = _binary_inv(gray)

    print(f"图像: {rectified.shape[1]}x{rectified.shape[0]}")

    # 扫描所有行
    results = scan_all_rows(binary_inv)
    print(f"\n检测到 {len(results)} 个有填涂的Y位置")

    # 聚类
    clusters = cluster_rows(results, tol=40)
    print(f"聚类为 {len(clusters)} 个题目行\n")

    print("══════ 扫描结果 ══════")
    question_num = 0
    for ci, cluster in enumerate(clusters):
        # 取簇中填涂最强的行
        best = max(cluster, key=lambda r: max(r['left_max'], r['right_max']))
        y = best['y']

        # 左半结果
        left_labels = []
        for i, f in enumerate(best['left']):
            if f > 0.15:
                left_labels.append((chr(65 + i), f))

        # 右半结果
        right_labels = []
        for i, f in enumerate(best['right']):
            if f > 0.15:
                right_labels.append((chr(65 + i), f))

        left_str = " ".join(f"{l}:{f:.3f}" for l, f in left_labels)
        right_str = " ".join(f"{l}:{f:.3f}" for l, f in right_labels)

        left_ans = left_labels[0][0] if left_labels else ""
        right_ans = right_labels[0][0] if right_labels else ""

        print(f"行{ci} Y={y}: 左[{left_str}] 右[{right_str}]")
        print(f"  → 左: {left_ans or '空'}  右: {right_ans or '空'}")

        # 打印所有填涂详情
        if left_labels:
            best_left = max(left_labels, key=lambda x: x[1])
            print(f"  左最佳: {best_left[0]} (fill={best_left[1]:.3f})")
        if right_labels:
            best_right = max(right_labels, key=lambda x: x[1])
            print(f"  右最佳: {best_right[0]} (fill={best_right[1]:.3f})")

    # ═══ 尝试映射到题号 ═══
    print("\n══════ 题号映射 ══════")
    # 假设: 左半Q1-Q20, 右半Q21-Q25
    # 左半有4组×5行=20题, 右半有1组×5行=5题

    left_rows = []
    right_rows = []
    for ci, cluster in enumerate(clusters):
        best = max(cluster, key=lambda r: max(r['left_max'], r['right_max']))
        y = best['y']

        left_labels = [chr(65 + i) for i, f in enumerate(best['left']) if f > 0.15]
        right_labels = [chr(65 + i) for i, f in enumerate(best['right']) if f > 0.15]

        left_ans = max(left_labels, key=lambda l: best['left'][ord(l) - 65]) if left_labels else ""
        right_ans = max(right_labels, key=lambda l: best['right'][ord(l) - 65]) if right_labels else ""

        left_rows.append((y, left_ans, best['left']))
        right_rows.append((y, right_ans, best['right']))

    print(f"\n左半 {len(left_rows)} 行:")
    for i, (y, ans, fills) in enumerate(left_rows):
        qnum = i + 1
        expected = EXPECTED['answers'].get(qnum, '')
        match = "✓" if ans == expected else "✗" if expected else ""
        fills_str = " ".join(f"{f:.3f}" for f in fills)
        print(f"  Q{qnum:2d} Y={y}: {ans or '空':4s} (预期: {expected or '空':4s}) {match}  [{fills_str}]")

    print(f"\n右半 {len(right_rows)} 行:")
    for i, (y, ans, fills) in enumerate(right_rows):
        qnum = 21 + i
        expected = EXPECTED['answers'].get(qnum, '')
        match = "✓" if ans == expected else "✗" if expected else ""
        fills_str = " ".join(f"{f:.3f}" for f in fills)
        print(f"  Q{qnum:2d} Y={y}: {ans or '空':4s} (预期: {expected or '空':4s}) {match}  [{fills_str}]")

    # ═══ 考号区分析 ═══
    print("\n══════ 考号区分析 ══════")
    # 考号在 Y=150~600 区域
    # 7位数字，每位0-9纵向排列
    # 需要找到数字列的X位置和选项的Y位置

    # 扫描考号区
    exam_fills = []
    for y in range(150, 600, 10):
        # 扫描所有可能的X位置
        row_fill = []
        for x in range(50, 2000, 20):
            f = sample_fill(binary_inv, x, y, 50, 40)
            row_fill.append((x, f))
        # 找高填涂点
        high = [(x, f) for x, f in row_fill if f > 0.2]
        if high:
            exam_fills.append((y, high))

    print(f"考号区高填涂位置:")
    for y, highs in exam_fills[:20]:
        xs = [f"X={x}:{f:.3f}" for x, f in highs[:5]]
        print(f"  Y={y}: {', '.join(xs)}")

    # ═══ 诊断图 ═══
    debug_img = rectified.copy()
    for cluster in clusters:
        best = max(cluster, key=lambda r: max(r['left_max'], r['right_max']))
        y = best['y']
        # 画行线
        cv2.line(debug_img, (0, y), (rectified.shape[1], y), (255, 0, 0), 1)
        # 标注左半
        for i, f in enumerate(best['left']):
            cx = LEFT_CENTERS[i]
            color = (0, 0, 255) if f > 0.15 else (0, 255, 0)
            cv2.rectangle(debug_img, (cx - BOX_W//2, y - BOX_H//2),
                         (cx + BOX_W//2, y + BOX_H//2), color, 2)
        # 标注右半
        for i, f in enumerate(best['right']):
            cx = RIGHT_CENTERS[i]
            color = (0, 0, 255) if f > 0.15 else (0, 255, 0)
            cv2.rectangle(debug_img, (cx - BOX_W//2, y - BOX_H//2),
                         (cx + BOX_W//2, y + BOX_H//2), color, 2)

    debug_path = os.path.join(os.path.dirname(__file__), 'debug_final.jpg')
    cv2.imwrite(debug_path, debug_img)
    print(f"\n诊断图: {debug_path}")


if __name__ == '__main__':
    main()
