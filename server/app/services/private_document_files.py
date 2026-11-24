"""Content validation shared by private exam and chat uploads."""
import re
from io import BytesIO
from pathlib import PurePath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


MAX_FILE_BYTES = 20 * 1024 * 1024
FORMATS = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".webp": ("image", "image/webp"),
}


class PrivateFileError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def validate_private_file(filename: str, data: bytes, *, allow_text: bool = False) -> str:
    if not filename or len(filename) > 256 or re.search(r"[/\\\x00-\x1f\x7f]", filename):
        raise PrivateFileError(422, "文件名称无效")
    ext = PurePath(filename).suffix.lower()
    formats = "PDF、DOCX、JPEG、PNG 和 WebP"
    if ext not in FORMATS and not (allow_text and ext == ".txt"):
        raise PrivateFileError(415, f"仅支持 {formats}" + (" 和 TXT" if allow_text else ""))
    if not data:
        raise PrivateFileError(422, "文件为空")
    if len(data) > MAX_FILE_BYTES:
        raise PrivateFileError(413, "单个文件最多 20 MB")

    if ext == ".txt":
        try:
            decoded = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise PrivateFileError(415, "TXT 文件须采用 UTF-8 编码") from error
        if "\x00" in decoded:
            raise PrivateFileError(415, "无法读取 TXT 文件")
    elif ext == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted or not len(pdf.pages):
                raise PrivateFileError(415, "PDF 加密或没有可读页面")
            if allow_text and len(pdf.pages) > 50:
                raise PrivateFileError(413, "问答附件单个 PDF 最多 50 页")
        except (PdfReadError, OSError, ValueError, RecursionError, EOFError, TypeError) as error:
            raise PrivateFileError(415, "无法读取 PDF 文件") from error
    elif ext == ".docx":
        try:
            with ZipFile(BytesIO(data)) as package:
                entries = package.infolist()
                if len(entries) > 1024 or sum(entry.file_size for entry in entries) > 60 * 1024 * 1024:
                    raise PrivateFileError(415, "DOCX 解压后的文件过大")
                declarations = package.getinfo("[Content_Types].xml")
                document = package.getinfo("word/document.xml")
                if declarations.file_size > 256 * 1024 or document.file_size > 10 * 1024 * 1024:
                    raise PrivateFileError(415, "DOCX 内部文件过大")
                contents = ElementTree.fromstring(package.read(declarations))
                media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
                if not any(item.get("PartName") == "/word/document.xml" and item.get("ContentType") == media
                           for item in contents):
                    raise PrivateFileError(415, "无法读取 DOCX 文档")
                body = ElementTree.fromstring(package.read(document))
                if body.tag.rsplit("}", 1)[-1] != "document":
                    raise PrivateFileError(415, "无法读取 DOCX 文档")
        except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, NotImplementedError) as error:
            raise PrivateFileError(415, "无法读取 DOCX 文档") from error
    else:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(BytesIO(data)) as image:
                expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[ext]
                if image.format != expected or image.width * image.height > 40_000_000:
                    raise PrivateFileError(415, "图片格式不匹配或像素过大")
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise PrivateFileError(415, "无法读取图片") from error
    return ext
