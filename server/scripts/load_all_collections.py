"""手动加载 Milvus 所有集合并验证检索"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from pymilvus import MilvusClient
import numpy as np

settings = get_settings()
uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
db_name = settings.MILVUS_DATABASE

print(f"数据库: {db_name}")

client = MilvusClient(uri=uri, db_name=db_name)
colls = ["teacher_documents", "student_errors", "teacher_chat_history",
         "student_chat_history", "quiz_questions", "word_semantics", "reading_materials"]

# 加载所有集合
for c in colls:
    try:
        client.load_collection(c)
        print(f"[{c}] load_collection 触发")
    except Exception as e:
        print(f"[{c}] load_collection 异常: {e}")

import time
time.sleep(2)  # 等待加载完成

# 验证加载状态
print("\n--- 加载状态验证 ---")
for c in colls:
    try:
        state = client.get_load_state(c)
        print(f"[{c}] {state}")
    except Exception as e:
        print(f"[{c}] {e}")

# 测试 teacher_documents 检索
print("\n--- 测试 teacher_documents 检索 ---")
dummy = np.zeros(1024, dtype=np.float32).tolist()
try:
    r = client.search(
        collection_name="teacher_documents", data=[dummy],
        anns_field="embedding", limit=3,
        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
        output_fields=["content", "title", "user_id", "source_type", "doc_category"],
    )
    if r and r[0]:
        print(f"命中 {len(r[0])} 条!")
        for h in r[0]:
            e = h.get('entity', {})
            print(f"  id={h['id']}, title={e.get('title','')[:50]}, cat={e.get('doc_category','?')}, user_id={e.get('user_id')}")
    else:
        print("0 条!")
except Exception as e:
    print(f"失败: {e}")
