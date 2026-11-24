"""检测答题卡上的选项圈位置，推断坐标布局"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
from app.services.omr_scanner import _load_image, _rectify, _binary_inv, _sample_circle_fill
from app.services.printable_sheet_constants import A4_WIDTH, A4_HEIGHT, FILL_THRESHOLD

image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "exam.jpg")
img = _load_image(image_path)
rectified, _ = _rectify(img)
gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
binary_inv = _binary_inv(gray)

h, w = gray.shape[:2]
print(f"矫正后尺寸: {w}x{h}")

# 用 HoughCircles 检测所有圆圈
# 参数需要调优：dp, minDist, param1, param2, minRadius, maxRadius
circles = cv2.HoughCircles(
    gray, cv2.HOUGH_GRADIENT,
    dp=1.0,
    minDist=30,
    param1=100,
    param2=15,
    minRadius=10,
    maxRadius=25,
)

if circles is None:
    print("未检测到圆圈，尝试调整参数...")
    # 降低阈值重试
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT,
        dp=1.0,
        minDist=25,
        param1=80,
        param2=12,
        minRadius=8,
        maxRadius=28,
    )

if circles is not None:
    circles = np.round(circles[0]).astype(int)
    print(f"检测到 {len(circles)} 个圆圈")
    
    # 按Y坐标聚类（找行）
    ys = circles[:, 1]
    xs = circles[:, 0]
    
    # 按Y排序，聚类
    sorted_idx = np.argsort(ys)
    sorted_circles = circles[sorted_idx]
    
    # 聚类：Y坐标相差 < 30 视为同一行
    rows = []
    current_row = [sorted_circles[0]]
    for i in range(1, len(sorted_circles)):
        if abs(sorted_circles[i][1] - current_row[-1][1]) < 30:
            current_row.append(sorted_circles[i])
        else:
            rows.append(current_row)
            current_row = [sorted_circles[i]]
    rows.append(current_row)
    
    print(f"\n共 {len(rows)} 行:")
    for ri, row in enumerate(rows):
        row_sorted = sorted(row, key=lambda c: c[0])
        y_avg = np.mean([c[1] for c in row])
        xs_str = [str(c[0]) for c in row_sorted]
        
        # 检查每个圆圈的填涂情况
        fills = []
        for c in row_sorted:
            fill = _sample_circle_fill(binary_inv, c[0], c[1], c[2] * 2)
            fills.append(fill)
        
        filled_str = " ".join([f"{'*' if f > FILL_THRESHOLD else '.'}" for f in fills])
        print(f"  行{ri:2d}: y={y_avg:.0f} 共{len(row)}个圆圈 x={xs_str}")
        print(f"         填涂: [{filled_str}]")
        print(f"         填充值: {[f'{f:.3f}' for f in fills]}")
else:
    print("未检测到任何圆圈!")
    
    # 尝试用轮廓检测
    print("\n尝试用轮廓检测...")
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    circle_like = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 100 < area < 2000:
            (cx, cy), r = cv2.minEnclosingCircle(cnt)
            # 检查是否近似圆形
            peri = cv2.arcLength(cnt, True)
            if peri > 0:
                circularity = 4 * np.pi * area / (peri * peri)
                if circularity > 0.5:
                    circle_like.append((int(cx), int(cy), int(r)))
    
    print(f"轮廓检测到 {len(circle_like)} 个圆形")
