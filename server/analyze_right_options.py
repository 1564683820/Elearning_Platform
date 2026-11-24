# -*- coding: utf-8 -*-
"""右侧选项列精细X扫描 + 完整布局验证"""
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

    # 1. 右侧精细X扫描 - 在Y=1114(Q6行)扫描X=1200~2100
    print("\n=== Right side fine X-scan at Y=1114 (Q6 row, step=5) ===")
    y = 1114
    for x in range(1200, 2100, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.15:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 2. 右侧在未填充行扫描（找方框轮廓）
    # Q13-Q20应该为空，找一个空行扫描
    print("\n=== Right side X-scan at Y=1800 (should be empty row, step=5) ===")
    y = 1800
    for x in range(1200, 2100, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.05:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 3. 右侧在Y=1577(Q11行)扫描 - 看右侧是否有内容
    print("\n=== Right side X-scan at Y=1577 (Q11 row, step=5) ===")
    y = 1577
    for x in range(1200, 2100, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.15:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 4. 右侧在Y=1658(Q12行)扫描
    print("\n=== Right side X-scan at Y=1658 (Q12 row, step=5) ===")
    y = 1658
    for x in range(1200, 2100, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.15:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 5. 右侧在Y=2039(Q21行)扫描 - 看右侧是否有Q21对应内容
    print("\n=== Right side X-scan at Y=2039 (Q21 row, step=5) ===")
    y = 2039
    for x in range(1200, 2100, 5):
        f = fill_ratio(bw, x, y, BOX_W, BOX_H)
        if f > 0.15:
            print(f"  X={x:4d}  fill={f:.3f}")

    # 6. 左侧在Q13-Q20预期位置扫描（Y=1700~2000）
    print("\n=== Left side Y-scan 1700~2000 (Q13-Q20 area?) ===")
    for y in range(1700, 2020, 3):
        max_f = 0
        max_opt = ''
        opts = {'A':215, 'B':330, 'C':445, 'D':560, 'E':675, 'F':790, 'G':905}
        for opt_name, opt_x in opts.items():
            f = fill_ratio(bw, opt_x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_opt = opt_name
        if max_f > 0.3:
            print(f"  Y={y:4d}  max_fill={max_f:.3f} opt={max_opt}")

    # 7. 右侧在Q13-Q20预期位置扫描
    print("\n=== Right side Y-scan 1500~2000 (Q13-Q20 area?) ===")
    for y in range(1500, 2020, 3):
        max_f = 0
        max_x = 0
        for x in range(1200, 2100, 10):
            f = fill_ratio(bw, x, y, BOX_W, BOX_H)
            if f > max_f:
                max_f = f
                max_x = x
        if max_f > 0.3:
            print(f"  Y={y:4d}  max_fill={max_f:.3f} at X={max_x}")

if __name__ == "__main__":
    main()
