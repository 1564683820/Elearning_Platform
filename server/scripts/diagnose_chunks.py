"""诊断 v5 — 查看 chunk 内容完整性，写入文件避免编码问题"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
from pymilvus import MilvusClient
client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}", db_name=settings.MILVUS_DATABASE)

# 读取所有 user_id=14 的 chunk
all_chunks = client.query(
    collection_name="teacher_documents",
    filter="user_id == 14",
    limit=1000,
    output_fields=["content", "chunk_order", "doc_title", "source_id"],
)
all_chunks.sort(key=lambda x: x.get("chunk_order", 0))

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chunk_analysis.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(f"user_id=14 共 {len(all_chunks)} 条记录\n\n")
    
    # 前20个 chunk 的概览
    f.write("=== 前20个 chunk 概览 ===\n")
    for c in all_chunks[:20]:
        content = c.get("content", "")
        order = c.get("chunk_order", -1)
        f.write(f"[order={order:3d}] len={len(content):4d}\n")
        f.write(f"  {content[:120].replace(chr(10), ' ')}\n\n")
    
    # 所有含"阅读"的 chunk
    f.write("\n=== 含'阅读'的chunk ===\n\n")
    for c in all_chunks:
        content = c.get("content", "")
        if "阅读" in content:
            f.write(f"--- order={c.get('chunk_order')} ---\n")
            f.write(content[:800] + "\n\n")
    
    # A篇/B篇/C篇/D篇内容
    f.write("\n=== 含'A篇'/'B篇'/'C篇'/'D篇'的chunk ===\n\n")
    for c in all_chunks:
        content = c.get("content", "")
        for kw in ["A篇", "B篇", "C篇", "D篇", "阅读理解"]:
            if kw in content:
                f.write(f"--- order={c.get('chunk_order')} ({kw}) ---\n")
                f.write(content[:800] + "\n\n")
                break

print(f"分析结果已写入: {out_path}")
