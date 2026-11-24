# -*- coding: utf-8 -*-
"""检查阶段8单词数据覆盖"""
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import get_settings

settings = get_settings()
out_path = str(Path(__file__).with_name("_debug_out.txt"))
conn = pymysql.connect(**settings.mysql_connection_kwargs(), database=settings.WORDS_DATABASE)
cur = conn.cursor()

lines = []

# 阶段8 按frq ASC 前30词
cur.execute("""
    SELECT dw.id, dw.word,
           COALESCE(dw.frq,'0') as frq,
           COALESCE((SELECT COUNT(*) FROM dict_word_root WHERE word_id = dw.id),0) as root_cnt,
           COALESCE((SELECT COUNT(*) FROM word_synonyms WHERE word_id = dw.id),0) as syn_cnt
    FROM stage_word sw
    JOIN dict_word dw ON dw.id = sw.word_id
    WHERE sw.stage = 8
    ORDER BY dw.frq ASC
    LIMIT 30
""")
lines.append("=== stage=8 TOP30 (by frq ASC) ===")
lines.append("ID\tWord\t\t\tfrq\troots\tsyns")
for r in cur.fetchall():
    wid, wword, wfrq, rcnt, scnt = r
    wfrq = wfrq if wfrq else '0'
    lines.append("{}\t{:25s}\t{}\t{}\t{}".format(wid, wword, str(wfrq), rcnt, scnt))

# 阶段8 按mastery_order 前30词
cur.execute("""
    SELECT dw.id, dw.word, sw.mastery_order, COALESCE(dw.frq,'0') as frq,
           COALESCE((SELECT COUNT(*) FROM dict_word_root WHERE word_id = dw.id),0) as root_cnt,
           COALESCE((SELECT COUNT(*) FROM word_synonyms WHERE word_id = dw.id),0) as syn_cnt
    FROM stage_word sw
    JOIN dict_word dw ON dw.id = sw.word_id
    WHERE sw.stage = 8
    ORDER BY sw.mastery_order ASC
    LIMIT 30
""")
lines.append("\n=== stage=8 TOP30 (by mastery_order ASC) ===")
lines.append("ID\tWord\t\t\torder\tfrq\troots\tsyns")
for r in cur.fetchall():
    wid, wword, order, wfrq, rcnt, scnt = r
    lines.append("{}\t{:25s}\t{}\t{}\t{}\t{}".format(wid, wword, order, str(wfrq), rcnt, scnt))

# 总统计
cur.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN (SELECT COUNT(*) FROM dict_word_root WHERE word_id = dw.id) > 0 THEN 1 ELSE 0 END) as has_roots,
        SUM(CASE WHEN (SELECT COUNT(*) FROM word_synonyms WHERE word_id = dw.id) > 0 THEN 1 ELSE 0 END) as has_syns
    FROM stage_word sw
    JOIN dict_word dw ON dw.id = sw.word_id
    WHERE sw.stage = 8
""")
r = cur.fetchone()
lines.append("\n=== stage=8 统计 ===")
lines.append("Total: {}".format(r[0]))
lines.append("Has roots: {} ({:.1f}%)".format(r[1], r[1]*100/r[0] if r[0]>0 else 0))
lines.append("Has synonyms: {} ({:.1f}%)".format(r[2], r[2]*100/r[0] if r[0]>0 else 0))

# 所有 synonyms 记录
cur.execute("""
    SELECT ws.word_id, dw.word, ws.synonym_word, ws.tag
    FROM word_synonyms ws
    JOIN dict_word dw ON dw.id = ws.word_id
    LIMIT 40
""")
lines.append("\n=== word_synonyms ===")
for r in cur.fetchall():
    lines.append("  id={} {} -> {} ({})".format(r[0], r[1], r[2], r[3]))

conn.close()

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Done -> " + out_path)
