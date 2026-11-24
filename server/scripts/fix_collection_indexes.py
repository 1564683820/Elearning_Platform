"""为 elearningtest_v2 所有集合补建索引（不删数据）"""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fix_indexes")

from app.core.config import get_settings
from pymilvus import MilvusClient

settings = get_settings()
uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
db_name = settings.MILVUS_DATABASE
DIM = settings.EMBEDDING_DIM

print(f"目标: {uri} / {db_name}")
client = MilvusClient(uri=uri, db_name=db_name)

# 7个集合的索引定义
INDEX_DEFS = {
    "teacher_documents": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "title", "index_type": "INVERTED", "params": {}},
        {"field": "doc_category", "index_type": "INVERTED", "params": {}},
        {"field": "material_type", "index_type": "INVERTED", "params": {}},
        {"field": "sub_type", "index_type": "INVERTED", "params": {}},
        {"field": "difficulty", "index_type": "INVERTED", "params": {}},
    ],
    "student_errors": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "student_name", "index_type": "INVERTED", "params": {}},
        {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
        {"field": "category", "index_type": "INVERTED", "params": {}},
        {"field": "exam_name", "index_type": "INVERTED", "params": {}},
        {"field": "related_word", "index_type": "INVERTED", "params": {}},
    ],
    "teacher_chat_history": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "session_id", "index_type": "INVERTED", "params": {}},
        {"field": "role", "index_type": "INVERTED", "params": {}},
    ],
    "student_chat_history": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "session_id", "index_type": "INVERTED", "params": {}},
        {"field": "role", "index_type": "INVERTED", "params": {}},
    ],
    "quiz_questions": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "type", "index_type": "INVERTED", "params": {}},
        {"field": "category", "index_type": "INVERTED", "params": {}},
        {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
    ],
    "word_semantics": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "word", "index_type": "INVERTED", "params": {}},
        {"field": "part_of_speech", "index_type": "INVERTED", "params": {}},
    ],
    "reading_materials": [
        {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
        {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        {"field": "title", "index_type": "INVERTED", "params": {}},
        {"field": "material_type", "index_type": "INVERTED", "params": {}},
    ],
}

for coll_name, idx_list in INDEX_DEFS.items():
    if not client.has_collection(coll_name):
        print(f"\n跳过 {coll_name}: 集合不存在")
        continue

    print(f"\n--- {coll_name} ---")
    for idx_def in idx_list:
        field = idx_def["field"]
        try:
            # 先检查索引是否已存在
            try:
                client.describe_index(coll_name, field)
                print(f"  [{field}] 索引已存在，跳过")
                continue
            except Exception:
                pass  # 不存在，创建

            index_params = {
                "field_name": field,
                "index_type": idx_def["index_type"],
                "params": idx_def.get("params", {}),
            }
            if "metric_type" in idx_def:
                index_params["metric_type"] = idx_def["metric_type"]

            client.create_index(collection_name=coll_name, index_params=index_params)
            print(f"  [{field}] 索引创建成功 ({idx_def['index_type']})")
        except Exception as e:
            print(f"  [{field}] 索引创建失败: {e}")

# 建完索引后加载所有集合
print("\n\n--- 加载集合 ---")
for coll_name in INDEX_DEFS:
    try:
        client.load_collection(coll_name)
        print(f"  [{coll_name}] load_collection 触发")
    except Exception as e:
        print(f"  [{coll_name}] load 失败: {e}")

time.sleep(2)
print("\n--- 加载状态 ---")
for coll_name in INDEX_DEFS:
    try:
        s = client.get_load_state(coll_name)
        print(f"  [{coll_name}] {s}")
    except Exception as e:
        print(f"  [{coll_name}] {e}")

print("\n=== 完成 ===")
