"""检查 MySQL 连接和锁"""
import pymysql

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

settings = get_settings()
conn = pymysql.connect(**settings.mysql_connection_kwargs())
cur = conn.cursor()

print("=== 当前 MySQL 连接 ===")
cur.execute("SHOW FULL PROCESSLIST")
for r in cur.fetchall():
    print(f"  ID={r[0]}  USER={r[1]}  HOST={r[2]}  DB={r[3] or '(none)'}  CMD={r[4]}  TIME={r[5]}s  STATE={r[6] or ''}")
    if r[7]:
        print(f"     SQL: {r[7][:120]}")

print()
print("=== 事务状态 ===")
cur.execute("""
    SELECT trx_id, trx_state, trx_mysql_thread_id, 
           trx_query, trx_rows_locked, trx_lock_structs
    FROM information_schema.INNODB_TRX
""")
for r in cur.fetchall():
    print(f"  trx_id={r[0]} state={r[1]} thread={r[2]} locked_rows={r[4]} locks={r[5]}")
    if r[3]:
        print(f"     query: {r[3][:80]}")

cur.close()
conn.close()
