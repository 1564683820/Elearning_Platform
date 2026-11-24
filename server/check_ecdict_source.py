"""检查 ECDICT 源数据库中的 detail 字段，看是否有词根和近义词数据"""
import sqlite3
import json

conn = sqlite3.connect('scripts/ecdict-data/stardict.db')

# 查看表结构
cursor = conn.execute('PRAGMA table_info(stardict)')
columns = [r[1] for r in cursor.fetchall()]
print('表结构 (stardict):', columns)

# 统计非空 detail 数量
cursor = conn.execute('SELECT COUNT(*) FROM stardict WHERE detail IS NOT NULL AND detail != ""')
print('\n有 detail 数据的行数:', cursor.fetchone()[0])

# 查看一些 detail 样本
print('\n--- 样本 1-5（完整） ---')
cursor = conn.execute('SELECT word, detail FROM stardict WHERE detail IS NOT NULL AND detail != "" LIMIT 5')
for row in cursor.fetchall():
    word = row[0]
    try:
        detail = json.loads(row[1])
        keys = list(detail.keys())
        print(f'{word}: keys={keys}, has root={any("root" in k.lower() or "词根" in k for k in keys)}, has syno={any("syno" in k.lower() or "近义" in k for k in keys)}')
    except:
        print(f'{word}: raw(detail[:150]) = {row[1][:150]}')

# 查看是否有词根相关关键字
print('\n--- 搜索包含 root 的关键词 ---')
cursor = conn.execute("SELECT word, detail FROM stardict WHERE detail LIKE '%root%' OR detail LIKE '%词根%' LIMIT 5")
found = False
for row in cursor.fetchall():
    found = True
    print(f'{row[0]}: {row[1][:200]}')
if not found:
    print('未找到包含 root/词根 的记录')

# 查看是否有近义词相关关键字
print('\n--- 搜索包含 synonym/近义 的关键词 ---')
cursor = conn.execute("SELECT word, detail FROM stardict WHERE (detail LIKE '%synonym%' OR detail LIKE '%近义%') AND length(detail) > 50 LIMIT 5")
found = False
for row in cursor.fetchall():
    found = True
    print(f'{row[0]}: {row[1][:200]}')
if not found:
    print('未找到包含 synonym/近义 的记录')

# 查看单词表总数
cursor = conn.execute('SELECT COUNT(*) FROM stardict')
print(f'\n总词条数: {cursor.fetchone()[0]}')

conn.close()
print('\n检查完成')
