"""
PDF 导出服务 — 将 Markdown 总结报告渲染为 PDF
优先使用 weasyprint（系统依赖），回退到 fpdf2 + 系统/下载中文字体
"""
import os
import re
import platform
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).parent.parent.parent / "fonts"
FONT_PATH = FONTS_DIR / "NotoSansSC-Regular.ttf"
FONT_BOLD_PATH = FONTS_DIR / "NotoSansSC-Bold.ttf"

# Noto Sans SC 字体的多个下载源（按优先级排列）
# GitHub 上 noto-cjk 仓库已迁移重组，改用 google/fonts 官方仓库
_FONT_URLS = [
    # 1. Google Fonts 官方仓库（静态版，最稳定）
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/static/NotoSansSC-Regular.ttf",
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/static/NotoSansSC-Bold.ttf",
    # 2. noto-cjk 仓库（旧路径，可能已失效但保留作为备选）
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf",
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Bold.otf",
]


def _ensure_font() -> Optional[str]:
    """确保中文字体可用，优先使用已下载或新下载的 Noto Sans SC（TTF 格式），回退到系统字体"""
    # 已下载过则直接返回
    if FONT_PATH.exists():
        logger.debug("使用已下载的 Noto Sans SC 字体: %s", FONT_PATH)
        return str(FONT_PATH)

    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    # 尝试从多个源下载字体
    import ssl

    def _try_download(url: str, target_path: Path, timeout: int = 60) -> bool:
        """尝试下载字体文件，返回是否成功"""
        try:
            import httpx
            r = httpx.get(url, follow_redirects=True, timeout=timeout)
            r.raise_for_status()
            target_path.write_bytes(r.content)
            logger.info("字体下载成功: %s → %s", url.rsplit("/", 1)[-1], target_path)
            return True
        except Exception as e:
            logger.debug("下载 %s 失败: %s", url, e)
            return False

    def _try_download_insecure(url: str, target_path: Path, timeout: int = 60) -> bool:
        """跳过 SSL 验证下载"""
        try:
            import httpx
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with httpx.Client(verify=ctx) as client:
                r = client.get(url, follow_redirects=True, timeout=timeout)
                r.raise_for_status()
                target_path.write_bytes(r.content)
                logger.info("字体下载成功 (跳过SSL): %s → %s", url.rsplit("/", 1)[-1], target_path)
                return True
        except Exception as e:
            logger.debug("跳过SSL下载 %s 失败: %s", url, e)
            return False

    logger.info("正在尝试下载中文字体 Noto Sans SC（约 4MB，首次使用）...")

    # 分离常规体和粗体的 URL
    regular_urls = [url for url in _FONT_URLS if "Regular" in url or "SC-Regular" in url]
    bold_urls = [url for url in _FONT_URLS if "Bold" in url or "SC-Bold" in url]

    # 依次尝试每个 URL，先标准 SSL 再跳过 SSL
    regular_success = False
    for url in regular_urls:
        if _try_download(url, FONT_PATH):
            regular_success = True
            break
        if _try_download_insecure(url, FONT_PATH):
            regular_success = True
            break

    if regular_success:
        # 尝试下载粗体（非必需）
        for url in bold_urls:
            if _try_download(url, FONT_BOLD_PATH):
                break
            if _try_download_insecure(url, FONT_BOLD_PATH):
                break
        return str(FONT_PATH)

    logger.warning("所有字体下载源均失败，使用系统字体兜底")

    # 回退到系统 CJK 字体
    system_font = _find_system_cjk_font()
    if system_font:
        logger.info("使用系统字体: %s", system_font)
        return system_font

    logger.warning("未找到任何中文字体，PDF 中的中文可能无法显示")
    return None


def _find_system_cjk_font() -> Optional[str]:
    """查找系统 CJK 字体"""
    system = platform.system()
    candidates = []

    if system == "Windows":
        win_dir = os.environ.get("WINDIR", "C:\\Windows")
        candidates = [
            # TTF 格式优先（fpdf2 兼容性最好）
            os.path.join(win_dir, "Fonts", "msyh.ttf"),           # Microsoft YaHei（首选）
            os.path.join(win_dir, "Fonts", "msyhbd.ttf"),         # Microsoft YaHei Bold
            os.path.join(win_dir, "Fonts", "msyhsl.ttf"),         # Microsoft YaHei UI
            os.path.join(win_dir, "Fonts", "deng.ttf"),           # DengXian（等线）
            os.path.join(win_dir, "Fonts", "yahei.ttf"),          # YaHei 别名
            os.path.join(win_dir, "Fonts", "simsun.ttf"),         # SimSun TTF（优先于 TTC）
            os.path.join(win_dir, "Fonts", "SIMLI.TTF"),          # LiSu（最后备选 TTF）
            # TTC 格式备选（部分 fpdf2 版本 subsetting 可能不完整）
            os.path.join(win_dir, "Fonts", "simsun.ttc"),         # SimSun (TTC)
        ]
    elif system == "Linux":
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
        ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ]

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def generate_report_pdf(title: str, markdown_content: str) -> bytes:
    """
    将 Markdown 报告内容生成为 PDF 字节流。

    优先使用 weasyprint（质量最好），回退到 fpdf2 手动排版。
    """
    try:
        return _generate_with_weasyprint(title, markdown_content)
    except ImportError:
        logger.info("weasyprint 不可用，使用 fpdf2 回退方案")
        return _generate_with_fpdf2_safe(title, markdown_content)
    except Exception as e:
        logger.warning("weasyprint 生成失败 (%s)，使用 fpdf2 回退方案", e)
        return _generate_with_fpdf2_safe(title, markdown_content)


def _generate_with_fpdf2_safe(title: str, md_content: str) -> bytes:
    """调用 _generate_with_fpdf2 并打印完整 traceback"""
    import traceback
    try:
        return _generate_with_fpdf2(title, md_content)
    except Exception:
        logger.error("fpdf2 生成 PDF 失败，完整 traceback:\n%s", traceback.format_exc())
        raise


def _generate_with_weasyprint(title: str, md_content: str) -> bytes:
    """使用 weasyprint 生成 PDF（支持完整 CSS + 中文 + 表格）"""
    import markdown as md_lib
    from weasyprint import HTML

    # Markdown → HTML（启用表格扩展）
    html_body = md_lib.markdown(
        md_content,
        extensions=["extra", "tables", "fenced_code"],
    )

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 2cm 2.5cm;
    @bottom-center {{
      content: counter(page) " / " counter(pages);
      font-size: 10px; color: #999;
    }}
  }}
  body {{
    font-family: "Noto Sans SC", "Microsoft YaHei", "PingFang SC", "WenQuanYi Micro Hei", sans-serif;
    font-size: 12pt; line-height: 1.8; color: #333;
  }}
  h1 {{ font-size: 20pt; font-weight: 700; color: #1F2937; margin: 24pt 0 12pt; }}
  h2 {{ font-size: 16pt; font-weight: 700; color: #1F2937; margin: 20pt 0 10pt; border-bottom: 1px solid #E5E7EB; padding-bottom: 4pt; }}
  h3 {{ font-size: 14pt; font-weight: 700; color: #1F2937; margin: 16pt 0 8pt; }}
  p  {{ margin: 6pt 0; }}
  ul, ol {{ padding-left: 24pt; }}
  li {{ margin: 3pt 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10pt 0; font-size: 11pt; }}
  th, td {{ border: 1px solid #D1D5DB; padding: 6pt 10pt; text-align: left; }}
  th {{ background: #F3F4F6; font-weight: 700; }}
  blockquote {{ border-left: 3px solid #5B9E6F; padding: 8pt 12pt; margin: 8pt 0; color: #4B5563; background: #F9FAFB; }}
  pre {{ background: #F3F4F6; padding: 12pt; border-radius: 4pt; font-size: 10pt; overflow-x: auto; }}
  code {{ background: #F3F4F6; padding: 1pt 4pt; border-radius: 3pt; font-size: 10pt; color: #D63384; }}
  strong {{ font-weight: 700; }}
  em {{ font-style: italic; }}
  hr {{ border: none; border-top: 1px solid #E5E7EB; margin: 16pt 0; }}
  .report-title {{
    text-align: center; font-size: 22pt; font-weight: 700; color: #1F2937;
    margin: 30pt 0 6pt; letter-spacing: 1pt;
  }}
  .report-meta {{
    text-align: center; font-size: 10pt; color: #9CA3AF; margin-bottom: 24pt;
  }}
  .watermark {{
    position: fixed; bottom: 20pt; right: 30pt;
    font-size: 10pt; color: #E5E7EB;
  }}
</style>
</head>
<body>
  <div class="report-title">{_escape_html(title)}</div>
  <div class="report-meta">小e英语学习助手 · 错题总结报告</div>
  {html_body}
  <div class="watermark">小e英语</div>
</body>
</html>"""

    pdf_data = HTML(string=full_html).write_pdf()
    return pdf_data


def _generate_with_fpdf2(title: str, md_content: str) -> bytes:
    """使用 fpdf2 手动排版 PDF（稳健版，多层 try/except 防护）"""
    from fpdf import FPDF

    # 获取字体
    font_path = _ensure_font()
    logger.info("fpdf2 将使用字体: %s", font_path)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # 注册字体（包裹 try/except，避免不兼容字体导致崩溃）
    font_registered = False
    if font_path:
        try:
            pdf.add_font("CJK", "", font_path, uni=True)
            font_registered = True
            logger.info("fpdf2 注册常规字体成功")
        except Exception as e:
            logger.warning("注册字体 %s 失败: %s，尝试降级", font_path, e)
            try:
                # 有些字体不支持 uni=True，尝试不带 uni
                pdf.add_font("CJK", "", font_path)
                font_registered = True
                logger.info("fpdf2 注册字体成功（非 uni 模式）")
            except Exception as e2:
                logger.warning("非 uni 模式也失败: %s", e2)

    if font_registered:
        # 注册粗体（如果可用，否则用常规字体）
        try:
            if FONT_BOLD_PATH.exists():
                pdf.add_font("CJK", "B", str(FONT_BOLD_PATH), uni=True)
            else:
                pdf.add_font("CJK", "B", font_path, uni=True)
        except Exception:
            try:
                pdf.add_font("CJK", "B", font_path, uni=False)
            except Exception:
                # 粗体注册失败，后续 set_font("CJK", "B") 将使用常规字体（通过 style mapping）
                pass

    # 安全设置字体的辅助函数
    def _safe_set_font(family, style, size):
        try:
            pdf.set_font(family, style, size)
            return True
        except Exception:
            pdf.set_font("Helvetica", "", size)
            return False

    # 安全 multi_cell（处理字体不支持的字符）
    def _safe_multi_cell(w, h, text, **kwargs):
        try:
            pdf.multi_cell(w, h, text, **kwargs)
        except Exception:
            # 逐字符尝试，跳过不支持的字符
            safe_text = ""
            for ch in text:
                try:
                    pdf.multi_cell(w, h, ch, **kwargs)
                    safe_text += ch
                except Exception:
                    safe_text += "?"
            if safe_text.strip():
                try:
                    pdf.multi_cell(w, h, safe_text, **kwargs)
                except Exception:
                    pdf.multi_cell(w, h, "[内容包含不兼容字符]", **kwargs)

    # ====== 封面 ======
    pdf.add_page()
    pdf.ln(60)
    _safe_set_font("CJK", "B", 20) if font_registered else pdf.set_font("Helvetica", "B", 20)
    _safe_multi_cell(0, 12, title, align="C")
    pdf.ln(6)
    _safe_set_font("CJK", "", 10) if font_registered else pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(156, 163, 175)
    _safe_multi_cell(0, 8, "小e英语学习助手 · 错题总结报告", align="C")
    pdf.set_text_color(51, 51, 51)

    # ====== 正文 ======
    pdf.add_page()
    lines = md_content.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pdf.ln(4)
            continue

        try:
            # H3 标题
            if stripped.startswith("### "):
                text = re.sub(r"^###\s+", "", stripped)
                text = re.sub(r"\s*#+\s*$", "", text)
                _safe_set_font("CJK", "B", 13) if font_registered else pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(31, 41, 55)
                _safe_multi_cell(0, 8, text)
                pdf.ln(2)

            # H2 标题
            elif stripped.startswith("## "):
                text = re.sub(r"^##\s+", "", stripped)
                text = re.sub(r"\s*#+\s*$", "", text)
                _safe_set_font("CJK", "B", 15) if font_registered else pdf.set_font("Helvetica", "B", 15)
                pdf.set_text_color(31, 41, 55)
                _safe_multi_cell(0, 9, text)
                pdf.ln(3)

            # H1 标题
            elif stripped.startswith("# "):
                text = re.sub(r"^#\s+", "", stripped)
                text = re.sub(r"\s*#+\s*$", "", text)
                _safe_set_font("CJK", "B", 17) if font_registered else pdf.set_font("Helvetica", "B", 17)
                pdf.set_text_color(31, 41, 55)
                _safe_multi_cell(0, 10, text)
                pdf.ln(4)

            # 分隔线
            elif re.match(r"^---+$", stripped):
                pdf.ln(2)
                x = pdf.get_x()
                y = pdf.get_y()
                pdf.set_draw_color(229, 231, 235)
                pdf.line(x, y, x + pdf.w - 2 * pdf.l_margin, y)
                pdf.ln(6)

            # 无序列表
            elif re.match(r"^[-*]\s", stripped):
                text = re.sub(r"^[-*]\s+", "", stripped)
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
                text = re.sub(r"\*(.+?)\*", r"\1", text)
                _safe_set_font("CJK", "", 11) if font_registered else pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(8)
                _safe_multi_cell(0, 7, "• " + text)

            # 有序列表
            elif re.match(r"^\d+\.\s", stripped):
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                text = re.sub(r"\*(.+?)\*", r"\1", text)
                _safe_set_font("CJK", "", 11) if font_registered else pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(8)
                _safe_multi_cell(0, 7, text)

            # 引用块
            elif stripped.startswith("> "):
                text = re.sub(r"^>\s+", "", stripped)
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
                _safe_set_font("CJK", "", 10) if font_registered else pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(75, 85, 99)
                x = pdf.get_x()
                y = pdf.get_y()
                pdf.cell(3)
                try:
                    pdf.set_fill_color(91, 158, 111)
                    pdf.rect(x + 2, y, 2, 12, "F")
                except Exception:
                    pass
                pdf.set_x(x + 8)
                _safe_multi_cell(0, 6, text)

            # 普通段落
            else:
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                text = re.sub(r"\*(.+?)\*", r"\1", text)
                text = re.sub(r"`(.+?)`", r"\1", text)
                _safe_set_font("CJK", "", 11) if font_registered else pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(55, 65, 81)
                _safe_multi_cell(0, 7, text)

        except Exception as line_err:
            logger.warning("渲染行失败: %s ... 错误: %s", stripped[:60], line_err)
            _safe_set_font("Helvetica", "", 10)
            pdf.set_text_color(150, 150, 150)
            pdf.multi_cell(0, 6, "[渲染异常行]")
            continue

    # 水印
    pdf.ln(10)
    _safe_set_font("CJK", "", 8) if font_registered else pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(200, 200, 200)
    try:
        pdf.cell(0, 6, "小e英语", align="R")
    except Exception:
        pass

    try:
        return bytes(pdf.output())
    except Exception as e:
        logger.error("fpdf2 output() 失败: %s", e)
        raise


def _escape_html(text: str) -> str:
    """HTML 转义"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))
