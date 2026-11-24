# -*- coding: utf-8 -*-
"""全面扫描 - 使用透视校正后的图像，精确定位所有选项列和题行"""
import cv2
import numpy as np
import json

from pathlib import Path

IMG_PATH = str(Path(__file__).resolve().parent / "tests/exam.jpg")

def load_and_rectify(path):
    """加载图像并透视校正到A4(2480x3508)"""
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
        dst_pts = np.float32([[0, 0], [2480, 0], [2480, 3508], [0, 3508]])
        M = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), dst_pts)
        warped = cv2.warpPerspective(img, M, (2480, 3508))
        gray_w = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray_w, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return warped, binary
    return img, None

print("Loading and rectifying...")
warped, binary = load_and_rectify(IMG_PATH)
h, w = binary.shape
print(f"Rectified: {h}x{w}")

def sample_rect(y, x, bw=22, bh=14):
    """采样矩形ROI的黑色像素比例"""
    y1, y2 = max(0, y-bh), min(h, y+bh)
    x1, x2 = max(0, x-bw), min(w, x+bw)
    roi = binary[y1:y2, x1:x2]
    total = roi.size
    if total == 0:
        return 0.0
    return float(np.sum(roi > 0)) / total

# ====== 1. 左侧精细X扫描 (step=1, Y=1114 Q1行) ======
print("\n" + "="*70)
print("1. 左侧 Q1行(Y=1114) 精细X扫描 step=1")
print("="*70)
peaks = []
for x in range(100, 1200):
    fill = sample_rect(1114, x, bw=22, bh=14)
    if fill > 0.3:
        peaks.append((x, round(fill, 3)))

if peaks:
    clusters = []
    current = [peaks[0]]
    for i in range(1, len(peaks)):
        if peaks[i][0] - peaks[i-1][0] <= 5:
            current.append(peaks[i])
        else:
            best = max(current, key=lambda p: p[1])
            clusters.append(best)
            current = [peaks[i]]
    if current:
        best = max(current, key=lambda p: p[1])
        clusters.append(best)
    
    print(f"找到 {len(clusters)} 个峰值列:")
    for cx, cf in clusters:
        opt_idx = "ABCDEFG"[(cx - clusters[0][0]) // 115] if clusters and len(clusters) > 1 else "?"
        if clusters:
            spacing = cx - clusters[0][0]
            opt_idx = f"[{spacing//115}]" if 0 <= spacing//115 < 7 else "[?]"
        print(f"  X={cx:4d} fill={cf:.3f} {opt_idx}")

# ====== 2. 右侧精细X扫描 (step=1, Y=1114 Q6行) ======
print("\n" + "="*70)
print("2. 右侧 Q6行(Y=1114) 精细X扫描 step=1")
print("="*70)
peaks = []
for x in range(1250, 1950):
    fill = sample_rect(1114, x, bw=22, bh=14)
    if fill > 0.3:
        peaks.append((x, round(fill, 3)))

if peaks:
    clusters = []
    current = [peaks[0]]
    for i in range(1, len(peaks)):
        if peaks[i][0] - peaks[i-1][0] <= 5:
            current.append(peaks[i])
        else:
            best = max(current, key=lambda p: p[1])
            clusters.append(best)
            current = [peaks[i]]
    if current:
        best = max(current, key=lambda p: p[1])
        clusters.append(best)
    
    print(f"找到 {len(clusters)} 个峰值列:")
    for cx, cf in clusters:
        print(f"  X={cx:4d} fill={cf:.3f}")
else:
    print("无高填充峰值！尝试降低阈值到0.15:")
    for x in range(1250, 1950):
        fill = sample_rect(1114, x, bw=22, bh=14)
        if fill > 0.15:
            peaks.append((x, round(fill, 3)))
    if peaks:
        clusters = []
        current = [peaks[0]]
        for i in range(1, len(peaks)):
            if peaks[i][0] - peaks[i-1][0] <= 5:
                current.append(peaks[i])
            else:
                best = max(current, key=lambda p: p[1])
                clusters.append(best)
                current = [peaks[i]]
        if current:
            best = max(current, key=lambda p: p[1])
            clusters.append(best)
        print(f"找到 {len(clusters)} 个峰值:")
        for cx, cf in clusters:
            print(f"  X={cx:4d} fill={cf:.3f}")

# ====== 3. 右侧多行Y扫描验证 ======
print("\n" + "="*70)
print("3. 右侧 Y扫描 1100~1600 (Q6-Q12区域)")
print("="*70)

# 在几个可能的关键X位置扫Y
test_xs = [1520, 1630]  # 已知的B和C位置
for tx in test_xs:
    print(f"\nX={tx}:")
    rows = []
    for y in range(1100, 1600, 2):
        fill = sample_rect(y, tx, bw=22, bh=14)
        if fill > 0.3:
            rows.append((y, round(fill, 3)))
    if rows:
        for ry, rf in rows:
            print(f"  Y={ry:4d} fill={rf:.3f}")
    else:
        print("  无填充行")

# ====== 4. 左侧 Q13-Q20 区域扫描 (Y=1700~2100) ======
print("\n" + "="*70)
print("4. 左侧 Y=1700~2100 (Q13-Q20区域) 全部7列扫描")
print("="*70)

# 已确认左侧7列: 195+115*n
LEFT_XS = [195 + i*115 for i in range(7)]
for col_x in LEFT_XS:
    opt = "ABCDEFG"[(col_x - 195) // 115]
    rows = []
    for y in range(1700, 2100, 2):
        fill = sample_rect(y, col_x, bw=22, bh=14)
        if fill > 0.25:
            rows.append((y, round(fill, 3)))
    if rows:
        print(f"\n列X={col_x} [{opt}]:")
        for ry, rf in rows:
            print(f"  Y={ry:4d} fill={rf:.3f}")

# ====== 5. 右侧 Q13-Q20 区域扫描 ======
print("\n" + "="*70)
print("5. 右侧 Y=1500~2000 (Q13-Q20? 区域)")
print("="*70)

# 扫描右侧可能的所有列位置
right_test_xs = range(1300, 1950, 30)
fills_found = False
for tx in right_test_xs:
    rows = []
    for y in range(1500, 2000, 2):
        fill = sample_rect(y, tx, bw=22, bh=14)
        if fill > 0.3:
            rows.append((y, round(fill, 3)))
    if rows:
        fills_found = True
        print(f"\nX={tx}:")
        for ry, rf in rows:
            print(f"  Y={ry:4d} fill={rf:.3f}")

if not fills_found:
    print("右侧1500-2000无任何填充（Q13-Q20确实为空）")

# ====== 6. 考号区详细扫描 ======
print("\n" + "="*70)
print("6. 考号区 热力图 (Y=490~700, X=50~2000)")
print("="*70)

# 找考号区精确Y范围
print("\n考号区密集行扫描:")
for y in range(480, 720, 1):
    fills = []
    for x in range(50, 2000, 10):
        fill = sample_rect(y, x, bw=10, bh=6)
        if fill > 0.4:
            fills.append(x)
    if fills:
        print(f"Y={y:4d}: X ranges = {min(fills)}~{max(fills)}, #points={len(fills)}")

# 考号区X列扫描（找每列数字位置）
print("\n考号区 X列扫描 (Y=600区域):")
for x in range(50, 2000, 5):
    fill = sample_rect(600, x, bw=10, bh=20)
    if fill > 0.4:
        print(f"  X={x:4d} fill={fill:.3f}")

print("\n完成!")
