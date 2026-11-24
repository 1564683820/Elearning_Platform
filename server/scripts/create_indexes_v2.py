"""使用 pymilvus 2.4.x IndexParams API 为所有集合创建索引"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import get_settings
from pymilvus import MilvusClient
from pymilvus.milvus_client.index import IndexParams

s = get_settings()
client = MilvusClient(uri=f"http://{s.MILVUS_HOST}:{s.MILVUS_PORT}", db_name=s.MILVUS_DATABASE)

ALL = {
    "teacher_documents": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("title","INVERTED",{},None), ("doc_category","INVERTED",{},None),
        ("material_type","INVERTED",{},None), ("sub_type","INVERTED",{},None),
        ("difficulty","INVERTED",{},None),
    ],
    "student_errors": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("student_name","INVERTED",{},None), ("knowledge_point","INVERTED",{},None),
        ("category","INVERTED",{},None), ("exam_name","INVERTED",{},None),
        ("related_word","INVERTED",{},None),
    ],
    "teacher_chat_history": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("session_id","INVERTED",{},None), ("role","INVERTED",{},None),
    ],
    "student_chat_history": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("session_id","INVERTED",{},None), ("role","INVERTED",{},None),
    ],
    "quiz_questions": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("type","INVERTED",{},None), ("category","INVERTED",{},None),
        ("knowledge_point","INVERTED",{},None),
    ],
    "word_semantics": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("word","INVERTED",{},None), ("part_of_speech","INVERTED",{},None),
    ],
    "reading_materials": [
        ("embedding","IVF_SQ8",{"nlist":1024},"IP"),
        ("sparse_embedding","SPARSE_INVERTED_INDEX",{},"IP"),
        ("title","INVERTED",{},None), ("material_type","INVERTED",{},None),
    ],
}

for cn, idxs in ALL.items():
    if not client.has_collection(cn):
        print(f"SKIP {cn}: no collection"); continue

    ip = IndexParams()
    new_count = 0
    for field, itype, params, metric in idxs:
        try:
            r = client.describe_index(cn, field)
            if r is not None:
                continue  # already exists
        except Exception:
            pass

        kwargs = {"field_name": field, "index_type": itype}
        if metric: kwargs["metric_type"] = metric
        if params: kwargs["params"] = params
        ip.add_index(**kwargs)
        new_count += 1

    if new_count > 0:
        try:
            client.create_index(collection_name=cn, index_params=ip)
            print(f"[{cn}] {new_count} indexes created")
        except Exception as e:
            print(f"[{cn}] FAIL: {e}")
    else:
        print(f"[{cn}] all indexes exist, skip")

# Load all collections
print("\nLoading collections...")
for cn in ALL:
    try:
        client.load_collection(cn)
        print(f"  [{cn}] load ok")
    except Exception as e:
        print(f"  [{cn}] load FAIL: {e}")

time.sleep(3)
print("\nLoad states:")
for cn in ALL:
    try: print(f"  [{cn}] {client.get_load_state(cn)}")
    except: print(f"  [{cn}] error")

# Test search
import numpy as np
dummy = np.zeros(1024, dtype=np.float32).tolist()
try:
    r = client.search("teacher_documents", [dummy], anns_field="embedding",
                      search_params={"metric_type":"IP","params":{"nprobe":10}},
                      limit=3, output_fields=["title","doc_category","user_id"])
    if r and r[0]:
        print(f"\nSEARCH: {len(r[0])} hits!")
        for h in r[0]:
            e = h.get('entity',{})
            print(f"  id={h['id']}, title={e.get('title','')[:50]}, cat={e.get('doc_category','?')}")
    else:
        print("\nSEARCH: 0 hits")
except Exception as e:
    print(f"\nSEARCH FAIL: {e}")

print("Done.")
