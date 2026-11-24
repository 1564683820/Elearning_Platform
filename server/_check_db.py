"""检查数据库实际数据"""
import sys, os
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from app.core.config import get_settings

engine = create_engine(get_settings().SYNC_WORDS_DATABASE_URL, echo=False)
with engine.connect() as conn:
    r1 = conn.execute(text('SELECT stage, COUNT(*) as cnt FROM stage_word GROUP BY stage ORDER BY stage'))
    print('=== stage_word 阶段分布 ===')
    for row in r1:
        print(f'  stage={row[0]}: {row[1]} words')
    
    r2 = conn.execute(text("""
        SELECT 
            CASE 
                WHEN frq=0 THEN 'frq=0' 
                WHEN frq>0 AND frq<1000 THEN '1-999' 
                WHEN frq>=1000 AND frq<5000 THEN '1000-4999' 
                WHEN frq>=5000 AND frq<10000 THEN '5000-9999' 
                WHEN frq>=10000 AND frq<30000 THEN '10000-29999' 
                WHEN frq>=30000 THEN '30000+' 
            END AS frq_range, 
            COUNT(*) 
        FROM dict_word 
        GROUP BY frq_range 
        ORDER BY MIN(frq)
    """))
    print('\n=== dict_word frq 分布 ===')
    for row in r2:
        print(f'  {row[0]}: {row[1]} words')
    
    r3 = conn.execute(text('SELECT COUNT(*) FROM dict_word'))
    print(f'\n=== dict_word 总数: {r3.scalar()} ===')
    
    r4 = conn.execute(text("""
        SELECT stage, COUNT(*) as cnt 
        FROM stage_word 
        WHERE stage IN (8,9,10,11,12,13) 
        GROUP BY stage ORDER BY stage
    """))
    print('\n=== stage_word 高中级阶段分布 ===')
    for row in r4:
        print(f'  stage={row[0]}: {row[1]} words')

engine.dispose()

engine2 = create_engine(get_settings().SYNC_DATABASE_URL, echo=False)
with engine2.connect() as conn2:
    r5 = conn2.execute(text('SELECT stage, COUNT(*) as cnt FROM question_bank GROUP BY stage ORDER BY stage'))
    print('\n=== question_bank 阶段分布 ===')
    for row in r5:
        print(f'  stage={row[0]}: {row[1]} questions')
    
    r6 = conn2.execute(text("""
        SELECT stage, type, COUNT(*) 
        FROM question_bank 
        WHERE type IN (1,2) 
        GROUP BY stage, type 
        ORDER BY stage, type
    """))
    print('\n=== question_bank 单词题型(type 1,2) 分阶段 ===')
    for row in r6:
        print(f'  stage={row[0]}, type={row[1]}: {row[2]} questions')
    
    r7 = conn2.execute(text('SELECT VERSION()'))
    print(f'\nMySQL版本: {r7.scalar()}')
    
    # Check question_bank total
    r8 = conn2.execute(text('SELECT COUNT(*) FROM question_bank'))
    print(f'\nquestion_bank 总数: {r8.scalar()}')

engine2.dispose()
