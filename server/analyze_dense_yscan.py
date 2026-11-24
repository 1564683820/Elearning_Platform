# -*- coding: utf-8 -*-
"""密集Y扫描 - 左右两侧分别扫描，找出所有填充行"""
import cv2
import numpy as np

from pathlib import Path

IMG_PATH = str(Path(__file__).resolve().parent / "tests/exam.jpg")
OUT_FILE = str(Path(__file__).resolve().parent / "dense_yscan_output.txt")

def load_and_rectify(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = max(contours, key=cv2.contourArea)
    eps = 0.02 * cv2.arcLength(best, True)
    approx = cv2.approxPolyDP(best, eps, True)
    if len(approx) == 4:
        pts = approx.reshape(4, 2).astype(np.float32)
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).flatten()
        tl = pts[np.argmin(s)]
        tr = pts[np.argmin(d)]
        br = pts[np.argmax(s)]
        bl = pts[np.argmax(d)]
        W, H = 2480, 3508
        dst = np.array([[0,0],[W,0],[W,H],[0,H]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(np.array([tl,tr,br,bl],dtype=np.float32), dst)
        warped = cv2.warpPerspective(gray, M, (W, H))
        return warped
    return gray

def fill_ratio(img, x, y, w, h):
    H, W = img.shape
    x1 = max(0, x - w//2)
    x2 = min(W, x + w//2)
    y1 = max(0, y - h//2)
    y2 = min(H, y + h//2)
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    return float(np.count_nonzero(roi)) / roi.size

def main():
    img = load_and_rectify(IMG_PATH)
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    H, W = bw.shape

    BOX_W = 40
    BOX_H = 30

    # 更新后的选项列坐标 (spacing=115)
    OPTIONS = {
        'A': 215, 'B': 330, 'C': 445, 'D': 560,
        'E': 675, 'F': 790, 'G': 905
    }

    lines = []
    lines.append(f"Image: {bw.shape}")
    lines.append(f"Options: {OPTIONS}")
    lines.append("")

    # 左侧密集Y扫描 - 在每个选项X位置扫描
    lines.append("=== LEFT SIDE: Dense Y-scan at each option X ===")
    for opt_name, opt_x in OPTIONS.items():
        lines.append(f"\n--- Option {opt_name} (X={opt_x}) ---")
        prev_y = -100
        for y in range(200, 2600, 2):
            f = fill_ratio(bw, opt_x, y, BOX_W, BOX_H)
            if f > 0.5:
                if y - prev_y > 10:
                    lines.append(f"  Y={y:4d}  fill={f:.3f}  <<< NEW ROW")
                prev_y = y

    # 右侧密集Y扫描
    lines.append("\n\n=== RIGHT SIDE: Dense Y-scan ===")
    # 先找右侧的选项列位置
    # 右侧X范围 1200~2000
    for y_test in [1114, 1194, 1274, 1354, 1434]:
        lines.append(f"\n--- Y={y_test} right side X-scan ---")
        for x in range(1200, 2000, 10):
            f = fill_ratio(bw, x, y_test, BOX_W, BOX_H)
            if f > 0.5:
                lines.append(f"  X={x:4d}  fill={f:.3f}")

    # 右侧全面Y扫描
    lines.append("\n--- Right side full Y-scan (X=1200~2000, step=3) ---")
    for y in range(200, 3500, 3):
        max_f = 0
        max_x = 0
        for x in range(1200, 2000, 10):
            f = fill_ratio(bw, x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_x = x
        if max_f > 0.5:
            lines.append(f"  Y={y:4d}  max_fill={max_f:.3f} at X={max_x}")

    # 左侧全面Y扫描 (所有选项的最大值)
    lines.append("\n\n=== LEFT SIDE: Full Y-scan (max across all options) ===")
    for y in range(200, 2600, 3):
        max_f = 0
        max_opt = ''
        for opt_name, opt_x in OPTIONS.items():
            f = fill_ratio(bw, opt_x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_opt = opt_name
        if max_f > 0.5:
            lines.append(f"  Y={y:4d}  max_fill={max_f:.3f} opt={max_opt}")

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Output saved to {OUT_FILE}")
    print(f"Total lines: {len(lines)}")

if __name__ == "__main__":
    main()
