"""精确测量考号区每个圆圈的中心位置"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
import cv2
import numpy as np

TEMPLATE = os.path.join(os.path.dirname(__file__), "uploads", "answer_sheets", "5_a4.png")
img = cv2.imread(TEMPLATE)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape[:2]

# 提取考号区域
exam = gray[200:300, 400:1200]
_, exam_bin = cv2.threshold(exam, 128, 255, cv2.THRESH_BINARY_INV)

# Hough圆检测考号区的圆圈
circles = cv2.HoughCircles(
    exam, cv2.HOUGH_GRADIENT, dp=1, minDist=10,
    param1=30, param2=8, minRadius=10, maxRadius=18)

if circles is not None:
    circles = np.uint16(np.around(circles))
    all_circles = []
    for cx, cy, r in circles[0]:
        all_circles.append((int(cx) + 400, int(cy) + 200, int(r)))
    all_circles.sort(key=lambda c: (c[1], c[0]))  # sort by y then x
    
    print("Detected %d circles in exam number zone:" % len(all_circles))
    for cx, cy, r in all_circles:
        print("  cx=%d cy=%d r=%d" % (cx, cy, r))
else:
    print("No circles detected with HoughCircles.")

# 备选：轮廓检测
cnts, _ = cv2.findContours(exam_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
circle_contours = []
for c in cnts:
    area = cv2.contourArea(c)
    if 200 < area < 800:  # 约为28px直径圆的范围
        x, y, cw, ch = cv2.boundingRect(c)
        cx = x + cw//2 + 400
        cy = y + ch//2 + 200
        aspect = cw / max(ch, 1)
        if 0.6 < aspect < 1.5:
            circle_contours.append((cx, cy, cw, ch, area))
            
circle_contours.sort(key=lambda c: (c[1], c[0]))
print("\nContour-based circles in exam zone (%d found):" % len(circle_contours))
for cx, cy, cw, ch, area in circle_contours:
    print("  cx=%d cy=%d w=%d h=%d area=%d" % (cx, cy, cw, ch, area))
