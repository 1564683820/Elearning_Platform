"""三级滑动窗口分块管理器 — Auto-merging Retriever 支持

分块层级:
  Level 1 (Parent):   1200 chars — 大段上下文
  Level 2 (Intermed):  600 chars — 中等粒度
  Level 3 (Leaf):      300 chars — 检索用（精粒度）

每个块通过 chunk_id → parent_chunk_id → root_chunk_id 链式追踪。

v2: 支持标题识别，每个 chunk 自动关联其所属的 Markdown 章节标题，
    标题路径会拼接到 content 中，提升 RAG 检索时的语义匹配精度。
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 三个层级的分块大小
CHUNK_SIZES = {1: 1200, 2: 600, 3: 300}
# Level 3 是叶子块，用于检索
LEAF_LEVEL = 3

# 标题匹配模式
_HEADING_PATTERN = re.compile(
    r'^(#{1,6})\s+(.+?)[ \t]*$',         # Markdown # 标题
    re.MULTILINE,
)
_CHINESE_HEADING_PATTERN = re.compile(
    r'^((?:第[一二三四五六七八九十百千\d]+[章节课]|'
    r'[一二三四五六七八九十]、|'
    r'（[一二三四五六七八九十]）|'
    r'\(\d+\)|'
    r'\d+[\.\、]|'
    r'[A-Z][\.\、]))[ \t]*(.+?)[ \t]*$',  # 中英文编号标题
    re.MULTILINE,
)

# 英语试卷篇章标记：独立的 A/B/C/D 字母行（无标点后缀）
# 这类标记在试题中用加粗/居中的单个字母标示阅读理解篇章的起始位置
_EXAM_SECTION_PATTERN = re.compile(
    r'^([A-D])\s*$',
    re.MULTILINE,
)

# 中文篇章标记：如 "A篇" "B篇"
_CN_SECTION_PATTERN = re.compile(
    r'^([A-D])篇\s*$',
    re.MULTILINE,
)


class ChunkInfo:
    """单个分块的元信息"""
    __slots__ = ("content", "level", "seq", "chunk_id",
                 "parent_chunk_id", "root_chunk_id", "section_title")

    def __init__(
        self,
        content: str,
        level: int,
        seq: int,
        chunk_id: str,
        parent_chunk_id: Optional[str] = None,
        root_chunk_id: Optional[str] = None,
        section_title: str = "",
    ):
        self.content = content
        self.level = level
        self.seq = seq
        self.chunk_id = chunk_id
        self.parent_chunk_id = parent_chunk_id
        self.root_chunk_id = root_chunk_id
        self.section_title = section_title

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "level": self.level,
            "seq": self.seq,
            "chunk_id": self.chunk_id,
            "parent_chunk_id": self.parent_chunk_id,
            "root_chunk_id": self.root_chunk_id,
            "section_title": self.section_title,
        }


def _normalize_text(text: str) -> str:
    """归一化空白字符"""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, chunk_size: int) -> list[str]:
    """按给定大小分块，优先按段落/句子边界切分"""
    paragraphs = re.split(r"\n\n+", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            # 按句子拆分长段落
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) > chunk_size:
                    if current:
                        chunks.append(current)
                    # 强行截断
                    for i in range(0, len(sent), chunk_size):
                        chunks.append(sent[i:i + chunk_size])
                    current = ""
                elif len(current) + len(sent) + 2 <= chunk_size:
                    current = (current + "\n" + sent) if current else sent
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            if current:
                chunks.append(current)
                current = ""
        else:
            if len(current) + len(para) + 2 <= chunk_size:
                current = (current + "\n\n" + para) if current else para
            else:
                if current:
                    chunks.append(current)
                current = para

    if current:
        chunks.append(current)

    return chunks


def _parse_all_headings(text: str) -> list[tuple[int, str, int]]:
    """解析文本中的所有标题（Markdown + 中文编号 + 英语试卷篇章标记）

    返回: [(字符位置, 标题文本, 层级), ...] 按位置升序
        层级: 1=最高 (H1/章), 2=H2/节, 3+=H3+/子节
    """
    headings = []

    # Markdown # 标题
    for m in _HEADING_PATTERN.finditer(text):
        level = len(m.group(1))  # # 的数量
        title = m.group(2).strip()
        headings.append((m.start(), title, level))

    # 中文编号标题（如 一、 二、 （一） 第X章 等）
    for m in _CHINESE_HEADING_PATTERN.finditer(text):
        if m.group(1):
            prefix = m.group(1).strip()
            title = m.group(2).strip() if m.lastindex >= 2 else prefix
            # 根据编号类型推断层级
            if prefix.startswith("第") and any(k in prefix for k in ["章", "课"]):
                level = 1
            elif any(prefix.startswith(c) for c in "一二三四五六七八九十"):
                level = 2
            elif prefix.startswith("（") or prefix.startswith("("):
                level = 3
            elif re.match(r'^\d+[\.\、]', prefix):
                level = 2
            elif re.match(r'^[A-Z][\.\、]', prefix):
                level = 3
            else:
                level = 2
            full_title = f"{prefix} {title}" if title and title != prefix else prefix
            headings.append((m.start(), full_title.strip(), level))

    # 英语试卷篇章标记：独立成行的 A/B/C/D（无标点后缀）
    # 防止与选择题选项中的 "C" 混淆：只有当字母前后都是空行才认定为篇章标记
    for m in _EXAM_SECTION_PATTERN.finditer(text):
        letter = m.group(1)
        title = f"阅读理解 {letter}篇"
        # 层级 3，与 [A-Z][\.\、] 同类
        headings.append((m.start(), title, 3))

    # 中文篇章标记：A篇 / B篇 / C篇 / D篇
    for m in _CN_SECTION_PATTERN.finditer(text):
        letter = m.group(1)
        title = f"{letter}篇"
        headings.append((m.start(), title, 3))

    # 按位置排序，位置相同按层级（更高级别在前）
    headings.sort(key=lambda x: (x[0], x[2]))
    return headings


def _build_heading_breadcrumb(
    headings: list[tuple[int, str, int]],
    pos: int,
) -> str:
    """根据文本位置构建标题面包屑路径

    例如: "Chapter 1 > Section 1.1 > Topic A"
    """
    stack: list[tuple[str, int]] = []  # [(title, level), ...]
    for h_pos, title, level in headings:
        if h_pos >= pos:
            break
        # 弹出同级或更深层级的旧标题，保持栈中每层级只有一个最新标题
        while stack and stack[-1][1] >= level:
            stack.pop()
        stack.append((title, level))
    if not stack:
        return ""
    return " > ".join(t for t, _ in stack)


def _annotate_chunks_with_headings(
    text: str,
    chunks: list[ChunkInfo],
    headings: list[tuple[int, str, int]],
) -> None:
    """为所有 chunk 标注其所属的标题路径，并将标题拼接到 content 前面

    先按在原文中的位置排序，确保游标增量查找正确。
    300+ 字符的 chunk 在单文档中几乎不会重复，直接用 find 定位即可。
    """
    if not headings:
        return

    # 先为每个 chunk 定位其在原文中的位置
    chunk_positions: list[tuple[int, ChunkInfo]] = []
    for chunk in chunks:
        pos = text.find(chunk.content)
        if pos >= 0:
            chunk_positions.append((pos, chunk))

    # 按位置排序，确保标题关联基于正确的文档顺序
    chunk_positions.sort(key=lambda x: x[0])

    for pos, chunk in chunk_positions:
        breadcrumb = _build_heading_breadcrumb(headings, pos)
        if not breadcrumb:
            continue

        chunk.section_title = breadcrumb

        # 避免标题与 content 开头重复（如 content 本身以该标题开头）
        content_stripped = chunk.content.lstrip("#").lstrip()
        last_heading = breadcrumb.split(" > ")[-1]
        if content_stripped.startswith(last_heading):
            # 内容开头已经是该标题文本，不重复拼接
            continue

        # 将标题路径拼接到 content 前面，提升向量检索的语义关联
        chunk.content = f"[{breadcrumb}]\n{chunk.content}"


def chunk_text_three_level(
    text: str,
    doc_id: int,
    chunk_sizes: Optional[dict[int, int]] = None,
) -> list[ChunkInfo]:
    """将文本按三级滑动窗口分块，并自动识别标题与内容关联

    参数:
        text: 原始文本
        doc_id: 文档 ID（用于生成 chunk_id）
        chunk_sizes: 可选的自定义各层级分块大小

    返回:
        所有层级分块的 ChunkInfo 列表（content 已含标题上下文）
    """
    if not text or not text.strip():
        return []

    sizes = chunk_sizes or CHUNK_SIZES
    text = _normalize_text(text)
    all_chunks: list[ChunkInfo] = []

    # === Level 1 (Parent) ===
    l1_raw = _split_text(text, sizes[1])
    l1_chunks = []
    for i, content in enumerate(l1_raw):
        c = ChunkInfo(
            content=content,
            level=1,
            seq=i,
            chunk_id=f"{doc_id}_1_{i}",
        )
        c.root_chunk_id = c.chunk_id  # L1 自已是 root
        l1_chunks.append(c)
        all_chunks.append(c)

    # === Level 2 (Intermediate) ===
    for l1 in l1_chunks:
        l2_raw = _split_text(l1.content, sizes[2])
        for i, content in enumerate(l2_raw):
            c = ChunkInfo(
                content=content,
                level=2,
                seq=i,
                chunk_id=f"{doc_id}_2_{l1.seq}_{i}",
                parent_chunk_id=l1.chunk_id,
                root_chunk_id=l1.root_chunk_id,
            )
            all_chunks.append(c)

            # === Level 3 (Leaf) ===
            l3_raw = _split_text(content, sizes[3])
            for j, leaf_content in enumerate(l3_raw):
                leaf = ChunkInfo(
                    content=leaf_content,
                    level=3,
                    seq=j,
                    chunk_id=f"{doc_id}_3_{l1.seq}_{i}_{j}",
                    parent_chunk_id=c.chunk_id,
                    root_chunk_id=l1.root_chunk_id,
                )
                all_chunks.append(leaf)

    # === 标题识别与内容关联 ===
    # 解析原文标题，为所有 chunk 标注所属标题路径
    try:
        headings = _parse_all_headings(text)
        if headings:
            _annotate_chunks_with_headings(text, all_chunks, headings)
            heading_count = len(headings)
            annotated = sum(1 for c in all_chunks if c.section_title)
            logger.info(
                f"标题关联完成: 识别 {heading_count} 个标题, "
                f"已标注 {annotated}/{len(all_chunks)} 个 chunk"
            )
    except Exception as e:
        logger.warning(f"标题识别异常（不影响分块）: {e}")

    return all_chunks


def get_leaves(chunks: list[ChunkInfo]) -> list[ChunkInfo]:
    """仅获取 Level 3 叶子块（用于 Milvus 检索）"""
    return [c for c in chunks if c.level == LEAF_LEVEL]


def get_parents(chunks: list[ChunkInfo]) -> list[ChunkInfo]:
    """获取 Level 1 + Level 2 父块（用于 MySQL 存储 / auto-merge）"""
    return [c for c in chunks if c.level < LEAF_LEVEL]
