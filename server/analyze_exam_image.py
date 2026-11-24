"""分析测试答题卡图片"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np

image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "exam.jpg")
img = cv2.imread(image_path)
if img is None:
    print(f"ERROR: 无法读取图像 {image_path}")
    sys.exit(1)

h, w = img.shape[:2]
print(f"图像尺寸: {w}x{h}")
print(f"宽高比: {w/h:.4f} (A4参考: {2480/3508:.4f})")

# 灰度
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# 检测边框
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
for low, high in [(50, 150), (30, 100), (75, 200)]:
    edges = cv2.Canny(blurred, low, high)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    
    min_area = h * w * 0.03
    found = False
    for cnt in contours[:5]:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        print(f"  Canny({low},{high}): 轮廓 area={area:.0f} ({area/(h*w)*100:.1f}%) vertices={len(approx)} peri={peri:.0f}")
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            print(f"    四边形角点: {pts.tolist()}")
            found = True
            break
    if found:
        break

# 透视矫正到 A4
from app.services.printable_sheet_constants import A4_WIDTH, A4_HEIGHT
from app.services.omr_scanner import _find_sheet_corners, _sort_corners, _rectify, _binary_inv

rectified, rect_ok = _rectify(img)
print(f"\n透视矫正: {'成功' if rect_ok else '未矫正'}")
print(f"矫正后尺寸: {rectified.shape[1]}x{rectified.shape[0]}")

# 二值化
gray_r = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
binary_inv = _binary_inv(gray_r)
white_pct = cv2.countNonZero(binary_inv) / binary_inv.size * 100
print(f"二值化: {white_pct:.1f}% 白色像素（墨迹）")

# 保存矫正后的图片供查看
debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "exam_rectified.jpg")
cv2.imwrite(debug_path, rectified)
print(f"矫正图已保存: {debug_path}")

# 保存二值化图
binary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "exam_binary.jpg")
cv2.imwrite(binary_path, binary_inv * 255 if binary_inv.max() <= 1 else binary_inv)
print(f"二值化图已保存: {binary_path}")

# 检查数据库中的试卷配置
print("\n=== 检查数据库中的试卷配置 ===")
try:
    from app.core.database import engine
    from sqlalchemy import text
    import asyncio
    
    async def check_db():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import Session
        
        # 使用同步连接检查
        sync_engine = create_async_engine("sqlite:///./data/exam.db")
        async with sync_engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT id, title, answer_sheet_config FROM teacher_exams LIMIT 10"
            ))
            rows = result.fetchall()
            for row in rows:
                eid, title, config = row
                if config:
                    import json
                    cfg = json.loads(config) if isinstance(config, str) else config
                    has_coord = "coordinate_config" in cfg if cfg else False
                    print(f"  试卷{id}: {title} 有坐标配置={has_coord}")
                    if has_coord:
                        coord = cfg.get("coordinate_config", {})
                        print(f"    canvas={coord.get('canvas_width')}x{coord.get('canvas_height')}")
                        print(f"    题目数={len(coord.get('question_regions', []))}")
                        print(f"    考号区={coord.get('exam_number_area', {})}")
                else:
                    print(f"  试卷{eid}: {title} 无配置")
    
    asyncio.run(check_db())
except Exception as e:
    print(f"  数据库检查失败: {e}")
