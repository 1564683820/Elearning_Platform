"""
教学助手文档检索诊断脚本
模拟完整流程：意图分类 → 多路检索 → 分析结果
用于诊断"新建对话无法检索文档"的问题
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import async_session
from app.services.intent_classifier import IntentClassifier
from app.services.embedding_service import EmbeddingService
from app.services.teaching_assistant_service import TeachingAssistantService
from app.services.parent_chunk_store import auto_merge
from app.models.user import User
from sqlalchemy import select, text, func
from app.models.class_models import ClassTeacher

# 测试查询
TEST_QUERY = "2023年高考英语试卷的阅读理解C篇的原文以及翻译"
# 备选查询（不同表述）
ALT_QUERIES = [
    "2023年高考英语试卷的C篇阅读理解原文",
    "给出2023年高考英语试卷的阅读理解C篇",
    "2023高考英语阅读理解C篇的内容",
]


async def check_milvus_documents(teacher_id: int):
    """Step 1: 检查 Milvus teacher_documents 集合中该教师的文档"""
    print("\n" + "=" * 60)
    print("【Step 1】检查 Milvus teacher_documents 集合")
    print("=" * 60)

    try:
        client = EmbeddingService.get_milvus_client()
        coll_name = EmbeddingService.TEACHER_DOCUMENTS

        if not client.has_collection(coll_name):
            print(f"❌ 集合 '{coll_name}' 不存在！")
            return None

        # 获取总数
        stats = client.get_collection_stats(coll_name)
        print(f"  集合 '{coll_name}' 总记录数: {stats.get('row_count', 'unknown')}")

        # 查询该教师的文档数量和 doc_title
        results = client.query(
            collection_name=coll_name,
            filter=f'(user_id == 0 or user_id == {teacher_id})',
            output_fields=["source_type", "source_id", "user_id", "doc_title", "doc_category", "chunk_id"],
            limit=100,
        )

        if not results:
            print(f"❌ 教师 {teacher_id} 没有任何文档在 Milvus 中！")
            return None

        print(f"  教师 {teacher_id} 在 Milvus 中有 {len(results)} 条记录")

        # 按 doc_title 分组统计
        doc_titles = {}
        doc_sources = set()
        for r in results:
            title = r.get("doc_title", "unknown")
            doc_titles[title] = doc_titles.get(title, 0) + 1
            doc_sources.add(r.get("source_type", "unknown"))

        print(f"\n  文档分布 ({len(doc_titles)} 个文档):")
        for title, count in sorted(doc_titles.items(), key=lambda x: -x[1]):
            print(f"    - {title}: {count} 块")

        print(f"\n  source_type 分布: {doc_sources}")

        # 检查是否有"高考"相关的文档
        exam_docs = [r for r in results if "高考" in (r.get("doc_title", "") or "")]
        if exam_docs:
            print(f"\n  ✅ 找到 {len(exam_docs)} 块包含'高考'的文档")
        else:
            print(f"\n  ⚠️ 未找到标题含'高考'的文档，列出所有文档标题:")
            for title in sorted(doc_titles.keys()):
                print(f"    - '{title}'")

        return results
    except Exception as e:
        print(f"❌ Milvus 连接/查询失败: {e}")
        return None


async def test_intent_classifier(db, teacher_id: int, query: str):
    """Step 2: 测试意图分类器"""
    print("\n" + "=" * 60)
    print(f"【Step 2】意图分类测试")
    print(f"  查询: '{query}'")
    print("=" * 60)

    try:
        result = await IntentClassifier.classify(db, query, teacher_id)
        intent = result.get("intent", "unknown")
        entities = result.get("entities", {})
        rewritten = result.get("rewritten_query", query)
        strategy = IntentClassifier.get_search_strategy(intent)

        print(f"  意图: {intent}")
        print(f"  实体: {json.dumps(entities, ensure_ascii=False)}")
        print(f"  改写查询: {rewritten}")
        print(f"  检索策略: knowledge_top_k={strategy.get('knowledge_top_k')}, "
              f"errors_top_k={strategy.get('errors_top_k')}, "
              f"use_mysql_stats={strategy.get('use_mysql_stats')}")

        if strategy.get("knowledge_top_k", 0) == 0:
            print(f"  ⚠️⚠️⚠️ 意图 '{intent}' 的知识库检索 top_k=0，文档检索被完全跳过！")
            print(f"  这可能是导致新对话无法检索文档的原因！")

        return result, strategy
    except Exception as e:
        print(f"❌ 意图分类失败: {e}")
        return None, None


async def test_hybrid_search(db, teacher_id: int, query: str, top_k: int = 15):
    """Step 3: 测试混合检索"""
    print("\n" + "=" * 60)
    print(f"【Step 3】混合检索测试 (top_k={top_k})")
    print(f"  查询: '{query}'")
    print("=" * 60)

    try:
        results = await EmbeddingService.hybrid_search(
            db, query,
            EmbeddingService.TEACHER_DOCUMENTS,
            top_k=top_k,
            user_id=teacher_id,
        )

        if not results:
            print("  ❌ 无搜索结果！")
            return []

        print(f"  命中 {len(results)} 条结果")

        # 分析结果
        source_types = set()
        for i, r in enumerate(results[:10]):
            st = r.get("source_type", "?")
            title = r.get("doc_title", "?") or "?"
            score = r.get("score", 0)
            content_preview = (r.get("content", "") or "")[:80].replace("\n", " ")
            source_types.add(st)
            print(f"  [{i+1}] score={score:.4f} type={st} title='{title}' content='{content_preview}...'")

        print(f"\n  检索到的 source_type: {source_types}")

        # 检查是否有 doc_ 前缀
        doc_results = [r for r in results if r.get("source_type", "").startswith("doc_")]
        print(f"  其中 source_type 以 'doc_' 开头: {len(doc_results)}/{len(results)}")

        return results
    except Exception as e:
        print(f"❌ 混合检索失败: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_auto_merge(db, results):
    """Step 4: 测试 auto-merge"""
    if not results:
        return []

    print("\n" + "=" * 60)
    print(f"【Step 4】Auto-merge 测试")
    print("=" * 60)

    try:
        merged = await auto_merge(db, results)
        print(f"  Auto-merge 前: {len(results)} 条")
        print(f"  Auto-merge 后: {len(merged)} 条")
        if merged:
            for i, r in enumerate(merged[:5]):
                print(f"  [{i+1}] level={r.get('merged_level', '?')} "
                      f"chunk_id={r.get('chunk_id', '?')} "
                      f"content_len={len(r.get('content', '') or '')}")
        return merged
    except Exception as e:
        print(f"  ⚠️ Auto-merge 失败 (可能数据库无父块记录): {e}")
        return results


async def main():
    print("=" * 60)
    print("教学助手文档检索诊断")
    print("=" * 60)

    async with async_session() as db:
        # 获取一个有效的 teacher_id
        result = await db.execute(
            select(User.id).where(User.role == "teacher").limit(1)
        )
        row = result.first()
        if not row:
            # 尝试任意用户
            result = await db.execute(select(User.id).limit(1))
            row = result.first()
            if not row:
                print("❌ 数据库中无用户！")
                return

        teacher_id = row[0]
        print(f"使用教师 ID: {teacher_id}")

        # Step 1: 检查 Milvus 中的文档
        milvus_docs = await check_milvus_documents(teacher_id)
        if not milvus_docs:
            print("\n⚠️ 该教师在 Milvus 中没有已索引的文档!")
            print("  如果其他对话能检索到文档，可能使用了不同的 teacher_id")
            print("  或文档被索引为 user_id=0 (全局文档)")
            # Check with user_id=0
            print("\n  尝试检查 user_id=0 的全局文档...")
            try:
                client = EmbeddingService.get_milvus_client()
                global_docs = client.query(
                    collection_name=EmbeddingService.TEACHER_DOCUMENTS,
                    filter="user_id == 0",
                    output_fields=["source_type", "source_id", "user_id", "doc_title"],
                    limit=10,
                )
                if global_docs:
                    print(f"  找到 {len(global_docs)} 条全局文档 (user_id=0):")
                    doc_titles = {}
                    for r in global_docs:
                        title = r.get("doc_title", "unknown")
                        doc_titles[title] = doc_titles.get(title, 0) + 1
                    for title, count in sorted(doc_titles.items()):
                        print(f"    - {title}: {count} 块")
                else:
                    print("  也没有全局文档")
            except Exception as e:
                print(f"  查询失败: {e}")

        print("\n" + "=" * 60)
        print("测试主查询")
        print("=" * 60)

        # Step 2: 意图分类
        intent_result, strategy = await test_intent_classifier(db, teacher_id, TEST_QUERY)
        intent = intent_result.get("intent", "general_chat") if intent_result else "general_chat"
        rewritten = intent_result.get("rewritten_query", TEST_QUERY) if intent_result else TEST_QUERY
        kv_top_k = strategy.get("knowledge_top_k", 5) if strategy else 5
        source_type_filter = (intent == "document_query")
        print(f"  document_query source_type 过滤: {'启用' if source_type_filter else '未启用'}")

        # Step 3: 混合检索
        results = await test_hybrid_search(db, teacher_id, rewritten, top_k=kv_top_k)

        # Step 3.1: 模拟 document_query 的 source_type 过滤
        if source_type_filter and results:
            before = len(results)
            results = [r for r in results if r.get("source_type", "").startswith("doc_")]
            print(f"\n  document_query 过滤: {before} → {len(results)} 条")
            if len(results) == 0 and before > 0:
                print(f"  ⚠️⚠️⚠️ 关键问题：所有 {before} 条结果的 source_type 都不以 'doc_' 开头！")
                print(f"  这意味着 document_query 意图的 source_type 过滤把所有结果都过滤掉了！")

        # Step 4: Auto-merge
        merged = await test_auto_merge(db, results)

        # 测试备选查询（比较不同表述的差异）
        print("\n" + "=" * 60)
        print("备选查询对比测试")
        print("=" * 60)
        for alt_query in ALT_QUERIES:
            alt_result, alt_strategy = await test_intent_classifier(db, teacher_id, alt_query)
            if alt_result:
                alt_intent = alt_result.get("intent", "?")
                alt_rewritten = alt_result.get("rewritten_query", alt_query)
                alt_top_k = alt_strategy.get("knowledge_top_k", 5) if alt_strategy else 5
                print(f"  查询: '{alt_query}'")
                print(f"    → 意图: {alt_intent}, top_k={alt_top_k}, 改写: '{alt_rewritten}'")
                if alt_strategy and alt_strategy.get("knowledge_top_k", 0) == 0:
                    print(f"    ⚠️ 这个表述会导致文档检索被跳过！")

        # 最终评估
        print("\n" + "=" * 60)
        print("【诊断结论】")
        print("=" * 60)

        issues = []
        if not milvus_docs:
            issues.append("❌ Milvus teacher_documents 中没有该教师的文档")
        if intent_result and kv_top_k == 0:
            issues.append(f"❌ 意图'{intent}'的知识库检索 top_k=0，完全跳过文档检索")
        if strategy and source_type_filter and results and not any(r.get("source_type", "").startswith("doc_") for r in results):
            issues.append("❌ document_query 过滤后无结果，所有文档的 source_type 不以 doc_ 开头")
        if not results:
            issues.append("❌ 混合检索未返回任何结果（可能是 Milvus 连接问题或 BM25/embedding 失败）")

        if issues:
            print("发现以下问题：")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("✅ 未发现明显问题，文档检索流程正常")
            if merged:
                print(f"  最终可用于回答的文档块数: {len(merged)}")


if __name__ == "__main__":
    asyncio.run(main())
