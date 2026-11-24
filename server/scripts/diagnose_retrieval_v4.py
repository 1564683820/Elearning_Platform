"""诊断 v4 — 用真实 embedding 测试语义检索 + 检查 chunk 内容完整性"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from app.core.config import get_settings
from app.services.embedding_service import EmbeddingService
from app.services.ai_service import AIService
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

settings = get_settings()

async def main():
    engine = create_async_engine(settings.SYNC_DATABASE_URL.replace("+pymysql", "+aiomysql").replace("mysql://", "mysql+aiomysql://"))
    async with AsyncSession(engine) as db:
        # 测试1: 用真实查询做 hybrid_search
        test_queries = [
            "翻译2022年高考英语试卷的第一篇阅读题的文章",
            "2022年高考英语新高考一卷阅读A篇",
            "2022年高考英语阅读理解",
            "A篇阅读文章内容",
        ]
        
        for q in test_queries:
            print(f"\n{'='*60}")
            print(f"查询: '{q}'")
            print(f"{'='*60}")
            results = await EmbeddingService.hybrid_search(
                db, q, EmbeddingService.TEACHER_DOCUMENTS,
                top_k=5, user_id=14,
                output_fields=["content", "doc_title", "doc_category", "source_type", "chunk_order", "source_id"],
            )
            if results:
                print(f"  命中: {len(results)} 条")
                for i, r in enumerate(results):
                    content = r.get("content", "")[:200]
                    score = r.get("score", 0)
                    doc_title = r.get("doc_title", "")
                    co = r.get("chunk_order", -1)
                    print(f"  [{i}] score={score:.4f}, chunk_order={co}, title={doc_title}")
                    print(f"      content: {content}")
                    print()
            else:
                print(f"  → **0 条结果!**")
        
        # 测试2: 检查 chunk 内容 — 读取完整内容看阅读题在哪
        print(f"\n{'='*60}")
        print("检查原文中阅读题所在位置")
        print(f"{'='*60}")
        
        # 用 "A篇" 相关内容做测试
        results_a = await EmbeddingService.hybrid_search(
            db, "2022年高考英语阅读A篇", EmbeddingService.TEACHER_DOCUMENTS,
            top_k=3, user_id=14,
            output_fields=["content", "doc_title", "chunk_order"],
        )
        if results_a:
            for r in results_a:
                print(f"  chunk_order={r.get('chunk_order')}, score={r.get('score'):.4f}")
                print(f"  content: {r.get('content','')[:300]}")
                print()
        else:
            print("  → 0 条结果!")
            # fallback: 直接查 Milvus 中有没有阅读相关内容
            from pymilvus import MilvusClient
            client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}", db_name=settings.MILVUS_DATABASE)
            all_chunks = client.query(
                collection_name="teacher_documents",
                filter="user_id == 14",
                limit=1000,
                output_fields=["content", "chunk_order", "doc_title"],
            )
            print(f"\n  Milvus 中 user_id=14 共 {len(all_chunks)} 条记录")
            for c in all_chunks:
                content = c.get("content", "")
                if "阅读" in content:
                    print(f"  order={c.get('chunk_order')}: {content[:200]}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
