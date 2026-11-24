"""检查数据库Enrichment数据覆盖率"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)

with engine.connect() as conn:
    # 各阶段单词数
    stages = conn.execute(text("SELECT stage, COUNT(*) FROM stage_word GROUP BY stage ORDER BY stage")).fetchall()
    print('各阶段单词数:')
    for s in stages:
        print(f'  阶段{s[0]}: {s[1]}')
    
    # 前100个阶段8单词
    print('\n阶段8(stage=8, CET-4) 前100个单词 enrichment 状态:')
    rows = conn.execute(text("""
        SELECT dw.word, dw.translation,
               CASE WHEN JSON_EXTRACT(dw.detail_json, '$.idiom') IS NOT NULL THEN 1 ELSE 0 END as has_idiom,
               CASE WHEN JSON_EXTRACT(dw.detail_json, '$.example') IS NOT NULL THEN 1 ELSE 0 END as has_example
        FROM dict_word dw
        JOIN stage_word sw ON dw.id = sw.word_id
        WHERE sw.stage = 8
        ORDER BY sw.mastery_order
        LIMIT 100
    """)).fetchall()
    
    has = sum(1 for r in rows if r[2])
    has_ex = sum(1 for r in rows if r[3])
    
    # 近义词状态
    rows_syno = conn.execute(text("""
        SELECT ws.word_id, dw.word
        FROM word_synonyms ws
        JOIN dict_word dw ON ws.word_id = dw.id
        JOIN stage_word sw ON dw.id = sw.word_id
        WHERE sw.stage = 8
        GROUP BY ws.word_id, dw.word
        ORDER BY sw.mastery_order
    """)).fetchall()
    syno_word_count = len(rows_syno)
    
    total_stage8 = stages[7][1] if len(stages) > 7 else 0
    
    print(f'  前100个: idiom={has}/100, example={has_ex}/100, 近义词单词={syno_word_count}/{total_stage8}')
    
    if syno_word_count > 0:
        print(f'  有近义词的单词（前20个）:')
        for r in rows_syno[:20]:
            print(f'    {r[1]}')
    
    # 查看synonyms表实际内容
    print(f'\nword_synonyms 表总记录数:')
    syno_total = conn.execute(text("SELECT COUNT(*) FROM word_synonyms")).scalar() or 0
    print(f'  {syno_total} 条记录')
    if syno_total > 0:
        syno_rows = conn.execute(text("""
            SELECT dw.word, ws.synonym_word, ws.tag, ws.usage_desc
            FROM word_synonyms ws
            JOIN dict_word dw ON ws.word_id = dw.id
            LIMIT 10
        """)).fetchall()
        for r in syno_rows:
            print(f'    {r[0]} -> {r[1]} ({r[2]}: {r[3][:40]})')

engine.dispose()
