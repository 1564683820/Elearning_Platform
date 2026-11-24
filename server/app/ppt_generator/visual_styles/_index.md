# Visual Styles Index — 19 风格完整目录

Reference: [ppt-master visual-styles](https://github.com/hugohe3/ppt-master)

## 五大分类 (5 Categories)

### 一、商务/产品 (Corporate & Product)
面向知识讲解、结构化内容、科技与数据场景。

| # | 风格名称 | Codename | 形状 | 装饰 DNA | 紧张度 |
|---|---------|----------|------|----------|--------|
| 1 | 瑞士极简 | `swiss-minimal` | 直角卡片 | 左侧色标 + 实线分隔 | 严谨 ★★★★ |
| 2 | 圆润亲和 | `soft-rounded` | 圆角卡片 12px | 顶部色条 + 背景圆 | 亲切 ★★ |
| 3 | 玻璃拟态 | `glassmorphism` | 透明面板 | 发光背景 + 玻璃分隔 | 科技 ★★★ |
| 4 | 暗色科技 | `dark-tech` | 圆角卡片 8px | 顶部色条 + 发光背景 | 酷炫 ★★★ |
| 5 | 工程蓝图 | `blueprint` | 直角线框 | 网格线 + 工程标注 | 严谨 ★★★★★ |

### 二、编辑/出版 (Editorial & Publication)
面向阅读材料、分析报告、长篇内容展示。

| # | 风格名称 | Codename | 形状 | 装饰 DNA | 紧张度 |
|---|---------|----------|------|----------|--------|
| 6 | 杂志风格 | `editorial` | 圆角卡片 6px | 顶部色条 + 网格背景 | 优雅 ★★★ |
| 7 | 摄影杂志 | `photo-editorial` | 全出血大图 | 细线规则 + 图注编号 | 大气 ★★ |
| 8 | 数据新闻 | `data-journalism` | 微圆角 2px | 微型图表 + 竖线分隔 | 精细 ★★★★ |
| 9 | 粗野主义 | `brutalist` | 直角线框 | 粗黑线框 + 极高密度 | 硬核 ★★★★★ |

### 三、表现/印刷 (Expressive & Print)
面向创意表现、文化主题、个性化学案。

| # | 风格名称 | Codename | 形状 | 装饰 DNA | 紧张度 |
|---|---------|----------|------|----------|--------|
| 10 | 孟菲斯 | `memphis` | 圆角 6px | 波尔卡圆点 + 几何色块 | 活泼 ★ |
| 11 | 独立杂志 | `zine` | 直角/微圆角 | 套印偏移 + 拼贴边框 | 个性 ★★★ |
| 12 | 复古海报 | `vintage-poster` | 直角色块 | 半色调网点 + 放射线 | 经典 ★★ |
| 13 | 剪纸风格 | `paper-cut` | 圆角卡片 4px | 层叠阴影 + 图案装饰 | 温暖 ★ |

### 四、手绘/笔触 (Hand-drawn & Brush)
面向知识梳理、创意笔记、课堂板书场景。

| # | 风格名称 | Codename | 形状 | 装饰 DNA | 紧张度 |
|---|---------|----------|------|----------|--------|
| 14 | 手绘风格 | `sketch-notes` | 无边框 | 网格纸背景 + 波浪分隔 | 随性 ★ |
| 15 | 墨迹笔记 | `ink-notes` | 手绘线框 | 墨点标记 + 语义色彩 | 深思 ★★ |
| 16 | 黑板风格 | `chalkboard` | 圆角卡片 6px | 左侧色标 + 虚线分隔 | 课堂 ★★ |
| 17 | 水墨风格 | `ink-wash` | 圆角 4px | 水墨渲染 + 印章红 | 东方 ★★ |

### 五、特色 (Specialty)
面向特定主题、游戏化、趣味场景。

| # | 风格名称 | Codename | 形状 | 装饰 DNA | 紧张度 |
|---|---------|----------|------|----------|--------|
| 18 | 像素艺术 | `pixel-art` | 像素锯齿边 | HUD 状态栏 + 像素网格 | 趣味 ★ |
| 19 | 温暖简洁 | `warm-simple` | 圆角卡片 8px | 顶部色条 + 背景圆 | 通用 ★★ |

---

## 教学场景自动选择矩阵 (Education Auto-Selection Matrix)

### 按课型匹配 (by Lesson Type)

```python
LESSON_TYPE_TO_STYLE = {
    # 新课 → 严谨或亲和
    "new_lesson":       "swiss-minimal",   # 默认瑞士极简
    "new_lesson_kids":  "soft-rounded",    # 少儿新授课 → 圆润亲和
    "new_lesson_arts":  "sketch-notes",    # 艺术新授课 → 手绘风格

    # 复习 → 信息密集型或手写笔记
    "review":           "editorial",        # 默认杂志风
    "review_exam":      "brutalist",        # 考前复习 → 粗野主义高密度
    "review_method":    "ink-notes",        # 方法梳理 → 墨迹笔记

    # 练习 → 严谨清晰
    "exercise":         "data-journalism",  # 默认数据新闻
    "exercise_basic":   "swiss-minimal",    # 基础练习 → 瑞士极简
    "exercise_game":    "pixel-art",        # 游戏化练习 → 像素艺术

    # 口语/听力 → 亲和温暖
    "conversation":     "soft-rounded",     # 默认圆润亲和
    "conversation_culture": "vintage-poster", # 文化对话 → 复古海报

    # 特定课型
    "listening":        "soft-rounded",     # 听力 → 亲和
    "speaking":         "soft-rounded",     # 口语 → 亲和
    "interactive":      "dark-tech",        # 互动 → 科技感
    "ai_interaction":   "dark-tech",        # AI → 科技感
}
```

### 按学科匹配 (by Subject)

```python
SUBJECT_TO_STYLE = {
    # 语言类
    "english":          "swiss-minimal",      # 英语 → 瑞士极简（清晰准确）
    "chinese":          "ink-wash",           # 语文 → 水墨风格
    "classical_chinese":"ink-wash",           # 古文 → 水墨风格
    "poetry":           "ink-wash",           # 诗词 → 水墨 + 印章红

    # 理工科
    "math":             "data-journalism",    # 数学 → 数据新闻
    "physics":          "blueprint",          # 物理 → 工程蓝图
    "chemistry":        "blueprint",          # 化学 → 工程蓝图
    "biology":          "photo-editorial",    # 生物 → 摄影杂志（配图多）
    "programming":      "pixel-art",          # 编程 → 像素艺术
    "engineering":      "blueprint",          # 工程 → 蓝图

    # 人文社科
    "history":          "vintage-poster",     # 历史 → 复古海报
    "geography":        "photo-editorial",    # 地理 → 摄影杂志
    "politics":         "editorial",          # 政治 → 杂志风
    "sociology":        "zine",               # 社会 → 独立杂志
    "philosophy":       "ink-notes",          # 哲学 → 墨迹笔记

    # 艺术/体育
    "art":              "memphis",            # 美术 → 孟菲斯
    "music":            "editorial",          # 音乐 → 杂志风
    "design":           "memphis",            # 设计 → 孟菲斯
    "sports":           "vintage-poster",     # 体育 → 复古海报

    # 综合素质
    "moral_education":  "warm-simple",        # 德育 → 温暖简洁
    "general":          "warm-simple",        # 通用 → 温暖简洁
}
```

### 按年级匹配 (by Grade)

```python
GRADE_TO_STYLE = {
    "preschool":        "soft-rounded",       # 幼儿园 → 圆润亲和
    "grade1-3":         "soft-rounded",       # 1-3年级 → 圆润亲和
    "grade4-6":         "editorial",          # 4-6年级 → 杂志风（过渡）
    "middle_school":    "swiss-minimal",      # 初中 → 瑞士极简（开始严谨）
    "high_school":      "editorial",          # 高中 → 杂志风/粗野主义
    "college":          "editorial",          # 大学 → 杂志风
    "adult":            "swiss-minimal",      # 成人 → 瑞士极简
}
```

### 按内容氛围匹配 (by Content Vibe)

```python
CONTENT_VIBE_TO_STYLE = {
    "structured":       "swiss-minimal",      # 结构清晰 → 瑞士极简
    "playful":          "memphis",            # 活泼趣味 → 孟菲斯
    "serious":          "editorial",          # 严肃专业 → 杂志风
    "warm":             "paper-cut",          # 温暖手作 → 剪纸
    "tech":             "dark-tech",          # 科技感 → 暗色科技
    "minimal":          "ink-notes",          # 极简深思 → 墨迹笔记
    "classic":          "vintage-poster",     # 经典复古 → 复古海报
    "creative":         "zine",               # 创意个性 → 独立杂志
    "data_driven":      "data-journalism",    # 数据驱动 → 数据新闻
    "eastern":          "ink-wash",           # 东方美学 → 水墨风格
    "game":             "pixel-art",          # 游戏化 → 像素艺术
    "engineering":      "blueprint",          # 工程感 → 蓝图
    "photo_rich":       "photo-editorial",    # 图文并茂 → 摄影杂志
    "info_dense":       "brutalist",          # 信息密集 → 粗野主义
    "modern_tech":      "glassmorphism",      # 现代科技 → 玻璃拟态
    "sketch":           "sketch-notes",       # 手绘笔记 → 手绘风格
    "classroom":        "chalkboard",         # 课堂板书 → 黑板风格
    "universal":        "warm-simple",        # 通用兜底 → 温暖简洁
}
```

---

## CSS Variable Bridge (每个风格的CSS变量映射)

每个风格通过 `ppt_html_style_bridge.py` 映射到CSS自定义属性：

| 风格 codename | `--slide-corner-radius` | `--slide-card-shadow` | `--slide-header-style` | `--slide-divider-style` |
|-------------|------------------------|----------------------|---------------------|---------------------|
| `swiss-minimal` | 0px | none | left-accent (2px solid) | solid 1px |
| `soft-rounded` | 12px | soft | top-bar + bg-circle | solid 1px |
| `editorial` | 6px | subtle | top-bar + left-accent + grid | dotted 1px |
| `dark-tech` | 8px | glow-medium | top-bar + left-accent + radial | glow-dashed |
| `blueprint` | 0px | none | cross-node left-accent | engineering-dashed |
| `brutalist` | 0px | none | heavy top-bar + block left | heavy-solid 2px |
| `data-journalism` | 2px | none | top-bar + column-rules | hairline 1px |
| `photo-editorial` | 0px | none | hairline left-accent | hairline 0.5px |
| `memphis` | 4-6px | none | wavy top-bar + circle left | wavy-dashed |
| `zine` | 0-2px | none | offset top-bar + offset left | offset-double |
| `vintage-poster` | 0px | none | heavy top-bar + sunburst left | vintage-double |
| `paper-cut` | 4px | layered-drop | top-bar + pattern decor | craft-dotted |
| `sketch-notes` | 0px | none | grid-bg + wave divider | wavy-dashed |
| `ink-notes` | 0px | none | ink-dot left + sketch lines | sketch-dashed |
| `chalkboard` | 6px | subtle | left-accent + chalk-dashed | dashed 2px |
| `ink-wash` | 4px | none | wash left + seal dot | wash-line |
| `pixel-art` | 0px | none | HUD bar + pixel-block left | pixel-step |
| `warm-simple` | 8px | light | top-bar + left-accent + bg-circle | solid 1px |
| `glassmorphism` | 12-20px | glow-layered | radial-bloom + glass-edge | glass-edge |
