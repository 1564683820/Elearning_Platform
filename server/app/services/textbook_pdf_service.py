"""
教材 PDF 解析导入服务

功能:
- 按页解析 PDF 提取文本
- 自动检测单元边界（Unit X / 第X单元 / Module X / Recycle X）
- 扫描版 PDF 自动 OCR 回退（PyMuPDF 渲染 + pytesseract）
- 每页渲染为图片保存，设置 image_url
- 将每页文本存入 TextbookPage，自动创建 TextbookUnit
- 支持异步后台处理 + 进度上报
"""
import os
import re
import logging
from typing import Optional
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models.textbook_models import TextbookUnit, TextbookPage
from app.models.textbook_upload import TextbookUpload

logger = logging.getLogger(__name__)

# 单元标题检测正则
_UNIT_PATTERNS = [
    re.compile(r"^(?:Unit|UNIT|unit)\s+(\d+|[A-Z])", re.IGNORECASE),         # Unit 1, Unit A
    re.compile(r"^(?:Module|MODULE|module)\s+(\d+|[A-Z])", re.IGNORECASE),   # Module 1
    re.compile(r"^(?:Lesson|LESSON|lesson)\s+(\d+)", re.IGNORECASE),        # Lesson 1
    re.compile(r"^(?:Recycle|RECYCLE|recycle)\s+(\d+)", re.IGNORECASE),     # Recycle 1 (PEP 特有)
    re.compile(r"^第([一二三四五六七八九十\d]+)单元"),                        # 第一单元 / 第1单元
    re.compile(r"^(?:Section|SECTION|section)\s+(\d+|[A-Z])", re.IGNORECASE), # Section 1
]

# 通用跳过模式（页眉页脚/占位符）
_SKIP_LINES_PATTERNS = [
    re.compile(r"^\d+\s*$"),                # 纯页码
    re.compile(r"^Page\s+\d+", re.I),       # Page X
    re.compile(r"^-\s*\d+\s*-$"),           # - 1 -
    re.compile(r"^www\.\S+\.\w+", re.I),   # 网址
    re.compile(r"^版权所有"),                  # 版权声明
]

# 单元名称映射（关键词 → 英文名称）
_UNIT_KEYWORDS = {
    "start": "Startup", "welcome": "Welcome", "hello": "Hello",
    "recycle": "Recycle", "review": "Review", "proj": "Project",
}

# 图片输出目录（相对 uploads/textbook/pages/）
_PAGES_IMAGE_DIR = "pages"


class TextbookPDFService:
    """教材 PDF 解析导入服务"""

    @staticmethod
    async def parse_and_import(
        db: AsyncSession,
        upload_id: int,
        file_path: str,
        version: str,
        grade: str,
        semester: str,
    ) -> dict:
        """解析 PDF 并将内容导入 textbook_page 表

        返回:
            {"success": bool, "units": int, "pages": int, "error": str}
        """
        upload = await db.get(TextbookUpload, upload_id)
        if not upload:
            return {"success": False, "error": "上传记录不存在"}

        if not os.path.exists(file_path):
            await _mark_upload_error(db, upload, "文件不存在")
            return {"success": False, "error": "文件不存在"}

        try:
            import pypdf
        except ImportError:
            await _mark_upload_error(db, upload, "pypdf 未安装，无法解析 PDF")
            return {"success": False, "error": "pypdf 未安装"}

        # 标记解析中
        upload.parse_status = 1
        await db.flush()

        # 准备图片输出目录
        upload_dir = os.path.dirname(os.path.dirname(file_path))  # uploads/textbook
        image_output_dir = os.path.join(upload_dir, _PAGES_IMAGE_DIR, str(upload_id))
        os.makedirs(image_output_dir, exist_ok=True)
        image_rel_dir = f"/uploads/textbook/{_PAGES_IMAGE_DIR}/{upload_id}"  # 服务器相对路径

        try:
            reader = pypdf.PdfReader(file_path)
            total = len(reader.pages)
            upload.total_pages = total
            await db.flush()

            if total == 0:
                await _mark_upload_error(db, upload, "PDF 为空")
                return {"success": False, "error": "PDF 为空"}

            # Step 1: 逐页提取文本，检测单元边界
            pages_text = []       # [(page_number, text, detected_unit_str), ...]
            unit_boundaries = {}  # {page_number: unit_number_str}

            for i, page in enumerate(reader.pages):
                pn = i + 1  # 1-based page number
                raw = page.extract_text() or ""
                cleaned = _clean_page_text(raw)

                # 如果 pypdf 提取文本为空或太短，尝试 OCR
                if len(cleaned.strip()) < 20:
                    ocr_text = _ocr_page(file_path, pn)
                    if ocr_text:
                        cleaned = ocr_text

                # 检测单元标题
                unit_match = _detect_unit_title(cleaned)
                if unit_match:
                    unit_boundaries[pn] = unit_match

                pages_text.append((pn, cleaned, unit_match))

            # Step 2: 构建单元结构
            unit_pages = _build_unit_structure(pages_text, unit_boundaries)

            # Step 3: 创建 TextbookUnit 和 TextbookPage 记录
            created_units = 0
            created_pages = 0

            for unit_info in unit_pages:
                unit_number = unit_info["unit_number"]
                unit_title = unit_info["title"]
                pages_in_unit = unit_info["pages"]

                # 检查是否已存在该单元（防止重复导入）
                existing = await db.execute(
                    select(TextbookUnit).where(and_(
                        TextbookUnit.textbook_version == version,
                        TextbookUnit.grade == grade,
                        TextbookUnit.semester == semester,
                        TextbookUnit.unit_number == unit_number,
                    ))
                )
                existing_unit = existing.scalar_one_or_none()

                if existing_unit:
                    unit_id = existing_unit.id
                    # 更新已有单元的起止页码
                    existing_unit.page_start = min(existing_unit.page_start or 9999, pages_in_unit[0][0])
                    existing_unit.page_end = max(existing_unit.page_end or 0, pages_in_unit[-1][0])
                    if unit_title and not existing_unit.title:
                        existing_unit.title = unit_title
                else:
                    new_unit = TextbookUnit(
                        textbook_version=version,
                        grade=grade,
                        semester=semester,
                        unit_number=unit_number,
                        title=unit_title or unit_number,
                        page_start=pages_in_unit[0][0],
                        page_end=pages_in_unit[-1][0],
                        sort_order=created_units,
                    )
                    db.add(new_unit)
                    await db.flush()
                    await db.refresh(new_unit)
                    unit_id = new_unit.id
                    created_units += 1

                # 创建页面记录
                for pn, text, _ in pages_in_unit:
                    # 检查页面是否已存在（去重）
                    existing_page = await db.execute(
                        select(TextbookPage).where(and_(
                            TextbookPage.textbook_version == version,
                            TextbookPage.grade == grade,
                            TextbookPage.semester == semester,
                            TextbookPage.unit_number == unit_number,
                            TextbookPage.page_number == pn,
                        ))
                    )
                    if existing_page.scalar_one_or_none():
                        continue

                    # 渲染该页图片并保存
                    page_image_path = _render_page_image(file_path, pn, image_output_dir)
                    image_url = ""
                    if page_image_path:
                        # 图片路径: uploads/textbook/pages/{upload_id}/{pn}.png
                        # URL 路径: /uploads/textbook/pages/{upload_id}/{pn}.png
                        image_url = f"{image_rel_dir}/{pn}.png"

                    new_page = TextbookPage(
                        unit_id=unit_id,
                        textbook_version=version,
                        grade=grade,
                        semester=semester,
                        unit_number=unit_number,
                        page_number=pn,
                        text_content=text[:10000],  # 截断过长文本
                        image_url=image_url,
                        is_active=1,
                    )
                    db.add(new_page)
                    created_pages += 1

                await db.flush()

            # 更新上传状态
            upload.parse_status = 2
            upload.parsed_pages = created_pages
            await db.flush()

            logger.info(
                f"PDF 解析完成 | upload_id={upload_id} "
                f"total_pages={total} created_units={created_units} created_pages={created_pages}"
            )

            return {
                "success": True,
                "total_pages": total,
                "created_units": created_units,
                "created_pages": created_pages,
            }

        except Exception as e:
            logger.error(f"PDF 解析失败 upload_id={upload_id}: {e}", exc_info=True)
            await _mark_upload_error(db, upload, f"解析异常: {str(e)}")
            return {"success": False, "error": f"解析异常: {str(e)}"}

    @staticmethod
    async def delete_pages_for_upload(
        db: AsyncSession,
        upload_id: int,
        version: str,
        grade: str,
        semester: str,
    ):
        """删除某次上传关联的所有页面和单元（如果单元不再有页面则删除单元）"""
        # 查找该版本/年级/学期下所有页面
        result = await db.execute(
            select(TextbookPage).where(and_(
                TextbookPage.textbook_version == version,
                TextbookPage.grade == grade,
                TextbookPage.semester == semester,
            ))
        )
        pages = result.scalars().all()
        for p in pages:
            await db.delete(p)

        # 删除已无页面的单元
        unit_result = await db.execute(
            select(TextbookUnit).where(and_(
                TextbookUnit.textbook_version == version,
                TextbookUnit.grade == grade,
                TextbookUnit.semester == semester,
            ))
        )
        for unit in unit_result.scalars().all():
            # 检查单元下是否还有页面
            check = await db.execute(
                select(func.count(TextbookPage.id)).where(
                    TextbookPage.unit_id == unit.id
                )
            )
            count = check.scalar() or 0
            if count == 0:
                await db.delete(unit)

        logger.info(
            f"已删除 upload_id={upload_id} 关联的页面和空单元 | version={version} grade={grade} semester={semester}"
        )


# ==================== 内部工具 ====================


def _detect_unit_title(text: str) -> Optional[str]:
    """检测页面文本中是否包含单元标题，返回单元号字符串

    如 "Unit 1" → "Unit1", "第一单元" → "第一单元", 检测不到 → None
    """
    if not text:
        return None

    # 取前 200 字符检测
    head = text[:200].strip()

    for pattern in _UNIT_PATTERNS:
        m = pattern.search(head)
        if m:
            matched = m.group(0).strip()
            # 标准化: 去掉多余空格，统一为数字
            normalized = re.sub(r"\s+", "", matched)
            return normalized

    return None


def _clean_page_text(text: str) -> str:
    """清理单页文本：过滤页眉页脚噪声，合并断裂行"""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过页眉页脚模式
        if any(p.match(stripped) for p in _SKIP_LINES_PATTERNS):
            continue
        cleaned.append(stripped)

    return "\n".join(cleaned)


def _build_unit_structure(
    pages_text: list,
    unit_boundaries: dict,
) -> list[dict]:
    """根据检测到的单元边界，构建单元→页面结构

    返回:
        [
            {
                "unit_number": "Unit1" 或 "PreUnit",
                "title": "My school" 或 "预备",
                "pages": [(1, text1, None), (2, text2, "Unit1"), ...]
            },
            ...
        ]
    """
    if not unit_boundaries:
        # 未检测到单元边界 → 整本书作为一个单元
        unit_number = "FullBook"
        return [{
            "unit_number": unit_number,
            "title": unit_number,
            "pages": [(pn, text, None) for pn, text, _ in pages_text],
        }]

    # 按页码排序的边界
    sorted_boundaries = sorted(unit_boundaries.items())  # [(page, unit_str), ...]

    units = []
    # 第一个单元之前的页面归为 "预备/Starter"
    first_unit_page = sorted_boundaries[0][0]
    if first_unit_page > 1:
        starter_pages = [(pn, text, None) for pn, text, _ in pages_text if pn < first_unit_page]
        if starter_pages:
            units.append({
                "unit_number": "Starter",
                "title": "预备单元",
                "pages": starter_pages,
            })

    # 遍历边界，组织每个单元的页面
    for idx, (page_num, unit_str) in enumerate(sorted_boundaries):
        # 该单元包含的所有页面
        next_boundary = sorted_boundaries[idx + 1][0] if idx + 1 < len(sorted_boundaries) else 99999

        unit_pages = []
        for pn, text, detected in pages_text:
            if pn == page_num:
                # 单元标题页也属于该单元（去掉标题行？保留全文）
                unit_pages.append((pn, text, detected))
            elif page_num < pn < next_boundary:
                unit_pages.append((pn, text, detected))

        # 提取单元标题：取单元标题页的第一段有意义文本中的标题
        title_text = _extract_unit_title_text(unit_str, unit_pages[0][1]) if unit_pages else unit_str

        units.append({
            "unit_number": unit_str,
            "title": title_text,
            "pages": unit_pages,
        })

    return units


def _extract_unit_title_text(unit_number: str, first_page_text: str) -> str:
    """从单元首页文本中提取单元名称（如 'My school'）"""
    if not first_page_text:
        return unit_number

    lines = first_page_text.split("\n")
    found_unit_line = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 找到包含 unit_number 的行
        if unit_number.lower().replace(" ", "") in stripped.lower().replace(" ", ""):
            found_unit_line = True
            continue
        if found_unit_line and stripped:
            # 返回单元号后的第一行非空文本作为标题
            # 排除纯数字、网址等
            if re.match(r"^[\d\s\-_/\\]+$", stripped):
                continue
            if len(stripped) > 50:
                stripped = stripped[:50]
            return stripped

    # fallback: 取第一个较长的非编号行
    for line in lines[:10]:
        s = line.strip()
        if s and len(s) > 3 and not re.match(r"^[\d\s\-_/\\]+$", s):
            return s[:50]

    return unit_number


def _render_page_image(pdf_path: str, page_number: int, output_dir: str) -> Optional[str]:
    """使用 PyMuPDF 渲染 PDF 页为图片并保存

    返回:
        图片路径（成功）或 None（失败）
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]  # 0-based index

        # 渲染为 2x 分辨率图片（清晰度较好）
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # 保存为 PNG
        image_path = os.path.join(output_dir, f"{page_number}.png")
        pix.save(image_path)
        doc.close()

        logger.debug(f"页面图片已渲染: page={page_number} -> {image_path}")
        return image_path
    except ImportError:
        logger.warning("PyMuPDF (fitz) 未安装，无法渲染页面图片")
        return None
    except Exception as e:
        logger.error(f"渲染页面图片失败 page={page_number}: {e}")
        return None


def _ocr_page(pdf_path: str, page_number: int) -> Optional[str]:
    """使用 PyMuPDF 渲染页面 + pytesseract OCR 提取文本

    返回:
        OCR 文本（成功）或 None（失败）
    """
    try:
        import fitz
        import pytesseract
    except ImportError:
        logger.debug("pytesseract 或 PyMuPDF 未安装，跳过 OCR")
        return None

    try:
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]

        # 渲染为图片
        zoom = 2.0  # 2x 分辨率提高识别率
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # 转为 PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        # OCR 识别（中文 + 英文）
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        text = text.strip()

        if text:
            logger.info(f"OCR 成功 page={page_number}, 字符数={len(text)}")
            return text

        logger.debug(f"OCR 未识别到文本 page={page_number}")
        return None
    except Exception as e:
        logger.error(f"OCR 失败 page={page_number}: {e}")
        return None


async def _mark_upload_error(db: AsyncSession, upload: TextbookUpload, error: str):
    """标记上传记录为失败状态"""
    upload.parse_status = 3
    upload.error_msg = error[:500]
    await db.flush()
