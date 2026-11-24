from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, Generic, TypeVar, List
from datetime import datetime

T = TypeVar("T")


# ========== 通用响应 ==========

class ResponseBase(BaseModel):
    code: int = 0
    message: str = "success"


class ResponseData(ResponseBase, Generic[T]):
    data: Optional[T] = None


class PaginatedData(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedResponse(ResponseBase, Generic[T]):
    data: Optional[PaginatedData[T]] = None


# ========== 分页请求 ==========

class PaginationRequest(BaseModel):
    page: int = 1
    page_size: int = 20


# ========== 用户 ==========

class UserBase(BaseModel):
    nickname: str = ""
    avatar_url: str = ""
    stage: int = 1  # 学习阶段 1-13


class UserOut(UserBase):
    id: int
    openid: str
    account: str = ""
    role: str = "student"
    membership: str = "free"
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    """个人主页响应 — 包含用户信息和学习统计"""
    id: int
    name: str = ""           # 昵称
    nickname: str = ""
    avatar_url: str = ""
    email: str = ""          # 先留空，后续可扩展
    role: str = ""           # 空表示未选择，由用户后续选择
    phase: str = "英语四级"  # 学习阶段文字
    stage: int = 1
    studyDays: int = 0
    totalWords: int = 0
    totalTraining: int = 0
    membership: str = "free"
    # 班级信息（学生视角）
    classes: list[dict] = []


class UserUpdate(BaseModel):
    """用户自主更新个人信息（禁止修改 role，防止权限提升）"""
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    stage: Optional[int] = None


class PasswordChangeRequest(BaseModel):
    """自助修改密码"""
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v):
        if len(v) < 6:
            raise ValueError("新密码至少 6 位")
        return v


class AdminUserUpdate(BaseModel):
    """管理员更新用户信息（允许修改 role）"""
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    stage: Optional[int] = None
    role: Optional[str] = None  # 仅管理员可修改角色

    @field_validator("role")
    @classmethod
    def check_role(cls, v):
        if v is not None and v not in ("student", "teacher", "admin"):
            raise ValueError("角色只能为 student、teacher 或 admin")
        return v


class LoginRequest(BaseModel):
    """统一登录请求：小程序传 code，教师后台传 account+password"""
    code: str = ""
    account: str = ""
    password: str = ""


class InviteCodeRegisterRequest(BaseModel):
    """邀请码注册（通用，含邀请码验证）"""
    account: str
    username: str = ""
    password: str
    role: str = "student"  # student/teacher
    invite_code: str = Field(alias="inviteCode")

    model_config = {"populate_by_name": True}

    @field_validator("role")
    @classmethod
    def check_role(cls, v):
        if v not in ("student", "teacher"):
            raise ValueError("角色只能为 student 或 teacher")
        return v


TeacherRegisterRequest = InviteCodeRegisterRequest


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ========== API Key ==========

class ApiKeyCreate(BaseModel):
    key_type: str  # llm/multimodal/embedding
    encrypted_key: str
    api_base: str = ""
    model_name: str = ""

    model_config = {"protected_namespaces": ()}


class ApiKeyOut(BaseModel):
    id: int
    key_type: str
    api_base: str
    model_name: str
    is_valid: int
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ApiKeyTestRequest(BaseModel):
    key_type: str


# ========== 单词（对齐 DBplan dict_word） ==========

class WordOut(BaseModel):
    id: int
    word: str
    phonetic: Optional[str] = None
    pos: Optional[str] = None
    translation: Optional[str] = None
    definition: Optional[str] = None
    collins: Optional[int] = None
    oxford: Optional[int] = None
    tag: Optional[str] = None
    bnc: Optional[int] = None
    frq: Optional[int] = None
    sw: str = ""
    exchange: Optional[str] = None
    audio_url: Optional[str] = None
    detail_json: Optional[dict] = None

    model_config = {"from_attributes": True}

    @field_validator("phonetic", "pos", "tag", "exchange", "audio_url", mode="before")
    @classmethod
    def str_default(cls, v):
        return v if v is not None else ""

    @field_validator("collins", "oxford", "bnc", "frq", mode="before")
    @classmethod
    def int_default(cls, v):
        return v if v is not None else 0


class WordDetail(WordOut):
    roots: List[dict] = []
    synonyms: List[dict] = []
    idiom: Optional[dict] = None
    progress: Optional[dict] = None


class WordProgressCreate(BaseModel):
    mastery_level: int = Field(0, ge=0, le=3)


class WordListQuery(PaginationRequest):
    search: str = ""
    stage: int = 0  # 学习阶段 1-13，0=不限
    tag: str = ""   # 考试标签筛选，如 cet4/cet6/zk/gk，为空时不限制
    sort_by: str = "importance"  # asc=升序, desc=倒序, importance=重要度, random=随机


# ========== 收藏（对齐 DBplan favorite） ==========

# 收藏目标类型映射
FAVORITE_TYPE_WORD = 1
FAVORITE_TYPE_ARTICLE = 2
FAVORITE_TYPE_SEGMENT = 3
FAVORITE_TYPE_SONG = 4

FAVORITE_TYPE_MAP = {
    "word": FAVORITE_TYPE_WORD,
    "article": FAVORITE_TYPE_ARTICLE,
    "segment": FAVORITE_TYPE_SEGMENT,
    "song": FAVORITE_TYPE_SONG,
}

FAVORITE_TYPE_REVERSE = {v: k for k, v in FAVORITE_TYPE_MAP.items()}


class FavoriteCreate(BaseModel):
    target_type: str  # word/article/segment/song
    target_id: int = 0
    word: str = ""
    phonetic: str = ""
    meaning: str = ""
    content: str = ""
    passage_type: str = ""


class FavoriteOut(BaseModel):
    id: int
    target_type: int  # 1=单词,2=文章,3=情景文段,4=歌曲
    target_type_name: str = ""
    target_id: int
    word: str = ""
    phonetic: str = ""
    meaning: str = ""
    content: str = ""
    passage_type: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


# ========== 训练（对齐 DBplan question_bank / training_session） ==========

class QuizGenerateRequest(BaseModel):
    question_types: List[int] = [1]  # 题型编号，对齐 DBplan
    stage: int = 0  # 学习阶段 1-13
    count: int = 10
    mode: str = "infinite"  # infinite/fixed


class QuestionOut(BaseModel):
    id: int
    type: int  # 题型 1-7
    stage: int  # 学习阶段
    difficulty: int = 1
    content: dict

    model_config = {"from_attributes": True}


class QuizSubmitRequest(BaseModel):
    question_id: int
    answer: Any
    time_spent: int = Field(0, ge=0)


class QuizSubmitResponse(BaseModel):
    is_correct: bool
    correct_answer: Any
    analysis: Optional[dict] = None


# ========== 情景（对齐 DBplan scenario_passage） ==========

class ScenarioGenerateRequest(BaseModel):
    word_ids: List[int]
    time_range: str = "week"  # day/week/month
    passage_type: str = "story"  # story/report/rhyme


class ScenarioOut(BaseModel):
    id: int
    content: str
    word_ids: List[int]
    passage_type: str
    video_url: str = ""
    video_status: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ========== 对话（对齐 DBplan chat_conversation / chat_message） ==========

class ChatSessionCreate(BaseModel):
    type: int = 1  # 1=情景对话,2=智能问答,3=智能翻译
    scene_desc: str = ""
    user_role: str = ""
    title: str = ""


class ChatConversationOut(BaseModel):
    id: int
    type: int
    scene_desc: str = ""
    user_role: str = ""
    title: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    message_type: str = "text"
    sources: Optional[list] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSendRequest(BaseModel):
    message: str
    message_type: str = "text"  # text/image/file


# ========== 翻译 ==========

class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "auto"  # auto/zh/en
    target_lang: str = "auto"  # auto/zh/en


class TranslateResponse(BaseModel):
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str


# ========== 统计 ==========

class DashboardStats(BaseModel):
    words_learned_today: int = 0
    words_learned_week: int = 0
    quiz_accuracy: float = 0.0
    total_words: int = 0
    total_quiz_count: int = 0


class DailyStatOut(BaseModel):
    stat_date: str
    words_learned: int = 0
    words_reviewed: int = 0
    quiz_count: int = 0
    quiz_correct: int = 0
    study_minutes: int = 0

    model_config = {"from_attributes": True}


# ========== 文档（对齐 DBplan user_document） ==========

class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    storage_key: str = ""
    parse_status: int = 0  # 0=待处理,1=解析中,2=已完成,3=失败
    vector_status: int = 0
    doc_category: str = "other"     # 新增：文档分类
    stage_category: str = "other"   # 新增：学段
    doc_tags: str = ""              # 新增：自定义标签
    created_at: datetime

    model_config = {"from_attributes": True}


# ========== 反馈（对齐 DBplan feedback） ==========

class FeedbackCreate(BaseModel):
    type: str = "bug"  # bug/suggestion
    content: str
    screenshot_url: str = ""
