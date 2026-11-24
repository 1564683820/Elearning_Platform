"""检查 ECDICT detail 字段结构"""
import sqlite3, json

conn = sqlite3.connect('scripts/ecdict-data/stardict.db')

# 看 detail 字段的典型结构
rows = conn.execute('SELECT detail FROM stardict WHERE detail IS NOT NULL AND detail != "" LIMIT 50').fetchall()
keys_count = {}
for row in rows:
    try:
        d = json.loads(row[0])
        for k in d:
            keys_count[k] = keys_count.get(k, 0) + 1
    except:
        pass
print('detail 字段常用key:', json.dumps(keys_count, ensure_ascii=False, indent=2))

# 看包含synonym的近义词
syno_count = conn.execute("SELECT COUNT(*) FROM stardict WHERE detail LIKE '%synonym%' OR detail LIKE '%近义%'").fetchone()[0]
print(f'\n包含近义词的记录: {syno_count}')

# 看样本
if syno_count > 0:
    rows = conn.execute("SELECT word, detail FROM stardict WHERE detail LIKE '%synonym%' LIMIT 5").fetchall()
    for r in rows:
        d = json.loads(r[1])
        syno = d.get('synonym', d.get('近义', ''))
        print(f'  {r[0]}: {json.dumps(syno, ensure_ascii=False)[:200]}')

# 看包含"同义词""辨析"的
other = conn.execute("SELECT COUNT(*) FROM stardict WHERE detail LIKE '%同义%' OR detail LIKE '%辨析%'").fetchone()[0]
print(f'\n包含同义/辨析的记录: {other}')

if other > 0:
    rows = conn.execute("SELECT word, detail FROM stardict WHERE detail LIKE '%同义%' OR detail LIKE '%辨析%' LIMIT 3").fetchall()
    for r in rows:
        print(f'  {r[0]}: {r[1][:300]}')

# 看例句
example_count = conn.execute("SELECT COUNT(*) FROM stardict WHERE detail LIKE '%example%' OR detail LIKE '%例句%'").fetchone()[0]
print(f'\n包含例句的记录: {example_count}')

# 看单词总表大小
total = conn.execute('SELECT COUNT(*) FROM stardict').fetchone()[0]
print(f'\nstardict 总词条数: {total}')
print(f'有 detail 的行数: {conn.execute("SELECT COUNT(*) FROM stardict WHERE detail IS NOT NULL AND detail != \"\" ").fetchone()[0]}')

conn.close()
print(f'\n------\n脚本完成')
