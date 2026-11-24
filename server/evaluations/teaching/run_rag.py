"""Live, read-only retrieval evaluation. Requires configured isolated demo services.

Runs 50 fixed queries. No synthetic scores, no teacher acceptance estimate.
"""
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.db.database import async_session
from app.core.config import get_settings
from app.services.teaching_agent import TeachingTools, MissingEvidence, PROMPT_VERSION


async def main():
    settings = get_settings()
    if settings.MYSQL_DATABASE != 'elearning_agent_dev' or settings.MILVUS_DATABASE != 'elearning_agent_demo':
        raise RuntimeError('Live evaluation requires the isolated demo databases')
    folder = Path(__file__).resolve().parent
    raw = (folder / 'rag_cases.json').read_bytes()
    cases = json.loads(raw)
    rows = []
    for case in cases:
        started = time.monotonic()
        task = SimpleNamespace(teacher_id=70001, class_id=case.get('class_id', 80001))
        citations, error = [], None
        async with async_session() as db:
            try:
                citations = await TeachingTools(db, task).search_materials(case['query'])
            except (MissingEvidence, PermissionError) as exc:
                error = type(exc).__name__
        expected = case['page']
        matched = (not citations) if expected is None else any(
            c['document_id'] == '90001' and c['page'] == expected for c in citations)
        rows.append({'id': case['id'], 'matched': matched, 'error': error,
                     'latency_ms': round((time.monotonic()-started)*1000),
                     'citations': [{k: c[k] for k in ('id', 'document_id', 'page', 'version')} for c in citations]})
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'dataset_sha256': hashlib.sha256(raw).hexdigest(),
        'prompt_version': PROMPT_VERSION, 'embedding_model': settings.EMBEDDING_MODEL,
        'case_count': len(rows), 'retrieval_match_rate': sum(r['matched'] for r in rows)/len(rows),
        'median_latency_ms': statistics.median(r['latency_ms'] for r in rows),
        'teacher_acceptance': None, 'cost': None, 'baseline_comparison': None, 'rows': rows}
    output = Path(__file__).resolve().parents[2] / 'output' / 'teaching-rag-report.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {output}; {sum(r["matched"] for r in rows)}/{len(rows)} retrieval assertions matched')


if __name__ == '__main__':
    asyncio.run(main())
