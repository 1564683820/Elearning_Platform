"""诊断模板图片上的所有黑色区块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
import cv2
import numpy as np

TEMPLATE = os.path.join(os.path.dirname(__file__), "uploads", "answer_sheets", "5_a4.png")
img = cv2.imread(TEMPLATE)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape[:2]
print("Template size: %dx%d" % (w, h))

# 固定阈值二值化 - 更适合纯白背景的矢量图
_, binary_fixed = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

# OTSU
_, binary_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

print("\nFixed thr=100: white pixels = %d (%.2f%%)" % (
    cv2.countNonZero(binary_fixed),
    cv2.countNonZero(binary_fixed) / binary_fixed.size * 100))
print("OTSU: white pixels = %d (%.2f%%)" % (
    cv2.countNonZero(binary_otsu),
    cv2.countNonZero(binary_otsu) / binary_otsu.size * 100))

# 检测左侧边缘(10-100px)的黑色方块（Dino行标记应该在这里）
left_strip = binary_fixed[:, 10:100]
n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(left_strip, connectivity=8)
print("\nFixed thr=100 - Left edge (10-100px) connected components:")
for i in range(1, n_labels):
    area = stats[i, cv2.CC_STAT_AREA]
    x = stats[i, cv2.CC_STAT_LEFT] + 10
    y = stats[i, cv2.CC_STAT_TOP]
    cy = int(centroids[i][1])
    if area > 100:
        print("  x=%d y=%d cy=%d area=%d" % (x, y, cy, area))

# 检测顶部边缘(10-100px)的黑色方块（Dino列标记应该在这里）
top_strip = binary_fixed[10:100, :]
n_labels_t, labels_t, stats_t, centroids_t = cv2.connectedComponentsWithStats(top_strip, connectivity=8)
print("\nFixed thr=100 - Top edge (10-100px) connected components:")
for i in range(1, n_labels_t):
    area = stats_t[i, cv2.CC_STAT_AREA]
    x = stats_t[i, cv2.CC_STAT_LEFT]
    y = stats_t[i, cv2.CC_STAT_TOP] + 10
    if area > 100:
        print("  x=%d y=%d area=%d" % (x, y, area))

# 检查考号区域
print("\n--- Exam number zone ---")
# 提取考号区域 (Y=200~310, X=400~900)
exam_zone = binary_fixed[200:310, 400:1000]
n_labels_e, labels_e, stats_e, centroids_e = cv2.connectedComponentsWithStats(exam_zone, connectivity=8)
print("Exam zone (Y200-310, X400-1000) components with area>50:")
for i in range(1, n_labels_e):
    area = stats_e[i, cv2.CC_STAT_AREA]
    x = stats_e[i, cv2.CC_STAT_LEFT] + 400
    y = stats_e[i, cv2.CC_STAT_TOP] + 200
    if area > 50:
        print("  x=%d y=%d area=%d" % (x, y, area))

# 检查原图考号区域的黑色像素位置
exam_region_gray = gray[200:310, 400:1000]
black_mask = exam_region_gray < 100
black_coords = np.where(black_mask)
if len(black_coords[0]) > 0:
    print("\nExam zone black pixel bounding box:")
    print("  Y range: %d - %d" % (black_coords[0].min() + 200, black_coords[0].max() + 200))
    print("  X range: %d - %d" % (black_coords[1].min() + 400, black_coords[1].max() + 400))
    
# 详细检查：在考号区找水平投影
for dy in range(0, 110, 10):
    row_sum = np.sum(black_mask[dy:min(dy+10, 110), :])
    if row_sum > 0:
        print("  Y=%d-%d: %d black pixels" % (200+dy, 200+min(dy+10, 110), row_sum))
