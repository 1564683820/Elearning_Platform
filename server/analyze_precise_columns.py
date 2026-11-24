# -*- coding: utf-8 -*-
"""精确列定位 - 在每个已知答案行做step=1 X扫描，映射全部7列选项"""
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
        tl, tr, br, bl = pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]
        dst_pts = np.float32([[0, 0], [2480, 0], [2480, 3508], [0, 3508]])
        M = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), dst_pts)
        warped = cv2.warpPerspective(img, M, (2480, 3508))
        gray_w = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray_w, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return warped, binary, gray_w
    return img, None, None

print("Loading and rectifying...")
warped, binary, gray = load_and_rectify(IMG_PATH)
h, w = binary.shape
print(f"Rectified: {h}x{w}")

def sample_rect(y, x, bw=22, bh=14):
    y1, y2 = max(0, y-bh), min(h, y+bh)
    x1, x2 = max(0, x-bw), min(w, x+bw)
    roi = binary[y1:y2, x1:x2]
    total = roi.size
    if total == 0:
        return 0.0
    return float(np.sum(roi > 0)) / total

def scan_x_line(y, x_start, x_end, step=1, bw=22, bh=14, threshold=0.35):
    """扫描一行中所有峰值列位置"""
    peaks = []
    for x in range(x_start, x_end, step):
        fill = sample_rect(y, x, bw, bh)
        if fill > threshold:
            peaks.append((x, round(fill, 3)))
    
    results = []
    for px, pf in peaks:
        results.append({"x": px, "fill": pf})
    
    # 聚类
    if not results:
        return []
    
    clusters = []
    current = [results[0]]
    for i in range(1, len(results)):
        if results[i]["x"] - results[i-1]["x"] <= 8:
            current.append(results[i])
        else:
            best = max(current, key=lambda r: r["fill"])
            clusters.append(best)
            current = [results[i]]
    if current:
        best = max(current, key=lambda r: r["fill"])
        clusters.append(best)
    
    return clusters

# ====== 策略：在每行已知答案处扫描，收集全部列中心X ======
# 已知答案及所在行Y（从dense_yscan确认）
KNOWN_ANSWERS_LEFT = {
    "Q1_B": 1114, "Q2_C": 1196, "Q3_B": 1274, "Q4_C": 1354, "Q5_B": 1436,
    "Q11_A": 1577, "Q12_D": 1658,
    "Q21_E": 2039, "Q22_G": 2120, "Q23_D": 2198, "Q24_F": 2279, "Q25_C": 2357
}

KNOWN_ANSWERS_RIGHT = {
    "Q6_B": 1128, "Q7_C": 1208, "Q8_B": 1284, "Q9_C": 1364, "Q10_C": 1442
}

# 先收集所有左侧峰值列X
left_all_x = {}
for qinfo, y_pos in sorted(KNOWN_ANSWERS_LEFT.items(), key=lambda x: x[1]):
    qname, opt = qinfo.split("_")
    clusters = scan_x_line(y_pos, 80, 1200, step=1, threshold=0.35)
    if clusters:
        for c in clusters:
            cx = c["x"]
            if cx not in left_all_x or c["fill"] > left_all_x[cx]["fill"]:
                left_all_x[cx] = {"x": cx, "fill": c["fill"], "found_at": qinfo}
        print(f"{qinfo} @ Y={y_pos}: {len(clusters)} peaks -> {[(c['x'], c['fill']) for c in clusters]}")

print(f"\n左侧去重列中心X: {sorted(left_all_x.keys())}")

# 收集右侧峰值列X
right_all_x = {}
for qinfo, y_pos in sorted(KNOWN_ANSWERS_RIGHT.items(), key=lambda x: x[1]):
    qname, opt = qinfo.split("_")
    clusters = scan_x_line(y_pos, 1250, 2000, step=1, threshold=0.35)
    if clusters:
        for c in clusters:
            cx = c["x"]
            if cx not in right_all_x or c["fill"] > right_all_x[cx]["fill"]:
                right_all_x[cx] = {"x": cx, "fill": c["fill"], "found_at": qinfo}
        print(f"{qinfo} @ Y={y_pos}: {len(clusters)} peaks -> {[(c['x'], c['fill']) for c in clusters]}")

print(f"\n右侧去重列中心X: {sorted(right_all_x.keys())}")

# ====== 增量X扫描：在已知列附近密集扫描找未发现的列 ======
print("\n" + "="*60)
print("增量扫描：已知列之间的空缺列")

# 左侧: 已知 333(B), 655(E), 885(G) -> 缺 A,C,D,F
# 在Y=1114行用更低阈值扫描
print("\n左侧低阈值扫描 Y=1114 (threshold=0.15, X=100-1200):")
all_peaks = scan_x_line(1114, 100, 1200, step=1, threshold=0.15)
# 过滤已知列
for p in all_peaks:
    px = p["x"]
    if px not in left_all_x:
        print(f"  NEW X={px} fill={p['fill']}")

# 同样扫描Y=1577 (Q11行) 看能否找到A列
print("\n左侧 Y=1577 低阈值扫描 (threshold=0.15, X=100-1200):")
all_peaks = scan_x_line(1577, 100, 1200, step=1, threshold=0.15)
for p in all_peaks:
    px = p["x"]
    if px not in left_all_x:
        left_all_x[px] = {"x": px, "fill": p["fill"], "found_at": "Y1577_low"}
        print(f"  NEW X={px} fill={p['fill']}")

# 扫描Y=2120 (Q22=G行)
print("\n左侧 Y=2120 低阈值扫描 (threshold=0.15, X=100-1200):")
all_peaks = scan_x_line(2120, 100, 1200, step=1, threshold=0.15)
for p in all_peaks:
    px = p["x"]
    if px not in left_all_x:
        left_all_x[px] = {"x": px, "fill": p["fill"], "found_at": "Y2120_low"}
        print(f"  NEW X={px} fill={p['fill']}")

# 右侧: 已知 1520(B), 1630(C) -> 缺 A,D,E,F,G
print("\n右侧低阈值扫描 Y=1114 (threshold=0.15, X=1250-2000):")
all_peaks = scan_x_line(1114, 1250, 2000, step=1, threshold=0.15)
for p in all_peaks:
    px = p["x"]
    if px not in right_all_x:
        right_all_x[px] = {"x": px, "fill": p["fill"], "found_at": "Y1114_low"}
        print(f"  NEW X={px} fill={p['fill']}")

print("\n右侧 Y=1442 低阈值扫描 (threshold=0.15, X=1250-2000):")
all_peaks = scan_x_line(1442, 1250, 2000, step=1, threshold=0.15)
for p in all_peaks:
    px = p["x"]
    if px not in right_all_x:
        right_all_x[px] = {"x": px, "fill": p["fill"], "found_at": "Y1442_low"}
        print(f"  NEW X={px} fill={p['fill']}")

# ====== 结果汇总 ======
print("\n" + "="*60)
print("最终列定位结果")
print("="*60)

left_sorted = sorted(left_all_x.keys())
print(f"\n左侧 {len(left_sorted)} 列:")
for i, x in enumerate(left_sorted):
    info = left_all_x[x]
    spacing = x - left_sorted[0] if left_sorted else 0
    opt_label = "ABCDEFG"[i] if i < 7 else "?"
    print(f"  [{opt_label}] X={x:4d} fill={info['fill']:.3f} found@{info['found_at']} (offset={spacing})")

right_sorted = sorted(right_all_x.keys())
print(f"\n右侧 {len(right_sorted)} 列:")
for i, x in enumerate(right_sorted):
    info = right_all_x[x]
    spacing = x - right_sorted[0]
    opt_label = "ABCDEFG"[i] if i < 7 else "?"
    print(f"  [{opt_label}] X={x:4d} fill={info['fill']:.3f} found@{info['found_at']} (offset={spacing})")

# ====== 考号区详细扫描 ======
print("\n" + "="*60)
print("考号区精细扫描")
print("="*60)

# 考号区有两块：左块(约X=90~220)和右块(约X=1320~1960)
# 扫描左块：每个数字0-9的列位置
print("\n考号区左块 (Y=535~535区间的列扫描):")
for y_test in [510, 530, 535, 580, 600]:
    print(f"\nY={y_test}:")
    peaks = scan_x_line(y_test, 50, 350, step=1, bw=10, bh=10, threshold=0.35)
    for p in peaks:
        print(f"  X={p['x']:4d} fill={p['fill']:.3f}")

# 扫描右块
print("\n考号区右块(Y=530~615区间的列扫描):")
for y_test in [530, 560, 580, 600, 615]:
    print(f"\nY={y_test}:")
    peaks = scan_x_line(y_test, 1300, 1960, step=1, bw=10, bh=10, threshold=0.35)
    for p in peaks:
        print(f"  X={p['x']:4d} fill={p['fill']:.3f}")

print("\n完成!")
