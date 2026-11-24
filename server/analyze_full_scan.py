# -*- coding: utf-8 -*-
"""全图密集扫描，找出所有高填充区域，推断答题卡真实布局"""
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
    print("Image:", bw.shape)

    # 全图扫描：X方向每10px，Y方向每5px
    BOX_W = 40
    BOX_H = 30
    STEP_X = 20
    STEP_Y = 5
    THRESHOLD = 0.4

    H, W = bw.shape
    hits = []  # (x, y, fill)

    for y in range(200, H, STEP_Y):
        for x in range(50, W, STEP_X):
            f = fill_ratio(bw, x, y, BOX_W, BOX_H)
            if f >= THRESHOLD:
                hits.append((x, y, round(f, 2)))

    print(f"\nTotal hits (fill >= {THRESHOLD}): {len(hits)}")

    # 按Y聚类
    hits_sorted = sorted(hits, key=lambda h: h[1])
    clusters = []
    for x, y, f in hits_sorted:
        if clusters and abs(y - clusters[-1][-1][-1]) <= 15:
            clusters[-1].append((x, y, f))
        else:
            clusters.append([(x, y, f)])

    print(f"\nY-clusters: {len(clusters)}")
    for i, cl in enumerate(clusters):
        ys = [h[1] for h in cl]
        xs = [h[0] for h in cl]
        fs = [h[2] for h in cl]
        y_med = int(np.median(ys))
        x_min, x_max = min(xs), max(xs)
        f_max = max(fs)
        # 找最高填充的X
        best_hit = max(cl, key=lambda h: h[2])
        print(f"  Cluster {i:3d}: Y={y_med:4d}  X=[{x_min:4d}~{x_max:4d}]  hits={len(cl):3d}  max_fill={f_max:.2f}  best_X={best_hit[0]}")

    # 按X聚类（找列）
    print("\n=== X-axis column analysis ===")
    hits_by_x = sorted(hits, key=lambda h: h[0])
    x_clusters = []
    for x, y, f in hits_by_x:
        if x_clusters and abs(x - x_clusters[-1][-1][0]) <= 25:
            x_clusters[-1].append((x, y, f))
        else:
            x_clusters.append([(x, y, f)])

    print(f"X-clusters: {len(x_clusters)}")
    for i, cl in enumerate(x_clusters):
        xs = [h[0] for h in cl]
        ys = [h[1] for h in cl]
        x_med = int(np.median(xs))
        y_min, y_max = min(ys), max(ys)
        print(f"  X-Cluster {i:3d}: X={x_med:4d}  Y=[{y_min:4d}~{y_max:4d}]  hits={len(cl):3d}")

if __name__ == "__main__":
    main()
