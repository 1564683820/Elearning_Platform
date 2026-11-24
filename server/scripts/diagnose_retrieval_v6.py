"""诊断 v6 — 完整检索链路测试（含真实 embedding）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
from pymilvus import MilvusClient
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
client = MilvusClient(uri=uri, db_name=settings.MILVUS_DATABASE)
coll_name = "teacher_documents"

# 1. 检查集合加载状态
print("=" * 60)
print("1. 集合加载状态")
print("=" * 60)
try:
    state = client.get_load_state(coll_name)
    print(f"  {coll_name}: {state}")
except Exception as e:
    print(f"  获取加载状态失败: {e}")

# 2. 检查索引状态
print(f"\n{'='*60}")
print("2. 索引状态")
print(f"{'='*60}")
try:
    indexes = client.list_indexes(coll_name)
    print(f"  索引列表: {indexes}")
except Exception as e:
    print(f"  获取索引失败: {e}")

# 3. 检查索引详情
print(f"\n{'='*60}")
print("3. 索引详情")
print(f"{'='*60}")
try:
    # 检查 embedding 索引
    idx_desc = client.describe_index(coll_name, "embedding")
    print(f"  embedding 索引: {idx_desc}")
except Exception as e:
    print(f"  embedding 索引详情失败: {e}")
try:
    sparse_idx = client.describe_index(coll_name, "sparse_embedding")
    print(f"  sparse_embedding 索引: {sparse_idx}")
except Exception as e:
    print(f"  sparse_embedding 索引详情失败: {e}")

print(f"\n{'='*60}")
print("4. 集合描述")
print(f"{'='*60}")
try:
    desc = client.describe_collection(coll_name)
    print(f"  集合: {desc.get('collection_name')}")
    print(f"  行数: {desc.get('row_count', '?')}")
    print(f"  自动加载: {desc.get('auto_load', '?')}")
    # 查看字段
    for f in desc.get('fields', []):
        print(f"  字段: {f['name']} ({f['type']}) nullable={f.get('nullable','?')} auto_id={f.get('auto_id','?')} is_primary={f.get('is_primary','?')}")
except Exception as e:
    print(f"  获取集合描述失败: {e}")

# 5. 用真实文本模拟查询（不调 AI，只用 Milvus 已有数据）
# 读取一些现有的 content 看看阅读题实际在哪些 chunk 里
print(f"\n{'='*60}")
print("5. 完整查看阅读题相关 chunk 内容")
print(f"{'='*60}")
all_chunks = client.query(
    collection_name=coll_name,
    filter="user_id == 14",
    limit=1000,
    output_fields=["content", "chunk_order", "doc_title", "source_id", "chunk_id"],
)
all_chunks.sort(key=lambda x: (x.get("source_id", 0), x.get("chunk_order", 0), x.get("chunk_id", "")))

# 找出A篇阅读的实际内容
for c in all_chunks:
    content = c.get("content", "")
    if "Grading Policies" in content or ("阅读" in content and "A" in content[:150]):
        print(f"\n  chunk_id={c.get('chunk_id')}, order={c.get('chunk_order')}")
        print(f"  content (完整):")
        print(f"  {content}")
        print(f"  {'='*40}")

print(f"\n=== 完成 ===")
