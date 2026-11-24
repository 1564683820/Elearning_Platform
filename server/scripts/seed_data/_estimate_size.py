"""估算 ECDICT 全量导入 MySQL 的存储需求"""
import os
import sqlite3

DB = "scripts/ecdict-data/stardict.db"

# 原始文件大小
file_size = os.path.getsize(DB)
print(f"ECDICT SQLite 文件大小: {file_size:,} 字节 ({file_size/1024/1024:.1f} MB)")

conn = sqlite3.connect(DB)
total = conn.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
print(f"总词条数: {total:,}")

# 各字段平均长度
fields = ["word", "sw", "phonetic", "definition", "translation", "pos", "exchange", "detail", "tag"]
print(f"\n{'='*70}")
print(f"{'字段名':12} {'平均长度(字节)':>16} {'非空数':>10} {'非空占比':>8}")
print(f"{'='*70}")

total_avg_row = 0
for field in fields:
    r = conn.execute(f'SELECT AVG(LENGTH(COALESCE({field}, ""))), COUNT(*) FROM stardict WHERE {field} IS NOT NULL AND {field} != ""').fetchone()
    avg_len = r[0] or 0
    nonnull = r[1]
    pct = nonnull * 100 // total
    total_avg_row += avg_len
    print(f"  {field:12} {avg_len:>16.1f} {nonnull:>10,} {pct:>7}%")

# 包含所有字段的完整平均行大小（包括空字段）
all_fields = ["word", "sw", "phonetic", "definition", "translation", "pos", "collins", "oxford", "tag", "bnc", "frq", "exchange", "detail", "audio"]
full_avg = 0
for field in all_fields:
    r = conn.execute(f'SELECT AVG(LENGTH(COALESCE({field}, ""))) FROM stardict').fetchone()
    full_avg += r[0] or 0

print(f"\n{'='*70}")
print(f"平均每行数据大小（所有字段含空值）: {full_avg:.1f} 字节")
print(f"理论最小数据大小: {full_avg * total / 1024 / 1024:.0f} MB")

# MySQL 存储估计
# MySQL 额外开销: 每行约 30-50 字节（行头、事务ID、指针等）
# VARCHAR 本身有 1-2 字节长度前缀
# 索引开销
mysql_overhead_per_row = 40
index_overhead = 0.5  # 索引约为数据量的50%

data_size = full_avg * total  # 裸数据
row_overhead = mysql_overhead_per_row * total
index_size = (data_size + row_overhead) * index_overhead

mysql_total = data_size + row_overhead + index_size

print(f"\n=== MySQL 存储估算 ===")
print(f"裸数据大小:       {data_size/1024/1024:.0f} MB")
print(f"每行MySQL开销:    {row_overhead/1024/1024:.0f} MB")
print(f"索引预估(50%):   {index_size/1024/1024:.0f} MB")
print(f"{'='*40}")
print(f"MySQL 总预估:    {mysql_total/1024/1024:.0f} MB")
print(f"                 约 {(mysql_total/1024/1024/1024):.2f} GB")

print(f"\n=== 实际建议 ===")
print(f"不导入全部 340 万条——只导入 dict_word 表里已有的单词即可")
# 检查 dict_word 数量
try:
    import sys
    sys.path.insert(0, os.path.dirname(DB))
    from app.core.config import get_settings
    from sqlalchemy import create_engine, text
    s = get_settings()
    e = create_engine(s.SYNC_WORDS_DATABASE_URL, echo=False)
    cnt = e.execute(text("SELECT COUNT(*) FROM dict_word")).scalar()
    print(f"当前 dict_word 单词数: {cnt:,}")
    # 估算仅导入这些单词的 exchange 数据
    est = cnt * 50  # 50 字节/条
    print(f"仅导入 exchange 字段给已有单词: 约 {est/1024:.0f} KB")
    e.dispose()
except Exception as ex:
    print(f"  无法查询 dict_word: {ex}")

conn.close()
