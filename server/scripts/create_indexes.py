"""简洁版：为所有集合创建索引"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import get_settings
from pymilvus import MilvusClient

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

ok = 0; skip = 0; fail = 0
for cn, idxs in ALL.items():
    if not client.has_collection(cn):
        print(f"SKIP {cn}: no collection"); continue
    for field, itype, params, metric in idxs:
        try:
            client.describe_index(cn, field)
            skip += 1
        except Exception:
            try:
                ip = {"field_name":field,"index_type":itype,"params":params}
                if metric: ip["metric_type"] = metric
                client.create_index(collection_name=cn, index_params=ip)
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {cn}.{field}: {e}")

print(f"\nIndex: created={ok}, already_exist={skip}, failed={fail}")

# Load all
print("Loading collections...")
for cn in ALL:
    try: client.load_collection(cn); print(f"  {cn}: load triggered")
    except Exception as e: print(f"  {cn}: load failed: {e}")

time.sleep(3)
print("\nLoad states:")
for cn in ALL:
    try: print(f"  {cn}: {client.get_load_state(cn)}")
    except: print(f"  {cn}: error")
print("Done.")
