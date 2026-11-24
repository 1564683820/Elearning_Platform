"""批量重索引文档脚本：解析所有 parse_status!=2 的文件，分块并向量化到 Milvus

用法:
    python scripts/reindex_documents.py                  # 处理所有未完成的文档
    python scripts/reindex_documents.py --user 42        # 处理指定用户
    python scripts/reindex_documents.py --doc 1,2,3      # 处理指定文档ID列表
"""
import asyncio
import argparse
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.database import async_session as get_async_session
from app.models.stats import UserDocument
from app.services.document_processor import DocumentProcessor


async def reindex_all(user_id: int | None = None, doc_ids: list[int] | None = None):
    """批量处理文档"""
    async with get_async_session() as db:
        stmt = select(UserDocument)

        if doc_ids:
            stmt = stmt.where(UserDocument.id.in_(doc_ids))
        elif user_id:
            stmt = stmt.where(
                UserDocument.user_id == user_id,
                UserDocument.parse_status.in_([0, 3]),
            )
        else:
            stmt = stmt.where(UserDocument.parse_status.in_([0, 3]))

        result = await db.execute(stmt)
        docs = result.scalars().all()

    if not docs:
        print("没有需要处理的文档")
        return

    print(f"共 {len(docs)} 个文档需要处理")
    success_count = 0
    fail_count = 0

    for i, doc in enumerate(docs):
        print(f"[{i+1}/{len(docs)}] 处理文档: {doc.filename} (id={doc.id}, type={doc.file_type})")
        async with get_async_session() as process_db:
            result = await DocumentProcessor.process_document(
                process_db, doc.id, doc.user_id
            )

        if result.get("success"):
            success_count += 1
            print(f"  ✓ 成功, 分块数: {result.get('chunk_count')}")
        else:
            fail_count += 1
            print(f"  ✗ 失败: {result.get('error')}")

    print(f"\n处理完成: 成功 {success_count}, 失败 {fail_count}, 共 {len(docs)}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="批量重索引文档到 Milvus")
    parser.add_argument("--user", type=int, help="只处理指定用户的文档")
    parser.add_argument("--doc", type=str, help="只处理指定文档ID(逗号分隔)")
    args = parser.parse_args()

    doc_ids = None
    if args.doc:
        doc_ids = [int(x.strip()) for x in args.doc.split(",") if x.strip()]

    asyncio.run(reindex_all(user_id=args.user, doc_ids=doc_ids))


if __name__ == "__main__":
    main()
