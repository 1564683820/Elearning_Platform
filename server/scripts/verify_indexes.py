"""验证每个集合的向量索引"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import get_settings
from pymilvus import MilvusClient

s = get_settings()
client = MilvusClient(uri=f"http://{s.MILVUS_HOST}:{s.MILVUS_PORT}", db_name=s.MILVUS_DATABASE)

# Check key collections and their vector indexes
for cn in ["teacher_documents", "student_errors", "teacher_chat_history",
           "student_chat_history", "quiz_questions", "word_semantics", "reading_materials"]:
    print(f"\n--- {cn} ---")
    desc = client.describe_collection(cn)
    print(f"  字段: {[f['name'] for f in desc.get('fields',[])]}")
    
    # Check embedding index
    for field in ["embedding", "sparse_embedding"]:
        try:
            info = client.describe_index(cn, field)
            print(f"  [{field}] idx: {info.get('index_type','?')} state: {info.get('state','?')}")
        except Exception as e:
            print(f"  [{field}] NO INDEX: {e}")

# Try to explicitly create the embedding index for teacher_documents
print("\n--- 强制重建 teacher_documents embedding 索引 ---")
try:
    client.create_index(
        collection_name="teacher_documents",
        index_params={"field_name":"embedding", "index_type":"IVF_SQ8", "metric_type":"IP", "params":{"nlist":1024}}
    )
    print("OK")
except Exception as e:
    print(f"FAIL: {e}")

# Now try load
try:
    client.load_collection("teacher_documents")
    print("teacher_documents: load OK")
except Exception as e:
    print(f"teacher_documents: load FAIL: {e}")
