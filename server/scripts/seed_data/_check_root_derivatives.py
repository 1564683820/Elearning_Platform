"""检查同根词能否生成衍生词"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
e = create_engine(s.SYNC_WORDS_DATABASE_URL, echo=False)

with e.connect() as c:
    # dict_root: root_type 列名
    roots = c.execute(text('''SELECT root, root_type, meaning FROM dict_root ORDER BY root_type, root''')).fetchall()
    print(f'dict_root 共有 {len(roots)} 条:')
    p = sum(1 for r in roots if r[1]=='prefix')
    r2 = sum(1 for r in roots if r[1]=='root')
    s2 = sum(1 for r in roots if r[1]=='suffix')
    print(f'  prefix: {p}, root: {r2}, suffix: {s2}')
    
    # 用同根词方法测试几个示例
    test_words = ['act', 'beauty', 'care', 'nation', 'power', 'science', 'agree']
    test_ids = {}
    for tw in test_words:
        wid = c.execute(text("SELECT id FROM dict_word WHERE word = :w LIMIT 1"), {'w': tw}).scalar()
        if wid:
            test_ids[tw] = wid
    
    if test_ids:
        print(f'\n=== 同根词生成衍生词测试 ===')
        for word, wid in test_ids.items():
            # 找出这个单词关联的根（只用 root 类型，不用 prefix/suffix）
            root_ids = c.execute(text('''SELECT dr.id, dr.root
                FROM dict_word_root dwr
                JOIN dict_root dr ON dr.id = dwr.root_id
                WHERE dwr.word_id = :wid AND dr.root_type = 'root' 
                ORDER BY dr.root'''), {'wid': wid}).fetchall()
            
            if root_ids:
                all_roots = [str(r[0]) for r in root_ids]
                root_names = [r[1] for r in root_ids]
                
                # 找所有同根词（排除自己）
                sibling_words = c.execute(text(f'''
                    SELECT DISTINCT dw.word
                    FROM dict_word_root dwr
                    JOIN dict_word dw ON dw.id = dwr.word_id
                    WHERE dwr.root_id IN ({','.join(all_roots)})
                    AND dw.id != :wid
                    ORDER BY dw.word
                '''), {'wid': wid}).fetchall()
                
                siblings = [r[0] for r in sibling_words]
                print(f'  {word:15} (根: {",".join(root_names)}) -> 衍生: {siblings[:8]}{"..." if len(siblings)>8 else ""}')
            else:
                print(f'  {word:15} -> 无词根关联')

    # 统计覆盖率
    total_words = c.execute(text('SELECT COUNT(*) FROM dict_word')).scalar()
    words_with_root = c.execute(text('''SELECT COUNT(DISTINCT word_id) 
        FROM dict_word_root dwr 
        JOIN dict_root dr ON dr.id = dwr.root_id 
        WHERE dr.root_type = 'root' ''')).scalar()
    print(f'\n=== 覆盖率 ===')
    print(f'dict_word 总单词: {total_words}')
    print(f'有 root 关联的: {words_with_root}')
    print(f'覆盖率: {words_with_root*100//total_words}%')
    
    # 统计哪些词有多个同根词
    multi = c.execute(text('''
        SELECT COUNT(*) FROM (
            SELECT dwr.word_id
            FROM dict_word_root dwr
            JOIN dict_root dr ON dr.id = dwr.root_id
            WHERE dr.root_type = 'root'
            GROUP BY dwr.word_id
            HAVING COUNT(DISTINCT dwr.root_id) >= 1
            AND (SELECT COUNT(DISTINCT dw2.id) FROM dict_word dw2
                 JOIN dict_word_root dwr2 ON dw2.id = dwr2.word_id
                 WHERE dwr2.root_id IN (SELECT DISTINCT dwr3.root_id FROM dict_word_root dwr3 WHERE dwr3.word_id = dwr.word_id)
                 AND dw2.id != dwr.word_id) > 0
        ) t
    ''')).scalar()
    print(f'有同根衍生词的单词: {multi}')
    
e.dispose()
