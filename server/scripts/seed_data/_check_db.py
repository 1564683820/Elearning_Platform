from sqlalchemy import create_engine, text
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import get_settings

s = get_settings()
e = create_engine(s.SYNC_WORDS_DATABASE_URL)
r = e.connect()

# word_synonyms
print("=== word_synonyms ===")
cols = r.execute(text("SHOW COLUMNS FROM word_synonyms")).fetchall()
for c in cols:
    print(f"  {str(c[0]):20} {str(c[1]):20} key={str(c[3]):5} null={str(c[2]):5}")
cnt = r.execute(text("SELECT COUNT(*) FROM word_synonyms")).scalar()
print(f"Rows: {cnt}")
dist = r.execute(text("SELECT COUNT(DISTINCT word_id) FROM word_synonyms")).scalar()
print(f"Distinct words: {dist}")

# dict_word columns
print("\n=== dict_word columns ===")
cols = r.execute(text("SHOW COLUMNS FROM dict_word")).fetchall()
for c in cols:
    print(f"  {str(c[0]):25} {str(c[1]):25} key={str(c[3]):5}")
# check detail_json sample
sample = r.execute(text("SELECT id, word, detail_json FROM dict_word WHERE detail_json IS NOT NULL LIMIT 3")).fetchall()
print(f"\ndetail_json sample ({len(sample)} rows):")
for s in sample:
    print(f"  {s[0]}: {s[1]} -> {str(s[2])[:200]}")

# stages: stage 8 CET-4
print("\n=== Stage 8 coverage ===")
# how many stage 8 words have synonyms
cnt_syn = r.execute(text("""
    SELECT COUNT(DISTINCT sw.word_id) 
    FROM stage_word sw 
    JOIN word_synonyms ws ON sw.word_id = ws.word_id 
    WHERE sw.stage = 8
""")).scalar()
cnt_s8 = r.execute(text("SELECT COUNT(*) FROM stage_word WHERE stage = 8")).scalar()
print(f"Stage 8 words with synonyms: {cnt_syn} / {cnt_s8}")

r.close()
e.dispose()
