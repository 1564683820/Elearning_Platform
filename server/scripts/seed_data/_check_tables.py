"""检查 dict_root 和 dict_word_root 表结构"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
e = create_engine(s.SYNC_WORDS_DATABASE_URL, echo=False)

with e.connect() as c:
    # 检查表结构
    for tbl in ['dict_root', 'dict_word_root', 'word_synonyms']:
        cols = c.execute(text(f'SHOW COLUMNS FROM {tbl}')).fetchall()
        print(f'\n=== {tbl} 表结构 ===')
        for col in cols:
            print(f'  {col[0]:20} {col[1]:20}')

    # 查看 dict_root 数据
    rcnt = c.execute(text('SELECT COUNT(*) FROM dict_root')).scalar()
    print(f'\n=== dict_root 共 {rcnt} 条 ===')
    rows = c.execute(text('SELECT * FROM dict_root LIMIT 10')).fetchall()
    for r in rows:
        print(f'  {r}')

    # dict_word_root 数据样例
    wrcnt = c.execute(text('SELECT COUNT(*) FROM dict_word_root')).scalar()
    print(f'\n=== dict_word_root 共 {wrcnt} 条 ===')
    rows = c.execute(text('SELECT * FROM dict_word_root LIMIT 10')).fetchall()
    for r in rows:
        print(f'  {r}')

    # WordSynonym 当前数据
    syncnt = c.execute(text('SELECT COUNT(*) FROM word_synonyms')).scalar()
    print(f'\n=== word_synonyms 共 {syncnt} 条 ===')
    tags = c.execute(text('SELECT tag, COUNT(*) FROM word_synonyms GROUP BY tag')).fetchall()
    for t in tags:
        print(f'  tag={t[0]}: {t[1]}')
    
    # 展示一些 word_synonyms 样例
    print('\n=== word_synonyms 样例 ===')
    rows = c.execute(text('''SELECT ws.id, dw.word, ws.synonym_word, ws.tag, ws.usage_desc
        FROM word_synonyms ws
        JOIN dict_word dw ON dw.id = ws.word_id
        LIMIT 10''')).fetchall()
    for r in rows:
        print(f'  id={r[0]}: {r[1]:15} -> {r[2]:20} tag={r[3]:6} desc={r[4] and r[4][:30]}')

e.dispose()
