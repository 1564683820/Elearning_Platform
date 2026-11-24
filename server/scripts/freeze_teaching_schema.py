"""One-time maintainer utility. Never regenerate an already applied baseline."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects.mysql import dialect
import app.models  # noqa: F401
from app.db.database import Base, WordBase


def main():
    folder = Path(__file__).resolve().parents[1] / 'database' / 'alembic_agent' / 'schema'
    folder.mkdir(parents=True, exist_ok=True)
    for name, metadata in [('main', Base.metadata), ('words', WordBase.metadata)]:
        target = folder / f'{name}.sql'
        if target.exists():
            raise RuntimeError('Frozen schema already exists; add a new migration instead')
        statements = []
        for table in metadata.sorted_tables:
            statements.append(str(CreateTable(table).compile(dialect=dialect())).strip())
            statements.extend(str(CreateIndex(index).compile(dialect=dialect()))
                              for index in sorted(table.indexes, key=lambda i: i.name))
        sql = ';\n'.join(statements) + ';\n'
        target.write_text('\n'.join(line.rstrip() for line in sql.splitlines()) + '\n', encoding='utf-8')
        print(f'{name}: {len(metadata.tables)} tables frozen')


if __name__ == '__main__':
    main()
