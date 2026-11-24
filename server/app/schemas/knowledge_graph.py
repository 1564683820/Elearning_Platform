"""知识图谱 Pydantic Schema"""
from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing import Optional, List, Annotated
from datetime import datetime


# ========== 知识图谱内部数据结构 ==========
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class KGGraphNode(BaseModel):
    """知识图谱中的单个知识点节点"""
    id: NonBlank                      # uuid
    title: NonBlank                   # 知识点名称
    description: str = ""             # 简要描述
    order: int = 0                    # 排序号
    suggested_page_type: str = ""     # AI 推荐的页面类型


class KGGraphSection(BaseModel):
    """知识图谱中的章节"""
    id: NonBlank                      # uuid
    title: NonBlank                   # 大标题
    order: int = 0                    # 排序号
    children: List[KGGraphNode] = []  # 知识点列表


# ========== 请求模型 ==========

class KGGenerateRequest(BaseModel):
    """AI 生成知识图谱请求"""
    title: Annotated[NonBlank, Field(max_length=256)]             # 课程标题
    lesson_type: str = "new_lesson"                             # 课型
    subject: str = ""                                           # 主题/单元
    grade: str = ""                                             # 年级
    supplement: str = ""                                        # 补充说明
    expected_sections: int = Field(4, ge=1)                      # 期望章节数
    expected_nodes_per_section: int = Field(3, ge=1)             # 期望每章节知识点数


class KGUpdateRequest(BaseModel):
    """更新知识图谱请求（整树替换）"""
    content: List[KGGraphSection]                               # 更新后的图谱内容
    title: Optional[Annotated[NonBlank, Field(max_length=256)]] = None

    @model_validator(mode='after')
    def unique_identifiers(self):
        seen = set()
        for section in self.content:
            for item in [section, *section.children]:
                if item.id in seen:
                    raise ValueError('章节和知识点 ID 必须全局唯一')
                seen.add(item.id)
        return self


# ========== 响应模型 ==========

class KGDetail(BaseModel):
    """知识图谱详情"""
    id: int
    ppt_id: Optional[int] = None
    teacher_id: int
    title: str
    lesson_type: str
    subject: str = ""
    grade: str = ""
    content: list
    status: str = "draft"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KGListItem(BaseModel):
    """知识图谱列表项"""
    id: int
    title: str
    lesson_type: str
    subject: str = ""
    grade: str = ""
    status: str = "draft"
    section_count: int = 0
    node_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KGGenerateResult(BaseModel):
    """AI 生成知识图谱结果"""
    id: int
    title: str
    content: list
    status: str = "draft"
