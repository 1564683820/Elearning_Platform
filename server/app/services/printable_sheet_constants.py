# 答题卡生成与 OMR 识别共用常量
# 所有坐标参数必须保持生成与识别一致

# ── 布局参数 ──
ITEMS_PER_ROW = 5          # 每行放5道题
OPTION_SPACING = 60        # 选项横向间距(px)
CIRCLE_DIAMETER = 40       # 选项圆圈直径(px)
CIRCLE_RADIUS = 20         # 选项圆圈半径
START_X = 400              # 第一题起始X坐标
START_Y = 400              # 第一题起始Y坐标
ROW_SPACING = 120          # 行间距(px)
OPTION_LABEL_OFFSET_X = 12  # 选项字母相对圆圈左边缘偏移
OPTION_LABEL_OFFSET_Y = 8   # 选项字母相对圆圈上边缘偏移
QUESTION_NUM_OFFSET_Y = 30  # 题号相对选项行上边缘偏移

# ── 四角定位块 ──
ANCHOR_SIZE = 50           # 定位块边长(px)
ANCHOR_MIN_AREA = 500      # 定位块最小轮廓面积(用于识别过滤)
ANCHOR_POSITIONS = {
    "top_left":     (50, 50),
    "top_right":    (2230, 50),
    "bottom_left":  (50, 3258),
    "bottom_right": (2230, 3258),
}

# ── CSDN 式行/列锚点块（答题卡左边缘与上边缘） ──
# 参考 CSDN「opencv +python采集识别填涂卡数据」中的 anchor block 方法
# 左侧锚点：每行开头一个小黑方块，用于动态检测行 Y 位置
# 顶部锚点：每列开头一个小黑方块，用于动态检测列 X 位置
# 这些锚点位于 canvas 虚拟坐标 (800x1100) 系统上，实际扫描时会被缩放

ROW_ANCHOR_X = 6            # 左侧行锚点的 X 坐标 (canvas 虚拟坐标)
ROW_ANCHOR_BLOCK_SIZE = 10  # 行锚点方块尺寸 (canvas 虚拟坐标)
ROW_ANCHOR_OFFSET_Y = 5     # 行锚点相对行起始的 Y 偏移

COL_ANCHOR_Y = 195          # 顶部列锚点的 Y 坐标 (canvas 虚拟坐标)
COL_ANCHOR_BLOCK_SIZE = 10  # 列锚点方块尺寸 (canvas 虚拟坐标)
COL_ANCHOR_OFFSET_X = 5     # 列锚点相对列起始的 X 偏移

# CSDN 填涂判定参数
CSDN_FILL_DIFF_THRESHOLD = 0.15  # max-min 差值阈值(归一化后)，低于此视为空题
CSDN_ROI_PADDING = 0.3           # ROI 区域相对于锚点间距的缩放比例，用于裁剪填涂区域

# A4@300dpi 标准尺寸
A4_WIDTH = 2480
A4_HEIGHT = 3508

# ── 考号区域 ──
EXAM_NUMBER_Y = 200        # 考号区域Y坐标
EXAM_NUMBER_DIGITS = 4     # 考号位数
EXAM_NUMBER_SPACING = 80   # 每位数字的间距
EXAM_NUMBER_X_START = 400  # 考号区域X起始
EXAM_NUMBER_OPTION_SPACING = 50  # 考号每位0-9圆圈间距
EXAM_NUMBER_OPTION_START_Y = 20  # 考号选项圈相对行起始的偏移

# ── 识别阈值 ──
FILL_THRESHOLD = 0.30      # 填涂判定阈值（黑色像素占比），提高到0.30减少误判
FILL_BLANK_RANGE = 0.08    # max-min差值阈值，低于此判定为空题（各选项接近）
BINARIZATION_THRESHOLD = 128  # 二值化灰度阈值
MORPH_KERNEL = 3           # 形态学开运算核大小(px)，减小以避免侵蚀填涂区域

# ── 长方形选项框参数（OMR 扫描用，基于 printable_sheet_generator 布局） ──
# ★ 2026-07-06 重构: 改为匹配 printable sheet 的 5列×N行 布局
# 每行5道题，每道题4个选项圆圈，CIRCLE_DIAMETER=40, OPTION_SPACING=60
OPT_PITCH = 60             # 选项圆圈中心间距(px)，对应 OPTION_SPACING
WIN_SIZE = 36              # 选项框检测窗口大小(px)，略小于 CIRCLE_DIAMETER(40)
COL_PITCH = 280            # 列起始间距(px)，step_x = OPTION_SPACING*4 + 40
COL0_A_X = 400             # 第0列(第一题)起始X坐标(px)，对应 START_X

# ── 行锚点检测参数（OMR 扫描用） ──
ROW_ANCHOR_X_THRESHOLD = 150   # 行锚点最大X坐标，用于过滤左侧边缘的小方块
ROW_ANCHOR_AREA_MIN = 800      # 行锚点最小轮廓面积
ROW_ANCHOR_AREA_MAX = 5000     # 行锚点最大轮廓面积（放宽到5000）
ROW_ANCHOR_BINARY_THRESHOLD = 70  # 锚点检测二值化阈值

# ── 锚点扫描判定参数（匹配 printable sheet 的 5列布局） ──
FILL_THRESHOLD_LOW = 0.06     # 锚点填涂最低阈值（低于此直接判定空白）
BLANK_FILL_CAP = 0.15         # 空白选项最大填涂比例边界（超此需进一步分析）
ANCHOR_SCAN_GROUPS = 2        # 最大锚点组数（一组=25题，两组=50题）
ANCHOR_QUESTIONS_PER_GROUP = 25  # 每组题数 = ITEMS_PER_ROW * 5行 = 25
ANCHOR_COLUMNS = 5            # 每行列数 = ITEMS_PER_ROW

# ════════════════════════════════════════════
# Dinosheet 风格行/列锚点标记 & 识别参数
# ════════════════════════════════════════════
# 参考 Dinosheet 的 process_sheet() 算法:
#   1. OTSU 二值化 → 轮廓过滤 (w>=40, x<100 or y<100, 4顶点, 小周长)
#   2. lexsort 排序 → 分离左侧行标记 / 顶部列标记
#   3. 网格定位: 行标记Y × 列标记X → 裁剪ROI
#   4. Canny 边缘图 countNonZero → 填涂判定
#      (填涂区域边缘少 → countNonZero 小 → min = 答案)
#   5. max-min < DINO_BLANK_DIFF → 空题

# 标记绘制参数 (200dpi 基准，与现有布局常量统一缩放)
DINO_MARKER_SIZE = 50          # 标记方块边长(px)，绘制时随DPI缩放
DINO_LEFT_MARKER_X = 20        # 左侧行标记的X坐标(px)
DINO_TOP_MARKER_Y = 20         # 顶部列标记的Y坐标(px)

# 标记检测过滤参数 (识别时使用，单位: 实际图像像素)
DINO_MIN_MARKER_WIDTH = 40     # 标记最小宽度(px)，过滤噪点
DINO_EDGE_MAX_X = 100          # 左侧标记最大X坐标(px)
DINO_EDGE_MAX_Y = 100          # 顶部标记最大Y坐标(px)
DINO_MIN_PERI = 10             # 轮廓最小周长(px)，过滤极小噪点
DINO_MARKER_VERTICES = 4       # 标记期望顶点数(四边形)
DINO_MARKER_MAX_PERI = 10      # 标记最大轮廓周长(用于过滤大轮廓)

# 填涂判定参数
DINO_BLANK_DIFF = 120          # countNonZero max-min 差值，低于此判定为空题
DINO_GRAY_BLUR = (5, 5)        # 高斯模糊核大小
DINO_CANNY_LOW = 75            # Canny 低阈值
DINO_CANNY_HIGH = 225          # Canny 高阈值
