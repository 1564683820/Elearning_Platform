"""Child process used only by the durable worker crash regression."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.teaching_worker import execute
from test_teaching_workflow import FakeTools


async def main():
    engine = create_async_engine('sqlite+aiosqlite:///' + Path(sys.argv[1]).as_posix())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    class BlockingTools(FakeTools):
        async def generate(self, state):
            Path(sys.argv[2]).write_text('generation_started', encoding='utf-8')
            await asyncio.sleep(300)
            return await super().generate(state)
    await execute(9007199254740993, sessions, BlockingTools)


if __name__ == '__main__':
    asyncio.run(main())
