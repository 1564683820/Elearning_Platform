"""检查阶段8(英语四级)已同步的单词数据"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)

with engine.connect() as conn:
    # 阶段8单词数
    total = conn.execute(text("""
        SELECT COUNT(*) FROM stage_word WHERE stage = 8
    """)).scalar() or 0
    
    # 前20个单词及已有enrichment
    rows = conn.execute(text("""
        SELECT dw.word, dw.translation, 
               JSON_EXTRACT(dw.detail_json, '$.idiom') IS NOT NULL as has_idiom,
               dw.detail_json
        FROM dict_word dw
        JOIN stage_word sw ON dw.id = sw.word_id
        WHERE sw.stage = 8
        ORDER BY sw.mastery_order
        LIMIT 20
    """)).fetchall()
    
    print(f'阶段8(stage=8, 英语四级) 总单词数: {total}')
    print(f'前20个单词:')
    for r in rows:
        has_d = '✅' if r[2] else '❌'
        print(f'  {r[0]:20s}  idiom={has_d}')
    
    # 阶段8中已有idiom的数量
    with_idiom = conn.execute(text("""
        SELECT COUNT(*) FROM dict_word dw
        JOIN stage_word sw ON dw.id = sw.word_id
        WHERE sw.stage = 8 AND JSON_EXTRACT(dw.detail_json, '$.idiom') IS NOT NULL
    """)).scalar() or 0
    print(f'\n阶段8有记忆金句(idiom): {with_idiom}/{total} ({with_idiom/total*100:.1f}%)')
    
    # 阶段8中已有example的数量
    with_example = conn.execute(text("""
        SELECT COUNT(*) FROM dict_word dw
        JOIN stage_word sw ON dw.id = sw.word_id
        WHERE sw.stage = 8 AND JSON_EXTRACT(dw.detail_json, '$.example') IS NOT NULL
    """)).scalar() or 0
    print(f'阶段8有例句(example): {with_example}/{total} ({with_example/total*100:.1f}%)')
    
    # 近义词
    syno_count = conn.execute(text("""
        SELECT COUNT(DISTINCT ws.word_id) FROM word_synonyms ws
        JOIN stage_word sw ON ws.word_id = sw.word_id
        WHERE sw.stage = 8
    """)).scalar() or 0
    print(f'阶段8有近义词(synonyms)的单词: {syno_count}/{total} ({syno_count/total*100:.1f}%)')
    
    # 词根
    root_count = conn.execute(text("""
        SELECT COUNT(DISTINCT wr.word_id) FROM dict_word_root wr
        JOIN stage_word sw ON wr.word_id = sw.word_id
        WHERE sw.stage = 8
    """)).scalar() or 0
    print(f'阶段8有词根关联的单词: {root_count}/{total} ({root_count/total*100:.1f}%)')

engine.dispose()
