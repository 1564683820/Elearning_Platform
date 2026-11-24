"""
向量数据库集合重建脚本
========================
用途: 在 Milvus 中创建所有 7 个优化后的集合（含完整 Schema、索引、Nullable、分词器、启用匹配）
运行: cd server && python -m scripts.rebuild_vector_collections
"""

import sys
import os
import logging

# 将 server 目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rebuild_vector")

from app.core.config import get_settings

settings = get_settings()

# ------ Milvus 连接配置 ------
MILVUS_URI = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
MILVUS_DB = settings.MILVUS_DATABASE
EMBEDDING_DIM = settings.EMBEDDING_DIM  # 1024

# ============================================================
#  7 个集合定义
# ============================================================

# --- 每个字段定义：dict 格式 ---
#   type: INT64 / VARCHAR / FLOAT_VECTOR / SPARSE_FLOAT_VECTOR
#   is_primary: 是否主键
#   auto_id: 是否自增
#   max_length: VARCHAR 最大长度
#   dim: 向量维度
#   nullable: 是否可空
#   enable_analyzer: 是否启用分词
#   enable_match: 是否启用 like/match 匹配
#   analyzer_params: 分词器配置（如 {"tokenizer": "chinese"}）

COLLECTION_DEFS = [
    # ==================== ① 学生错题库 ====================
    {
        "name": "student_errors",
        "description": "学生错题库 — 支持按学生、试卷、单词、题型检索",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 4096},
            {"name": "source_type", "type": "VARCHAR", "max_length": 64},
            {"name": "source_id", "type": "INT64"},
            {"name": "user_id", "type": "INT64"},
            {"name": "student_name", "type": "VARCHAR", "max_length": 64, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "knowledge_point", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "category", "type": "VARCHAR", "max_length": 64, "nullable": True, "enable_match": True},
            {"name": "question_type", "type": "INT64", "nullable": True},
            {"name": "exam_name", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "related_word", "type": "VARCHAR", "max_length": 128, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "related_word_id", "type": "INT64", "nullable": True},
            {"name": "difficulty", "type": "INT64", "nullable": True},
            {"name": "wrong_count", "type": "INT64", "nullable": True},
            {"name": "mastered", "type": "INT64", "nullable": True},
            {"name": "class_id", "type": "INT64", "nullable": True},
            {"name": "created_at", "type": "VARCHAR", "max_length": 32, "nullable": True},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 1024}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            # 为所有 enable_match=True 的 VARCHAR 字段创建 INVERTED 索引
            {"field": "student_name", "index_type": "INVERTED", "params": {}},
            {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
            {"field": "category", "index_type": "INVERTED", "params": {}},
            {"field": "exam_name", "index_type": "INVERTED", "params": {}},
            {"field": "related_word", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ② 教师文档库 ====================
    {
        "name": "teacher_documents",
        "description": "教师端上传文档库 — 试卷/教案/教材/PPT/习题/参考资料",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 8192},
            {"name": "source_type", "type": "VARCHAR", "max_length": 32},
            {"name": "source_id", "type": "INT64"},
            {"name": "user_id", "type": "INT64"},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "doc_category", "type": "VARCHAR", "max_length": 32, "nullable": True, "enable_match": True},
            {"name": "doc_title", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "doc_tags", "type": "VARCHAR", "max_length": 512, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "level", "type": "INT64"},
            {"name": "chunk_id", "type": "VARCHAR", "max_length": 128},
            {"name": "parent_chunk_id", "type": "VARCHAR", "max_length": 128, "nullable": True},
            {"name": "root_chunk_id", "type": "VARCHAR", "max_length": 128, "nullable": True},
            {"name": "chunk_order", "type": "INT64", "nullable": True},
            {"name": "subject", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "grade_level", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "class_id", "type": "INT64", "nullable": True},
            {"name": "created_at", "type": "VARCHAR", "max_length": 32, "nullable": True},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 2048}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "doc_category", "index_type": "INVERTED", "params": {}},
            {"field": "doc_title", "index_type": "INVERTED", "params": {}},
            {"field": "doc_tags", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ③ 教学助手对话历史 ====================
    {
        "name": "teacher_chat_history",
        "description": "教学助手对话历史 — 长期记忆和上下文检索",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 4096},
            {"name": "conversation_id", "type": "INT64"},
            {"name": "message_id", "type": "INT64", "nullable": True},
            {"name": "user_id", "type": "INT64"},
            {"name": "role", "type": "VARCHAR", "max_length": 16, "enable_match": True},
            {"name": "message_type", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "intent", "type": "VARCHAR", "max_length": 64, "nullable": True, "enable_match": True},
            {"name": "sources", "type": "VARCHAR", "max_length": 2048, "nullable": True},
            {"name": "summary", "type": "VARCHAR", "max_length": 1024, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "class_id", "type": "INT64", "nullable": True},
            {"name": "created_at", "type": "VARCHAR", "max_length": 32},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 512}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "role", "index_type": "INVERTED", "params": {}},
            {"field": "intent", "index_type": "INVERTED", "params": {}},
            {"field": "summary", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ④ 小e学生对话历史 ====================
    {
        "name": "student_chat_history",
        "description": "小e学生对话历史 — 学习轨迹追踪",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 4096},
            {"name": "conversation_id", "type": "INT64"},
            {"name": "message_id", "type": "INT64", "nullable": True},
            {"name": "user_id", "type": "INT64"},
            {"name": "role", "type": "VARCHAR", "max_length": 16, "enable_match": True},
            {"name": "conversation_type", "type": "INT64", "nullable": True},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "evaluation", "type": "VARCHAR", "max_length": 1024, "nullable": True},
            {"name": "created_at", "type": "VARCHAR", "max_length": 32},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 1024}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "role", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ⑤ 题库向量 ====================
    {
        "name": "quiz_questions",
        "description": "题库向量 — 语义相似题检索、智能出卷",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 4096,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "question_id", "type": "INT64"},
            {"name": "question_type", "type": "INT64", "enable_match": True},
            {"name": "difficulty", "type": "INT64", "enable_match": True},
            {"name": "knowledge_point", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "source", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "user_id", "type": "INT64"},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 1024}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "content", "index_type": "INVERTED", "params": {}},
            {"field": "question_type", "index_type": "INVERTED", "params": {}},
            {"field": "difficulty", "index_type": "INVERTED", "params": {}},
            {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
            {"field": "source", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ⑥ 单词语义向量 ====================
    {
        "name": "word_semantics",
        "description": "单词语义向量 — 近义词推荐、词根关联",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 2048,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "word_id", "type": "INT64"},
            {"name": "word_text", "type": "VARCHAR", "max_length": 128,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "english"}},
            {"name": "translation", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "tag", "type": "VARCHAR", "max_length": 32, "nullable": True, "enable_match": True},
            {"name": "pos", "type": "VARCHAR", "max_length": 16, "nullable": True},
            {"name": "collins", "type": "INT64", "nullable": True},
            {"name": "root_info", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 512}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "content", "index_type": "INVERTED", "params": {}},
            {"field": "word_text", "index_type": "INVERTED", "params": {}},
            {"field": "translation", "index_type": "INVERTED", "params": {}},
            {"field": "tag", "index_type": "INVERTED", "params": {}},
            {"field": "root_info", "index_type": "INVERTED", "params": {}},
        ],
    },
    # ==================== ⑦ 阅读/听力材料向量 ====================
    {
        "name": "reading_materials",
        "description": "阅读/听力材料向量 — 按主题/难度/字数精准推荐",
        "fields": [
            {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
            {"name": "embedding", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
            {"name": "sparse_embedding", "type": "SPARSE_FLOAT_VECTOR"},
            {"name": "content", "type": "VARCHAR", "max_length": 8192,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "content_cn", "type": "VARCHAR", "max_length": 8192, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "material_id", "type": "INT64"},
            {"name": "material_type", "type": "VARCHAR", "max_length": 32, "enable_match": True},
            {"name": "title", "type": "VARCHAR", "max_length": 256, "nullable": True,
             "enable_analyzer": True, "enable_match": True, "analyzer_params": {"tokenizer": "chinese"}},
            {"name": "sub_type", "type": "VARCHAR", "max_length": 32, "nullable": True, "enable_match": True},
            {"name": "difficulty", "type": "INT64", "nullable": True, "enable_match": True},
            {"name": "word_count", "type": "INT64", "nullable": True},
            {"name": "stage", "type": "VARCHAR", "max_length": 32, "nullable": True},
            {"name": "user_id", "type": "INT64"},
        ],
        "indexes": [
            {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP",
             "params": {"nlist": 512}},
            {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP",
             "params": {}},
            {"field": "content", "index_type": "INVERTED", "params": {}},
            {"field": "content_cn", "index_type": "INVERTED", "params": {}},
            {"field": "material_type", "index_type": "INVERTED", "params": {}},
            {"field": "title", "index_type": "INVERTED", "params": {}},
            {"field": "sub_type", "index_type": "INVERTED", "params": {}},
            {"field": "difficulty", "index_type": "INVERTED", "params": {}},
        ],
    },
]


# ============================================================
#  Build 逻辑
# ============================================================

def build_field_schema(fdef: dict):
    """根据字段定义 dict 构建 FieldSchema"""
    from pymilvus import FieldSchema, DataType

    DTYPE_MAP = {
        "INT64": DataType.INT64,
        "VARCHAR": DataType.VARCHAR,
        "FLOAT_VECTOR": DataType.FLOAT_VECTOR,
        "SPARSE_FLOAT_VECTOR": DataType.SPARSE_FLOAT_VECTOR,
    }

    dtype = DTYPE_MAP.get(fdef["type"], DataType.INT64)
    is_primary = fdef.get("is_primary", False)
    auto_id = fdef.get("auto_id", False)
    nullable = fdef.get("nullable", False)
    max_length = fdef.get("max_length")
    dim = fdef.get("dim")

    # 构建 params（分词器、match）
    params = {}
    if fdef.get("enable_analyzer"):
        params["enable_analyzer"] = True
    if fdef.get("enable_match"):
        params["enable_match"] = True
    analyzer_params = fdef.get("analyzer_params")
    if analyzer_params:
        params["analyzer_params"] = analyzer_params

    kwargs = dict(
        name=fdef["name"],
        dtype=dtype,
        is_primary=is_primary,
        auto_id=auto_id,
        nullable=nullable,
    )
    if max_length:
        kwargs["max_length"] = max_length
    if dim:
        kwargs["dim"] = dim
    if params:
        kwargs["params"] = params

    return FieldSchema(**kwargs)


def ensure_database(db_name: str, dry_run: bool = False):
    """确保目标数据库存在（不存在则创建）"""
    if dry_run:
        logger.info(f"\n🔄 将创建数据库「{db_name}」(如不存在)")
        return

    from pymilvus import connections, db

    # 先连接到默认数据库进行管理操作
    connections.connect(
        alias="__admin__",
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )
    try:
        databases = db.list_database(using="__admin__")
        if db_name not in databases:
            db.create_database(db_name, using="__admin__")
            logger.info(f"   ✅ 数据库「{db_name}」创建成功")
        else:
            logger.info(f"   ✅ 数据库「{db_name}」已存在")
    finally:
        connections.disconnect("__admin__")


def create_collections(dry_run: bool = False, db_name: str = None):
    """
    创建所有 7 个集合（在新数据库中，如果已存在则跳过）
    dry_run=True: 只打印计划，不实际执行
    db_name: 目标数据库名（默认使用 MILVUS_DB）
    """
    from pymilvus import CollectionSchema, MilvusClient

    target_db = db_name or MILVUS_DB

    logger.info("=" * 60)
    logger.info(f"Milvus URI:   {MILVUS_URI}")
    logger.info(f"目标数据库:   {target_db}")
    logger.info(f"Embedding Dim: {EMBEDDING_DIM}")
    logger.info(f"Dry Run:       {dry_run}")
    logger.info(f"旧数据库备份:  elearningtest (保留原 knowledge_vectors + 旧版 student_errors)")
    logger.info("=" * 60)

    # --- 确保数据库存在 ---
    ensure_database(target_db, dry_run)

    if dry_run:
        logger.info("\n🔄 Dry-Run 模式 — 仅打印计划，不执行任何操作\n")

    # --- 连接到目标数据库 ---
    if not dry_run:
        client = MilvusClient(uri=MILVUS_URI, db_name=target_db)

    for coll_def in COLLECTION_DEFS:
        coll_name = coll_def["name"]
        desc = coll_def["description"]
        fields_def = coll_def["fields"]
        indexes_def = coll_def["indexes"]

        logger.info(f"\n{'='*60}")
        logger.info(f"📦 集合: {coll_name}")
        logger.info(f"   描述: {desc}")

        if dry_run:
            logger.info(f"   字段 ({len(fields_def)} 个):")
            for fdef in fields_def:
                nullable_str = ", nullable=True" if fdef.get("nullable") else ""
                analyzer_str = ""
                if fdef.get("enable_analyzer"):
                    tok = fdef.get("analyzer_params", {}).get("tokenizer", "?")
                    analyzer_str = f", 分词器={tok}"
                match_str = ", 启用匹配" if fdef.get("enable_match") else ""
                logger.info(f"     - {fdef['name']}: {fdef['type']}{nullable_str}{analyzer_str}{match_str}")
            logger.info(f"   索引 ({len(indexes_def)} 个):")
            for idx in indexes_def:
                logger.info(f"     - {idx['field']}: {idx['index_type']} ({idx.get('metric_type','')})")
            continue

        # --- 检查是否存在 ---
        if client.has_collection(coll_name):
            logger.info(f"    ⚠️ 集合已存在，跳过创建")
            continue

        # --- 创建 Schema ---
        fields = [build_field_schema(fdef) for fdef in fields_def]
        schema = CollectionSchema(fields, description=desc)
        client.create_collection(collection_name=coll_name, schema=schema)
        logger.info(f"    ✅ 集合创建成功")

        # --- 创建索引 ---
        from pymilvus.milvus_client.index import IndexParams
        index_params = IndexParams()
        for idx_def in indexes_def:
            kwargs = {
                "field_name": idx_def["field"],
                "index_type": idx_def["index_type"],
            }
            if "metric_type" in idx_def:
                kwargs["metric_type"] = idx_def["metric_type"]
            if "params" in idx_def and idx_def["params"]:
                kwargs["params"] = idx_def["params"]
            index_params.add_index(**kwargs)

        client.create_index(collection_name=coll_name, index_params=index_params)
        logger.info(f"    ✅ 索引批量创建: {len(indexes_def)} 个")

        # --- 加载集合 ---
        try:
            client.load_collection(coll_name)
            logger.info(f"    ✅ 集合已加载到内存")
        except Exception as e:
            logger.warning(f"    ⚠️ 加载失败（可能自动加载）: {e}")

    if not dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("📊 最终集合列表:")
        for coll_def in COLLECTION_DEFS:
            exists = client.has_collection(coll_def["name"])
            status = "✅" if exists else "❌"
            logger.info(f"   {status} {coll_def['name']}: {coll_def['description']}")
        logger.info("=" * 60)
        logger.info("🎉 完成！")
        logger.info("   旧数据库「elearningtest」保留原 knowledge_vectors + 旧版 student_errors 作为备份")
        logger.info("   新数据库「elearningtest_v2」已创建以上 7 个集合")
        logger.info("   请确认 .env 中 MILVUS_DATABASE=elearningtest_v2 后重启服务")


def drop_collections(dry_run: bool = False, db_name: str = None):
    """删除当前数据库中所有 7 个集合"""
    from pymilvus import MilvusClient

    target_db = db_name or MILVUS_DB

    if dry_run:
        logger.info(f"\n🔍 Dry-Run 模式 — 以下集合将从「{target_db}」删除:")
        for coll_def in COLLECTION_DEFS:
            logger.info(f"   - {coll_def['name']}: {coll_def['description']}")
        return

    confirm = input(f"\n⚠️  确定要从「{target_db}」删除所有 7 个集合？输入 'rebuild_confirm' 确认: ").strip()
    if confirm != "rebuild_confirm":
        logger.info("取消操作")
        return

    client = MilvusClient(uri=MILVUS_URI, db_name=target_db)
    for coll_def in COLLECTION_DEFS:
        coll_name = coll_def["name"]
        if client.has_collection(coll_name):
            client.drop_collection(coll_name)
            logger.info(f"🗑️  已删除: {coll_name}")
        else:
            logger.info(f"  跳过（不存在）: {coll_name}")


def list_collections(db_name: str = None):
    """列出指定数据库中所有集合"""
    from pymilvus import MilvusClient

    target_db = db_name or MILVUS_DB
    client = MilvusClient(uri=MILVUS_URI, db_name=target_db)
    all_colls = client.list_collections()
    logger.info(f"\n📋 数据库「{target_db}」集合 ({len(all_colls)} 个):")
    for name in sorted(all_colls):
        desc = client.describe_collection(name)
        field_count = len(desc.get("fields", []))
        logger.info(f"   - {name} ({field_count} 字段)")
    return all_colls


# ============================================================
#  Main
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="重建 E-Learning 向量数据库集合")
    parser.add_argument("action", nargs="?", default="create", choices=["create", "drop", "list"],
                        help="create=创建集合, drop=删除集合, list=列出集合")
    parser.add_argument("--database", default=None,
                        help="目标数据库名（默认使用 .env 中的配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划不执行")
    args = parser.parse_args()

    db = args.database or None  # None 表示使用 MILVUS_DB
    if args.action == "create":
        create_collections(dry_run=args.dry_run, db_name=db)
    elif args.action == "drop":
        drop_collections(dry_run=args.dry_run, db_name=db)
    elif args.action == "list":
        list_collections(db_name=db)
