"""诊断 Milvus 检索问题 v3 — 检查 user_id=14 所有数据和检索效果"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
db_name = settings.MILVUS_DATABASE

from pymilvus import MilvusClient
import numpy as np

client = MilvusClient(uri=uri, db_name=db_name)
coll_name = "teacher_documents"

# 1. 查询 user_id=14 的所有记录
print("=" * 60)
print("1. user_id=14 所有文档统计")
print("=" * 60)
all_u14 = client.query(
    collection_name=coll_name,
    filter="user_id == 14",
    limit=10000,
    output_fields=["user_id", "doc_title", "source_id", "chunk_order", "content", "doc_category", "stage"],
)
print(f"user_id=14 共 {len(all_u14)} 条记录")

# 按 source_id（文档ID）分组
docs = {}
for r in all_u14:
    sid = r.get("source_id")
    title = r.get("doc_title", "")
    if sid not in docs:
        docs[sid] = {"title": title, "count": 0, "sample_content": ""}
    docs[sid]["count"] += 1
    if not docs[sid]["sample_content"]:
        docs[sid]["sample_content"] = (r.get("content") or "")[:200]

print(f"\n共 {len(docs)} 个独立文档:")
for sid, info in docs.items():
    print(f"  source_id={sid}: {info['count']} chunks, title={info['title']}")
    print(f"    内容样: {info['sample_content']}")
    print()

# 特别注意：检查是否有 "阅读" 相关的内容
print(f"\n{'='*60}")
print("2. 检查 chunks 中是否包含阅读题相关内容")
print(f"{'='*60}")
reading_hits = [r for r in all_u14 if "阅读" in (r.get("content") or "")]
print(f"包含'阅读'的chunk: {len(reading_hits)} 条")
if reading_hits:
    for r in reading_hits[:5]:
        print(f"  order={r.get('chunk_order')}, content={r.get('content','')[:150]}")

# 检查是否有A篇/B篇阅读题相关
part_a = [r for r in all_u14 if "A" in (r.get("content") or "")[:10]]
print(f"开头含'A'的chunk: {len(part_a)} 条")

# 3. 用真实内容做零向量检索测试
print(f"\n{'='*60}")
print("3. 零向量检索测试（无过滤 vs 有过滤）")
print(f"{'='*60}")
dummy_vec = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32).tolist()

# 3a. 无过滤 — 期望看到所有数据
res_all = client.search(
    collection_name=coll_name,
    data=[dummy_vec],
    anns_field="embedding",
    search_params={"metric_type": "IP", "params": {"nprobe": 10}},
    limit=10,
    output_fields=["user_id", "doc_title", "source_id"],
    filter=None,
)
count_all = len(res_all[0]) if res_all and res_all[0] else 0
print(f"  无过滤: {count_all} 条")

# 3b. 过滤 user_id=14
res_14 = client.search(
    collection_name=coll_name,
    data=[dummy_vec],
    anns_field="embedding",
    search_params={"metric_type": "IP", "params": {"nprobe": 10}},
    limit=10,
    output_fields=["user_id", "doc_title", "source_id"],
    filter="(user_id == 0 or user_id == 14)",
)
count_14 = len(res_14[0]) if res_14 and res_14[0] else 0
print(f"  filter(user_id=0 or 14): {count_14} 条")
if res_14 and res_14[0]:
    for h in res_14[0]:
        e = h.get('entity', {})
        print(f"    dist={h['distance']:.4f}, uid={e.get('user_id')}, title={e.get('doc_title','')[:40]}")

# 3c. 过滤 user_id=14 不带 0
res_14_only = client.search(
    collection_name=coll_name,
    data=[dummy_vec],
    anns_field="embedding",
    search_params={"metric_type": "IP", "params": {"nprobe": 10}},
    limit=10,
    output_fields=["user_id", "doc_title", "source_id"],
    filter="user_id == 14",
)
count_14_only = len(res_14_only[0]) if res_14_only and res_14_only[0] else 0
print(f"  filter(user_id=14 only): {count_14_only} 条")

print(f"\n{'='*60}")
print("4. 检查 big user_id 的数据")
print(f"{'='*60}")
# 找出有数据的大 user_id
big_user_ids = set()
for uid in [327443946470903808, 327443946470903809, 327443946470903810, 327443946470903811, 327443946470903812]:
    res = client.query(
        collection_name=coll_name,
        filter=f"user_id == {uid}",
        limit=3,
        output_fields=["user_id", "doc_title", "source_id"],
    )
    if res:
        big_user_ids.add(uid)
        print(f"  user_id={uid}: {len(res)} 条")
        for r in res:
            print(f"    title={r.get('doc_title','')[:50]}, source_id={r.get('source_id')}")

print(f"\n=== 完成 ===")
