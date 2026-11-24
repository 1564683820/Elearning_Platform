"""诊断 Milvus 检索问题 v2 — 检查 user_id 分布和检索效果"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
db_name = settings.MILVUS_DATABASE
print(f"目标数据库: {db_name}")

from pymilvus import MilvusClient
import numpy as np

client = MilvusClient(uri=uri, db_name=db_name)
coll_name = "teacher_documents"

# 1. 查询所有数据（无过滤）
print(f"\n{'='*60}")
print(f"1. teacher_documents 集合概览")
print(f"{'='*60}")
stat = client.get_collection_stats(coll_name)
print(f"总行数: {stat.get('row_count', '?')}")

# 2. 按 user_id 分组统计
print(f"\n{'='*60}")
print(f"2. 按 user_id 分组查询")
print(f"{'='*60}")
try:
    # query 不支持 group by，所以手动查一些 user_id 范围
    for uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 20, 23]:
        res = client.query(
            collection_name=coll_name,
            filter=f'user_id == {uid}',
            limit=5,
            output_fields=["user_id", "source_type", "doc_title", "source_id"],
        )
        if res:
            titles = [r.get("doc_title", "")[:30] for r in res[:3]]
            print(f"  user_id={uid}: {len(res)} 条 (前3: {titles})")
except Exception as e:
    print(f"  user_id 查询失败: {e}")

# 3. 用零向量做一次无过滤检索
print(f"\n{'='*60}")
print(f"3. 无过滤检索测试（零向量）")
print(f"{'='*60}")
dummy_vec = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32).tolist()
try:
    results = client.search(
        collection_name=coll_name,
        data=[dummy_vec],
        anns_field="embedding",
        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
        limit=5,
        output_fields=["content", "doc_title", "user_id", "source_type", "doc_category", "source_id"],
        filter=None,
    )
    if results and len(results[0]) > 0:
        for h in results[0]:
            e = h.get('entity', {})
            title = e.get('doc_title', '')[:50]
            content_preview = e.get('content', '')[:80]
            print(f"  id={h['id']}, uid={e.get('user_id')}, title={title}")
            print(f"    content: {content_preview}")
            print(f"    dist={h['distance']:.4f}")
    else:
        print("  0 条结果!")
except Exception as e:
    print(f"  检索失败: {e}")

print(f"\n{'='*60}")
print(f"4. 带 user_id 过滤检索")
print(f"{'='*60}")
# 先查有哪些 user_id 有数据
all_uids = set()
for uid in range(0, 25):
    res = client.query(
        collection_name=coll_name,
        filter=f'user_id == {uid}',
        limit=1,
        output_fields=["user_id"],
    )
    if res:
        all_uids.add(uid)
print(f"有数据的 user_id: {sorted(all_uids)}")

# 对每个有数据的 user_id 做检索
for uid in sorted(all_uids):
    try:
        results = client.search(
            collection_name=coll_name,
            data=[dummy_vec],
            anns_field="embedding",
            search_params={"metric_type": "IP", "params": {"nprobe": 10}},
            limit=3,
            output_fields=["doc_title", "source_id", "user_id"],
            filter=f'(user_id == 0 or user_id == {uid})',
        )
        count = len(results[0]) if results and results[0] else 0
        titles = []
        if results and results[0]:
            for h in results[0]:
                t = h.get('entity', {}).get('doc_title', '')[:30]
                titles.append(t)
        print(f"  filter(user_id={uid}): {count} 条匹配, titles={titles}")
    except Exception as e:
        print(f"  filter(user_id={uid}): 失败 {e}")

print(f"\n{'='*60}")
print(f"5. 直接查询关键过滤表达式")
print(f"{'='*60}")
try:
    # 模拟 _build_filter 中的表达式
    test_uid = 14  # 常见的 teacher_id
    expr = f'(user_id == 0 or user_id == {test_uid})'
    res = client.query(
        collection_name=coll_name,
        filter=expr,
        limit=10,
        output_fields=["user_id", "doc_title", "source_id"],
    )
    print(f"  表达式: {expr}")
    print(f"  命中: {len(res)} 条")
    for r in res[:5]:
        print(f"    uid={r.get('user_id')}, title={r.get('doc_title','')[:40]}, source_id={r.get('source_id')}")
except Exception as e:
    print(f"  查询失败: {e}")

print(f"\n=== 完成 ===")
