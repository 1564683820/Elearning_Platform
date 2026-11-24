"""查询试卷5的answer字段实际值"""
import asyncio, sys, json
sys.path.insert(0, '.')
from app.core.config import get_settings

async def main():
    s = get_settings()
    import aiomysql
    conn = await aiomysql.connect(
        host=s.MYSQL_HOST, port=s.MYSQL_PORT,
        user=s.MYSQL_USER, password=s.MYSQL_PASSWORD,
        db=s.MYSQL_DATABASE
    )
    cur = await conn.cursor(aiomysql.DictCursor)
    
    await cur.execute(
        "SELECT id, title, questions, total_score, status FROM teacher_exam WHERE id = 5"
    )
    row = await cur.fetchone()
    if not row:
        print("ID=5 不存在")
        return
    print(f"考试: id={row['id']} title={row['title']!r} status={row['status']!r} total_score={row['total_score']}")
    qs = json.loads(row['questions'])
    print(f"\n=== questions JSON ({len(qs)} 题) ===")
    for i, q in enumerate(qs):
        ans = (q.get('answer') or q.get('correct_answer') or '?').strip().upper()
        opts = q.get('options', [])
        stem = str(q.get('stem','') or q.get('question_text',''))[:50]
        print(f"  [{i}] sort={q.get('sort_order',i+1)} answer={ans!r} stem={stem!r}")
        if isinstance(opts, list):
            for j, opt in enumerate(opts[:6]):
                label = chr(65 + j)
                print(f"         {label}: {str(opt)[:30]!r}")
        else:
            print(f"       options(直接值)={opts!r}")
    
    # question_regions
    print("\n=== question_regions ===")
    from app.services.printable_sheet_generator import generate_printable_sheet
    q_list = [{"number": i+1, "options": 4} for i in range(5)]
    sheet = generate_printable_sheet(5, q_list, 4, "A4", 200, "test", "class")
    regions = sheet['coordinate_config']['question_regions']
    for r in regions:
        print(f"  Q{r['number']}: x={r['x']} y={r['y']}")
    
    await cur.close()
    conn.close()

if __name__ == '__main__':
    asyncio.run(main())
