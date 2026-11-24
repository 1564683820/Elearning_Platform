"""文档处理器：解析上传文件 → 三级分块 → 向量化到 Milvus（含混合检索）

改进:
  1. 三级滑动窗口分块 (1200/600/300)
  2. 父级分块持久化（MySQL, 用于 auto-merge）
  3. BM25 稀疏向量写入（支持 hybrid_search）
  4. 渐进式进度上报（job 模式）
  5. PDF 优先使用 MinerU v4 API 转 Markdown，fallback 到 pypdf
"""
import os
import logging
import re
from typing import BinaryIO, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.stats import UserDocument
from app.services.document_scope import PRIVATE_DOCUMENT_CATEGORIES
from app.services.rag_service import RAGService
from app.services.document_service import get_source_type_for_category
from app.services.chunk_manager import chunk_text_three_level, get_leaves, get_parents
from app.services.parent_chunk_store import (
    store_parent_chunks,
    ensure_table as ensure_parent_table,
)
from app.services.bm25_index import get_bm25_index
from app.services.document_progress import (
    init_progress, update_step, set_progress_done, set_progress_error,
    STEP_EXTRACT, STEP_CHUNK, STEP_EMBED,
)
from app.services.upload_job_manager import (
    update_job_step, set_job_done, set_job_error,
)
from app.services.pdf_to_md import pdf_to_markdown

logger = logging.getLogger(__name__)

# 默认分块参数（三级）
DEFAULT_CHUNK_SIZE = 1200     # Level 1 (parent)
DEFAULT_CHUNK_INTER = 600     # Level 2 (intermediate)
DEFAULT_CHUNK_LEAF = 300      # Level 3 (leaf)
MAX_CHUNK_SIZE = 8192         # Milvus content 字段最大长度


class DocumentProcessor:
    """文档处理服务：提取文本 → 三级分块 → 双向量化到 Milvus"""

    @staticmethod
    async def process_document(
        db: AsyncSession,
        doc_id: int,
        teacher_id: int,
        job_id: Optional[str] = None,
        class_id: int = 0,
    ) -> dict:
        """处理单个文档：提取文本、三级分块、双向量化

        参数:
            db - 数据库会话
            doc_id - 文档ID
            teacher_id - 教师用户ID
            job_id - 可选的上传 job_id（用于进度上报）
            class_id - 所属班级ID（0=教师私有）

        返回: 处理结果字典
        """
        doc = await db.get(UserDocument, doc_id)
        if not doc or doc.doc_category in PRIVATE_DOCUMENT_CATEGORIES:
            return {"success": False, "error": "文档不存在"}
        if doc.user_id != teacher_id:
            return {"success": False, "error": "无权限处理此文档"}

        # 如果未显式传入 class_id，从文档记录读取
        if not class_id and doc.class_id:
            class_id = doc.class_id

        # 标记解析中 + 初始化进度
        doc.parse_status = 1
        await db.flush()
        await init_progress(doc.id)

        # 确保父级分块表存在
        try:
            await ensure_parent_table(db)
        except Exception:
            pass  # 表已存在则忽略

        try:
            # === 1. 提取文本 ===
            file_path = doc.file_path or ""
            if not file_path or not os.path.exists(file_path):
                await set_progress_error(doc.id, "文件不存在")
                return {"success": False, "error": "文件不存在"}

            await _report_step(doc.id, job_id, "parse", 10, "正在提取文本...")
            raw_text = await DocumentProcessor._extract_text(file_path, doc.file_type, doc.filename, doc.id, job_id)
            if not raw_text or not raw_text.strip():
                doc.parse_status = 3
                doc.vector_status = 3
                await db.flush()
                await _report_error(doc.id, job_id, "无法提取文档文本内容")
                return {"success": False, "error": "无法提取文档文本内容"}

            # 保存提取的文本（按 UTF-8 字节数截断以防止 MySQL 超限）
            doc.parsed_text = DocumentProcessor._truncate_stored_text(raw_text)

            # 如果是 PDF，将完整 Markdown 另存为 .md 文件
            if doc.file_type == "pdf" or (doc.file_path or "").lower().endswith(".pdf"):
                try:
                    md_path = os.path.splitext(file_path)[0] + ".md"
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(raw_text)
                    doc.md_file_path = md_path
                    logger.info(f"Markdown 文件已保存: {md_path} ({len(raw_text)} 字符)")
                except Exception as e:
                    logger.warning(f"保存 Markdown 文件失败: {e}")

            doc.parse_status = 2
            await db.flush()
            await _report_step(doc.id, job_id, "parse", 100, "文本提取完成")

            # === 2. 三级分块 ===
            await _report_step(doc.id, job_id, "chunk", 30, "正在三级滑动窗口分块...")
            all_chunks = chunk_text_three_level(raw_text, doc.id)
            if not all_chunks:
                doc.vector_status = 3
                await db.flush()
                await _report_error(doc.id, job_id, "文档内容分块结果为空")
                return {"success": False, "error": "文档内容分块结果为空"}

            leaves = get_leaves(all_chunks)       # Level 3（检索用）
            parents = get_parents(all_chunks)      # Level 1 + Level 2（存 MySQL）
            await _report_step(doc.id, job_id, "chunk", 50, f"分块完成: L1={sum(1 for c in all_chunks if c.level==1)} L2={sum(1 for c in all_chunks if c.level==2)} L3={len(leaves)}")

            # === 3. 存储父级分块到 MySQL（auto-merge 支持）===
            await _report_step(doc.id, job_id, "chunk", 70, "正在存储父级分块...")
            try:
                await store_parent_chunks(db, doc.id, parents)
            except Exception as e:
                logger.warning(f"父级分块存储失败（不影响主流程）: {e}")
            await _report_step(doc.id, job_id, "chunk", 100, "分块完成")

            # === 4. 添加到 BM25 语料库 ===
            try:
                bm25 = get_bm25_index()
                for leaf in leaves:
                    bm25.add_document(leaf.content)
            except Exception as e:
                logger.warning(f"BM25 语料更新失败（不影响主流程）: {e}")

            # === 5. 双向量入库（稠密 + 稀疏）===
            source_type = get_source_type_for_category(doc.doc_category or "other")
            await _report_step(doc.id, job_id, "embed", 0, f"准备入库 0/{len(leaves)} 块")

            success_count = await RAGService.index_document_chunks(
                db=db,
                chunks=leaves,
                source_type=source_type,
                source_id=doc.id,
                user_id=teacher_id,
                stage=doc.stage_category or "",
                doc_category=doc.doc_category or "other",
                doc_title=doc.filename,
                doc_tags=doc.doc_tags or "",
                doc_id=doc.id,
                job_id=job_id,
                class_id=class_id,
            )

            doc.vector_status = 2 if success_count > 0 else 3
            doc.chunk_count = success_count
            await db.flush()

            if success_count > 0:
                msg = f"处理完成，成功入库 {success_count}/{len(leaves)} 块"
                await set_progress_done(doc.id, msg)
                # 注意：不要在 process_document 内调用 set_job_done！
                # 由调用方（_async_process）在 commit() 之后才标记 job done，
                # 避免前端在 DB 提交前就刷新列表导致看到旧的状态。
                return {
                    "success": True,
                    "doc_id": doc.id,
                    "filename": doc.filename,
                    "chunk_count": success_count,
                    "total_chunks": len(leaves),
                }
            else:
                await _report_error(doc.id, job_id, "向量入库失败")
                return {
                    "success": False,
                    "error": "向量入库失败",
                    "doc_id": doc.id,
                    "filename": doc.filename,
                    "chunk_count": 0,
                    "total_chunks": len(leaves),
                }

        except Exception as e:
            logger.error(f"文档处理失败 doc_id={doc_id}: {e}", exc_info=True)
            doc.parse_status = 3
            doc.vector_status = 3
            await db.flush()
            await _report_error(doc.id, job_id, f"文档处理异常: {str(e)}")
            return {"success": False, "error": f"文档处理异常: {str(e)}"}

    @staticmethod
    async def reindex_document(
        db: AsyncSession,
        doc_id: int,
        teacher_id: int,
        class_id: int = 0,
    ) -> dict:
        """重新向量化已解析的文档（支持重新提取文本以应用提取器改进）

        适用于 Milvus 集合重建后，或文档提取逻辑更新后需要重新建立向量索引的场景。
        """
        doc = await db.get(UserDocument, doc_id)
        if not doc or doc.doc_category in PRIVATE_DOCUMENT_CATEGORIES:
            return {"success": False, "error": "文档不存在"}
        if doc.user_id != teacher_id:
            return {"success": False, "error": "无权限处理此文档"}
        if doc.parse_status != 2:
            return {"success": False, "error": f"文档解析状态为 {doc.parse_status}（需要 2=已完成），请先完成解析"}

        text = doc.parsed_text
        if not text or not text.strip():
            return {"success": False, "error": "文档无已提取的文本内容"}

        # 如果缓存的 parsed_text 没有经过篇章标记规范化处理，重新从文件提取
        # 适用于 docx 文件升级 _normalize_exam_section_markers 后的场景
        file_path = doc.file_path or ""
        if file_path and os.path.exists(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".docx" and "## 阅读理解" not in text and "阅读理解" not in text:
                # 缓存文本缺少篇章标记，可能来自旧版提取器 → 重新提取
                logger.info(
                    f"reindex: 检测到旧版缓存文本（缺少篇章标记），"
                    f"从文件重新提取: {file_path}"
                )
                fresh_text = await DocumentProcessor._extract_text(
                    file_path, doc.file_type, doc.filename, doc.id
                )
                if fresh_text and len(fresh_text.strip()) > 50:
                    text = fresh_text
                    # 更新缓存的 parsed_text，后续操作使用新版文本
                    doc.parsed_text = DocumentProcessor._truncate_stored_text(fresh_text)
                    await db.flush()
                    logger.info(
                        f"reindex: 已更新 parsed_text，新版包含篇章标记"
                    )

        if not class_id and doc.class_id:
            class_id = doc.class_id

        # 确保父级分块表存在
        try:
            await ensure_parent_table(db)
        except Exception:
            pass

        try:
            doc.vector_status = 1
            await db.flush()
            await init_progress(doc.id)

            # === 1. 三级分块 ===
            all_chunks = chunk_text_three_level(text, doc.id)
            if not all_chunks:
                doc.vector_status = 3
                await db.flush()
                return {"success": False, "error": "文档内容分块结果为空"}

            leaves = get_leaves(all_chunks)
            parents = get_parents(all_chunks)

            # === 2. 存储父级分块到 MySQL ===
            try:
                await store_parent_chunks(db, doc.id, parents)
            except Exception as e:
                logger.warning(f"父级分块存储失败（不影响主流程）: {e}")

            # === 3. 更新 BM25 语料库 ===
            try:
                bm25 = get_bm25_index()
                for leaf in leaves:
                    bm25.add_document(leaf.content)
            except Exception as e:
                logger.warning(f"BM25 语料更新失败（不影响主流程）: {e}")

            # === 4. 双向量入库 ===
            source_type = get_source_type_for_category(doc.doc_category or "other")
            success_count = await RAGService.index_document_chunks(
                db=db,
                chunks=leaves,
                source_type=source_type,
                source_id=doc.id,
                user_id=teacher_id,
                stage=doc.stage_category or "",
                doc_category=doc.doc_category or "other",
                doc_title=doc.filename,
                doc_tags=doc.doc_tags or "",
                doc_id=doc.id,
                class_id=class_id,
            )

            doc.vector_status = 2 if success_count > 0 else 3
            doc.chunk_count = success_count
            await db.flush()

            if success_count > 0:
                msg = f"重索引完成，成功入库 {success_count}/{len(leaves)} 块"
                await set_progress_done(doc.id, msg)
                return {
                    "success": True,
                    "doc_id": doc.id,
                    "filename": doc.filename,
                    "chunk_count": success_count,
                    "total_chunks": len(leaves),
                }
            else:
                return {"success": False, "error": "向量入库失败", "doc_id": doc.id}

        except Exception as e:
            logger.error(f"重索引失败 doc_id={doc_id}: {e}", exc_info=True)
            doc.vector_status = 3
            await db.flush()
            return {"success": False, "error": f"重索引异常: {str(e)}"}

    # ==================== 文本提取 ====================

    @staticmethod
    async def _extract_text(file_path: str, file_type: str, filename: str = "",
                            doc_id: int = 0, job_id: Optional[str] = None) -> str:
        """根据文件类型提取文本内容"""
        ext = os.path.splitext(file_path)[1].lower()
        if file_type == "pdf" or ext == ".pdf":
            return await DocumentProcessor._extract_pdf(file_path, filename, doc_id, job_id)
        elif file_type in ("word",) or ext in (".docx", ".doc"):
            if ext == ".doc":
                return DocumentProcessor._extract_doc(file_path)
            return DocumentProcessor._extract_docx(file_path)
        elif ext == ".pptx":
            return DocumentProcessor._extract_pptx(file_path)
        elif file_type == "ppt" or ext == ".ppt":
            return DocumentProcessor._extract_ppt(file_path)
        elif file_type == "txt" or ext == ".txt":
            return DocumentProcessor._extract_txt(file_path)
        elif file_type == "image" or ext in (".png", ".jpg", ".jpeg"):
            return DocumentProcessor._extract_image_text(file_path)
        else:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception:
                return ""

    @staticmethod
    async def _extract_pdf(file_path: str, filename: str = "",
                           doc_id: int = 0, job_id: Optional[str] = None) -> str:
        """PDF 提取：优先使用 MinerU v4 API 转为 Markdown，失败时 fallback 到 pypdf，
        pypdf 也无法提取时尝试 OCR（扫描版 PDF）
        """
        # 进度回调：将 MinerU 解析进度映射到文档进度
        async def _mineru_progress(pct: int, msg: str):
            # MinerU 进度占整个 parse 阶段的 5%-95%
            mapped = 5 + int(pct * 90 / 100)
            await _report_step(doc_id, job_id, "parse", mapped, msg)

        # 优先使用 MinerU
        try:
            md_text = await pdf_to_markdown(
                file_path,
                filename or os.path.basename(file_path),
                progress_cb=_mineru_progress if doc_id else None,
            )
            if md_text and len(md_text.strip()) > 50:
                logger.info(f"MinerU PDF→Markdown 成功: {len(md_text)} 字符")
                return md_text
            logger.info("MinerU 结果不足，fallback 到 pypdf")
        except Exception as e:
            logger.warning(f"MinerU 调用异常 (fallback 到 pypdf): {e}")

        # fallback 1: pypdf 逐页提取
        text = DocumentProcessor._extract_pdf_with_pypdf(file_path)
        if text and len(text.strip()) > 50:
            return text

        # fallback 2: OCR 兜底（扫描版/图片型 PDF）
        logger.info("pypdf 结果不足，尝试 OCR 兜底...")
        try:
            ocr_text = DocumentProcessor._extract_pdf_with_ocr(file_path)
            if ocr_text and len(ocr_text.strip()) > 50:
                logger.info(f"PDF OCR 兜底成功: {len(ocr_text)} 字符")
                return ocr_text
        except Exception as e:
            logger.warning(f"PDF OCR 兜底失败: {e}")

        return ""

    @staticmethod
    def _extract_pdf_with_pypdf(file_path: str | BinaryIO, *, max_pages: int | None = None) -> str:
        """使用 pypdf 提取 PDF 文本"""
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            texts = []
            pages = reader.pages if max_pages is None else reader.pages[:max_pages]
            for page in pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            return "\n\n".join(texts)
        except ImportError:
            logger.warning("pypdf 未安装，无法解析 PDF")
            return ""
        except Exception as e:
            logger.error(f"PDF 解析失败: {e}")
            return ""

    @staticmethod
    def _extract_pdf_with_ocr(file_path: str) -> str:
        """使用 OCR 提取扫描版 PDF 文本

        将 PDF 逐页转为图片，再用 pytesseract 进行 OCR 识别。
        """
        try:
            import pypdf
            from PIL import Image, ImageEnhance, ImageFilter
            import pytesseract
            import io

            reader = pypdf.PdfReader(file_path)
            total_pages = len(reader.pages)
            logger.info(f"PDF OCR: 共 {total_pages} 页")

            texts = []
            for i, page in enumerate(reader.pages):
                page_num = i + 1
                try:
                    # 提取页面图像
                    # 方法1: 尝试从页面资源中提取嵌入的图片
                    page_images = []
                    for image_file_object in page.images:
                        try:
                            img_data = image_file_object.data
                            img = Image.open(io.BytesIO(img_data))
                            page_images.append(img)
                        except Exception:
                            continue

                    if page_images:
                        # 合并页面中的所有图片
                        for img in page_images:
                            ocr_result = DocumentProcessor._ocr_image(img)
                            if ocr_result:
                                texts.append(ocr_result)
                    else:
                        # 方法2: 尝试提取页面文本（之前已失败，这里作为 pypdf 提取方式不同）
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            texts.append(page_text)
                            continue
                        # 页面既没有嵌入图片也没有提取文本，跳过
                        logger.debug(f"OCR 兜底: 第{page_num}页无可用图像资源")

                except Exception as e:
                    logger.warning(f"OCR 兜底: 第{page_num}页处理异常: {e}")
                    continue

            result = "\n\n".join(texts)
            if result.strip():
                logger.info(f"PDF OCR 兜底完成: {len(result)} 字符, {total_pages} 页")
            return result
        except ImportError as e:
            logger.warning(f"PDF OCR 依赖缺失: {e}")
            return ""
        except Exception as e:
            logger.error(f"PDF OCR 兜底失败: {e}")
            return ""

    @staticmethod
    def _ocr_image(img, *, timeout: int = 0) -> str:
        """对单张图像执行 OCR，返回识别文本"""
        try:
            import pytesseract
            from PIL import ImageEnhance, ImageFilter

            # 预处理
            if img.mode != "L":
                img = img.convert("L")
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            img = img.point(lambda p: 255 if p > 128 else 0)
            img = img.filter(ImageFilter.MedianFilter(size=3))

            text = pytesseract.image_to_string(img, lang="chi_sim+eng", timeout=timeout)
            return text.strip()
        except ImportError:
            return ""
        except Exception as e:
            logger.debug(f"OCR 单张图片失败: {e}")
            return ""

    @staticmethod
    def _extract_docx(file_path: str | BinaryIO) -> str:
        try:
            import docx
            doc = docx.Document(file_path)
            texts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    texts.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_texts:
                        texts.append(" | ".join(row_texts))
            raw_text = "\n\n".join(texts)

            # === 后处理：将 docx 格式化的篇章标记转换为文本标题 ===
            # 英语试卷中 A/B/C/D 阅读篇章经常用加粗/居中的单字母标示，
            # 原始提取结果只是单独的 "A" "B" "C" "D" 段落，分块器无法识别为标题。
            # 这里基于 docx 段落元数据检测并转换为 "# C篇 阅读理解" 格式。
            raw_text = DocumentProcessor._normalize_exam_section_markers(
                doc, raw_text
            )

            return raw_text
        except ImportError:
            logger.warning("python-docx 未安装，无法解析 DOCX")
            return ""
        except Exception as e:
            logger.error(f"DOCX 解析失败: {e}")
            return ""

    @staticmethod
    def _normalize_exam_section_markers(doc, raw_text: str) -> str:
        """检测 docx 中加粗/居中的篇章标记 (A/B/C/D)，转换为标准标题格式

        英语试卷的阅读理解 A/B/C/D 篇章常以单独的加粗字母段落标示，
        分块器无法识别为标题，导致所有篇章的 chunk 被归到错误的 section_title。
        此方法扫描 docx 段落元数据，将这类视觉标记替换为 "# C篇 阅读理解" 格式。

        判定条件（需全部满足）：
          1. 段落文本为单个字母 A-D
          2. 至少有一个 run 是加粗的 (bold=True)
          3. 前向看：后面的段落是较长的英文文本（阅读篇章正文）
        """
        try:
            paragraphs = doc.paragraphs
            markers: list[tuple[int, str, str]] = []  # [(段落索引, 原文本, 新标签), ...]

            for i, para in enumerate(paragraphs):
                text = para.text.strip()
                if not text or len(text) > 3:
                    continue

                # 检查是否为单个大写字母 A-D
                if text not in ("A", "B", "C", "D"):
                    continue

                # 检查是否加粗（篇章标记通常加粗）
                has_bold = any(run.bold for run in para.runs if run.text.strip())
                is_centered = para.alignment == 1  # CENTER

                if not has_bold and not is_centered:
                    # 至少有一个格式特征才认定为篇章标记
                    continue

                # 前向验证：后面 1-3 个非空段落是否为较长英文（篇章正文）
                subsequent_text = ""
                for j in range(i + 1, min(len(paragraphs), i + 5)):
                    next_text = paragraphs[j].text.strip()
                    if next_text and len(next_text) > 60:
                        subsequent_text += next_text[:200]
                        break

                if not subsequent_text:
                    continue  # 后面没有长段落，可能只是选项标记

                # 确认为篇章标记，构造有意义的标题
                # 尝试从上下文推断篇章类型
                label = f"阅读理解 {text}篇"
                markers.append((i, text, label))
                logger.debug(
                    f"docx 篇章标记检测: 段落[{i}] '{text}' → '{label}' "
                    f"bold={has_bold} centered={is_centered}"
                )

            if not markers:
                return raw_text

            # 在 raw_text 中替换独立的 "A" / "B" / "C" / "D" 为标题格式
            # 使用正则确保只匹配独立的行（前后有换行符或文本边界）
            result = raw_text
            for _para_idx, original, label in markers:
                # 匹配独立成行的单个字母（可能前后有空白）
                pattern = rf'(^|\n\n)\s*{re.escape(original)}\s*(\n\n|$)'
                replacement = rf'\1## {label}\2'
                new_result = re.sub(pattern, replacement, result, count=1)
                if new_result != result:
                    result = new_result
                    logger.info(
                        f"docx 篇章标记转换: '{original}' → '## {label}'"
                    )

            return result
        except Exception as e:
            logger.warning(f"docx 篇章标记检测异常（不影响主流程）: {e}")
            return raw_text

    @staticmethod
    def _is_garbage_text(text: str) -> bool:
        """检测文本是否为二进制垃圾（用于 .doc UTF-16LE 解码后的质量校验）"""
        if not text or len(text) < 50:
            return True

        # 1. 检查可打印字符比例（真实文本应 > 70%）
        printable = sum(1 for c in text if c.isprintable())
        if printable / len(text) < 0.7:
            return True

        # 2. 检查二进制伪影字符：null / U+FFFE / U+FFFF / 控制字符
        bad = sum(1 for c in text if ord(c) in (0, 0xFFFE, 0xFFFF))
        if bad / max(len(text), 1) > 0.01:
            return True

        # 3. 检查字母/数字/中日韩统一表意文字的总占比
        valid = sum(1 for c in text if c.isalpha() or c.isdigit())
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
        if (valid + cjk) / max(len(text), 1) < 0.2:
            return True

        # 4. IME 扩展区 / 私用区字符比例过高说明是二进制垃圾
        private = sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF or 0xF0000 <= ord(c) <= 0x10FFFF)
        if private / max(len(text), 1) > 0.1:
            return True

        return False

    @staticmethod
    def _extract_doc(file_path: str) -> str:
        """从旧版 .doc（Word 97-2003 OLE2 二进制格式）文件中提取文本

        python-docx 不支持该格式，使用多种策略提取可读文本。
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # 方法1：尝试 olefile 从 OLE2 文档流中提取文本
            try:
                import olefile
                ole = olefile.OleFileIO(file_path)
                candidates = []
                for stream_parts in ole.listdir():
                    stream_name = '/'.join(stream_parts)
                    try:
                        raw = ole.openstream(stream_name).read()
                        # 尝试 UTF-16LE 解码
                        text = raw.decode('utf-16-le', errors='replace')
                        if not DocumentProcessor._is_garbage_text(text):
                            candidates.append(text)
                    except Exception:
                        try:
                            text = raw.decode('utf-8', errors='replace')
                            if not DocumentProcessor._is_garbage_text(text):
                                candidates.append(text)
                        except Exception:
                            pass
                ole.close()

                if candidates:
                    best = max(candidates, key=len)
                    logger.info(f".doc 通过 olefile 提取文本 {len(best)} 字符")
                    return DocumentProcessor._truncate_stored_text(best)
            except ImportError:
                logger.debug("olefile 未安装，跳过 OLE2 流解析")
            except Exception as e:
                logger.warning(f"olefile 解析异常: {e}")

            # 方法2：尝试 UTF-16LE 解码（适用 Word Unicode 文本存储）
            try:
                text = data.decode('utf-16-le', errors='replace')
                lines = [l.strip() for l in text.split('\n')
                        if l.strip() and len(l.strip()) >= 4]
                combined = '\n'.join(lines)
                if not DocumentProcessor._is_garbage_text(combined) and len(combined) > 50:
                    logger.info(f".doc 通过 UTF-16LE 提取文本 {len(combined)} 字符")
                    return DocumentProcessor._truncate_stored_text(combined)
            except Exception:
                pass

            # 方法3：提取 ASCII 可读文本块（类似 strings 命令）
            result = []
            current = []
            for byte in data:
                b = byte if isinstance(byte, int) else ord(byte)
                if 32 <= b <= 126 or b >= 160:
                    current.append(chr(b))
                else:
                    if current and len(current) >= 4:
                        result.append(''.join(current))
                    current = []
            if current and len(current) >= 4:
                result.append(''.join(current))

            final = '\n'.join(result[:500])
            if len(final.strip()) > 20:
                logger.info(f".doc 通过 ASCII 提取文本 {len(final)} 字符")
                return final

            logger.warning("无法从 .doc 文件中提取可读文本")
            return ""
        except Exception as e:
            logger.error(f".doc 文本提取失败: {e}")
            return ""

    @staticmethod
    def _truncate_stored_text(text: str, max_utf8_bytes: int = 50000) -> str:
        """按 UTF-8 字节数截断文本，避免 MySQL TEXT 超限"""
        encoded = text.encode('utf-8')
        if len(encoded) <= max_utf8_bytes:
            return text
        # 逐字符回退到安全字节数
        while len(encoded) > max_utf8_bytes:
            text = text[:-1]
            encoded = text.encode('utf-8')
        return text

    @staticmethod
    def _extract_pptx(file_path: str) -> str:
        """提取 PPTX（Office Open XML 格式）文本内容

        逐幻灯片提取：标题（按字号分级）、正文、列表、表格、备注。
        输出 Markdown 格式，方便后续分块和 RAG 检索。
        """
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            texts = []
            for i, slide in enumerate(prs.slides):
                slide_texts = []

                # 提取幻灯片备注
                try:
                    if slide.has_notes_slide:
                        notes_slide = slide.notes_slide
                        if notes_slide and notes_slide.notes_text_frame:
                            notes = notes_slide.notes_text_frame.text.strip()
                            if notes:
                                slide_texts.append(f"[备注]: {notes}")
                except Exception:
                    pass  # 备注提取失败不影响主流程

                # 提取所有形状中的文本
                for shape in slide.shapes:
                    # 判断是否为标题形状（通常在左上角，字体较大）
                    if shape.shape_type is not None and hasattr(shape, 'has_text_frame') and shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text = para.text.strip()
                            if not text:
                                continue
                            # 识别标题级别（基于字体大小和缩进）
                            if para.level == 0 and (para.runs and para.runs[0].font.size):
                                font_size = para.runs[0].font.size.pt if para.runs[0].font.size else 0
                                if font_size >= 20:
                                    slide_texts.append(f"## {text}")
                                elif font_size >= 16:
                                    slide_texts.append(f"### {text}")
                                else:
                                    slide_texts.append(text)
                            else:
                                if para.level == 0:
                                    slide_texts.append(text)
                                else:
                                    slide_texts.append(f"  - {text}")

                    if hasattr(shape, 'has_table') and shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                            if row_texts:
                                slide_texts.append("| " + " | ".join(row_texts) + " |")

                if slide_texts:
                    texts.append(f"## 第{i+1}页\n" + "\n".join(slide_texts))
            return "\n\n".join(texts)
        except ImportError:
            logger.warning("python-pptx 未安装，无法解析 PPTX")
            return ""
        except Exception as e:
            logger.error(f"PPTX 解析失败: {e}")
            return ""

    @staticmethod
    def _extract_ppt(file_path: str) -> str:
        """提取旧版 .ppt（PowerPoint 97-2003 OLE2 格式）文本内容

        python-pptx 不支持 .ppt 格式，使用 olefile 从 OLE2 流中提取文本。
        """
        try:
            import olefile
            ole = olefile.OleFileIO(file_path)
            texts = []
            slide_count = 0

            # PowerPoint 97-2003 将文本存储在 "PowerPoint Document" 流中
            # 也尝试遍历所有流寻找可读文本
            for stream_parts in ole.listdir():
                stream_name = '/'.join(stream_parts)
                try:
                    raw = ole.openstream(stream_name).read()
                    # 跳过明显的二进制流
                    if len(raw) < 100:
                        continue

                    # 尝试 UTF-16LE 解码（PPT 同 Word 一样存储 Unicode 文本）
                    text = raw.decode('utf-16-le', errors='replace')
                    if DocumentProcessor._is_garbage_text(text):
                        # 尝试 UTF-8
                        text = raw.decode('utf-8', errors='replace')
                        if DocumentProcessor._is_garbage_text(text):
                            # 尝试 ASCII 提取
                            result_lines = []
                            current_line = []
                            for byte in raw:
                                b = byte if isinstance(byte, int) else ord(byte)
                                if 32 <= b <= 126:
                                    current_line.append(chr(b))
                                elif b in (10, 13):
                                    if current_line and len(current_line) >= 4:
                                        result_lines.append(''.join(current_line))
                                    current_line = []
                            if result_lines:
                                text = '\n'.join(result_lines)
                            else:
                                continue

                    # 过滤掉含过多二进制伪影的文本
                    if len(text.strip()) > 20:
                        slide_count += 1
                        # 截取有意义的文本（PPT 流中常有大量重复/无关数据）
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        # 去重连续相同行
                        deduped = []
                        for line in lines:
                            if not deduped or deduped[-1] != line:
                                deduped.append(line)
                        if deduped:
                            texts.append(f"## 幻灯片{slide_count}\n" + "\n".join(deduped[:200]))
                except Exception:
                    continue

            ole.close()

            if texts:
                result = "\n\n".join(texts)
                logger.info(f".ppt 通过 olefile 提取文本: {len(result)} 字符, {slide_count} 幻灯片")
                return result

            logger.warning("无法从 .ppt 文件中提取可读文本（OLE2 流无有效UTF-16LE数据）")
            return ""
        except ImportError:
            logger.warning("olefile 未安装，无法解析旧版 .ppt")
            return ""
        except Exception as e:
            logger.error(f".ppt 文本提取失败: {e}")
            return ""

    @staticmethod
    def _extract_txt(file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.error(f"TXT 解析失败: {e}")
            return ""

    @staticmethod
    def _extract_image_text(file_path: str) -> str:
        try:
            from PIL import Image
            img = Image.open(file_path)
            return DocumentProcessor._ocr_image(img)
        except ImportError:
            logger.warning("pytesseract / Pillow 未安装，无法进行 OCR")
            return ""
        except Exception as e:
            logger.error(f"图片 OCR 失败: {e}")
            return ""


# ==================== 辅助函数 ====================

async def _report_step(doc_id: int, job_id: Optional[str], step: str, percent: int, message: str):
    """同时更新 document_progress 和 upload_job（如果有 job_id）"""
    status = "running" if percent < 100 else "done"

    # 映射 document_progress 步骤名
    progress_step_map = {
        "parse": STEP_EXTRACT,
        "chunk": STEP_CHUNK,
        "embed": STEP_EMBED,
    }
    pstep = progress_step_map.get(step, step)
    await update_step(doc_id, pstep, percent, status, message)

    if job_id:
        await update_job_step(job_id, step, percent, status, message)


async def _report_error(doc_id: int, job_id: Optional[str], message: str):
    """报告处理错误"""
    await set_progress_error(doc_id, message)
    if job_id:
        await set_job_error(job_id, message)
