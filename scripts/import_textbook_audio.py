"""
教材音频批量导入脚本

从夸克网盘手动下载的 MP3 音频文件夹，批量导入到系统中：
  1. 递归扫描音频目录，按页码分组（文件名如 P04_01_描述.mp3 → page 4）
  2. 将同一页的所有句子音频用 ffmpeg 合并成一个完整页面音频
  3. 复制到 服务端上传目录的 textbook/audio/ 目录
  4. 更新 textbook_page.audio_url 字段

用法:
  python scripts/import_textbook_audio.py --audio-dir <下载的音频目录> [选项]

示例:
  # 预览匹配（不实际导入）
  python scripts/import_textbook_audio.py --audio-dir data/download/pep3s_audio --dry-run

  # 实际导入 - 三年级上册 PEP
  python scripts/import_textbook_audio.py --audio-dir "data/download/pep3s_audio/教师专用：人教版小学英语-PEP-三年级-上册-配套音频-单句分离" --version PEP --grade 3 --semester 上

  # 仅复制文件，不更新数据库
  python scripts/import_textbook_audio.py --audio-dir ... --skip-db

文件名格式:
  P{页码}_{序号}_{描述}.mp3   如 P04_01_A_我们怎样问候朋友？.mp3
"""

import os
import re
import sys
import json
import shutil
import subprocess
import argparse
import logging
import tempfile
from pathlib import Path
from collections import defaultdict

# 添加 server 目录到 Python 路径
_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server")
sys.path.insert(0, _SERVER_DIR)

from app.core.paths import UPLOADS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── 支持的音频扩展 ──
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}

# ── 文件名 → 页码提取（匹配 P{数字} 前缀模式，如 P04_01, Page02_01）──
PAGE_NUM_PATTERN = re.compile(r"(?:^|[_\s\\/])(?:P|p(?:age)?)[_\s]*(?P<page>\d{1,3})", re.IGNORECASE)


def find_ffmpeg() -> str | None:
    """查找 ffmpeg 可执行文件路径"""
    # 1. 检查 PATH
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 2. 检查常见安装路径
    candidates = [
        os.path.expanduser("~/AppData/Local/ffmpeg"),
        os.path.expanduser("~/scoop/apps/ffmpeg/current"),
        "C:/ffmpeg",
        "C:/tools/ffmpeg",
    ]
    for base in candidates:
        for root, dirs, files in os.walk(base):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")
    return None


def find_audio_files_recursive(audio_dir: str) -> list[Path]:
    """递归扫描目录中的所有音频文件，返回按文件名排序的文件列表"""
    audio_dir = Path(audio_dir)
    if not audio_dir.exists() or not audio_dir.is_dir():
        logger.error(f"音频目录不存在: {audio_dir}")
        sys.exit(1)

    files = []
    for f in sorted(audio_dir.rglob("*")):
        if f.suffix.lower() in AUDIO_EXTS and not f.name.startswith("."):
            files.append(f)

    if not files:
        logger.warning(f"在 {audio_dir} 中未找到任何音频文件（支持: {', '.join(AUDIO_EXTS)}）")
        sys.exit(1)

    logger.info(f"找到 {len(files)} 个音频文件")
    return files


def extract_page_from_filename(filename: str) -> int | None:
    """从文件名中提取页码（匹配 P{数字} 前缀）"""
    m = PAGE_NUM_PATTERN.search(filename)
    if m:
        return int(m.group("page"))
    return None


def group_files_by_page(audio_files: list[Path]) -> dict[int, list[Path]]:
    """将音频文件按页码分组，并按文件名序号排序"""
    page_groups = defaultdict(list)
    unmatched = []

    for af in audio_files:
        stem = af.stem
        page_num = extract_page_from_filename(stem)
        if page_num is None:
            unmatched.append(af)
            continue
        page_groups[page_num].append(af)

    # 每组内按文件名排序（确保 P04_01 在 P04_02 之前）
    for page_num in page_groups:
        page_groups[page_num].sort(key=lambda f: f.name)

    if unmatched:
        logger.warning(f"未提取到页码的文件 ({len(unmatched)} 个):")
        for f in unmatched:
            logger.warning(f"  {f.name}")

    logger.info(f"按页码分组: {len(page_groups)} 个页面，共 {sum(len(v) for v in page_groups.values())} 个音频文件")
    return dict(page_groups)


def merge_audio_files(audio_files: list[Path], output_path: Path, ffmpeg_path: str) -> bool:
    """使用 ffmpeg 合并多个音频文件为一个"""
    if not ffmpeg_path:
        logger.error("ffmpeg 不可用，无法合并音频文件")
        return False

    if len(audio_files) == 1:
        # 只有一个文件，直接复制
        shutil.copy2(str(audio_files[0]), str(output_path))
        logger.info(f"  单文件复制 → {output_path.name}")
        return True

    # 创建 ffmpeg concat 清单文件
    tmp_dir = Path(tempfile.mkdtemp())
    concat_file = tmp_dir / "concat.txt"
    try:
        with open(concat_file, "w", encoding="utf-8") as f:
            for af in audio_files:
                # ffmpeg concat 要求路径用引号括起来
                escaped = str(af.absolute()).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
               "-i", str(concat_file),
               "-c", "copy",
               str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"  ffmpeg 合并失败: {result.stderr[:200]}")
            return False
        logger.info(f"  合并完成: {len(audio_files)} 个片段 → {output_path.name}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("  ffmpeg 超时（>5分钟）")
        return False
    except Exception as e:
        logger.error(f"  合并出错: {e}")
        return False
    finally:
        # 清理临时文件
        try:
            shutil.rmtree(tmp_dir)
        except OSError:
            pass


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="教材音频批量导入工具（支持逐句音频合并）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--audio-dir", required=True,
        help="音频文件所在目录（从夸克网盘下载的文件夹，含子目录）",
    )
    parser.add_argument(
        "--version", default="PEP",
        help="教材版本（默认: PEP）",
    )
    parser.add_argument(
        "--grade", required=True,
        help="年级（如 3,4,5,6）",
    )
    parser.add_argument(
        "--semester", required=True,
        help="学期（上/下）",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="音频输出目录（默认: 服务端上传目录的 textbook/audio/）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：只显示匹配结果，不实际合并文件和更新数据库",
    )
    parser.add_argument(
        "--skip-db", action="store_true",
        help="仅合并/复制文件到 uploads 目录，不更新数据库",
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="不合并，每个句子音频单独保存（仅第一段会匹配到页面）",
    )
    parser.add_argument(
        "--sentence-level", action="store_true",
        help="逐句模式：复制每个句子音频并更新 sentences_json，同时合并整页音频",
    )
    return parser.parse_args()


def get_db_connection():
    """使用 .env 配置连接数据库"""
    try:
        import pymysql
    except ImportError:
        logger.error("请安装 pymysql: pip install pymysql")
        sys.exit(1)

    try:
        from app.config import get_settings
        settings = get_settings()
        host = settings.MYSQL_HOST
        port = settings.MYSQL_PORT
        user = settings.MYSQL_USER
        password = settings.MYSQL_PASSWORD
        database = settings.MYSQL_DATABASE
    except Exception as e:
        logger.warning(f"通过 Settings 读取配置失败: {e}，尝试直接解析 .env")
        env_path = os.path.join(_SERVER_DIR, ".env")
        if not os.path.exists(env_path):
            logger.error(f".env 文件未找到: {env_path}")
            sys.exit(1)
        env_vars = {}
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
        host = env_vars.get("MYSQL_HOST", "127.0.0.1")
        port = int(env_vars.get("MYSQL_PORT", 3306))
        user = env_vars.get("MYSQL_USER", "root")
        password = env_vars.get("MYSQL_PASSWORD", "")
        database = env_vars.get("MYSQL_DATABASE", "elearningtest")

    try:
        conn = pymysql.connect(
            host=host, port=port, user=user,
            password=password, database=database,
            charset="utf8mb4",
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        logger.info(f"已连接到 MySQL: {host}:{port}/{database}")
        return conn, cursor
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        sys.exit(1)


def fetch_pages(cursor, version: str, grade: str | None = None,
                semester: str | None = None) -> list[dict]:
    """查询 textbook_page 记录"""
    where_clauses = ["is_active = 1", "textbook_version = %s"]
    params = [version]

    if grade:
        where_clauses.append("grade = %s")
        params.append(grade)
    if semester:
        where_clauses.append("semester = %s")
        params.append(semester)

    sql = f"""
        SELECT id, textbook_version, grade, semester,
               unit_number, page_number, audio_url
        FROM textbook_page
        WHERE {' AND '.join(where_clauses)}
        ORDER BY unit_number, page_number
    """
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    if not rows:
        logger.warning(f"未查询到符合条件的教材页面: version={version}, grade={grade}, semester={semester}")
        return []

    logger.info(f"查询到 {len(rows)} 个教材页面 (version={version}, grade={grade}, semester={semester})")
    return rows


def get_output_dir(args) -> Path:
    """获取音频输出目录"""
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = UPLOADS_DIR / "textbook" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def print_summary(page_groups, matched_pages, pages, args, total_audio_files):
    """打印匹配概况"""
    total_audio = sum(len(v) for v in page_groups.values())
    unmatched_count = total_audio_files - total_audio

    print("\n" + "=" * 60)
    print("  音频导入概览")
    print("=" * 60)
    print(f"  教材版本:    {args.version}")
    print(f"  年级:        {args.grade}")
    print(f"  学期:        {args.semester}")
    if args.sentence_level:
        merge_mode = "逐句复制 + 合并整页 (--sentence-level)"
    elif args.no_merge:
        merge_mode = "否 (--no-merge，仅取第一个音频)"
    else:
        merge_mode = "是 (ffmpeg 合并每页句子)"
    print(f"  合并音频:    {merge_mode}")
    print(f"  {'[预览模式]' if args.dry_run else '[实际导入]'}")
    print("-" * 60)
    print(f"  音频文件总数:    {total_audio_files}")
    print(f"  提取到页码:      {total_audio} 个（{len(page_groups)} 页）")
    print(f"  未提取页码:      {unmatched_count} 个")
    print(f"  匹配教材页面:    {len(matched_pages)} 页")
    print(f"  未匹配教材页面:  {len(pages) - len(matched_pages)} 页（数据库中无对应页面）")
    print("=" * 60)

    # 打印匹配详情
    if matched_pages:
        print("\n匹配详情:")
        for page_info in sorted(matched_pages, key=lambda x: x["page_number"]):
            files = page_groups.get(page_info["page_number"], [])
            flag = "[有音频]" if files else "[无音频]"
            print(f"  {flag} {page_info['unit_number']}-P{page_info['page_number']:02d}  ({len(files)} 个片段)")


def _update_sentence_audio(cursor, page_id: int, sentence_audio_paths: list[str]):
    """更新指定页面的 sentences_json，为每个句子添加 audio_url"""
    sql = "SELECT sentences_json FROM textbook_page WHERE id = %s"
    cursor.execute(sql, (page_id,))
    row = cursor.fetchone()
    if not row:
        logger.warning(f"  page_id={page_id} 未找到记录，跳过 sentences_json 更新")
        return

    sentences = row["sentences_json"]
    if isinstance(sentences, str):
        sentences = json.loads(sentences)
    if not sentences or not isinstance(sentences, list) or len(sentences) == 0:
        logger.warning(f"  page_id={page_id} 没有分句数据 (sentences_json 为空)，无法添加 audio_url")
        return

    updated_count = 0
    for i, s in enumerate(sentences):
        if i < len(sentence_audio_paths):
            s["audio_url"] = sentence_audio_paths[i]
            updated_count += 1

    if updated_count > 0:
        sql = "UPDATE textbook_page SET sentences_json = %s WHERE id = %s"
        cursor.execute(sql, (json.dumps(sentences, ensure_ascii=False), page_id))
        logger.info(f"  已更新 {updated_count}/{len(sentences)} 个句子的 audio_url")
    else:
        logger.warning(f"  page_id={page_id}: 句子数与音频数不匹配，未更新")


def main():
    """主入口"""
    args = parse_args()
    audio_dir_arg = args.audio_dir

    # 1. 查找 ffmpeg
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        logger.info(f"ffmpeg 可用: {ffmpeg_path}")
    else:
        logger.warning("ffmpeg 未找到，无法合并音频。将仅使用每个页面的第一个音频文件。")

    # 2. 递归扫描音频文件
    audio_files = find_audio_files_recursive(audio_dir_arg)
    total_count = len(audio_files)

    # 3. 按页码分组
    page_groups = group_files_by_page(audio_files)

    if not page_groups:
        logger.error("没有提取到任何页码，无法匹配。请检查文件名是否包含 P{数字} 模式。")
        sys.exit(1)

    # 4. 获取数据库连接
    conn, cursor = get_db_connection()

    try:
        # 5. 查询教材页面
        pages = fetch_pages(cursor, args.version, args.grade, args.semester)
        if not pages:
            logger.info("没有可更新的页面，结束。")
            return

        # 6. 构建 页码 → pages 的索引
        page_map = {}
        for p in pages:
            pnum = p["page_number"]
            if pnum not in page_map:
                page_map[pnum] = []
            page_map[pnum].append(p)

        # 7. 匹配音频页码到教材页面
        matched_pages = []
        unmatched_pages = []
        for p in pages:
            if p["page_number"] in page_groups:
                matched_pages.append(p)
            else:
                unmatched_pages.append(p)

        # 8. 打印概要
        output_dir = get_output_dir(args)
        print_summary(page_groups, matched_pages, pages, args, total_count)

        if not matched_pages:
            logger.warning("没有成功匹配的页面！")
            return

        if args.dry_run:
            logger.info("\n预览模式结束，去掉 --dry-run 执行导入。")
            return

        # 9. 执行导入：合并音频 + 复制 + 更新 DB
        updated_count = 0
        failed_pages = []

        for page_info in sorted(matched_pages, key=lambda x: x["page_number"]):
            pnum = page_info["page_number"]
            clips = page_groups[pnum]

            if args.sentence_level:
                # ── 逐句模式：复制每个句子音频 + 合并整页音频 ──
                sentence_audio_rel_paths = []
                for seq, src_clip in enumerate(clips, 1):
                    s_out_name = f"P{pnum:02d}_{seq:02d}{src_clip.suffix}"
                    s_dest = output_dir / s_out_name
                    if not args.dry_run:
                        shutil.copy2(str(src_clip), str(s_dest))
                    logger.info(f"  逐句复制: {src_clip.name} → {s_out_name}")
                    sentence_audio_rel_paths.append(f"/uploads/textbook/audio/{s_out_name}")

                # 合并整页音频用于全文朗读
                page_out_name = f"P{pnum:02d}.mp3"
                page_dest = output_dir / page_out_name
                is_ok = merge_audio_files(clips, page_dest, ffmpeg_path) if not args.dry_run else True
                rel_path = f"/uploads/textbook/audio/{page_out_name}"

                if is_ok and not args.dry_run and not args.skip_db:
                    # 更新页面 audio_url
                    sql = "UPDATE textbook_page SET audio_url = %s, audio_duration = 0 WHERE id = %s"
                    cursor.execute(sql, (rel_path, page_info["id"]))
                    # 更新 sentences_json 添加逐句 audio_url
                    _update_sentence_audio(cursor, page_info["id"], sentence_audio_rel_paths)

                updated_count += 1
                action = "[预览]" if args.dry_run else "[更新]"
                logger.info(f"  {action} page_id={page_info['id']}, "
                           f"{page_info['unit_number']}-P{pnum:02d}, "
                           f"音频: {page_out_name} + {len(clips)} 个单句")

            elif args.no_merge:
                # 不倒带：仅取第一个音频
                src = clips[0]
                out_name = f"P{pnum:02d}{src.suffix}"
                dest = output_dir / out_name
                is_ok = True
                if not args.dry_run:
                    shutil.copy2(str(src), str(dest))
                    logger.info(f"  复制（单文件）: {src.name} → {out_name}")

                if is_ok:
                    rel_path = f"/uploads/textbook/audio/{dest.name}"
                    if not args.dry_run and not args.skip_db:
                        sql = "UPDATE textbook_page SET audio_url = %s, audio_duration = 0 WHERE id = %s"
                        cursor.execute(sql, (rel_path, page_info["id"]))
                    updated_count += 1
                    action = "[预览]" if args.dry_run else "[更新]"
                    logger.info(f"  {action} page_id={page_info['id']}, "
                               f"{page_info['unit_number']}-P{pnum:02d}, "
                               f"音频: {out_name} ({len(clips)} 个片段)")
                else:
                    failed_pages.append(pnum)
                    logger.error(f"  [失败] {page_info['unit_number']}-P{pnum:02d}: 复制失败")
            else:
                # 合并：所有片段合成一个音频
                out_name = f"P{pnum:02d}.mp3"
                dest = output_dir / out_name
                is_ok = merge_audio_files(clips, dest, ffmpeg_path) if not args.dry_run else True

                if is_ok:
                    rel_path = f"/uploads/textbook/audio/{dest.name}"
                    if not args.dry_run and not args.skip_db:
                        sql = "UPDATE textbook_page SET audio_url = %s, audio_duration = 0 WHERE id = %s"
                        cursor.execute(sql, (rel_path, page_info["id"]))
                    updated_count += 1
                    action = "[预览]" if args.dry_run else "[更新]"
                    logger.info(f"  {action} page_id={page_info['id']}, "
                               f"{page_info['unit_number']}-P{pnum:02d}, "
                               f"音频: {out_name} ({len(clips)} 个片段)")
                else:
                    failed_pages.append(pnum)
                    logger.error(f"  [失败] {page_info['unit_number']}-P{pnum:02d}: 音频合并失败")

        # 提交事务
        if not args.dry_run and not args.skip_db:
            conn.commit()
            logger.info(f"\n✅ 数据库已提交 {updated_count} 条更新")

        if failed_pages:
            logger.warning(f"\n⚠️ 以下页面合并失败: {failed_pages}")

        # 写入本次导入日志
        log_path = UPLOADS_DIR / "textbook" / "audio_import_log.txt"
        if not args.dry_run:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{__import__('datetime').datetime.now()}] "
                       f"version={args.version} grade={args.grade} "
                       f"semester={args.semester} "
                       f"pages_updated={updated_count} "
                       f"audio_dir={audio_dir_arg}\n")

        if unmatched_pages:
            logger.info(f"\n⚠️ 以下页面没有音频文件（{len(unmatched_pages)} 页），将继续走 TTS 合成:")
            for p in unmatched_pages:
                logger.info(f"  {p['unit_number']}-P{p['page_number']:02d}")

        logger.info(f"\n{'='*20} 导入完成！共更新 {updated_count} 页音频 {'='*20}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
