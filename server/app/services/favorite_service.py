from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.word import Favorite
from app.schemas.common import FavoriteCreate, FavoriteOut, FAVORITE_TYPE_MAP, FAVORITE_TYPE_REVERSE
from typing import Optional


class FavoriteService:

    @staticmethod
    async def list_favorites(
        db: AsyncSession, user_id: int, target_type: str = "", page: int = 1, page_size: int = 20
    ) -> dict:
        """收藏列表"""
        stmt = select(Favorite).where(Favorite.user_id == user_id)

        if target_type:
            type_int = FAVORITE_TYPE_MAP.get(target_type, 0)
            if type_int:
                stmt = stmt.where(Favorite.target_type == type_int)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Favorite.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        favorites = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size

        items = []
        for f in favorites:
            out = FavoriteOut(
                id=f.id,
                target_type=f.target_type,
                target_type_name=FAVORITE_TYPE_REVERSE.get(f.target_type, "unknown"),
                target_id=f.target_id,
                word=f.word or "",
                phonetic=f.phonetic or "",
                meaning=f.meaning or "",
                content=f.content or "",
                passage_type=f.passage_type or "",
                created_at=f.created_at,
            )
            items.append(out)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    @staticmethod
    async def add_favorite(db: AsyncSession, user_id: int, data: FavoriteCreate) -> FavoriteOut:
        """添加收藏"""
        target_type_int = FAVORITE_TYPE_MAP.get(data.target_type, 0)
        if not target_type_int:
            raise ValueError(f"无效的收藏类型: {data.target_type}")

        # 检查是否已收藏
        stmt = select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.target_type == target_type_int,
            Favorite.target_id == data.target_id,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return FavoriteOut(
            id=existing.id,
            target_type=existing.target_type,
            target_type_name=FAVORITE_TYPE_REVERSE.get(existing.target_type, "unknown"),
            target_id=existing.target_id,
            word=existing.word or "",
            phonetic=existing.phonetic or "",
            meaning=existing.meaning or "",
            content=existing.content or "",
            passage_type=existing.passage_type or "",
            created_at=existing.created_at,
        )

        favorite = Favorite(
            user_id=user_id,
            target_type=target_type_int,
            target_id=data.target_id,
            word=data.word or "",
            phonetic=data.phonetic or "",
            meaning=data.meaning or "",
            content=data.content or "",
            passage_type=data.passage_type or "",
        )
        db.add(favorite)
        await db.flush()
        await db.refresh(favorite)
        return FavoriteOut(
            id=favorite.id,
            target_type=favorite.target_type,
            target_type_name=FAVORITE_TYPE_REVERSE.get(favorite.target_type, "unknown"),
            target_id=favorite.target_id,
            word=favorite.word or "",
            phonetic=favorite.phonetic or "",
            meaning=favorite.meaning or "",
            content=favorite.content or "",
            passage_type=favorite.passage_type or "",
            created_at=favorite.created_at,
        )

    @staticmethod
    async def remove_favorite(db: AsyncSession, user_id: int, favorite_id: int) -> dict:
        """取消收藏"""
        result = await db.execute(
            select(Favorite).where(
                Favorite.id == favorite_id,
                Favorite.user_id == user_id,
            )
        )
        favorite = result.scalar_one_or_none()
        if not favorite:
            raise ValueError("收藏记录不存在")

        await db.delete(favorite)
        await db.flush()
        return {"message": "已取消收藏"}

    @staticmethod
    async def batch_remove_favorites(db: AsyncSession, user_id: int, ids: list[int]) -> dict:
        """批量取消收藏"""
        stmt = select(Favorite).where(
            Favorite.id.in_(ids),
            Favorite.user_id == user_id,
        )
        result = await db.execute(stmt)
        favorites = result.scalars().all()
        for fav in favorites:
            await db.delete(fav)
        await db.flush()
        return {"message": f"已取消 {len(favorites)} 条收藏", "deleted_count": len(favorites)}

    @staticmethod
    async def check_favorite(db: AsyncSession, user_id: int, target_type: str, target_id: int) -> dict:
        """检查是否已收藏，返回 {is_favorite, favorite_id}"""
        type_int = FAVORITE_TYPE_MAP.get(target_type, 0)
        if not type_int:
            return {"is_favorite": False, "favorite_id": None}

        result = await db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.target_type == type_int,
                Favorite.target_id == target_id,
            )
        )
        fav = result.scalar_one_or_none()
        if fav:
            return {"is_favorite": True, "favorite_id": fav.id}
        return {"is_favorite": False, "favorite_id": None}
