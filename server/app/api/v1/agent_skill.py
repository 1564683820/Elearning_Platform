"""Agent 自定义技能管理 API — 上传/列表/激活/删除 SKILL.md

技能按类型分类:
  ppt  - PPT课件设计技能（控制PPT生成的颜色/字体/布局/组件）
  exam - 试卷设计技能（控制试卷排版/题型结构/分值分布/题目格式）

激活规则: 每个教师每类技能可激活一个，不同类型的技能互不影响。
         例如：教师可以同时激活一个PPT技能和一个试卷技能。

端点清单:
  POST   /teaching-assistant/skills/upload        上传 SKILL.md 文件
  GET    /teaching-assistant/skills                技能列表（支持按类型过滤）
  GET    /teaching-assistant/skills/{id}           技能详情
  POST   /teaching-assistant/skills/{id}/activate  激活技能（同类型互斥）
  POST   /teaching-assistant/skills/{id}/deactivate 停用技能
  DELETE /teaching-assistant/skills/{id}           删除技能
  GET    /teaching-assistant/skills/active/current 获取当前激活技能（按类型）
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, desc

from app.db.database import get_db
from app.api.deps import get_current_teacher_id
from app.models.agent_skill import AgentSkill
from app.models.user import User
from app.utils.skill_parser import MAX_QA_SKILL_BYTES, QA_SKILL_TYPE, VALID_SKILL_TYPES, parse_qa_skill, parse_skill_md
from app.schemas.common import ResponseData

router = APIRouter(prefix="/teaching-assistant/skills", tags=["Agent技能管理"])
logger = logging.getLogger(__name__)

SKILL_TYPE_LABELS = {
    "ppt": "PPT设计",
    "exam": "试卷设计",
    QA_SKILL_TYPE: "问答",
}


class SkillResponse(BaseModel):
    """技能响应模型"""
    id: str
    name: str
    description: str
    skill_type: str = "ppt"
    is_active: bool
    color_count: int = 0
    created_at: str = ""
    updated_at: str = ""


def _skill_to_dict(skill: AgentSkill) -> dict:
    """将模型对象转为API响应字典"""
    color_count = len((skill.design_tokens or {}).get("colors", {})) if skill.design_tokens else 0
    return {
        "id": str(skill.id),
        "teacher_id": str(skill.teacher_id) if skill.teacher_id else "",
        "name": skill.name,
        "description": skill.description or "",
        "skill_type": skill.skill_type or "ppt",
        "file_name": skill.source_filename or f"{skill.name}.md",
        "raw_content": skill.raw_content,
        "design_tokens": skill.design_tokens,
        "prompt_snippet": skill.prompt_snippet or "",
        "is_active": bool(skill.is_active),
        "color_count": color_count,
        "created_at": skill.created_at.isoformat() if skill.created_at else "",
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else "",
    }


# ==================== 上传 SKILL.md ====================

async def _upload_qa_skill(db: AsyncSession, teacher_id: int, file: UploadFile):
    filename = file.filename or ""
    if not re.fullmatch(r"[^/\\\x00-\x1f\x7f]{1,256}", filename) or not filename.lower().endswith((".md", ".markdown")):
        raise HTTPException(status_code=400, detail="文件格式不支持，请选择 .md 或 .markdown。")
    raw = await file.read(MAX_QA_SKILL_BYTES + 1)
    if len(raw) > MAX_QA_SKILL_BYTES:
        raise HTTPException(status_code=413, detail="Skill 文件不能超过 48 KB")
    try:
        content = raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="请使用 UTF-8 编码的 Markdown 文件") from error
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", content):
        raise HTTPException(status_code=400, detail="无法解析文件，请选择 UTF-8 Markdown 文件")
    try:
        name, description = parse_qa_skill(content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    # A teacher's account row serializes concurrent uploads without a new table or unique constraint.
    await db.scalar(select(User.id).where(User.id == teacher_id).with_for_update())
    duplicate = await db.scalar(select(AgentSkill.id).where(
        AgentSkill.teacher_id == teacher_id, AgentSkill.skill_type == QA_SKILL_TYPE,
        AgentSkill.name == name, AgentSkill.status == 1,
    ).limit(1).with_for_update())
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"已存在同名问答技能「{name}」")
    skill = AgentSkill(
        teacher_id=teacher_id, skill_type=QA_SKILL_TYPE, name=name, source_filename=filename,
        description=description, raw_content=content, prompt_snippet="", is_active=0, status=1,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    await db.commit()
    return ResponseData(data=_skill_to_dict(skill), message="Skill 已上传")


@router.post("/upload", response_model=ResponseData)
async def upload_skill(
    file: UploadFile = File(...),
    skill_type: str = Form(default="ppt", description="技能类型: ppt、exam 或 qa"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """上传 SKILL.md 文件作为自定义 Agent 技能"""
    # 验证 skill_type
    skill_type = skill_type.strip().lower()
    if skill_type == QA_SKILL_TYPE:
        return await _upload_qa_skill(db, teacher_id, file)
    if skill_type not in VALID_SKILL_TYPES:
        raise HTTPException(
            status_code=400,
            detail="无效的技能类型，仅支持 ppt、exam 或 qa"
        )

    # 验证文件类型
    filename = (file.filename or "").lower()
    if not filename.endswith((".md", ".markdown")):
        raise HTTPException(status_code=400, detail="仅支持 .md 或 .markdown 格式的 SKILL 文件")

    # 读取文件内容
    try:
        raw_bytes = await file.read()
        raw_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw_content = raw_bytes.decode("gbk")
        except Exception:
            raise HTTPException(status_code=400, detail="无法解析文件编码，请使用 UTF-8 编码的 Markdown 文件")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取文件失败: {e}")

    if not raw_content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 解析 SKILL.md
    parsed = parse_skill_md(raw_content)
    if not parsed.get("name"):
        raise HTTPException(status_code=400, detail="SKILL.md 缺少 name 字段，请确保 frontmatter 中有 name 属性")

    # 如果SKILL.md中声明了skill_type但用户手动指定了不同值，以SKILL.md为准（用户可覆盖）
    if parsed.get("skill_type") and parsed["skill_type"] in VALID_SKILL_TYPES:
        # 优先使用SKILL.md中声明的类型，但允许用户覆盖
        effective_type = skill_type
    else:
        effective_type = skill_type

    # 检查同名同类型技能
    existing = await db.execute(
        select(AgentSkill).where(
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.skill_type == effective_type,
            AgentSkill.name == parsed["name"],
            AgentSkill.status == 1,
        )
    )
    if existing.scalar_one_or_none():
        type_label = SKILL_TYPE_LABELS.get(effective_type, effective_type)
        raise HTTPException(
            status_code=400,
            detail=f"已存在同名{type_label}技能「{parsed['name']}」，请先删除旧版再上传"
        )

    # 创建技能记录
    skill = AgentSkill(
        teacher_id=teacher_id,
        skill_type=effective_type,
        name=parsed["name"],
        description=parsed.get("description", ""),
        raw_content=raw_content,
        design_tokens=parsed.get("design_tokens"),
        prompt_snippet=parsed.get("prompt_snippet", ""),
        is_active=0,
        status=1,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)

    # 自动激活（如果该类型没有其他激活的技能）
    count_result = await db.execute(
        select(func.count()).select_from(
            select(AgentSkill).where(
                AgentSkill.teacher_id == teacher_id,
                AgentSkill.skill_type == effective_type,
                AgentSkill.status == 1,
                AgentSkill.is_active == 1,
            ).subquery()
        )
    )
    active_count = count_result.scalar() or 0
    if active_count == 0:
        skill.is_active = 1
        await db.flush()

    await db.commit()
    await db.refresh(skill)

    type_label = SKILL_TYPE_LABELS.get(effective_type, effective_type)
    return ResponseData(data=_skill_to_dict(skill), message=f"{type_label}技能「{parsed['name']}」上传成功")


# ==================== 技能列表 ====================

@router.get("", response_model=ResponseData)
async def list_skills(
    skill_type: Optional[str] = Query(default=None, description="按类型过滤: ppt、exam 或 qa"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取当前教师的所有自定义技能（支持按类型过滤）"""
    conditions = [
        AgentSkill.teacher_id == teacher_id,
        AgentSkill.status == 1,
    ]
    if skill_type and skill_type.strip().lower() in SKILL_TYPE_LABELS:
        conditions.append(AgentSkill.skill_type == skill_type.strip().lower())

    result = await db.execute(
        select(AgentSkill).where(*conditions)
        .order_by(desc(AgentSkill.is_active), desc(AgentSkill.skill_type), desc(AgentSkill.updated_at))
    )
    skills = result.scalars().all()

    items = [_skill_to_dict(s) for s in skills]

    # 按类型分组统计
    ppt_count = sum(1 for s in skills if s.skill_type == "ppt")
    exam_count = sum(1 for s in skills if s.skill_type == "exam")

    return ResponseData(data={
        "items": items,
        "total": len(items),
        "ppt_count": ppt_count,
        "exam_count": exam_count,
    })


# ==================== 技能详情 ====================

@router.get("/{skill_id}", response_model=ResponseData)
async def get_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取技能详情（含原始 SKILL.md 内容和设计令牌）"""
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.id == skill_id,
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.status == 1,
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    return ResponseData(data=_skill_to_dict(skill))


# ==================== 激活技能 ====================

@router.post("/{skill_id}/activate", response_model=ResponseData)
async def activate_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """激活指定技能（同类型内互斥：激活此技能会自动取消同类型其他技能的激活状态）

    不同类型的技能互不影响，教师可以同时拥有：
    - 一个激活的PPT设计技能
    - 一个激活的试卷设计技能
    """
    # 验证技能存在
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.id == skill_id,
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.status == 1,
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 取消同类型其他技能的激活状态（而不是取消所有类型的）
    if skill.skill_type == QA_SKILL_TYPE:
        raise HTTPException(status_code=409, detail="问答 Skill 的生效规则待确认")
    await db.execute(
        update(AgentSkill).where(
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.skill_type == skill.skill_type,
            AgentSkill.status == 1,
            AgentSkill.id != skill_id,
        ).values(is_active=0)
    )

    # 激活目标技能
    skill.is_active = 1
    await db.flush()
    await db.commit()
    await db.refresh(skill)

    type_label = SKILL_TYPE_LABELS.get(skill.skill_type, skill.skill_type)
    return ResponseData(data={
        "id": str(skill.id),
        "name": skill.name,
        "skill_type": skill.skill_type,
        "is_active": True,
    }, message=f"{type_label}技能「{skill.name}」已激活")


# ==================== 取消激活 ====================

@router.post("/{skill_id}/deactivate", response_model=ResponseData)
async def deactivate_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """取消激活指定技能，恢复该类型的默认设计风格"""
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.id == skill_id,
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.status == 1,
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    skill.is_active = 0
    await db.flush()
    await db.commit()
    await db.refresh(skill)

    type_label = SKILL_TYPE_LABELS.get(skill.skill_type, skill.skill_type)
    return ResponseData(message=f"{type_label}技能「{skill.name}」已停用")


# ==================== 删除技能 ====================

@router.delete("/{skill_id}", response_model=ResponseData)
async def delete_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """软删除指定技能"""
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.id == skill_id,
            AgentSkill.teacher_id == teacher_id,
            AgentSkill.status == 1,
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    skill.status = 0
    skill.is_active = 0
    await db.flush()
    await db.commit()
    await db.refresh(skill)

    return ResponseData(message=f"技能「{skill.name}」已删除")


# ==================== 获取当前激活技能 ====================

@router.get("/active/current", response_model=ResponseData)
async def get_active_skill(
    skill_type: Optional[str] = Query(default=None, description="按类型查询: ppt 或 exam（不传则返回所有类型的激活技能）"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取当前激活的技能（用于对话时注入 prompt）

    支持按技能类型查询，不传则返回所有类型中激活的技能。
    """
    conditions = [
        AgentSkill.teacher_id == teacher_id,
        AgentSkill.status == 1,
        AgentSkill.is_active == 1,
        AgentSkill.skill_type.in_(VALID_SKILL_TYPES),
    ]
    if skill_type and skill_type.strip().lower() in SKILL_TYPE_LABELS:
        conditions.append(AgentSkill.skill_type == skill_type.strip().lower())

    result = await db.execute(
        select(AgentSkill).where(*conditions)
    )
    skills = result.scalars().all()

    if not skills:
        return ResponseData(data=None, message="未激活任何自定义技能")

    # 返回所有激活技能（按类型分组）
    items = [_skill_to_dict(s) for s in skills]
    return ResponseData(data={
        "items": items,
        "total": len(items),
        # 向后兼容：返回第一个技能作为默认
        "id": items[0]["id"],
        "name": items[0]["name"],
        "skill_type": items[0]["skill_type"],
        "description": items[0]["description"],
        "prompt_snippet": items[0]["prompt_snippet"],
        "design_tokens": items[0]["design_tokens"],
        "has_prompt": bool(items[0]["prompt_snippet"]),
    })
