# -*- coding: utf-8 -*-
"""精准分析：在已知Y位置做精细X扫描，推断真实布局"""
import cv2
import numpy as np

from pathlib import Path

IMG_PATH = str(Path(__file__).resolve().parent / "tests/exam.jpg")

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
    print("Image:", bw.shape)

    BOX_W = 40
    BOX_H = 30

    # 已知：Q1=B at Y=1114, Q21=E at Y=2077
    # Q21-Q25 间距约80px: 2077, 2158, 2236, 2329, 2401
    # 假设Q1-Q12也有类似间距

    # 1. 在Y=1114(Q1)做精细X扫描，确认选项列位置
    print("\n=== Fine X-scan at Y=1114 (Q1=B) ===")
    y = 1114
    for x in range(100, 1200, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.3:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 2. 在Y=2077(Q21=E)做精细X扫描
    print("\n=== Fine X-scan at Y=2077 (Q21=E) ===")
    y = 2077
    for x in range(100, 1200, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.3:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 3. 假设Q1-Q12间距约80px，在预期Y位置做X扫描
    print("\n=== Predicted Q2-Q12 Y positions (spacing=80 from Q1=1114) ===")
    q1_y = 1114
    spacing = 80
    for qi in range(2, 13):
        y_pred = q1_y + (qi - 1) * spacing
        # 扫描X=100~1100找最高填充
        best_x = 0
        best_f = 0
        fills = []
        for x in range(100, 1100, 5):
            f = fill_ratio(bw, x, y_pred, BOX_W, BOX_H)
            fills.append((x, f))
            if f > best_f:
                best_f = f
                best_x = x
        # 找所有 > 0.5 的
        high = [(x, f) for x, f in fills if f > 0.5]
        print(f"  Q{qi:2d} Y={y_pred:4d}: best_X={best_x:4d} fill={best_f:.3f}  high_fills={high[:5]}")

    # 4. 也尝试更大间距
    print("\n=== Try different spacings ===")
    for sp in [70, 75, 80, 85, 90, 95, 100]:
        # Q2 position
        y2 = 1114 + sp
        best_f = 0
        best_x = 0
        for x in range(100, 1100, 5):
            f = fill_ratio(bw, x, y2, BOX_W, BOX_H)
            if f > best_f:
                best_f = f
                best_x = x
        print(f"  spacing={sp}  Q2_Y={y2}  best_X={best_x} fill={best_f:.3f}")

    # 5. 在Y=1114到Y=2077之间做密集Y扫描，找所有高填充行
    print("\n=== Dense Y-scan between Q1 and Q21 (X=100~1100) ===")
    for y in range(1100, 2080, 3):
        max_f = 0
        max_x = 0
        for x in range(100, 1100, 10):
            f = fill_ratio(bw, x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_x = x
        if max_f > 0.5:
            print(f"  Y={y:4d}  max_fill={max_f:.3f} at X={max_x}")

    # 6. 右侧也做同样扫描
    print("\n=== Dense Y-scan right side (X=1200~2400) ===")
    for y in range(200, 3500, 3):
        max_f = 0
        max_x = 0
        for x in range(1200, 2400, 10):
            f = fill_ratio(bw, x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_x = x
        if max_f > 0.5:
            print(f"  Y={y:4d}  max_fill={max_f:.3f} at X={max_x}")

if __name__ == "__main__":
    main()
