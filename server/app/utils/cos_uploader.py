import os
import logging
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def upload_to_cos(
    data: bytes,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """上传二进制数据到腾讯云 COS

    参数:
        data: 文件二进制数据
        key: COS 对象键（如 textbook/PEP/3/Unit1/anim_2.gif）
        content_type: MIME 类型

    返回:
        str: CDN 公开访问 URL

    依赖: cos-python-sdk-v5 (pip install cos-python-sdk-v5)
    """
    cos_secret_id = getattr(settings, "COS_SECRET_ID", "") or os.environ.get("COS_SECRET_ID", "")
    cos_secret_key = getattr(settings, "COS_SECRET_KEY", "") or os.environ.get("COS_SECRET_KEY", "")
    cos_region = getattr(settings, "COS_REGION", "ap-guangzhou")
    cos_bucket = settings.COS_BUCKET
    cdn_base = settings.CDN_BASE_URL

    # 如果配置了 COS 凭证，使用 SDK 上传
    if cos_secret_id and cos_secret_key:
        try:
            from qcloud_cos import CosConfig, CosS3Client
            from qcloud_cos.cos_exception import CosServiceError

            config = CosConfig(
                Region=cos_region,
                SecretId=cos_secret_id,
                SecretKey=cos_secret_key,
                Token=None,
                Scheme="https",
            )
            client = CosS3Client(config)

            # 将 bytes 写入内存流
            from io import BytesIO
            stream = BytesIO(data)

            client.put_object(
                Bucket=cos_bucket,
                Body=stream,
                Key=key,
                ContentType=content_type,
            )

            # 返回 CDN URL
            if cdn_base:
                return f"{cdn_base.rstrip('/')}/{key.lstrip('/')}"
            return f"https://{cos_bucket}.cos.{cos_region}.myqcloud.com/{key}"

        except ImportError:
            logger.warning("cos-python-sdk-v5 未安装，无法上传 COS")
            raise
        except CosServiceError as e:
            logger.error("COS 上传失败: %s", e)
            raise
        except Exception as e:
            logger.error("COS 上传异常: %s", e)
            raise

    # 未配置 COS 时，使用本地文件路径或 mock URL
    logger.warning("COS 未配置，使用 mock URL: %s/%s", cdn_base, key)
    if cdn_base:
        return f"{cdn_base.rstrip('/')}/{key.lstrip('/')}"
    return f"https://cos-mock/{key}"


async def upload_local_file_to_cos(
    local_path: str,
    key: str,
    content_type: Optional[str] = None,
) -> str:
    """上传本地文件到 COS

    参数:
        local_path: 本地文件路径
        key: COS 对象键
        content_type: MIME 类型（自动推断为 None）

    返回:
        str: CDN 公开访问 URL
    """
    with open(local_path, "rb") as f:
        data = f.read()

    if not content_type:
        # 根据扩展名推断
        ext = os.path.splitext(local_path)[1].lower()
        content_type = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".srt": "text/plain",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")

    return await upload_to_cos(data, key, content_type)
