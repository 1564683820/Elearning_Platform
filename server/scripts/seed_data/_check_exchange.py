"""检查 ECDICT exchange 字段是否能用于衍生词"""
import sqlite3, sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join(os.path.dirname(__file__), '..', 'ecdict-data', 'stardict.db')
conn = sqlite3.connect(db_path)

# 常见单词，查看 exchange 数据
words = ['act','action','active','activity','actor','accept','agree','beauty',
         'beautiful','care','careful','create','creation','decide','decision',
         'educate','education','employ','employer','employee','employment',
         'express','expression','fail','failure','happy','happiness',
         'help','helpful','helpless','imagine','imagination','happy','happiness',
         'important','importance','invent','invention','inventor','kind','kindness',
         'lead','leader','leadership','manage','management','manager','move','movement',
         'nation','national','nationality','nature','natural','operate','operation',
         'organize','organization','perform','performance','performer','person','personal',
         'pollute','pollution','possible','possibility','power','powerful','produce',
         'production','product','productive','protect','protection','protect',
         'react','reaction','read','reader','real','reality','realize','rely','reliable',
         'respond','response','responsible','responsibility','safe','safety',
         'satisfy','satisfaction','science','scientist','select','selection',
         'succeed','success','successful','suggest','suggestion','teach','teacher',
         'translate','translation','translator','understand','use','useful','useless',
         'vary','various','variety','visit','visitor','wonder','wonderful',
         'warm','warmth','weak','weaken','weakness','wide','widen','width']

print("=== exchange 字段分析 ===")
found = 0
for w in words:
    r = conn.execute('SELECT word, exchange FROM stardict WHERE word=? AND exchange IS NOT NULL AND exchange!=""', (w,)).fetchone()
    if r:
        found += 1
        print(f'  {r[0]:20} => {r[1]}')

print(f'\n{found}/{len(words)} 个单词有 exchange 数据')

# exchange 格式解析
print('\n\n=== exchange 字段格式说明 ===')
# 看一些格式多样的样本
rows = conn.execute('SELECT word, exchange FROM stardict WHERE exchange LIKE "%p:/%" AND exchange LIKE "%d:/%" LIMIT 5').fetchall()
print('含 p:/d: 的样本（过去式/过去分词）:')
for r in rows:
    print(f'  {r[0]:20} => {r[1]}')

# 统计 exchange 中不同字符的分布
print('\n\n=== exchange 中出现的标记字符统计 ===')
all_tags = {}
total_exch = conn.execute('SELECT COUNT(*) FROM stardict WHERE exchange IS NOT NULL AND exchange!=""').fetchone()[0]
print(f'有 exchange 数据: {total_exch} 条')

# 查看从 ECDICT 导入到 MySQL 的 dict_word 数据情况
print('\n\n=== 现有 MySQL 数据库（elearnword）状态 ===')
try:
    from sqlalchemy import create_engine, text
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app.core.config import get_settings
    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)
    with engine.connect() as conn2:
        total = conn2.execute(text("SELECT COUNT(*) FROM dict_word")).scalar()
        print(f'dict_word 总单词: {total}')
        
        syn = conn2.execute(text("SELECT COUNT(*) FROM word_synonyms")).scalar()
        print(f'word_synonyms 总条数: {syn}')
        
        # 按 tag 分组统计
        tags = conn2.execute(text("SELECT tag, COUNT(*) FROM word_synonyms GROUP BY tag")).fetchall()
        for t in tags:
            print(f'  tag={t[0]}: {t[1]} 条')
        
        # 看下 dict_word 中 exchange 字段情况
        has_exch = conn2.execute(text("SELECT COUNT(*) FROM dict_word WHERE exchange IS NOT NULL AND exchange != ''")).scalar()
        print(f'dict_word 有 exchange 数据: {has_exch}')
        
        # 查询 dict_word_root 表
        wrcount = conn2.execute(text("SELECT COUNT(*) FROM dict_word_root")).scalar()
        rootcount = conn2.execute(text("SELECT COUNT(*) FROM dict_root")).scalar()
        print(f'dict_word_root: {wrcount} 条')
        print(f'dict_root: {rootcount} 条')
except Exception as e:
    print(f'数据库查询失败: {e}')

conn.close()
