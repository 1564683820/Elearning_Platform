from io import BytesIO
from typing import Optional
from PIL import Image


def compose_gif(
    frame_bytes_list: list[bytes],
    duration: int = 800,
    loop: int = 0,
    max_size_bytes: int = 512 * 1024,
    output_path: Optional[str] = None,
) -> bytes:
    """将多帧图片合成为 GIF 动画

    参数:
        frame_bytes_list: 各帧图片的二进制数据（PNG/JPEG）
        duration: 每帧显示时长（毫秒），默认 800ms
        loop: 循环次数，0 表示无限循环
        max_size_bytes: GIF 最大体积（字节），默认 512KB
        output_path: 若指定，将 GIF 写入本地文件

    返回:
        bytes: GIF 二进制数据
    """
    if not frame_bytes_list:
        raise ValueError("帧列表不能为空")

    # 将各帧加载为 PIL Image
    frames = []
    for raw in frame_bytes_list:
        img = Image.open(BytesIO(raw))
        # 统一转为 RGBA 或 RGB（GIF 需要调色板模式）
        if img.mode not in ("P", "L", "RGBA", "RGB"):
            img = img.convert("RGBA")
        frames.append(img)

    # 如果各帧尺寸不一致，统一缩放到第一帧尺寸
    base_size = frames[0].size
    for i in range(1, len(frames)):
        if frames[i].size != base_size:
            frames[i] = frames[i].resize(base_size, Image.LANCZOS)

    # 合成 GIF
    out_buf = BytesIO()
    frames[0].save(
        out_buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=loop,
        optimize=True,
    )

    gif_bytes = out_buf.getvalue()

    # 如果超过最大体积，尝试压缩
    if len(gif_bytes) > max_size_bytes:
        gif_bytes = _compress_gif(frame_bytes_list, gif_bytes, duration, loop, max_size_bytes)

    # 写入本地文件
    if output_path:
        with open(output_path, "wb") as f:
            f.write(gif_bytes)

    return gif_bytes


def _compress_gif(
    frame_bytes_list: list[bytes],
    current_gif: bytes,
    duration: int,
    loop: int,
    target_size: int,
) -> bytes:
    """递归压缩 GIF 至目标体积以内

    策略：减少颜色数（先 128 → 64 → 32），直到体积达标或无法再压缩
    """
    max_colors = 128
    while len(current_gif) > target_size and max_colors >= 16:
        frames = []
        for raw in frame_bytes_list:
            img = Image.open(BytesIO(raw))
            if img.mode == "RGBA":
                img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)
            elif img.mode == "RGB":
                img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)
            else:
                img = img.quantize(colors=max_colors)
            frames.append(img)

        out_buf = BytesIO()
        frames[0].save(
            out_buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=loop,
            optimize=True,
        )
        current_gif = out_buf.getvalue()
        max_colors //= 2

    return current_gif


def get_gif_info(gif_bytes: bytes) -> dict:
    """获取 GIF 基本信息

    参数:
        gif_bytes: GIF 二进制数据

    返回:
        dict: {frame_count, duration_ms, size_bytes, width, height}
    """
    img = Image.open(BytesIO(gif_bytes))
    frame_count = getattr(img, "n_frames", 1)
    width, height = img.size
    return {
        "frame_count": frame_count,
        "duration_ms": img.info.get("duration", 800),
        "size_bytes": len(gif_bytes),
        "width": width,
        "height": height,
    }
