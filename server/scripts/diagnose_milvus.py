"""Milvus 数据库诊断脚本"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
settings = get_settings()
print(f"[Config] MILVUS_DATABASE = {settings.MILVUS_DATABASE}")
print(f"[Config] MILVUS_HOST:PORT = {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
print(f"[Config] MYSQL_DATABASE = {settings.MYSQL_DATABASE}")

uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"

from pymilvus import MilvusClient

for db_name in ["elearningtest_v2", "elearningtest"]:
    print(f"\n{'='*60}")
    print(f"数据库: {db_name}")
    print(f"{'='*60}")
    try:
        client = MilvusClient(uri=uri, db_name=db_name)
        colls = client.list_collections()
        print(f"集合数: {len(colls)} -> {colls}")
        for c in colls:
            try:
                stat = client.get_collection_stats(c)
                rc = stat.get("row_count", "?")
                print(f"  [{c}] rows={rc}")
            except Exception as e:
                print(f"  [{c}] 获取统计失败: {e}")
    except Exception as e:
        print(f"连接失败: {e}")

print("\n=== 完成 ===")
