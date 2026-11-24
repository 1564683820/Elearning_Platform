"""
阶段值迁移脚本 — 将旧 stage 1-13 映射到新值 1-4

映射规则:
  旧 1-4  (启蒙/小三/小四/小五)  → 新 1 (小学)
  旧 5-7  (初一/初二/初三)      → 新 2 (初中)
  旧 8-10 (四级/六级/雅思)      → 新 3 (高中)
  旧 11-13 (cet4/cet6/ielts)     → 新 4 (四六级)

安全特性:
  - 支持 --dry-run 预览变更
  - 逐表逐条 UPDATE（非单条大 SQL，避免锁表过久）
  - 带计数确认提示

用法:
  python scripts/migrate_stage_values.py           # 执行迁移
  python scripts/migrate_stage_values.py --dry-run  # 仅预览，不改写
"""
import argparse
import os
import sys

import pymysql

# 确保能找到 服务端 Python 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from app.core.config import get_settings

# 数据库配置（与 .env / config.py 一致）
settings = get_settings()
DB_CONFIG = dict(settings.mysql_connection_kwargs(), charset="utf8mb4")

MAIN_DB = settings.MYSQL_DATABASE
WORDS_DB = settings.WORDS_DATABASE

# 映射: (old_min, old_max) → new_value
STAGE_MAP = [
    (1, 4, 1),     # → 小学
    (5, 7, 2),     # → 初中
    (8, 10, 3),    # → 高中
    (11, 13, 4),   # → 四六级
]

# 需要迁移的表（库名, 表名, 字段名）
TABLES = [
    ("main", "user", "stage"),
    ("main", "class", "stage"),
    ("main", "question_bank", "stage"),
    ("main", "reading_material", "stage"),
    ("main", "listening_material", "stage"),
    ("main", "song", "stage"),
    ("words", "stage_word", "stage"),
]


def build_safe_case():
    """构造安全的 CASE WHEN 表达式，防止 SQL 注入（值都是硬编码的数字）"""
    parts = ["CASE `{col}`"]
    for lo, hi, new_val in STAGE_MAP:
        if lo == hi:
            parts.append(f"  WHEN {lo} THEN {new_val}")
        else:
            parts.append(f"  WHEN `{{col}}` BETWEEN {lo} AND {hi} THEN {new_val}")
    parts.append("  ELSE `{col}`")
    parts.append("END")
    return "\n".join(parts)


def make_update_sql(table, column):
    """生成针对单个表的 UPDATE SQL"""
    case_when = build_safe_case().format(col=column)
    return f"UPDATE `{table}` SET `{column}` = {case_when} WHERE `{column}` BETWEEN 1 AND 13;"


def make_count_sql(table, column, old_min, old_max, new_val):
    """统计有多少行会被影响"""
    return (
        f"SELECT COUNT(*) AS cnt FROM `{table}` "
        f"WHERE `{column}` BETWEEN {old_min} AND {old_max} "
        f"  AND `{column}` != {new_val}"
    )


def make_summary_sql(table, column):
    """统计旧值分布"""
    return (
        f"SELECT `{column}` AS old_val, COUNT(*) AS cnt "
        f"FROM `{table}` "
        f"WHERE `{column}` BETWEEN 1 AND 13 "
        f"GROUP BY `{column}` "
        f"ORDER BY `{column}`"
    )


def get_db(db_name):
    """获取指定库的连接"""
    conn = pymysql.connect(
        database=db_name,
        autocommit=False,
        **DB_CONFIG,
    )
    return conn


def print_header(title):
    """打印分区标题"""
    print()
    print("=" * 66)
    print(f"  {title}")
    print("=" * 66)


def run_migration(dry_run: bool):
    """执行或预览 stage 值迁移"""
    errors = []
    total_affected = 0

    for db_label, table, column in TABLES:
        db_name = MAIN_DB if db_label == "main" else WORDS_DB
        print_header(f"📂 库: {db_name}  →  表: `{table}`.`{column}`")

        try:
            conn = get_db(db_name)
            with conn.cursor() as cur:
                # Step 1: 打印旧值分布
                cur.execute(make_summary_sql(table, column))
                rows = cur.fetchall()
                if not rows:
                    print("  ℹ️  表中无旧 stage 值（1-13），跳过")
                    conn.close()
                    continue

                print("  旧值分布:")
                for old_val, cnt in rows:
                    print(f"    stage={old_val}: {cnt} 行")

                # Step 2: 逐段统计影响
                print()
                table_total = 0
                for lo, hi, new_val in STAGE_MAP:
                    cur.execute(make_count_sql(table, column, lo, hi, new_val))
                    (cnt,) = cur.fetchone()
                    hint = {1: "→ 1(小学)", 2: "→ 2(初中)", 3: "→ 3(高中)", 4: "→ 4(四六级)"}
                    label = f"旧 {lo}-{hi}" if lo != hi else f"旧 {lo}"
                    print(f"    {label} [{cnt} 行] {hint[new_val]}")
                    table_total += cnt

                if table_total == 0:
                    print("  ✅ 无需迁移")
                    conn.close()
                    continue

                print(f"  📊 总计: {table_total} 行将被更新")

                # Step 3: 执行或跳过
                if dry_run:
                    print("  🟡 DRY RUN 模式 — 未实际写入")
                    total_affected += table_total
                    conn.close()
                    continue

                update_sql = make_update_sql(table, column)
                cur.execute(update_sql)
                affected = cur.rowcount
                conn.commit()
                print(f"  ✅ 已更新 {affected} 行")
                total_affected += affected

            conn.close()

        except pymysql.Error as e:
            err_msg = f"❌ 表 `{table}` 迁移失败: {e}"
            print(f"  {err_msg}")
            errors.append(err_msg)

    # 最终汇总
    print()
    print("=" * 66)
    if dry_run:
        print(f"  🟡 DRY RUN 完成 — 预计影响 {total_affected} 行（未实际写入）")
    else:
        if not errors:
            print(f"  ✅ 迁移完成 — 共更新 {total_affected} 行数据")
            print()
            print("  ⚠️  建议执行完后验证:")
            print("     1. 重启后端服务使缓存失效")
            print(
                "     2. 检查小程序首页学习阶段显示是否正常"
            )
            print("     3. 检查单词/题库/阅读材料等数据检索是否正常")
        else:
            print(f"  ⚠️  完成，但有 {len(errors)} 个错误:")
            for e in errors:
                print(f"    - {e}")

    print("=" * 66)


def main():
    global MAIN_DB, WORDS_DB
    parser = argparse.ArgumentParser(
        description="迁移旧 stage 值（1-13）到新值（1-4）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览变更，不实际写入数据库",
    )
    parser.add_argument(
        "--host",
        default=DB_CONFIG["host"],
        help=f"MySQL 主机 (默认: {DB_CONFIG['host']})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DB_CONFIG["port"],
        help=f"MySQL 端口 (默认: {DB_CONFIG['port']})",
    )
    parser.add_argument(
        "--user",
        default=DB_CONFIG["user"],
        help=f"MySQL 用户 (默认: {DB_CONFIG['user']})",
    )
    parser.add_argument(
        "--password",
        default=DB_CONFIG["password"],
        help="MySQL 密码（默认读取 server/.env 或环境变量）",
    )
    parser.add_argument(
        "--main-db",
        default=MAIN_DB,
        help=f"主库名称 (默认: {MAIN_DB})",
    )
    parser.add_argument(
        "--words-db",
        default=WORDS_DB,
        help=f"单词库名称 (默认: {WORDS_DB})",
    )

    args = parser.parse_args()

    # 更新配置
    DB_CONFIG["host"] = args.host
    DB_CONFIG["port"] = args.port
    DB_CONFIG["user"] = args.user
    DB_CONFIG["password"] = args.password

    MAIN_DB = args.main_db
    WORDS_DB = args.words_db

    print(f"🔧 数据库连接: {args.user}@{args.host}:{args.port}")
    print(f"  主库: {MAIN_DB}")
    print(f"  单词库: {WORDS_DB}")
    print(f"  模式: {'DRY RUN (只读)' if args.dry_run else '实际写入'}")

    # 确认提示（dry-run 模式跳过）
    if not args.dry_run:
        print()
        print("⚠️  ⚠️  ⚠️  即将修改数据库数据！请确认：")
        print("   - 已备份数据库？")
        print("   - 已停止相关服务？")
        print()
        try:
            confirm = input("确认执行迁移？(输入 YES 确认): ").strip()
        except (EOFError, KeyboardInterrupt):
            confirm = ""
        if confirm != "YES":
            print("❌ 已取消")
            sys.exit(0)

    run_migration(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
