"""Incrementally reconcile one teacher's exam-question vectors from committed SQL rows."""
import argparse
import asyncio
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.database import async_session
from app.models.exam_models import TeacherExam
from app.services.embedding_service import EmbeddingService
from app.services.exam_knowledge import EXAM_QUESTION_SOURCE, exam_question_chunks
from app.services.exam_source_text import read_original_questions


COLLECTION = EmbeddingService.TEACHER_DOCUMENTS


def _query(existing_filter: str) -> list[dict]:
    client = EmbeddingService.get_milvus_client()
    if not client.has_collection(COLLECTION):
        raise RuntimeError("现有教师文档集合未初始化")
    return client.query(
        collection_name=COLLECTION, filter=existing_filter, limit=8192,
        output_fields=["id", "chunk_id"], consistency_level="Strong",
    )


async def reconcile_exam(db: AsyncSession, exam: TeacherExam, *, apply: bool) -> tuple[int, int]:
    scope = f'source_type == "{EXAM_QUESTION_SOURCE}" and user_id == {exam.teacher_id} and source_id == {exam.id}'
    originals = await read_original_questions(db, [exam])
    expected = {chunk["chunk_id"]: chunk for chunk in exam_question_chunks(exam, originals.get(exam.id))}
    existing = await run_in_threadpool(_query, scope)
    kept = set()
    stale = []
    for row in sorted(existing, key=lambda row: row["id"]):
        chunk = row["chunk_id"]
        if chunk in expected and chunk not in kept:
            kept.add(chunk)
        else:
            stale.append(row["id"])
    missing = [chunk for key, chunk in expected.items() if key not in kept]
    if apply:
        for start in range(0, len(missing), 32):
            batch = missing[start:start + 32]
            indexed = await EmbeddingService.index_chunks_batch(db, COLLECTION, batch, user_id=exam.teacher_id)
            if indexed != len(batch):
                raise RuntimeError("新题目索引写入不完整，原索引保留")
        if missing:
            visible = {row["chunk_id"] for row in await run_in_threadpool(_query, scope)}
            if not expected.keys() <= visible:
                raise RuntimeError("新题目索引尚不可读，原索引保留，可重试")
        for start in range(0, len(stale), 128):
            ids = ",".join(str(identity) for identity in stale[start:start + 128])
            if not await run_in_threadpool(EmbeddingService.delete_by_expr, COLLECTION, f"{scope} and id in [{ids}]"):
                raise RuntimeError("旧题目索引清理失败，可重试")
    return len(missing), len(stale)


async def main(teacher_id: int, after: int, apply: bool) -> int:
    totals = Counter(exams=0, added=0, retired=0, failed=0)
    while True:
        async with async_session() as db:
            exams = list(await db.scalars(select(TeacherExam).where(
                TeacherExam.teacher_id == teacher_id, TeacherExam.id > after,
            ).order_by(TeacherExam.id).limit(30)))
        if not exams:
            break
        for exam in exams:
            async with async_session() as db:
                try:
                    added, retired = await reconcile_exam(db, exam, apply=apply)
                    totals.update(exams=1, added=added, retired=retired)
                except Exception as error:
                    totals.update(failed=1)
                    print(f"exam_id={exam.id}: {error}")
        after = exams[-1].id
    print(f"{'apply' if apply else 'preview'}: {dict(totals)}")
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-id", type=int, required=True)
    parser.add_argument("--after", type=int, default=0, help="从指定试卷 ID 之后继续")
    parser.add_argument("--apply", action="store_true", help="执行写入，默认只预览变化数量")
    args = parser.parse_args()
    if args.teacher_id <= 0 or args.after < 0:
        parser.error("teacher-id 必须大于 0，after 不得为负数")
    raise SystemExit(asyncio.run(main(args.teacher_id, args.after, args.apply)))
