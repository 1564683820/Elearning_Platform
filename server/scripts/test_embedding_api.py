"""测试 SiliconFlow Embedding API + Milvus 真实语义检索"""
import sys, os, httpx, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 测试 embedding API
url = "https://api.siliconflow.cn/v1/embeddings"
headers = {
    "Authorization": "Bearer " + os.environ["EMBEDDING_API_KEY"],
    "Content-Type": "application/json",
}
payload = {
    "model": "BAAI/bge-large-zh-v1.5",
    "input": "翻译2022年高考英语试卷的第一篇阅读题的文章"
}

r = httpx.post(url, headers=headers, json=payload, timeout=30)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
if r.status_code == 200:
    data = r.json()
    emb = data["data"][0]["embedding"]
    print(f"\nEmbedding dim: {len(emb)}")
    print(f"First 5 values: {emb[:5]}")

    # 用这个 embedding 做 Milvus 搜索
    from pymilvus import MilvusClient
    from app.core.config import get_settings
    settings = get_settings()
    client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}", db_name=settings.MILVUS_DATABASE)
    
    results = client.search(
        collection_name="teacher_documents",
        data=[emb],
        anns_field="embedding",
        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
        limit=10,
        output_fields=["content", "doc_title", "source_id", "chunk_order", "user_id"],
        filter="(user_id == 0 or user_id == 14)",
    )
    if results and results[0]:
        print(f"\nMilvus 检索命中: {len(results[0])} 条")
        for i, h in enumerate(results[0]):
            e = h.get('entity', {})
            content = e.get('content', '')[:150]
            title = e.get('doc_title', '')[:40]
            uid = e.get('user_id')
            print(f"[{i}] dist={h['distance']:.4f}, uid={uid}, title={title}")
            print(f"    {content}")
    else:
        print("\n0 条结果!")
else:
    print(f"API 调用失败: {r.status_code} {r.text[:300]}")
