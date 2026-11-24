"""调试 OMR ROI：检查阈值图中每个选项圆圈的实际像素"""
import cv2
import numpy as np
import os
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import UPLOADS_DIR

def create_circle_mask(diameter):
    radius = diameter // 2
    mask = np.zeros((diameter, diameter), dtype=np.uint8)
    cv2.circle(mask, (radius, radius), radius, 1, thickness=-1)
    return mask.astype(bool)

def check_roi(gray, x, y, diameter, spacing, option_count, label):
    """检查指定位置每个选项的填充比"""
    print(f"\n  [{label}] region=({x},{y})")
    for opt_idx in range(option_count):
        ox = x + opt_idx * spacing
        oy = y
        roi = gray[oy:oy + diameter, ox:ox + diameter]
        if roi.shape[0] < diameter or roi.shape[1] < diameter:
            print(f"    {chr(65+opt_idx)}: ROI越界 ({roi.shape})")
            continue
        
        mask = create_circle_mask(diameter)
        black = np.sum((roi < 128) & mask[:roi.shape[0], :roi.shape[1]])
        total = np.sum(mask[:roi.shape[0], :roi.shape[1]])
        ratio = black / total if total > 0 else 0
        
        # 检查ROI四角值
        corners = f"tl={roi[0,0]} tr={roi[0,-1]} bl={roi[-1,0]} br={roi[-1,-1]}"
        center_val = roi[diameter//2, diameter//2]
        print(f"    {chr(65+opt_idx)}: x={ox} ratio={ratio:.4f} center={center_val} {corners}")

# 查找最新的调试图
debug_dir = str(UPLOADS_DIR / "scans/test")
thresh_files = sorted(glob.glob(os.path.join(debug_dir, "filled_*_debug_thresh.png")))
rectified_files = sorted(glob.glob(os.path.join(debug_dir, "filled_*_debug_rectified.png")))

if not thresh_files:
    print("未找到调试图")
    exit()

thresh_path = thresh_files[-1]  # 最新的
rectified_path = rectified_files[-1] if rectified_files else None
print(f"阈值图: {thresh_path}")
if rectified_path:
    print(f"矫正图: {rectified_path}")

gray = cv2.imread(thresh_path, cv2.IMREAD_GRAYSCALE)
rect = cv2.imread(rectified_path) if rectified_path else None

if gray is None:
    print("无法读取阈值图")
    exit()

print(f"图像尺寸: {gray.shape} (HxW)")
print(f"唯一像素值: {np.unique(gray)}")

# 检查各区域
diameter = 40
spacing = 60
regions = [
    (400, 400, "Q1"),
    (680, 400, "Q2"),
    (960, 400, "Q3"),
    (1240, 400, "Q4"),
    (1520, 400, "Q5"),
]

# 每个选项的预期填充偏移（相对于region起始）
# Q1: B, Q2: B, Q3: B, Q4: A, Q5: B
fills = {
    "Q1": 1,  # B: idx=1
    "Q2": 1,  # B: idx=1
    "Q3": 1,  # B: idx=1
    "Q4": 0,  # A: idx=0
    "Q5": 1,  # B: idx=1
}

for rx, ry, label in regions:
    fill_idx = fills[label]
    # 选项检查（A, B, C, D）
    check_roi(gray, rx, ry, diameter, spacing, 4, label)
    
    # 额外的: 也检查填充位置周围像素
    fx = rx + fill_idx * spacing
    # 填充圆圈的中心应该在 fx+20, ry+20（40px圆圈中心）
    center_x, center_y = fx + 20, ry + 20
    print(f"    填充期望位置: ({fx},{ry}) 中心=({center_x},{center_y}) gray[{center_y},{center_x}]={gray[center_y, center_x]}")

print("\n\n=== 检查考号区域 ===")
# 考号区域
exam_x, exam_y = 400, 200
for digit_idx in range(4):
    dx = exam_x + digit_idx * 80 + 80
    for opt_idx in range(10):
        ox = dx + opt_idx * 50
        oy = exam_y + 20 + 30  # label_y + 30
        if oy + 28 < gray.shape[0] and ox + 28 < gray.shape[1]:
            roi_28 = gray[oy:oy+28, ox:ox+28]
            black_28 = np.sum(roi_28 < 128)
            if black_28 > 30:  # 有填充
                print(f"  第{digit_idx+1}位 数字{opt_idx}: x={ox} y={oy} black_px={black_28}/{784}")

# 保存ROI可视化
if rect is not None:
    vis = rect.copy()
    for rx, ry, label in regions:
        cv2.rectangle(vis, (rx, ry-25), (rx + spacing*4 + 20, ry + diameter + 5), (0, 255, 0), 1)
        # 每个选项圆圈
        for opt_idx in range(4):
            ox = rx + opt_idx * spacing
            cv2.rectangle(vis, (ox, ry), (ox + diameter, ry + diameter), (0, 0, 255), 1)
            cv2.putText(vis, chr(65+opt_idx), (ox+5, ry-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
    
    # 额外: 在填充位置画大圈
    for idx, (rx, ry, label) in enumerate(regions):
        fill_idx = fills[label] if label != "Q4" else 0
        fx = rx + fill_idx * spacing
        cv2.circle(vis, (fx + 20, ry + 20), 22, (255, 0, 0), 2)
    
    vis_path = thresh_path.replace("_debug_thresh.png", "_roi_overlay.png")
    cv2.imwrite(vis_path, vis)
    print(f"\nROI可视化已保存: {vis_path}")

# 检查原始fill图像（未矫正前的）对应的区域
print("\n\n=== 原始图像(未矫正) ===")
filled_path = thresh_path.replace("_debug_thresh.png", "").replace("filled_", "filled_")
# 实际文件名去掉_debug后缀
base_filled = thresh_path.replace("_debug_thresh.png", ".png")
print(f"原始填涂图: {base_filled}")
orig = cv2.imread(base_filled)
if orig is not None:
    orig_gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    _, orig_bin = cv2.threshold(orig_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    print("\n  -- 原始图上Q2选项区 --")
    rx, ry = 680, 400
    for opt_idx in range(4):
        ox = rx + opt_idx * spacing
        roi = orig_bin[ry:ry+diameter, ox:ox+diameter]
        mask = create_circle_mask(diameter)
        black = np.sum((roi < 128) & mask[:roi.shape[0], :roi.shape[1]])
        total = np.sum(mask[:roi.shape[0], :roi.shape[1]])
        ratio = black / total if total > 0 else 0
        print(f"    {chr(65+opt_idx)}: x={ox} ratio={ratio:.4f}")
else:
    print("无法读取原始图")
