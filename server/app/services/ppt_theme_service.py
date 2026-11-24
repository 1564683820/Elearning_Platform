"""PPT 主题管理服务：8 套内置教学主题 + 自定义主题 CRUD"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.models.ppt_theme_models import PPTTheme
from app.services.ppt_theme_data import BUILTIN_THEMES


class PPTThemeService:
    """PPT 主题管理服务"""

    @staticmethod
    async def init_builtin_themes(db: AsyncSession):
        """初始化 8 套内置主题到数据库（批量查询 + 批量插入）"""
        # 一次查询所有已存在的内置主题
        names = [t["name"] for t in BUILTIN_THEMES]
        result = await db.execute(
            select(PPTTheme.name).where(
                PPTTheme.name.in_(names), PPTTheme.is_builtin == 1
            )
        )
        existing_names = {row[0] for row in result.all()}

        to_insert = [t for t in BUILTIN_THEMES if t["name"] not in existing_names]
        if not to_insert:
            return

        for theme_data in to_insert:
            theme = PPTTheme(
                name=theme_data["name"],
                display_name=theme_data["display_name"],
                description=theme_data.get("description", ""),
                css_variables=theme_data["css_variables"],
                css_content=theme_data["css_content"],
                preview_color=theme_data.get("preview_color", "#2d7d46"),
                sort_order=theme_data.get("sort_order", 0),
                is_builtin=1,
                style_skill=theme_data.get("style_skill"),
                slide_layouts=theme_data.get("slide_layouts"),
                font_pairings=theme_data.get("font_pairings"),
            )
            db.add(theme)
        await db.commit()

    @staticmethod
    async def list_themes(
        db: AsyncSession, teacher_id: int | None = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """获取主题列表（内置 + 教师的自定义主题）"""
        query = select(PPTTheme).where(
            (PPTTheme.is_builtin == 1) | (PPTTheme.teacher_id == teacher_id)
        )
        query = query.order_by(PPTTheme.sort_order, PPTTheme.id)
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        themes = result.scalars().all()
        items = []
        for t in themes:
            items.append({
                "id": t.id,
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "preview_color": t.preview_color,
                "preview_url": t.preview_url or "",
                "sort_order": t.sort_order,
                "is_builtin": bool(t.is_builtin),
            })
        return {"items": items, "total": total}

    @staticmethod
    async def get_theme(db: AsyncSession, theme_id: int) -> dict | None:
        """获取单个主题详情（含完整 CSS、设计规范和布局推荐）"""
        result = await db.execute(select(PPTTheme).where(PPTTheme.id == theme_id))
        t = result.scalar_one_or_none()
        if not t:
            return None
        return {
            "id": t.id,
            "name": t.name,
            "display_name": t.display_name,
            "description": t.description,
            "css_variables": t.css_variables,
            "css_content": t.css_content,
            "preview_color": t.preview_color,
            "preview_url": t.preview_url or "",
            "sort_order": t.sort_order,
            "is_builtin": bool(t.is_builtin),
            "style_skill": t.style_skill,
            "slide_layouts": t.slide_layouts,
            "font_pairings": t.font_pairings or [],
        }

    @staticmethod
    async def get_theme_by_name(db: AsyncSession, name: str) -> dict | None:
        """按主题名获取主题（含样式技能和布局推荐）"""
        result = await db.execute(select(PPTTheme).where(PPTTheme.name == name))
        t = result.scalar_one_or_none()
        if not t:
            return None
        return {
            "id": t.id,
            "name": t.name,
            "display_name": t.display_name,
            "css_variables": t.css_variables,
            "css_content": t.css_content,
            "style_skill": t.style_skill,
            "slide_layouts": t.slide_layouts,
            "font_pairings": t.font_pairings or [],
        }

    @staticmethod
    async def create_custom_theme(
        db: AsyncSession, teacher_id: int,
        name: str, display_name: str,
        css_variables: str, css_content: str,
        description: str = "",
        preview_color: str = "#2d7d46",
        style_skill: dict = None,
    ) -> dict:
        """创建自定义主题"""
        existing = await db.execute(
            select(PPTTheme).where(PPTTheme.name == name, PPTTheme.teacher_id == teacher_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"主题名 '{name}' 已存在")

        theme = PPTTheme(
            name=name,
            display_name=display_name,
            description=description,
            css_variables=css_variables,
            css_content=css_content,
            preview_color=preview_color,
            sort_order=99,
            is_builtin=0,
            teacher_id=teacher_id,
            style_skill=style_skill,
        )
        db.add(theme)
        await db.commit()
        await db.refresh(theme)
        return {"id": theme.id, "name": theme.name, "display_name": theme.display_name}

    @staticmethod
    async def update_theme(
        db: AsyncSession, theme_id: int, teacher_id: int, update_data: dict,
    ) -> dict | None:
        """更新自定义主题"""
        result = await db.execute(
            select(PPTTheme).where(PPTTheme.id == theme_id, PPTTheme.teacher_id == teacher_id)
        )
        theme = result.scalar_one_or_none()
        if not theme:
            return None
        for key in ["display_name", "css_variables", "css_content", "description", "preview_color", "style_skill"]:
            if key in update_data:
                setattr(theme, key, update_data[key])
        await db.commit()
        await db.refresh(theme)
        return {"id": theme.id, "name": theme.name, "display_name": theme.display_name}

    @staticmethod
    async def delete_theme(db: AsyncSession, theme_id: int, teacher_id: int) -> bool:
        """删除自定义主题"""
        result = await db.execute(
            select(PPTTheme).where(PPTTheme.id == theme_id, PPTTheme.teacher_id == teacher_id)
        )
        theme = result.scalar_one_or_none()
        if not theme:
            return False
        await db.delete(theme)
        await db.commit()
        return True
