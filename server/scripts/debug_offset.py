"""精确定位透视矫正导致的偏移量"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
import numpy as np
import glob

from app.core.paths import UPLOADS_DIR

debug_dir = str(UPLOADS_DIR / "scans/test")
thresh_files = sorted(glob.glob(os.path.join(debug_dir, "filled_*_debug_thresh.png")))
rect_files = sorted(glob.glob(os.path.join(debug_dir, "filled_*_debug_rectified.png")))
orig_files = sorted(glob.glob(os.path.join(debug_dir, "filled_*.png")))
orig_files = [f for f in orig_files if '_debug_' not in f and '_roi_' not in f]

gray = cv2.imread(thresh_files[-1], cv2.IMREAD_GRAYSCALE)
rect = cv2.imread(rect_files[-1])
orig = cv2.imread(orig_files[-1])
orig_gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
_, orig_bin = cv2.threshold(orig_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

diameter = 40
spacing = 60

mask = np.zeros((diameter, diameter), dtype=np.uint8)
cv2.circle(mask, (diameter//2, diameter//2), diameter//2, 1, thickness=-1)

# Check the ORIGINAL image first to confirm fill IS at B
print("=== 原始图上 Q2 区域 横扫描 ===")
rx, ry = 680, 400
fill_x = rx + 1 * spacing  # 740

for x_off in range(-120, 200, 10):
    test_x = fill_x + x_off
    roi = orig_bin[ry:ry+diameter, test_x:test_x+diameter]
    if roi.shape[0] < diameter or roi.shape[1] < diameter: continue
    black = np.sum((roi < 128) & mask.astype(bool))
    total = np.sum(mask.astype(bool))
    ratio = black / total if total > 0 else 0
    if ratio > 0.05:
        print(f"  偏移{x_off:+4d}px (x={test_x}): ratio={ratio:.4f}")

print("\n=== 阈值(矫正后)图上 Q2 区域 横扫描 ===")
for x_off in range(-120, 200, 10):
    test_x = fill_x + x_off
    roi = gray[ry:ry+diameter, test_x:test_x+diameter]
    if roi.shape[0] < diameter or roi.shape[1] < diameter: continue
    black = np.sum((roi < 128) & mask.astype(bool))
    total = np.sum(mask.astype(bool))
    ratio = black / total if total > 0 else 0
    if ratio > 0.05:
        print(f"  偏移{x_off:+4d}px (x={test_x}): ratio={ratio:.4f}")

# Find peak for each question in threshold image
print("\n=== 阈值图(矫正后) Q1-Q5 实际填充峰位扫描 ===")
questions = [(400,400,"Q1"),(680,400,"Q2"),(960,400,"Q3"),(1240,400,"Q4"),(1520,400,"Q5")]
expected_fills = {"Q1":1,"Q2":1,"Q3":1,"Q4":0,"Q5":1}

for rx, ry, label in questions:
    exp_idx = expected_fills[label]
    exp_fill_x = rx + exp_idx * spacing
    
    # Scan full range
    ratios_scan = []
    for x_off in range(-120, 200, 4):
        test_x = rx + x_off
        roi = gray[ry:ry+diameter, test_x:test_x+diameter]
        if roi.shape[0] < diameter or roi.shape[1] < diameter: continue
        black = np.sum((roi < 128) & mask.astype(bool))
        total = np.sum(mask.astype(bool))
        ratio = black / total if total > 0 else 0
        ratios_scan.append((x_off, test_x, ratio))
    
    # Find peaks (local maxima)
    peaks = []
    for i in range(1, len(ratios_scan)-1):
        if ratios_scan[i][2] > ratios_scan[i-1][2] and ratios_scan[i][2] > ratios_scan[i+1][2] and ratios_scan[i][2] > 0.15:
            peaks.append(ratios_scan[i])
    
    peaks.sort(key=lambda p: -p[2])
    if peaks:
        best = peaks[0]
        actual_opt_idx = (best[1] - rx) / spacing
        print(f"  {label}: 期望B({exp_fill_x}) 实际峰x={best[1]}(偏移={best[0]:+d}) ratio={best[2]:.4f} 对应选项索引={actual_opt_idx:.1f}")
    else:
        print(f"  {label}: 未检测到有效填充")

# Also check: is the issue in the anchor detection itself?
print("\n=== 锚点检测验证 ===")
from app.services.omr_scanner import rectify_perspective, _find_anchor_blocks
from app.services.printable_sheet_constants import ANCHOR_MIN_AREA

img = cv2.imread(orig_files[-1])
gray_orig_inv = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh_inv = cv2.threshold(gray_orig_inv, 128, 255, cv2.THRESH_BINARY_INV)
contours, _ = cv2.findContours(thresh_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

anchors = _find_anchor_blocks(contours, int(ANCHOR_MIN_AREA))
print(f"  找到 {len(anchors)} 个锚点:")
if len(anchors) >= 4:
    # Sort them properly
    from app.services.omr_scanner import _sort_anchors
    anchors_sorted = _sort_anchors(anchors[:4])
    for i, (name, exp) in enumerate([("TL",(50,50)),("TR",(2230,50)),("BR",(2230,3258)),("BL",(50,3258))]):
        p = anchors_sorted[i]
        dx, dy = int(p[0]) - exp[0], int(p[1]) - exp[1]
        print(f"  {name}: 实测({int(p[0])},{int(p[1])}) 理论({exp[0]},{exp[1]}) 误差(dx={dx},dy={dy})")
