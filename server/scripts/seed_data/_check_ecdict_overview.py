"""ECDICT 数据库全面概览"""
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

DB = "scripts/ecdict-data/stardict.db"

conn = sqlite3.connect(DB)

# 表结构
cursor = conn.execute('PRAGMA table_info(stardict)')
cols = [r for r in cursor.fetchall()]
print("=== ECDICT 表结构 ===")
for c in cols:
    print(f"  {c[1]:15} {c[2]:10} notnull={c[3]}")

total = conn.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
print(f"\n总词条数: {total:,}")

# 各字段非空统计
print(f"\n{'='*60}")
print(f"{'字段名':15} {'非空数':>10} {'占比':>6}")
print(f"{'='*60}")
for c in cols:
    name = c[1]
    if name == "id":
        continue
    cnt = conn.execute(f'SELECT COUNT(*) FROM stardict WHERE {name} IS NOT NULL AND {name} != ""').fetchone()[0]
    pct = cnt * 100 // total
    print(f"  {name:15} {cnt:>10,}  {pct:>4}%")

# 常见单词的exchange预览
print(f"\n\n=== exchange 字段格式示例（常见单词）===")
common = ["act", "be", "big", "book", "care", "child", "city", "come", "day", "do",
          "drink", "easy", "eat", "fly", "friend", "get", "give", "go", "good", "happy",
          "hard", "have", "help", "house", "kind", "know", "large", "learn", "leave", "love",
          "make", "man", "many", "much", "name", "new", "old", "one", "other", "own",
          "part", "people", "place", "play", "put", "read", "right", "run", "say", "see",
          "seem", "show", "small", "start", "take", "tell", "thing", "think", "time", "try",
          "turn", "use", "want", "way", "will", "work", "world", "write", "year"]
sample = []
for w in common:
    r = conn.execute("SELECT word, exchange FROM stardict WHERE word=? AND exchange IS NOT NULL AND exchange != ''", (w,)).fetchone()
    if r:
        sample.append(r)
print(f"共找到 {len(sample)}/{len(common)} 个常见单词有 exchange 数据\n")
for w, e in sample[:20]:
    print(f"  {w:10} => {e}")
print("  ...")
for w, e in sample[-10:]:
    print(f"  {w:10} => {e}")

# exchange 字段的格式分析 - 列出所有不同的前缀/类型
print(f"\n\n=== exchange 字段前缀类型统计分析 ===")
exchange_types = {}
for r in conn.execute("SELECT exchange FROM stardict WHERE exchange IS NOT NULL AND exchange != '' LIMIT 5000").fetchall():
    parts = r[0].split(",")
    for p in parts:
        p = p.strip()
        if ":" in p:
            key = p.split(":")[0].strip()
            exchange_types[key] = exchange_types.get(key, 0) + 1
sorted_types = sorted(exchange_types.items(), key=lambda x: -x[1])
for k, v in sorted_types:
    print(f"  {k:10} -> {v:>6} 次出现")

# 完整示例
print(f"\n\n=== 完整 exchange 示例（前15条）===")
for r in conn.execute("SELECT word, exchange FROM stardict WHERE exchange IS NOT NULL AND exchange != '' LIMIT 15").fetchall():
    print(f"  {r[0]:15} => {r[1]}")

# 看几条detail有数据的
print(f"\n\n=== detail 字段非空数据（前5条）===")
for r in conn.execute("SELECT word, detail FROM stardict WHERE detail IS NOT NULL AND detail != '' LIMIT 5").fetchall():
    print(f"  {r[0]}: {str(r[1])[:300]}")

conn.close()
