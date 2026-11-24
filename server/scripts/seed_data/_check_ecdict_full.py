"""检查 ECDICT 完整表结构和各字段数据量"""
import sqlite3, os, sys
sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join(os.path.dirname(__file__), '..', 'ecdict-data', 'stardict.db')
print(f"数据库路径: {os.path.abspath(db_path)}")
print(f"文件存在: {os.path.exists(db_path)}")

if not os.path.exists(db_path):
    # 试试其他路径
    alt_paths = [
        'scripts/ecdict-data/stardict.db',
        '../ecdict-data/stardict.db',
        'ecdict-data/stardict.db',
    ]
    for p in alt_paths:
        full = os.path.join(os.path.dirname(__file__), p)
        if os.path.exists(full):
            db_path = full
            print(f"找到数据库: {db_path}")
            break

conn = sqlite3.connect(db_path)

# 表结构
cursor = conn.execute('PRAGMA table_info(stardict)')
cols = [r for r in cursor.fetchall()]
print('\n表结构 (stardict):')
for c in cols:
    print(f'  {c[1]:20} {c[2]:15}')

total = conn.execute('SELECT COUNT(*) FROM stardict').fetchone()[0]
print(f'\n总词条: {total}')

# 各字段非空数
print('\n各字段非空统计:')
for c in cols:
    name = c[1]
    if name == 'id':
        continue
    notnull = conn.execute('SELECT COUNT(*) FROM stardict WHERE %s IS NOT NULL AND %s != ""' % (name, name)).fetchone()[0]
    if notnull > 0:
        print(f'  {name:20} 非空: {notnull} ({notnull*100//total}%)')

# 前3条样本
print('\n--- 前3条样本 (只显示非空字段) ---')
for r in conn.execute('SELECT * FROM stardict LIMIT 3'):
    for i, name in enumerate([c[1] for c in cols]):
        val = r[i]
        if val:
            s = str(val)[:200]
            try:
                print(f'  {name}: {s}')
            except:
                print(f'  {name}: [encoding error] {s.encode("utf-8", errors="replace")[:200]}')
    print()

# 检查 exchange 字段包含什么（这个字段通常有单词变形）
exch_rows = conn.execute('SELECT word, exchange FROM stardict WHERE exchange IS NOT NULL AND exchange != "" LIMIT 5').fetchall()
if exch_rows:
    print('\n--- exchange 字段样本 ---')
    for r in exch_rows:
        print(f'  {r[0]}: {r[1][:200]}')

conn.close()
