"""全局检查：比对 ORM 模型字段 与 MySQL 实际表结构"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect as sa_inspect
from app.db.database import Base
from app.core.config import get_settings

def check_schema():
    engine = create_engine(get_settings().SYNC_DATABASE_URL)
    inspector = sa_inspect(engine)
    
    db_tables = {}
    for table_name in inspector.get_table_names():
        cols = inspector.get_columns(table_name)
        db_tables[table_name] = {c['name'] for c in cols}
    
    # 从 Base metadata 遍历所有 ORM 表
    all_ok = True
    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            print(f"[MISSING TABLE] {table_name}")
            all_ok = False
            continue
        
        orm_cols = {c.name for c in table.columns}
        db_cols = db_tables[table_name]
        missing = orm_cols - db_cols
        extra = db_cols - orm_cols
        
        if missing:
            print(f"[MISSING COLS] {table_name}: {missing}")
            all_ok = False
        elif extra:
            print(f"[EXTRA COLS  ] {table_name}: {extra}")
        else:
            print(f"[OK] {table_name}: {len(orm_cols)} cols match")
    
    if all_ok:
        print("\nAll tables match.")
    else:
        print("\nIssues found.")
    
    engine.dispose()

if __name__ == "__main__":
    check_schema()
