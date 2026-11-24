"""
E-Learning 向量检索服务
=======================
基于 Milvus 的 Embedding + 混合检索（稠密+稀疏），支持 7 个集合：
  student_errors      — 学生错题库
  teacher_documents   — 教师文档库（代替旧 knowledge_vectors）
  teacher_chat_history — 教学助手对话历史
  student_chat_history — 小e学生对话历史
  quiz_questions      — 题库向量
  word_semantics      — 单词语义向量
  reading_materials   — 阅读材料向量
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ai_service import AIService
from app.services.bm25_index import get_bm25_index
from app.core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding + 向量检索服务（Milvus）- 支持 7 集合 + 混合检索"""

    _milvus_client = None
    _schema_verified = {}  # {collection_name: bool}

    # ==================== 集合名常量 ====================
    # 旧集合（过渡期仍使用，数据迁移完成后可删除）
    KNOWLEDGE_COLLECTION = "knowledge_vectors"
    STUDENT_ERROR_COLLECTION = "student_errors"

    # 新集合（正式使用）
    TEACHER_DOCUMENTS = "teacher_documents"            # 替代 knowledge_vectors
    STUDENT_ERRORS = "student_errors"                  # 升级版
    TEACHER_CHAT_HISTORY = "teacher_chat_history"      # 新增 — 教学助手对话
    STUDENT_CHAT_HISTORY = "student_chat_history"      # 新增 — 小e学生对话
    QUIZ_QUESTIONS = "quiz_questions"                  # 新增 — 题库向量
    WORD_SEMANTICS = "word_semantics"                  # 新增 — 单词语义
    READING_MATERIALS = "reading_materials"            # 新增 — 阅读材料

    # 所有正式集合列表
    ALL_COLLECTIONS = [
        STUDENT_ERRORS, TEACHER_DOCUMENTS,
        TEACHER_CHAT_HISTORY, STUDENT_CHAT_HISTORY,
        QUIZ_QUESTIONS, WORD_SEMANTICS, READING_MATERIALS,
    ]

    # ==================== 7 集合 Schema 定义（dict 格式） ====================
    # 字段属性:
    #   type, is_primary, auto_id, max_length, dim,
    #   nullable, enable_analyzer, enable_match, analyzer_params

    @staticmethod
    def _build_collection_defs():
        """返回所有集合的字段和索引定义"""
        DIM = settings.EMBEDDING_DIM  # 1024

        return {

            # ---------- ① 学生错题库 ----------
            EmbeddingService.STUDENT_ERRORS: {
                "description": "学生错题库 — 支持按学生、试卷、单词、题型检索",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "student_name", "index_type": "INVERTED", "params": {}},
                    {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
                    {"field": "category", "index_type": "INVERTED", "params": {}},
                    {"field": "exam_name", "index_type": "INVERTED", "params": {}},
                    {"field": "related_word", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ② 教师文档库（替代 knowledge_vectors） ----------
            EmbeddingService.TEACHER_DOCUMENTS: {
                "description": "教师端上传文档库 — 试卷/教案/教材/PPT/习题/参考资料",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"name": "section_title", "type": "VARCHAR", "max_length": 512, "nullable": True,
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 2048}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "doc_category", "index_type": "INVERTED", "params": {}},
                    {"field": "doc_title", "index_type": "INVERTED", "params": {}},
                    {"field": "doc_tags", "index_type": "INVERTED", "params": {}},
                    {"field": "section_title", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ③ 教学助手对话历史 ----------
            EmbeddingService.TEACHER_CHAT_HISTORY: {
                "description": "教学助手对话历史 — 长期记忆和上下文检索",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 512}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "role", "index_type": "INVERTED", "params": {}},
                    {"field": "intent", "index_type": "INVERTED", "params": {}},
                    {"field": "summary", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ④ 小e学生对话历史 ----------
            EmbeddingService.STUDENT_CHAT_HISTORY: {
                "description": "小e学生对话历史 — 学习轨迹追踪",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "role", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ⑤ 题库向量 ----------
            EmbeddingService.QUIZ_QUESTIONS: {
                "description": "题库向量 — 语义相似题检索、智能出卷",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 1024}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "content", "index_type": "INVERTED", "params": {}},
                    {"field": "question_type", "index_type": "INVERTED", "params": {}},
                    {"field": "difficulty", "index_type": "INVERTED", "params": {}},
                    {"field": "knowledge_point", "index_type": "INVERTED", "params": {}},
                    {"field": "source", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ⑥ 单词语义向量 ----------
            EmbeddingService.WORD_SEMANTICS: {
                "description": "单词语义向量 — 近义词推荐、词根关联",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 512}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "content", "index_type": "INVERTED", "params": {}},
                    {"field": "word_text", "index_type": "INVERTED", "params": {}},
                    {"field": "translation", "index_type": "INVERTED", "params": {}},
                    {"field": "tag", "index_type": "INVERTED", "params": {}},
                    {"field": "root_info", "index_type": "INVERTED", "params": {}},
                ],
            },

            # ---------- ⑦ 阅读材料向量 ----------
            EmbeddingService.READING_MATERIALS: {
                "description": "阅读/听力材料向量 — 按主题/难度/字数推荐",
                "fields": [
                    {"name": "id", "type": "INT64", "is_primary": True, "auto_id": True},
                    {"name": "embedding", "type": "FLOAT_VECTOR", "dim": DIM},
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
                    {"field": "embedding", "index_type": "IVF_SQ8", "metric_type": "IP", "params": {"nlist": 512}},
                    {"field": "sparse_embedding", "index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
                    {"field": "content", "index_type": "INVERTED", "params": {}},
                    {"field": "content_cn", "index_type": "INVERTED", "params": {}},
                    {"field": "material_type", "index_type": "INVERTED", "params": {}},
                    {"field": "title", "index_type": "INVERTED", "params": {}},
                    {"field": "sub_type", "index_type": "INVERTED", "params": {}},
                    {"field": "difficulty", "index_type": "INVERTED", "params": {}},
                ],
            },
        }

    @staticmethod
    def get_milvus_client():
        """获取 Milvus 客户端（懒加载，REST 模式）
        
        连接超时 10 秒，防止 Milvus 不可达时无限阻塞。
        """
        if EmbeddingService._milvus_client is None:
            try:
                from pymilvus import MilvusClient
                client = MilvusClient(
                    uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}",
                    db_name=settings.MILVUS_DATABASE,
                    timeout=10,  # HTTP 请求超时（秒），防止 TCP 阻塞
                )
                EmbeddingService._milvus_client = client
                # 初始化 schema
                EmbeddingService._ensure_collections(client)
            except ImportError:
                raise ValueError("pymilvus 未安装，请运行 pip install pymilvus")
            except Exception as e:
                raise ValueError(f"Milvus 连接失败: {e}")
        return EmbeddingService._milvus_client

    # ==================== Schema 管理 ====================

    @staticmethod
    def _get_collection_defs():
        """懒加载集合定义"""
        if not hasattr(EmbeddingService, "_coll_defs_cache"):
            EmbeddingService._coll_defs_cache = EmbeddingService._build_collection_defs()
        return EmbeddingService._coll_defs_cache

    @staticmethod
    def _get_fields_def(collection_name: str) -> list:
        """获取指定集合的字段定义列表"""
        defs = EmbeddingService._get_collection_defs()
        if collection_name not in defs and collection_name in ("knowledge_vectors",):
            # 旧集合名映射到新集合
            return EmbeddingService._get_fields_def(EmbeddingService.TEACHER_DOCUMENTS)
        return defs.get(collection_name, {}).get("fields", [])

    @staticmethod
    def _get_output_fields(collection_name: str) -> list:
        """获取指定集合的非向量字段名列表（用于 search output_fields）"""
        fields = EmbeddingService._get_fields_def(collection_name)
        skip = {"id", "embedding", "sparse_embedding"}
        return [f["name"] for f in fields if f["name"] not in skip]

    @staticmethod
    def _ensure_collections(client):
        """确保所有新集合存在（自动创建缺失的集合，全量字段比对）+ 全部加载到内存"""
        logger.info("Milvus _ensure_collections: 开始检查 7 个集合...")
        defs = EmbeddingService._get_collection_defs()
        for coll_name in EmbeddingService.ALL_COLLECTIONS:
            if not client.has_collection(coll_name):
                EmbeddingService._create_collection(client, coll_name)
            else:
                # 全量字段比对：检查 schema 中所有必需字段都在现有集合中
                desc = client.describe_collection(coll_name)
                existing_fields = {f["name"]: f for f in desc.get("fields", [])}
                expected_fields = EmbeddingService._get_fields_def(coll_name)
                expected_names = {f["name"] for f in expected_fields}
                missing = expected_names - existing_fields.keys()
                if missing:
                    logger.warning(
                        f"集合 {coll_name} schema 过旧，缺少字段 {missing}，重建中"
                    )
                    client.drop_collection(coll_name)
                    EmbeddingService._create_collection(client, coll_name)
                elif "sparse_embedding" not in existing_fields:
                    logger.warning(f"集合 {coll_name} 缺少 sparse_embedding，重建以支持混合检索")
                    client.drop_collection(coll_name)
                    EmbeddingService._create_collection(client, coll_name)
                else:
                    # 集合 schema 正常，检查并补建缺失的索引
                    EmbeddingService._ensure_indexes(client, coll_name)

        # 确保所有集合都已加载到内存（无论新建还是已存在）
        for coll_name in EmbeddingService.ALL_COLLECTIONS:
            try:
                load_state = client.get_load_state(coll_name)
                logger.info(f"  {coll_name}: 加载状态={load_state}")
                if str(load_state) != "LoadState.Loaded":
                    client.load_collection(coll_name)
                    logger.info(f"  {coll_name}: 已触发加载")
                else:
                    logger.info(f"  {coll_name}: 已加载，跳过")
            except Exception as e:
                logger.warning(f"  {coll_name}: 加载检查失败 {e}，尝试强制加载")
                try:
                    client.load_collection(coll_name)
                    logger.info(f"  {coll_name}: 强制加载完成")
                except Exception as e2:
                    logger.warning(f"  {coll_name}: 强制加载也失败 {e2}")

    @staticmethod
    def _create_collection(client, coll_name: str):
        """创建集合（含 nullable / enable_analyzer / enable_match）"""
        from pymilvus import CollectionSchema, FieldSchema, DataType

        DTYPE_MAP = {
            "INT64": DataType.INT64,
            "VARCHAR": DataType.VARCHAR,
            "FLOAT_VECTOR": DataType.FLOAT_VECTOR,
            "SPARSE_FLOAT_VECTOR": DataType.SPARSE_FLOAT_VECTOR,
        }

        fields_def = EmbeddingService._get_fields_def(coll_name)
        if not fields_def:
            raise ValueError(f"未找到集合 {coll_name} 的字段定义")

        # 获取集合描述（从 collection def 顶层获取）
        coll_defs = EmbeddingService._get_collection_defs()
        description = coll_defs.get(coll_name, {}).get("description", coll_name)

        fields = []
        for fdef in fields_def:
            dtype = DTYPE_MAP.get(fdef["type"], DataType.INT64)
            is_primary = fdef.get("is_primary", False)
            auto_id = fdef.get("auto_id", False)
            nullable = fdef.get("nullable", False)
            max_length = fdef.get("max_length")
            dim = fdef.get("dim")

            # 分词器 + match 参数
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
            if dtype == DataType.FLOAT_VECTOR and dim:
                kwargs["dim"] = dim
            if params:
                kwargs["params"] = params

            fields.append(FieldSchema(**kwargs))

        schema = CollectionSchema(fields, description=description, enable_dynamic_field=True)
        client.create_collection(collection_name=coll_name, schema=schema)
        logger.info(f"Milvus 集合 {coll_name} 创建完成")
        # 创建向量和标量索引
        EmbeddingService._ensure_indexes(client, coll_name)

    @staticmethod
    def _ensure_indexes(client, coll_name: str):
        """确保集合的所有索引存在（缺失则创建）"""
        from pymilvus.milvus_client.index import IndexParams

        coll_defs = EmbeddingService._get_collection_defs()
        indexes_def = coll_defs.get(coll_name, {}).get("indexes", [])
        if not indexes_def:
            logger.info(f"集合 {coll_name} 无索引定义，跳过")
            return

        # pymilvus 2.4.x: 使用 IndexParams + add_index()，一次调用创建所有索引
        index_params = IndexParams()
        has_missing_indexes = False
        for idx_def in indexes_def:
            field_name = idx_def["field"]
            # 检查索引是否已存在
            try:
                result = client.describe_index(coll_name, field_name)
                if result is not None:
                    continue  # 索引已存在
            except Exception:
                pass  # 不存在，继续

            kwargs = {
                "field_name": field_name,
                "index_type": idx_def["index_type"],
            }
            if "metric_type" in idx_def:
                kwargs["metric_type"] = idx_def["metric_type"]
            if "params" in idx_def and idx_def["params"]:
                kwargs["params"] = idx_def["params"]

            index_params.add_index(**kwargs)
            has_missing_indexes = True
            logger.info(f"  索引待创建: {coll_name}.{field_name} ({idx_def['index_type']})")

        # 一次性创建所有缺失的索引
        if has_missing_indexes:
            try:
                client.create_index(
                    collection_name=coll_name,
                    index_params=index_params,
                )
                logger.info(f"  索引批量创建完成: {coll_name}")
            except Exception as e:
                logger.warning(f"  索引批量创建失败 {coll_name}: {e}")
        else:
            logger.info(f"  索引已全部存在: {coll_name}")

        # 索引创建/变更后，必须加载集合到内存才能检索
        try:
            client.load_collection(coll_name)
            logger.info(f"  集合加载完成: {coll_name}")
        except Exception as e:
            logger.warning(f"  集合加载失败 {coll_name}: {e}")

    # ---- 索引写入 ----

    # ==================== 通用插入 ====================

    @staticmethod
    def _build_record(
        content: str,
        dense_embedding: list,
        extra_fields: dict = None,
        collection_name: str = None,
    ) -> dict:
        """构造 Milvus 插入记录（自动补全所有 schema 字段）

        - 自动加 embedding + sparse_embedding + content + extra
        - 空稀疏向量用 {0: 0.0} 代替，避免 Milvus 拒绝
        - 自动补全集 schema 中缺失的可空字段（防止 field don't match）
        """
        sparse_vec = get_bm25_index().compute_sparse_vector(content)
        # 防御：空稀疏向量会导致 Milvus "invalid input for sparse float vector"
        if not sparse_vec:
            sparse_vec = {0: 0.0}

        record = {
            "embedding": dense_embedding,
            "sparse_embedding": sparse_vec,
            "content": content[:8000],
        }
        if extra_fields:
            record.update(extra_fields)

        # 自动补全 schema 中缺失的可空字段，避免 Milvus 字段不匹配错误
        if collection_name:
            fields_def = EmbeddingService._get_fields_def(collection_name)
            for fdef in fields_def:
                fname = fdef["name"]
                if fname in record:
                    continue
                if not fdef.get("nullable", False):
                    continue
                # 跳过 auto_id 主键
                if fdef.get("is_primary") and fdef.get("auto_id"):
                    continue
                # 根据类型填入默认值
                dtype = fdef["type"]
                if dtype == "INT64":
                    record[fname] = 0
                elif dtype == "VARCHAR":
                    record[fname] = ""
                elif dtype == "FLOAT_VECTOR":
                    record[fname] = dense_embedding
                elif dtype == "SPARSE_FLOAT_VECTOR":
                    record[fname] = sparse_vec

        return record

    @staticmethod
    def _insert_record(
        collection_name: str,
        content: str,
        dense_embedding: list,
        **extra_fields,
    ) -> bool:
        """插入单条记录到 Milvus（extra_fields 自动合并到记录）"""
        try:
            client = EmbeddingService.get_milvus_client()
            record = EmbeddingService._build_record(
                content, dense_embedding, extra_fields, collection_name=collection_name,
            )
            client.insert(collection_name=collection_name, data=[record])
            return True
        except Exception as e:
            logger.error(f"_insert_record 失败 ({collection_name}): {e}")
            return False

    @staticmethod
    async def index_chunk(
        db: AsyncSession,
        collection_name: str,
        content: str,
        source_type: str,
        source_id: int,
        user_id: int = 0,
        stage: str = "",
        level: int = 3,
        chunk_id: str = "",
        parent_chunk_id: str = "",
        root_chunk_id: str = "",
        chunk_order: int = 0,
        **extra_fields,
    ) -> bool:
        """将单条记录向量化后写入 Milvus

        通用方法，支持任意集合。extra_fields 传入该集合所需的额外字段。
        例如 teacher_documents 需要 doc_category, doc_title, doc_tags 等。
        """
        try:
            dense_embedding = await AIService.get_embedding(db, content, user_id if user_id else None)
            fields = {
                "source_type": source_type,
                "source_id": source_id,
                "user_id": user_id,
                "stage": stage,
                "level": level,
                "chunk_id": chunk_id,
                "parent_chunk_id": parent_chunk_id,
                "root_chunk_id": root_chunk_id,
                "chunk_order": chunk_order,
            }
            fields.update(extra_fields)
            return EmbeddingService._insert_record(collection_name, content, dense_embedding, **fields)
        except Exception as e:
            logger.error(f"index_chunk 失败 ({collection_name}): {e}")
            return False

    @staticmethod
    async def index_chunks_batch(
        db: AsyncSession,
        collection_name: str,
        chunks: list[dict],
        user_id: int = 0,
        stage: str = "",
    ) -> int:
        """批量向量化并写入 Milvus

        Args:
            chunks: 每项至少含 content，其余字段自动识别并写入
                    如 teacher_documents: source_type, source_id, level, chunk_id, doc_category, doc_title...
                    如 student_errors: source_type, source_id, student_name, category, exam_name...
        Returns:
            成功写入数量
        """
        if not chunks:
            return 0
        try:
            texts = [c["content"] for c in chunks]
            dense_embeddings = await AIService.get_embeddings_batch(db, texts, user_id if user_id else None)

            records = []
            for i, c in enumerate(chunks):
                extra = {k: v for k, v in c.items() if k != "content"}
                extra.setdefault("user_id", user_id)
                extra.setdefault("stage", stage)
                records.append(EmbeddingService._build_record(
                    c["content"], dense_embeddings[i], extra, collection_name=collection_name,
                ))

            client = EmbeddingService.get_milvus_client()
            client.insert(collection_name=collection_name, data=records)
            # 必须 flush，否则插入的数据对检索不可见
            try:
                client.flush(collection_name=collection_name)
                logger.info(f"index_chunks_batch flush 完成 ({collection_name}): {len(records)} 条")
            except Exception as flush_err:
                logger.warning(f"index_chunks_batch flush 失败 ({collection_name}): {flush_err}")
            return len(records)
        except Exception as e:
            logger.error(f"index_chunks_batch 失败 ({collection_name}): {e}")
            return 0

    @staticmethod
    async def index_text(
        db: AsyncSession,
        collection_name: str,
        text: str,
        source_type: str,
        source_id: int,
        user_id: int = 0,
        stage: str = "",
    ) -> bool:
        """兼容旧接口"""
        return await EmbeddingService.index_chunk(
            db, collection_name, text, source_type, source_id,
            user_id=user_id, stage=stage,
        )

    # ==================== 检索 ====================

    @staticmethod
    def _build_filter(
        user_id: int = 0,
        stage: str = "",
        source_type: str = "",
        extra_filters: list = None,
        class_id: int = 0,
    ) -> str:
        """构建 Milvus 标量过滤表达式"""
        parts = []
        if user_id:
            parts.append(f'(user_id == 0 or user_id == {user_id})')
        if stage:
            parts.append(f'(stage == "" or stage == "{stage}")')
        if source_type:
            parts.append(f'(source_type like "{source_type}" or source_type == "{source_type}")')
        if class_id:
            parts.append(f'(class_id == 0 or class_id == {class_id})')
        if extra_filters:
            parts.extend(extra_filters)
        return " and ".join(parts) if parts else ""

    @staticmethod
    def _parse_hit(hit: dict, output_fields: list) -> dict:
        """将 Milvus 单条 hit 解析为统一 dict"""
        entity = hit.get("entity", {})
        result = {"content": entity.get("content", ""), "score": hit.get("distance", 0)}
        for field in output_fields:
            if field != "content" and field in entity:
                result[field] = entity[field]
        return result

    @staticmethod
    async def hybrid_search(
        db: AsyncSession,
        query: str,
        collection_name: str = KNOWLEDGE_COLLECTION,
        top_k: int = 5,
        user_id: int = 0,
        stage: str = "",
        source_type: str = "",
        extra_filter: str = "",
        output_fields: list = None,
        class_id: int = 0,
    ) -> list[dict]:
        """稠密 + 稀疏混合检索（RRF 合并）

        Args:
            extra_filter: 额外过滤表达式，如 'doc_category == "exam"'
            output_fields: 返回字段列表（None=自动从 schema 推断）
        """
        try:
            dense_embedding = await AIService.get_embedding(db, query, user_id if user_id else None)
            sparse_vec = get_bm25_index().compute_sparse_vector(query)

            client = EmbeddingService.get_milvus_client()
            if not client.has_collection(collection_name):
                return []

            # 自动推断 output_fields
            if output_fields is None:
                output_fields = EmbeddingService._get_output_fields(collection_name)

            # 过滤条件
            extra = []
            if extra_filter:
                extra.append(f"({extra_filter})")
            if collection_name == EmbeddingService.TEACHER_DOCUMENTS and source_type != "exam_question":
                extra.append('source_type != "exam_question"')
            filter_expr = EmbeddingService._build_filter(user_id, stage, source_type, extra, class_id)

            try:
                # 稠密搜索
                dense_res = client.search(
                    collection_name=collection_name,
                    data=[dense_embedding],
                    anns_field="embedding",
                    search_params={"metric_type": "IP", "params": {"nprobe": 10}},
                    limit=top_k * 2,
                    output_fields=output_fields,
                    filter=filter_expr if filter_expr else None,
                )
                # 稀疏搜索
                sparse_res = client.search(
                    collection_name=collection_name,
                    data=[sparse_vec],
                    anns_field="sparse_embedding",
                    search_params={"metric_type": "IP"},
                    limit=top_k * 2,
                    output_fields=output_fields,
                    filter=filter_expr if filter_expr else None,
                )

                # RRF 合并
                dense_hits = dense_res[0] if dense_res else []
                sparse_hits = sparse_res[0] if sparse_res else []
                rrf_score = {}
                hit_map = {}
                rrf_k = 60
                for rank, hit in enumerate(dense_hits):
                    hid = hit["id"]
                    rrf_score[hid] = rrf_score.get(hid, 0) + 1.0 / (rrf_k + rank)
                    hit_map[hid] = hit
                for rank, hit in enumerate(sparse_hits):
                    hid = hit["id"]
                    rrf_score[hid] = rrf_score.get(hid, 0) + 1.0 / (rrf_k + rank)
                    hit_map[hid] = hit

                sorted_ids = sorted(rrf_score.keys(), key=lambda x: rrf_score[x], reverse=True)
                merged = []
                for hid in sorted_ids[:top_k]:
                    hit = dict(hit_map[hid])
                    hit["distance"] = rrf_score[hid]
                    merged.append(hit)
                results = [merged] if merged else []

            except Exception as search_err:
                # fallback: 纯稠密
                logger.warning(f"hybrid_search 混合检索失败 ({collection_name}), fallback 纯稠密: {search_err}")
                try:
                    results = client.search(
                        collection_name=collection_name,
                        data=[dense_embedding],
                        anns_field="embedding",
                        search_params={"metric_type": "IP", "params": {"nprobe": 10}},
                        limit=top_k,
                        output_fields=output_fields,
                        filter=filter_expr if filter_expr else None,
                    )
                except Exception as fb_err:
                    logger.error(f"hybrid_search 稠密 fallback 也失败 ({collection_name}): {fb_err}")
                    results = []

            if results and len(results) > 0:
                hits = [EmbeddingService._parse_hit(hit, output_fields) for hit in results[0]]
                logger.info(f"hybrid_search 成功 ({collection_name}): top_k={top_k}, 命中={len(hits)}, filter={filter_expr}")
                return hits
            logger.info(f"hybrid_search 无结果 ({collection_name}): top_k={top_k}, filter={filter_expr}")
            return []
        except Exception as e:
            logger.error(f"hybrid_search 失败 ({collection_name}): {e}", exc_info=True)
            return []

    @staticmethod
    async def search(
        db: AsyncSession,
        query: str,
        collection_name: str = KNOWLEDGE_COLLECTION,
        top_k: int = 5,
        user_id: int = 0,
        stage: str = "",
        source_type: str = "",
        extra_filter: str = "",
        output_fields: list = None,
        class_id: int = 0,
    ) -> list[dict]:
        """纯稠密语义检索"""
        try:
            dense_embedding = await AIService.get_embedding(db, query, user_id if user_id else None)
            client = EmbeddingService.get_milvus_client()
            if not client.has_collection(collection_name):
                return []

            if output_fields is None:
                output_fields = EmbeddingService._get_output_fields(collection_name)

            extra = []
            if extra_filter:
                extra.append(f"({extra_filter})")
            if collection_name == EmbeddingService.TEACHER_DOCUMENTS and source_type != "exam_question":
                extra.append('source_type != "exam_question"')
            filter_expr = EmbeddingService._build_filter(user_id, stage, source_type, extra, class_id)

            results = client.search(
                collection_name=collection_name,
                data=[dense_embedding],
                anns_field="embedding",
                search_params={"metric_type": "IP", "params": {"nprobe": 10}},
                limit=top_k,
                output_fields=output_fields,
                filter=filter_expr if filter_expr else None,
            )

            if results and len(results) > 0:
                return [EmbeddingService._parse_hit(hit, output_fields) for hit in results[0]]
            return []
        except Exception as e:
            logger.error(f"search 失败 ({collection_name}): {e}")
            return []

    # ==================== 删除 ====================

    @staticmethod
    def delete_by_expr(collection_name: str, expr: str) -> bool:
        """按过滤表达式删除记录（如 'source_type like "doc%" and source_id == 123'）"""
        try:
            client = EmbeddingService.get_milvus_client()
            if client.has_collection(collection_name):
                client.delete(collection_name=collection_name, filter=expr)
                return True
            return False
        except Exception as e:
            logger.error(f"delete_by_expr 失败 ({collection_name}): {e}")
            return False
