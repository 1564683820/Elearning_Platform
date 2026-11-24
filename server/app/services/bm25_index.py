"""BM25 稀疏向量索引 — 用于 Milvus hybrid_search

维护一个基于字符 n-gram 的 BM25 模型，支持增量增删语料，
为每个文档/分块生成 SPARSE_FLOAT_VECTOR 格式的稀疏向量。

持久化到 JSON 文件：./data/bm25_corpus.json
"""
import json
import os
import math
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# BM25 参数
K1 = 1.5  # 词频饱和度
B = 0.75  # 文档长度归一化

# n-gram 范围（适用于中英文混合文本）
NGRAM_MIN = 2
NGRAM_MAX = 3

# 持久化路径（放在 server/data/ 而非 app/data/，避免 uvicorn reload 监控到写入触发无限重载）
DEFAULT_CORPUS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "bm25_corpus.json"
)


def _char_ngrams(text: str, n_min: int = NGRAM_MIN, n_max: int = NGRAM_MAX) -> list[str]:
    """将文本切成字符 n-gram（适用于中英文混合场景）"""
    text = text.lower().strip()
    tokens = []
    for n in range(n_min, n_max + 1):
        for i in range(len(text) - n + 1):
            tokens.append(text[i:i + n])
    return tokens


class BM25Index:
    """轻量 BM25 稀疏向量索引（可持久化）"""

    def __init__(self, corpus_path: str = DEFAULT_CORPUS_PATH):
        self.corpus_path = corpus_path
        # term -> {doc_count, total_freq}
        self.term_stats: dict[str, dict] = {}
        self.total_docs = 0  # corpus 中的文档总数
        self.avg_doc_len = 0.0
        self._loaded = False

    # ---- 持久化 ----

    def save(self):
        """保存 corpus 统计到 JSON"""
        os.makedirs(os.path.dirname(self.corpus_path), exist_ok=True)
        data = {
            "term_stats": self.term_stats,
            "total_docs": self.total_docs,
            "avg_doc_len": self.avg_doc_len,
        }
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"BM25 corpus saved: {len(self.term_stats)} terms, {self.total_docs} docs")

    def load(self):
        """从 JSON 加载 corpus 统计"""
        if not os.path.exists(self.corpus_path):
            self._loaded = True
            return
        try:
            with open(self.corpus_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.term_stats = data.get("term_stats", {})
            self.total_docs = data.get("total_docs", 0)
            self.avg_doc_len = data.get("avg_doc_len", 0.0)
            self._loaded = True
            logger.info(f"BM25 corpus loaded: {len(self.term_stats)} terms, {self.total_docs} docs")
        except Exception as e:
            logger.warning(f"Failed to load BM25 corpus: {e}")
            self._loaded = True

    def ensure_loaded(self):
        if not self._loaded:
            self.load()

    # ---- 增量更新 ----

    def add_document(self, text: str):
        """向 corpus 添加一篇文档"""
        self.ensure_loaded()
        tokens = _char_ngrams(text)
        unique_terms = set(tokens)
        term_freq = defaultdict(int)
        for t in tokens:
            term_freq[t] += 1

        for term in unique_terms:
            if term not in self.term_stats:
                self.term_stats[term] = {"doc_count": 0, "total_freq": 0}
            self.term_stats[term]["doc_count"] += 1
            self.term_stats[term]["total_freq"] += term_freq[term]

        # 更新总统计
        old_total = self.total_docs * self.avg_doc_len
        new_doc_len = len(tokens)
        self.total_docs += 1
        self.avg_doc_len = (old_total + new_doc_len) / self.total_docs

        self.save()

    def remove_document(self, text: str):
        """从 corpus 移除一篇文档"""
        self.ensure_loaded()
        if self.total_docs <= 0:
            return

        tokens = _char_ngrams(text)
        unique_terms = set(tokens)
        term_freq = defaultdict(int)
        for t in tokens:
            term_freq[t] += 1

        for term in unique_terms:
            if term not in self.term_stats:
                continue
            self.term_stats[term]["doc_count"] = max(0, self.term_stats[term]["doc_count"] - 1)
            self.term_stats[term]["total_freq"] = max(0, self.term_stats[term]["total_freq"] - term_freq[term])
            if self.term_stats[term]["doc_count"] <= 0:
                del self.term_stats[term]

        # 更新总统计
        old_total = self.total_docs * self.avg_doc_len
        doc_len = len(tokens)
        self.total_docs = max(0, self.total_docs - 1)
        self.avg_doc_len = (old_total - doc_len) / self.total_docs if self.total_docs > 0 else 0.0

        self.save()

    def add_batch(self, texts: list[str]):
        """批量添加文档（一次性保存）"""
        self.ensure_loaded()
        total_len_change = 0
        for text in texts:
            tokens = _char_ngrams(text)
            unique_terms = set(tokens)
            term_freq = defaultdict(int)
            for t in tokens:
                term_freq[t] += 1

            for term in unique_terms:
                if term not in self.term_stats:
                    self.term_stats[term] = {"doc_count": 0, "total_freq": 0}
                self.term_stats[term]["doc_count"] += 1
                self.term_stats[term]["total_freq"] += term_freq[term]

            total_len_change += len(tokens)

        old_total = self.total_docs * self.avg_doc_len
        self.total_docs += len(texts)
        self.avg_doc_len = (old_total + total_len_change) / self.total_docs

        self.save()

    def remove_batch(self, texts: list[str]):
        """批量移除文档"""
        for text in texts:
            self.remove_document(text)
        self.save()

    # ---- 稀疏向量生成 ----

    def compute_sparse_vector(self, text: str) -> dict[int, float]:
        """为文本计算 BM25 稀疏向量

        返回: {dimension_id: bm25_score, ...}
        其中 dimension_id = hash(term) % 65536
        """
        self.ensure_loaded()
        tokens = _char_ngrams(text)
        if not tokens or self.total_docs == 0:
            return {}

        term_freq = defaultdict(int)
        for t in tokens:
            term_freq[t] += 1

        doc_len = len(tokens)
        sparse: dict[int, float] = defaultdict(float)

        for term, tf in term_freq.items():
            stats = self.term_stats.get(term)
            if stats is None or stats["doc_count"] <= 0:
                continue

            # BM25 公式
            idf = math.log((self.total_docs - stats["doc_count"] + 0.5) / (stats["doc_count"] + 0.5) + 1.0)
            score = idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * (doc_len / self.avg_doc_len)))

            # hash term 到固定维度
            dim_id = hash(term) % 65536  # 0~65535 固定空间
            sparse[dim_id] += score

        return dict(sparse)


# 全局单例
_bm25_index: Optional[BM25Index] = None


def get_bm25_index() -> BM25Index:
    """获取全局 BM25 索引单例"""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
        _bm25_index.load()
    return _bm25_index


def reset_bm25_index():
    """重置 BM25 索引（测试用）"""
    global _bm25_index
    _bm25_index = None
