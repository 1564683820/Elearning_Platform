"""测试 Milvus 检索是否正常 — teacher_documents 集合"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
db_name = settings.MILVUS_DATABASE

print(f"目标数据库: {db_name}")

from pymilvus import MilvusClient

client = MilvusClient(uri=uri, db_name=db_name)

# 检查集合加载状态
for coll in ["teacher_documents", "student_errors", "quiz_questions"]:
    try:
        state = client.get_load_state(coll)
        print(f"[{coll}] 加载状态: {state}")
    except Exception as e:
        print(f"[{coll}] 加载状态获取失败: {e}")

# 尝试用零向量做一次检索
print("\n--- 测试 teacher_documents 检索 ---")
import numpy as np
dummy_vec = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32).tolist()

try:
    results = client.search(
        collection_name="teacher_documents",
        data=[dummy_vec],
        anns_field="embedding",
        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
        limit=3,
        output_fields=["content", "title", "user_id", "source_type"],
        filter=None,
    )
    if results and len(results) > 0:
        hits = results[0]
        print(f"命中: {len(hits)} 条")
        for h in hits:
            print(f"  id={h['id']}, title={h.get('entity',{}).get('title','')[:50]}, dist={h['distance']:.4f}")
    else:
        print("0 条结果!")
except Exception as e:
    print(f"检索失败: {e}")

# 测试带 filter 的检索
print("\n--- 测试带 user_id 过滤的检索 ---")
try:
    results2 = client.search(
        collection_name="teacher_documents",
        data=[dummy_vec],
        anns_field="embedding",
        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
        limit=3,
        output_fields=["content", "title", "user_id", "source_type", "doc_category"],
        filter="user_id > 0",
    )
    if results2 and len(results2) > 0:
        hits2 = results2[0]
        print(f"带filter命中: {len(hits2)} 条")
        for h in hits2:
            e = h.get('entity', {})
            print(f"  id={h['id']}, title={e.get('title','')[:50]}, user_id={e.get('user_id')}, category={e.get('doc_category','?')}")
    else:
        print("0 条结果!")
except Exception as e:
    print(f"带filter检索失败: {e}")

print("\n=== 完成 ===")
