"""父级分块持久化存储 — 用于 Auto-merging Retriever

将 Level 1 和 Level 2 分块存到 MySQL，索引阶段返回的 Level 3 叶子块
通过 parent_chunk_id 回溯到父块，实现 auto-merge 上下文增强。

表结构: document_chunk_parents
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chunk_manager import ChunkInfo

logger = logging.getLogger(__name__)


async def ensure_table(db: AsyncSession):
    """确保 document_chunk_parents 表存在"""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS document_chunk_parents (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            doc_id BIGINT NOT NULL COMMENT '文档ID',
            chunk_id VARCHAR(128) NOT NULL COMMENT '唯一分块标识',
            level INT NOT NULL COMMENT '分块层级: 1=parent, 2=intermediate',
            content TEXT NOT NULL COMMENT '分块文本内容',
            parent_chunk_id VARCHAR(128) DEFAULT NULL COMMENT '父分块ID',
            seq_order INT NOT NULL COMMENT '分块顺序',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_chunk_id (chunk_id),
            KEY idx_doc_id (doc_id),
            KEY idx_parent (parent_chunk_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    await db.commit()
    logger.info("document_chunk_parents 表已就绪")


async def store_parent_chunks(
    db: AsyncSession,
    doc_id: int,
    parent_chunks: list[ChunkInfo],
):
    """批量存储 Level 1 和 Level 2 分块到 MySQL

    参数:
        db: 数据库会话
        doc_id: 文档 ID
        parent_chunks: Level 1 / Level 2 的分块列表
    """
    if not parent_chunks:
        return

    # 先清除旧数据
    await clear_doc_parents(db, doc_id)

    values = []
    for c in parent_chunks:
        escaped_content = c.content.replace("'", "''")
        parent_id_str = "NULL" if c.parent_chunk_id is None else f"'{c.parent_chunk_id}'"
        values.append(
            f"({doc_id}, '{c.chunk_id}', {c.level}, "
            f"'{escaped_content}', "
            f"{parent_id_str}, "
            f"{c.seq})"
        )

    if not values:
        return

    sql = f"""
        INSERT INTO document_chunk_parents 
            (doc_id, chunk_id, level, content, parent_chunk_id, seq_order)
        VALUES {', '.join(values)}
    """
    await db.execute(text(sql))
    await db.flush()
    logger.info(f"存储了 {len(parent_chunks)} 个父级分块 (doc_id={doc_id})")


async def get_parent_chunk(
    db: AsyncSession,
    chunk_id: str,
) -> Optional[dict]:
    """根据 chunk_id 获取单个父级分块

    返回: {content, level, chunk_id, parent_chunk_id} 或 None
    """
    sql = """
        SELECT content, level, chunk_id, parent_chunk_id
        FROM document_chunk_parents
        WHERE chunk_id = :chunk_id
    """
    result = await db.execute(text(sql), {"chunk_id": chunk_id})
    row = result.fetchone()
    if row is None:
        return None
    return {
        "content": row[0],
        "level": row[1],
        "chunk_id": row[2],
        "parent_chunk_id": row[3],
    }


async def get_parent_chunks_batch(
    db: AsyncSession,
    chunk_ids: list[str],
) -> dict[str, dict]:
    """批量获取父级分块

    参数:
        chunk_ids: chunk_id 列表

    返回: {chunk_id: {content, level, ...}, ...}
    """
    if not chunk_ids:
        return {}

    placeholders = ", ".join([f"'{cid}'" for cid in chunk_ids])
    sql = f"""
        SELECT content, level, chunk_id, parent_chunk_id
        FROM document_chunk_parents
        WHERE chunk_id IN ({placeholders})
    """
    result = await db.execute(text(sql))
    mapping = {}
    for row in result.fetchall():
        mapping[row[2]] = {
            "content": row[0],
            "level": row[1],
            "chunk_id": row[2],
            "parent_chunk_id": row[3],
        }
    return mapping


async def get_parent_chunks_by_doc(db: AsyncSession, doc_id: int) -> list[dict]:
    """获取某文档的所有父级分块"""
    sql = """
        SELECT content, level, chunk_id, parent_chunk_id, seq_order
        FROM document_chunk_parents
        WHERE doc_id = :doc_id
        ORDER BY level, seq_order
    """
    result = await db.execute(text(sql), {"doc_id": doc_id})
    return [
        {
            "content": row[0],
            "level": row[1],
            "chunk_id": row[2],
            "parent_chunk_id": row[3],
            "seq_order": row[4],
        }
        for row in result.fetchall()
    ]


async def clear_doc_parents(db: AsyncSession, doc_id: int):
    """清除某文档的所有父级分块"""
    await db.execute(
        text("DELETE FROM document_chunk_parents WHERE doc_id = :doc_id"),
        {"doc_id": doc_id},
    )
    await db.flush()


async def auto_merge(
    db: AsyncSession,
    leaf_results: list[dict],
) -> list[dict]:
    """Auto-merging：将检索到的叶子块按 parent_chunk_id 分组合并

    如果连续多个叶子块属于同一个父块，返回父块内容而不是多个叶子块。
    这确保了 LLM 获得更完整的上下文。

    参数:
        leaf_results: Milvus 检索结果列表，每个包含 content, source_type,
                      source_id, score, chunk_id, parent_chunk_id, level 等字段

    返回:
        合并后的结果列表
    """
    if not leaf_results:
        return []

    # 收集需要查询的 parent_chunk_id
    parent_ids = set()
    for r in leaf_results:
        pid = r.get("parent_chunk_id")
        if pid:
            parent_ids.add(pid)

    # 批量查询父块内容
    parent_map = await get_parent_chunks_batch(db, list(parent_ids))

    # 按 parent_chunk_id 分组（保持原始顺序）
    merged = []
    seen_parents: set[str] = set()

    for r in leaf_results:
        pid = r.get("parent_chunk_id")
        if pid and pid in parent_map:
            if pid not in seen_parents:
                seen_parents.add(pid)
                parent = parent_map[pid]
                merged.append({
                    "content": parent["content"],
                    "source_type": r.get("source_type", ""),
                    "source_id": r.get("source_id", 0),
                    "score": r.get("score", 0.0),
                    "original_level": r.get("level", 3),
                    "merged_level": parent["level"],
                    "chunk_id": pid,
                    "child_chunks": [r.get("chunk_id", "")],
                })
            else:
                # 同一父块的后续叶子，追加 child_chunks
                for m in merged:
                    if m.get("chunk_id") == pid:
                        m["child_chunks"].append(r.get("chunk_id", ""))
                        # 取最高分
                        if r.get("score", 0) > m.get("score", 0):
                            m["score"] = r["score"]
                        break
        else:
            # 没有父块信息的叶子，原样保留
            merged.append({
                "content": r.get("content", ""),
                "source_type": r.get("source_type", ""),
                "source_id": r.get("source_id", 0),
                "score": r.get("score", 0.0),
                "original_level": r.get("level", 3),
                "merged_level": 3,
                "chunk_id": r.get("chunk_id", ""),
            })

    return merged
