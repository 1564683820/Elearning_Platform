"""使用 MinerU v4 精准解析 API 将 PDF 转为 Markdown

流程:
  1. 调用 /api/v4/file-urls/batch 获取 MinerU 签名上传 URL
  2. PUT 上传本地 PDF 文件到签名 URL（无需外部 COS）
  3. 轮询 /api/v4/extract-results/batch/{batch_id} 直到完成
  4. 下载 full_zip_url 结果包，提取 Markdown 内容
  5. 返回 Markdown 文本

如果 MinerU 不可用或出错，返回空字符串以便上层 fallback。
"""
import os
import io
import json
import time
import asyncio
import logging
import zipfile
import re
from typing import Optional, Callable, Awaitable
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 轮询参数
POLL_INTERVAL = 3    # 每次轮询间隔（秒）
MAX_POLL_TIME = 300  # 最长等待时间（秒）


async def pdf_to_markdown(
    file_path: str,
    filename: str,
    progress_cb: Optional[Callable[[int, str], Awaitable[None]]] = None,
) -> str:
    """使用 MinerU v4 精准解析 API 将 PDF 转为 Markdown（无需 COS）

    参数:
        file_path: 本地 PDF 文件路径
        filename: 原始文件名（仅用于显示）
        progress_cb: 可选进度回调，接收 (percent: 0-100, message)

    返回:
        str: Markdown 文本。失败时返回空字符串。
    """
    api_key = getattr(settings, "MINERU_API_KEY", "") or ""
    if not api_key:
        logger.warning("MINERU_API_KEY 未配置，跳过 MinerU 转换")
        return ""

    api_base = getattr(settings, "MINERU_API_BASE", "https://mineru.net/api/v4")
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # 进度辅助
    async def _prog(pct: int, msg: str):
        if progress_cb:
            try:
                await progress_cb(pct, msg)
            except Exception:
                pass

    try:
        # === Step 1: 获取 MinerU 签名上传 URL ===
        logger.info("MinerU: 申请签名上传 URL...")
        await _prog(5, "正在连接 MinerU 解析服务...")
        file_urls_resp = await _post_json(
            f"{api_base}/file-urls/batch",
            {**headers, "Content-Type": "application/json"},
            {
                "enable_formula": True,
                "enable_table": True,
                "language": "ch",
                "files": [
                    {
                        "name": os.path.basename(filename),
                        "data_id": "doc",
                        "is_ocr": True,
                    }
                ],
                "model_version": "pipeline",
            },
        )
        if file_urls_resp.get("code") != 0:
            logger.error(f"MinerU 获取上传 URL 失败: {file_urls_resp}")
            return ""

        batch_id = file_urls_resp.get("data", {}).get("batch_id", "")
        file_urls = file_urls_resp.get("data", {}).get("file_urls", [])
        if not batch_id or not file_urls:
            logger.error(f"MinerU 返回中没有 batch_id 或 file_urls: {file_urls_resp}")
            return ""

        signed_upload_url = file_urls[0]
        logger.info(f"MinerU: 获取到签名上传 URL, batch_id={batch_id}")

        # === Step 2: PUT 上传文件到签名 URL ===
        await _prog(10, "正在上传 PDF 到 MinerU...")
        logger.info("MinerU: 上传文件...")
        with open(file_path, "rb") as f:
            file_data = f.read()

        async with httpx.AsyncClient(timeout=120) as client:
            upload_resp = await client.put(signed_upload_url, content=file_data)
            upload_resp.raise_for_status()
        logger.info(f"MinerU: 文件上传完成 ({len(file_data)} bytes)，解析已自动开始")
        await _prog(20, "上传完成，等待 MinerU 解析...")

        # === Step 3: 轮询批量结果（带进度）===
        poll_url = f"{api_base}/extract-results/batch/{batch_id}"
        last_progress_pct = 20  # 初始值
        elapsed = 0
        while elapsed < MAX_POLL_TIME:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            status_resp = await _get_json(poll_url, headers)
            if status_resp.get("code") != 0:
                logger.warning(f"MinerU 轮询返回异常: {status_resp}")
                continue

            data = status_resp.get("data", {})
            extract_results = data.get("extract_result", [])

            if not extract_results:
                logger.debug("MinerU: 尚无结果，继续轮询...")
                continue

            result = extract_results[0]
            state = result.get("state", "")

            if state == "done":
                logger.info(f"MinerU 任务完成: batch_id={batch_id}")
                full_zip_url = result.get("full_zip_url", "")
                if not full_zip_url:
                    logger.error(f"MinerU 结果中没有 full_zip_url: {result}")
                    return ""

                # 下载结果 Zip 包
                await _prog(90, "正在下载 MinerU 解析结果...")
                logger.info(f"MinerU 下载结果: {full_zip_url}")
                try:
                    zip_bytes = await _get_binary(full_zip_url)
                except Exception as e:
                    logger.error(f"下载 MinerU 结果失败: {e}。"
                                 f"可手动在浏览器打开链接下载: {full_zip_url}")
                    return ""
                await _prog(95, "正在提取 Markdown 内容...")
                md_text = _extract_md_from_zip(zip_bytes)
                if md_text:
                    return _clean_markdown(md_text)
                logger.warning(f"MinerU Zip 提取为空: {full_zip_url}")
                return ""

            elif state in ("failed", "error", "canceled"):
                err_msg = result.get("err_msg", "未知错误")
                logger.error(f"MinerU 任务失败: {err_msg}")
                return ""

            # 仍在处理中 — 基于 MinerU 的提取进度计算百分比
            progress = result.get("extract_progress", {})
            if progress:
                extracted = progress.get("extracted_pages", 0)
                total = progress.get("total_pages", 0)
                if total > 0:
                    parse_pct = min(int(extracted / total * 60), 59)
                    report_pct = 20 + parse_pct
                    if report_pct > last_progress_pct:
                        last_progress_pct = report_pct
                        await _prog(report_pct, f"MinerU 解析中: {extracted}/{total} 页")
                logger.debug(f"MinerU 处理中: {extracted}/{total} 页")
            else:
                logger.debug(f"MinerU 处理中: state={state}")

        # 超时
        logger.error(f"MinerU 任务超时: batch_id={batch_id}")
        return ""

    except httpx.HTTPStatusError as e:
        logger.error(f"MinerU HTTP 错误: {e.response.status_code} {e.response.text[:500]}")
        return ""
    except httpx.TimeoutException as e:
        logger.error(f"MinerU 请求超时: {e}")
        return ""
    except ImportError as e:
        logger.error(f"MinerU 依赖缺失: {e}")
        return ""
    except Exception as e:
        logger.error(f"MinerU 转换异常: {e}", exc_info=True)
        return ""


def _resolve_proxy() -> Optional[str]:
    """解析代理配置，优先级: MINERU_PROXY (.env) > HTTPS_PROXY > HTTP_PROXY > ALL_PROXY"""
    return (
        getattr(settings, "MINERU_PROXY", None)
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("ALL_PROXY")
        or None
    )


def _make_client(timeout: int = 60, follow_redirects: bool = False) -> httpx.AsyncClient:
    """创建 httpx 异步客户端，自动加载代理配置"""
    proxy = _resolve_proxy()
    client_kw: dict = {"timeout": timeout}
    if follow_redirects:
        client_kw["follow_redirects"] = True
    if proxy:
        client_kw["proxy"] = proxy
    return httpx.AsyncClient(**client_kw)


async def _request_with_fallback(
    method: str,
    url: str,
    headers: dict,
    json_data: dict = None,
    timeout: int = 60,
    follow_redirects: bool = False,
    raw_binary: bool = False,
):
    """执行 HTTP 请求，代理失败时自动降级为直连

    参数:
        method: HTTP 方法（GET/POST）
        url: 请求 URL
        headers: 请求头
        json_data: POST 请求的 JSON body（GET 时忽略）
        timeout: 超时秒数
        follow_redirects: 是否跟随重定向
        raw_binary: 是否返回原始二进制（否则解析 JSON）
    """
    logger.debug(f"MinerU {method} {url}")
    proxy = _resolve_proxy()
    try:
        client_kw = {"timeout": timeout}
        if follow_redirects:
            client_kw["follow_redirects"] = True
        if proxy:
            client_kw["proxy"] = proxy
        async with httpx.AsyncClient(**client_kw) as client:
            if method.upper() == "POST":
                resp = await client.post(url, headers=headers, json=json_data)
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content if raw_binary else resp.json()
    except (httpx.ConnectError, httpx.ProxyError, httpx.ConnectTimeout) as e:
        if not proxy:
            raise
        logger.warning(
            f"MinerU 代理连接失败 ({proxy}): {e}，尝试直连..."
        )
        # 临时禁用代理，直连重试
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as client:
            if method.upper() == "POST":
                resp = await client.post(url, headers=headers, json=json_data)
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content if raw_binary else resp.json()


async def _post_json(url: str, headers: dict, json_data: dict) -> dict:
    """异步 POST JSON 请求（支持代理，失败自动降级直连）"""
    return await _request_with_fallback("POST", url, headers, json_data=json_data, timeout=60)


async def _get_json(url: str, headers: dict) -> dict:
    """异步 GET 请求（支持代理，失败自动降级直连）"""
    return await _request_with_fallback("GET", url, headers, timeout=60)


async def _get_binary(url: str) -> bytes:
    """异步下载二进制数据（支持代理，失败自动降级直连）"""
    return await _request_with_fallback(
        "GET", url, {},
        timeout=300, follow_redirects=True, raw_binary=True,
    )


def _extract_md_from_zip(zip_bytes: bytes) -> str:
    """从 MinerU 返回的 Zip 包中提取 Markdown 内容"""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_files:
                logger.warning(f"Zip 包中没有 .md 文件: {zf.namelist()}")
                return ""

            # 取最大的 .md 文件（通常是主内容文件）
            md_files.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
            md_name = md_files[0]
            content = zf.read(md_name).decode("utf-8", errors="replace")
            logger.info(f"MinerU: 从 {md_name} 提取 Markdown ({len(content)} 字符)")
            return content
    except zipfile.BadZipFile:
        logger.error("MinerU 结果不是有效的 Zip 文件")
        return ""
    except Exception as e:
        logger.error(f"Zip 提取失败: {e}")
        return ""


def _clean_markdown(text: str) -> str:
    """清理 MinerU 输出的 Markdown：移除多余空行、无关元数据等"""
    if not text:
        return ""

    # 移除连续的空白行（保留最多 1 个空行）
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 移除常见 MinerU 元数据行（如 <!-- page: xxx -->）
    text = re.sub(r"<!--.*?-->", "", text)

    # 移除首尾空白
    text = text.strip()

    return text
