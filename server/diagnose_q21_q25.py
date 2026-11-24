# -*- coding: utf-8 -*-
"""诊断Q21-Q25：用omr_scanner自身的rectify后，精扫Y位置"""
import cv2
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.omr_scanner import (
    _load_image, _rectify, _binary_inv, _sample_rect_fill, REAL_SHEET_COORDINATES
)

img = _load_image(r"tests\exam.jpg")
rectified, _ = _rectify(img)
gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
binary = _binary_inv(gray)
print(f"Rectified: {binary.shape}")

left_cols = REAL_SHEET_COORDINATES["left_columns"]
labels = ['A','B','C','D','E','F','G']

# 对Q21-Q25每个题，在附近Y范围扫描找最佳填充位置
# 已知答案：Q21=E(667), Q22=G(897), Q23=D(557), Q24=F(778), Q25=C(443)
expected_map = {21: (667, 'E'), 22: (897, 'G'), 23: (557, 'D'), 24: (778, 'F'), 25: (443, 'C')}

y_starts = {21: 2020, 22: 2100, 23: 2180, 24: 2260, 25: 2340}
y_ends =   {21: 2080, 22: 2160, 23: 2240, 24: 2320, 25: 2400}

for qn in [21, 22, 23, 24, 25]:
    exp_col_x, exp_label = expected_map[qn]
    y_start, y_end = y_starts[qn], y_ends[qn]
    
    print(f"\nQ{qn} (expected={exp_label}, colX={exp_col_x}):")
    print(f"  Y range {y_start}-{y_end}:")
    
    best_y, best_fill = 0, 0
    for y in range(y_start, y_end, 1):
        fill = _sample_rect_fill(binary, exp_col_x, y, box_w=44, box_h=30)
        if fill > best_fill:
            best_fill = fill
            best_y = y
    
    # 在最佳Y位置扫描所有列
    print(f"  最佳Y={best_y}, fill={best_fill:.3f}")
    print(f"  全部列在Y={best_y}:")
    all_scores = {}
    for oi, col_x in enumerate(left_cols):
        fill = _sample_rect_fill(binary, col_x, best_y, box_w=44, box_h=30)
        all_scores[labels[oi]] = round(fill, 3)
    
    for opt, f in sorted(all_scores.items(), key=lambda x: x[1], reverse=True):
        marker = " <--" if opt == exp_label else ""
        print(f"    {opt}: {f:.3f}{marker}")

# 也检查当前配置中的Y值扫描结果
print("\n" + "="*50)
print("当前配置Y值的扫描结果:")
for q in REAL_SHEET_COORDINATES["questions"]:
    qn = q["number"]
    if qn >= 21:
        row_y = q["row_y"]
        side = q["side"]
        cols = left_cols if side == "left" else REAL_SHEET_COORDINATES["right_columns"]
        scores = {}
        for oi, col_x in enumerate(cols):
            fill = _sample_rect_fill(binary, col_x, row_y, box_w=44, box_h=30)
            scores[labels[oi]] = round(fill, 3)
        exp = expected_map.get(qn, (0, '?'))[1]
        best = max(scores, key=scores.get)
        print(f"  Q{qn} Y={row_y}: best={best}({scores[best]:.3f}) exp={exp} {'OK' if best==exp else 'X'}")
