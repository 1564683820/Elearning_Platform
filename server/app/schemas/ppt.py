"""备课 PPT Pydantic Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# ========== 课型常量 ==========
LESSON_TYPES = {
    "new_lesson": "新授课",
    "review": "复习课",
    "exercise": "练习课",
    "conversation": "口语课",
}

# ========== 布局意图常量 ==========
LAYOUT_INTENTS = [
    "auto",           # 自动：根据课型和内容自适应选择
    "cover",          # 封面：标题成为视觉焦点
    "data_focus",     # 数据焦点：内容为主导
    "comparison",     # 对比：便于对比的结构
    "timeline",       # 时间线：递进展示
    "concept",        # 概念：清晰的视觉层次
    "process",        # 流程：步骤展示
    "summary",        # 总结：结论先导
    "quote",          # 引言：引言为视觉锚点
    "image_focus",    # 图片焦点：视觉素材主导
]

# ========== 页面切换动画类型 ==========
TRANSITION_TYPES = ["fade", "slide", "push"]

# ========== 请求模型 ==========

class PPTGenerateRequest(BaseModel):
    """AI 生成 PPT 请求"""
    title: str
    lesson_type: str = "new_lesson"       # 课型
    subject: str = ""                      # 主题/单元
    grade: str = ""                        # 年级
    class_id: Optional[int] = None         # 目标班级
    slide_count: int = 6                   # 期望页数（服务层会根据课型模板自动调整最小值）
    knowledge_points: List[str] = []       # 知识点标签
    stage_category: str = ""               # 学段: preschool/primary/junior/senior/other
    use_rag: bool = True                   # 是否启用 RAG 参考教案/课件
    additional_references: str = ""        # 用户补充参考内容（可粘贴教案、教材片段等）
    theme_name: str = "classic"            # 主题名（默认为 classic）
    synthesize_audio: Optional[bool] = None  # 是否合成TTS音频，None=自动判断（根据课型和页面类型决定）
    layout_intent: str = "auto"            # 布局意图: auto/cover/data_focus/comparison/timeline/concept/process/summary/quote/image_focus
    transition_type: str = "slide"         # 页面切换动画: fade/slide/push
    transition_duration: int = 400         # 切换动画时长（ms）
    # 布局变体覆盖：可为每种 slide type 指定布局（list/grid/cards）
    layout_overrides: Optional[dict] = None  # e.g. {"vocabulary": "grid", "grammar": "cards"}
    # spec_lock：设计规格锁定（Phase 3.3），传入后覆盖 theme/layout/visual_style 的自动选择
    spec_lock: Optional[dict] = None


class PPTUpdateRequest(BaseModel):
    """更新 PPT 请求"""
    title: Optional[str] = None
    lesson_type: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    class_id: Optional[int] = None
    pages_json: Optional[List[dict]] = None
    outline: Optional[List[dict]] = None
    interaction_config: Optional[dict] = None
    status: Optional[str] = None
    theme_name: Optional[str] = None
    layout_intent: Optional[str] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[int] = None
    animation_config: Optional[dict] = None
    layout_overrides: Optional[dict] = None
    spec_lock: Optional[dict] = None


class PPTRegenerateOutlineRequest(BaseModel):
    """重新生成大纲请求"""
    title: str
    lesson_type: str
    subject: str = ""
    grade: str = ""
    slide_count: int = 6
    knowledge_points: List[str] = []


# ========== 教学助手大纲生成 ==========

class PPTOutlineSection(BaseModel):
    """大纲章节"""
    title: str = ""
    subtopics: List[str] = []


class PPTGenerateOutlineRequest(BaseModel):
    """教学助手：生成 PPT 大纲请求"""
    title: str
    lesson_type: str = "new_lesson"
    subject: str = ""
    grade: str = ""
    knowledge_points: List[str] = []


class PPTGenerateOutlineResponse(BaseModel):
    """教学助手：生成大纲响应"""
    sections: List[PPTOutlineSection]


class PPTGenerateFromOutlineRequest(BaseModel):
    """教学助手：基于大纲生成完整 PPT 请求"""
    title: str
    lesson_type: str = "new_lesson"
    subject: str = ""
    grade: str = ""
    knowledge_points: List[str] = []
    sections: List[PPTOutlineSection] = []
    theme_name: str = "classic"
    stage_category: str = ""
    synthesize_audio: Optional[bool] = None  # 是否合成TTS音频，None=自动判断


class PPTRegeneratePageRequest(BaseModel):
    """重新生成单页请求"""
    page_index: int
    outline_title: str
    lesson_type: str
    subject: str = ""
    grade: str = ""


# ========== 课堂互动请求 ==========

class ClassroomStartRequest(BaseModel):
    """开始课堂请求"""
    ppt_id: int


class ClassroomVoteRequest(BaseModel):
    """投票互动请求"""
    question: str
    options: List[str]


class ClassroomQuizRequest(BaseModel):
    """课堂答题请求"""
    question: str
    options: List[str]
    correct_answer: int


class ClassroomDanmakuRequest(BaseModel):
    """发送弹幕请求（session_id 已从路径参数获取，此处设为可选）"""
    session_id: int = 0
    student_name: str = ""
    content: str


class ClassroomQuestionRequest(BaseModel):
    """提问请求"""
    session_id: int
    student_name: str = ""
    question: str


class SlideAnswerRequest(BaseModel):
    """幻灯片练习题答题记录请求"""
    page_index: int = Field(..., ge=0, description="页面索引")
    question_index: int = Field(..., ge=0, description="题目索引")
    selected: int = Field(..., ge=0, description="选择的选项索引")
    correct: bool = Field(..., description="是否选对")


# ========== 响应模型 ==========

class PPTOutlineItem(BaseModel):
    """大纲条目"""
    index: int
    title: str
    slide_type: str
    description: str = ""


class PPTListItem(BaseModel):
    """PPT 列表项"""
    id: int
    title: str
    lesson_type: str
    lesson_type_name: str = ""
    subject: str = ""
    grade: str = ""
    slide_count: int = 0
    status: str = "draft"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PPTDetail(BaseModel):
    """PPT 详情"""
    id: int
    teacher_id: int
    class_id: Optional[int] = None
    title: str
    lesson_type: str
    lesson_type_name: str = ""
    subject: str = ""
    grade: str = ""
    outline: Optional[list] = None
    pages_json: list
    html_content: Optional[str] = None
    theme_name: str = "classic"
    version: int = 1
    thumbnail_url: str = ""
    slide_count: int = 0
    interaction_config: Optional[dict] = None
    status: str = "draft"
    layout_intent: str = "auto"
    transition_type: str = "slide"
    transition_duration: int = 400
    layout_overrides: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PPTGenerateResult(BaseModel):
    """AI 生成结果"""
    id: int
    title: str
    outline: List[PPTOutlineItem]
    pages_json: list
    html_content: Optional[str] = None
    theme_name: str = "classic"
    slide_count: int
    layout_intent: str = "auto"
    transition_type: str = "slide"
    transition_duration: int = 400


class ClassroomSessionOut(BaseModel):
    """课堂会话响应"""
    id: int
    ppt_id: int
    title: str = ""
    status: str = "active"
    current_page: int = 0
    student_count: int = 0
    interaction_data: Optional[dict] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ClassroomReportOut(BaseModel):
    """课堂报告"""
    session: ClassroomSessionOut
    interaction_summary: dict = {}
    page_stats: List[dict] = []


# ========== 主题管理 ==========

class ThemeItem(BaseModel):
    """主题列表项"""
    id: int
    name: str
    display_name: str
    description: str = ""
    preview_color: str = ""
    preview_url: str = ""
    sort_order: int = 0
    is_builtin: bool = True

    model_config = {"from_attributes": True}


class ThemeDetail(ThemeItem):
    """主题详情（含完整 CSS 和设计规范）"""
    css_variables: str = ""
    css_content: str = ""
    style_skill: Optional[dict] = None      # 设计规范: color_scheme/typography/layout_rules/recommended_animations等
    font_pairings: List[str] = []            # 可用字体配对名
    slide_layouts: Optional[dict] = None     # 各slide类型推荐布局


class ThemeCreate(BaseModel):
    """创建自定义主题"""
    name: str = Field(..., min_length=1, max_length=64, description="主题标识名，如 my-theme")
    display_name: str = Field(..., min_length=1, max_length=128, description="主题显示名")
    css_variables: str = Field(..., description="CSS 变量定义（:root {...}）")
    css_content: str = Field(..., description="完整主题 CSS")
    description: str = ""
    preview_color: str = "#2d7d46"
    style_skill: Optional[dict] = None       # 设计规范


class ThemeUpdate(BaseModel):
    """更新自定义主题"""
    display_name: Optional[str] = None
    css_variables: Optional[str] = None
    css_content: Optional[str] = None
    description: Optional[str] = None
    preview_color: Optional[str] = None
    style_skill: Optional[dict] = None


# ========== 版本历史 ==========

class PptVersionItem(BaseModel):
    """版本历史列表项"""
    id: int
    ppt_id: int
    version: int
    theme_name: str = ""
    change_summary: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class PptVersionDetail(PptVersionItem):
    """版本详情"""
    html_content: str = ""
    pages_json: list = []


# ========== PPT 导出 ==========

class PptExportOut(BaseModel):
    """PPT 导出结果"""
    id: int
    title: str
    html_content: str
    theme_name: str
    slide_count: int
    transition_type: str = "slide"
    transition_duration: int = 400


# ========== 动画与布局配置 ==========

class SlideAnimation(BaseModel):
    """元素级动画配置"""
    anim_type: str = "fade-up"        # 动画类型: fade/fade-up/slide-up/zoom-in/等
    trigger: str = "after"             # 触发时机: load/with/after/click
    duration: int = 500                # 持续时间（ms）
    delay: int = 0                     # 延迟（ms）
    direction: str = ""                # 方向: left/right/top/bottom（可选）

class PPTAnimationConfig(BaseModel):
    """PPT 级别动画配置"""
    transition_type: str = "slide"     # 页面切换动画
    transition_duration: int = 400     # 切换动画时长
    element_animations: Optional[List[SlideAnimation]] = None  # 元素级动画

class PPTLayoutConfig(BaseModel):
    """PPT 布局配置"""
    layout_intent: str = "auto"                     # 整体布局意图
    slide_overrides: Optional[dict] = None           # 各 slide type 的布局覆盖
    default_vocab_layout: str = "list"              # 词汇默认布局
    default_grammar_layout: str = "list"             # 语法默认布局
    default_practice_layout: str = "list"            # 练习默认布局

# ========== 字体配置 ==========

class FontConfig(BaseModel):
    """字体配置"""
    name: str = ""                    # 显示名
    family: str = ""                  # CSS font-family
    source: str = "system"            # system/google/uploaded
    google_id: str = ""               # Google Fonts ID
    weights: List[int] = [400, 700]   # 可用字重
    category: str = "sans-serif"      # sans-serif/serif/handwriting/display

class FontPairing(BaseModel):
    """字体配对"""
    title_font: str = ""              # 标题字体族名
    body_font: str = ""               # 正文字体族名
    description: str = ""             # 搭配说明
    best_for: List[str] = []          # 适合的风格名
