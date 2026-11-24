"""检查 dict_word_root 表能否用于生成衍生词"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
e = create_engine(s.SYNC_WORDS_DATABASE_URL, echo=False)

with e.connect() as c:
    # 查看 dict_word_root 数据样例
    rows = c.execute(text('''SELECT dwr.id, dw.word, dr.root, dr.type, dwr.match_type
        FROM dict_word_root dwr
        JOIN dict_word dw ON dw.id = dwr.word_id
        JOIN dict_root dr ON dr.id = dwr.root_id
        LIMIT 20''')).fetchall()
    print('=== dict_word_root 数据样例 ===')
    for r in rows:
        print(f'  id={r[0]}: word={r[1]:15} root={r[2]:10} type={r[3]:8} match={r[4]}')
    
    # 统计不同类型的匹配数量
    mt = c.execute(text('''SELECT dwr.match_type, dr.type, COUNT(*)
        FROM dict_word_root dwr
        JOIN dict_root dr ON dr.id = dwr.root_id
        GROUP BY dwr.match_type, dr.type
        ORDER BY COUNT(*) DESC''')).fetchall()
    print('\n=== 按匹配类型统计 ===')
    for r in mt:
        print(f'  match_type={r[0]:10} root_type={r[1]:8} count={r[2]}')
    
    # 检查同根词群 - 用词根 "act"、"spect"、"port" 为例
    for root_name in ['act', 'spect', 'port', 'struct', 'dict']:
        rows2 = c.execute(text('''SELECT dw.word, dwr.match_type
            FROM dict_word_root dwr
            JOIN dict_word dw ON dw.id = dwr.word_id
            JOIN dict_root dr ON dr.id = dwr.root_id
            WHERE dr.root = :r AND dr.type = 'root'
            ORDER BY dw.word'''), {'r': root_name}).fetchall()
        print(f'\n===词根 {root_name} 关联的单词（共{len(rows2)}个）===') if root_name == 'act' else None
        if rows2:
            if root_name != 'act':
                print(f'\n===词根 {root_name} 关联的单词（共{len(rows2)}个）===')
            for r in rows2:
                print(f'  {r[0]:15} match={r[1]}')
        else:
            print(f'  无')
    
    # 看总的词根数量和有多个词的词根数量
    total_roots = c.execute(text('''SELECT COUNT(DISTINCT dr.id)
        FROM dict_word_root dwr JOIN dict_root dr ON dr.id = dwr.root_id
        WHERE dr.type = 'root' ''')).scalar()
    multi_roots = c.execute(text('''SELECT COUNT(*) FROM (
        SELECT dr.id, COUNT(DISTINCT dw.id) as cnt
        FROM dict_word_root dwr
        JOIN dict_word dw ON dw.id = dwr.word_id
        JOIN dict_root dr ON dr.id = dwr.root_id
        WHERE dr.type = 'root'
        GROUP BY dr.id HAVING cnt > 1) t''')).scalar()
    print(f'\n=== 统计 ===')
    print(f'有2个以上词的词根数量: {multi_roots}/{total_roots}')
    
    # 统计 dict_word 中有 exchange 数据的比例
    has_exch = c.execute(text('''SELECT COUNT(*) FROM dict_word WHERE exchange IS NOT NULL AND exchange != '' ''')).scalar()
    total_words = c.execute(text('SELECT COUNT(*) FROM dict_word')).scalar()
    print(f'dict_word 有 exchange: {has_exch}/{total_words}')

    # 看看 word_synonyms 当前数据
    syn_cnt = c.execute(text('SELECT COUNT(*) FROM word_synonyms')).scalar()
    syn_tag = c.execute(text('SELECT tag, COUNT(*) FROM word_synonyms GROUP BY tag')).fetchall()
    print(f'\nword_synonyms 总条数: {syn_cnt}')
    for t in syn_tag:
        print(f'  tag={t[0]}: {t[1]}')
    
    # 检查 ECDICT 数据库中的 translation 字段是否包含近义词信息
    # 有些词典会在翻译字段里面包含 "近义词" 信息
    print('\n--- 检查 MySQL 中 dict_word 的 detail_json ---')
    has_detail = c.execute(text('''SELECT COUNT(*) FROM dict_word WHERE detail_json IS NOT NULL AND detail_json != '{}' ''')).scalar()
    print(f'有 detail_json 的单词: {has_detail}/{total_words}')

e.dispose()
