#!/usr/bin/env python3
"""
清理 stage_word 中的低质量词汇（词缀、化学名、编号、短语等）

ECDICT 的考试标签（如 cet6）过宽泛，包含了大量非标准词汇。
本脚本将它们从 stage_word 中移除。

用法:
    python scripts/cleanup_low_quality_words.py [--stage 9] [--dry-run]

参数:
    --stage    指定要清理的阶段（默认 9 = 英语六级）
    --dry-run  仅预览将要删除的行数，不实际执行删除
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings

# 尝试加载 tqdm，没有则用简单回退
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable=None, **kwargs):
        """简易 tqdm 回退"""
        if iterable is None:
            class _DummyCtx:
                def update(self, n=1): pass
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return _DummyCtx()
        if isinstance(iterable, (list, tuple, range)):
            total = len(iterable)
            for i, item in enumerate(iterable):
                if total > 0 and (i + 1) % max(1, total // 20) == 0:
                    _log(f"  进度: {i+1}/{total} ({100*(i+1)//total}%)")
                yield item
        else:
            yield from iterable
    tqdm.__name__ = "tqdm(fallback)"

    class _TqdmContext:
        def __init__(self, total=0, desc=""):
            self.total = total
            self.desc = desc
            self.n = 0
        def update(self, n=1):
            self.n += n
            if self.total > 0 and self.n % max(1, self.total // 20) == 0:
                _log(f"  {self.desc}: {self.n}/{self.total} ({100*self.n//self.total}%)")
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass


def _log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# 过滤条件定义：(标签, SQL条件, 说明)
FILTERS = [
    ("以 '-' 开头（词缀）",          "dw.word LIKE '-%'",           "词缀"),
    ("以数字开头（化学名/编号）",      "dw.word REGEXP '^[0-9]'",     "化学名/编号"),
    ("不含英文字母",                  "dw.word NOT REGEXP '[a-zA-Z]'", "纯符号/数字"),
    ("不以字母开头（如 .idd）",        "dw.word NOT REGEXP '^[a-zA-Z]'", "非字母开头"),
    ("含空格（多词短语）",            "dw.word LIKE '% %'",           "短语"),
    ("含 '/' 符号",                   "dw.word LIKE '%/%'",           "带斜杠"),
    ("大写开头（地名/人名等专有名词）", "dw.word REGEXP BINARY '^[A-Z]'", "地名/人名"),
    ("低频词汇（frq >= 30000）",      "dw.frq >= 30000",              "低频词"),
    ("翻译含 [网络] 标签",             "dw.translation LIKE '%[网络]%'",  "网络词汇"),
    ("翻译含 [人名] 标签",             "dw.translation LIKE '%[人名]%'",  "人名"),
    ("翻译含 [地名] 标签",             "dw.translation LIKE '%[地名]%'",  "地名"),
]


def _make_delete_where() -> str:
    """生成 DELETE 的 WHERE 子句（OR 连接所有条件）"""
    return " OR ".join(f"({cond})" for _, cond, _ in FILTERS)


def _make_delete_sql() -> str:
    return f"""
        DELETE sw FROM stage_word sw
        JOIN dict_word dw ON dw.id = sw.word_id
        WHERE sw.stage = :stage AND ({_make_delete_where()})
    """


def _make_count_sql(for_label: str = None) -> str:
    """生成单个条件的 COUNT 或所有条件的 UNION COUNT"""
    if for_label:
        _, cond, _ = next(f for f in FILTERS if f[0] == for_label)
        return f"""
            SELECT COUNT(DISTINCT sw.word_id)
            FROM stage_word sw
            JOIN dict_word dw ON dw.id = sw.word_id
            WHERE sw.stage = :stage AND {cond}
        """
    else:
        where = _make_delete_where()
        return f"""
            SELECT COUNT(DISTINCT sw.word_id)
            FROM stage_word sw
            JOIN dict_word dw ON dw.id = sw.word_id
            WHERE sw.stage = :stage AND ({where})
        """


def main():
    parser = argparse.ArgumentParser(description="清理 stage_word 低质量词汇")
    parser.add_argument("--stage", type=int, default=9, help="要清理的阶段（默认 9）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际删除")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)
    stage = args.stage
    dry_run = args.dry_run

    _log(f"{'[预览模式] ' if dry_run else ''}开始清理 stage={stage} 的低质量词汇...")

    with engine.connect() as conn:
        # 1. 总览
        total = conn.execute(
            text("SELECT COUNT(*) FROM stage_word WHERE stage = :stage"),
            {"stage": stage},
        ).scalar() or 0
        _log(f"stage={stage} 总数: {total}")
        if total == 0:
            _log("没有记录，退出")
            engine.dispose()
            return

        # 2. 按类别统计（每类单独 COUNT，可能有重叠）
        _log("统计各类噪声...")
        per_label_counts = {}
        for label, _, desc in tqdm(FILTERS, desc="分析类别"):
            cnt = conn.execute(
                text(_make_count_sql(for_label=label)),
                {"stage": stage},
            ).scalar() or 0
            per_label_counts[label] = cnt
            _log(f"  待删除 - {label}: {cnt}")

        # 3. 用 UNION 去重后准确统计总数
        _log("计算去重后的待删除总数...")
        dedup_count = conn.execute(
            text(_make_count_sql()),
            {"stage": stage},
        ).scalar() or 0
        _log(f"去重后共需删除: {dedup_count}/{total} ({dedup_count * 100 / total:.1f}%)")

        # 4. 展示前 30 个示例
        if dedup_count > 0:
            samples = conn.execute(
                text(f"""
                    SELECT dw.word, dw.tag, dw.bnc, dw.frq
                    FROM stage_word sw
                    JOIN dict_word dw ON dw.id = sw.word_id
                    WHERE sw.stage = :stage AND ({_make_delete_where()})
                    GROUP BY dw.word, dw.tag, dw.bnc, dw.frq
                    ORDER BY dw.word
                    LIMIT 30
                """),
                {"stage": stage},
            ).fetchall()
            _log(f"前 {len(samples)} 个待删除单词:")
            for row in samples:
                _log(f"  {row[0]:45s} tag={str(row[1]):20s} bnc={row[2]} frq={row[3]}")

        # 5. 执行删除
        if not dry_run and dedup_count > 0:
            _log("正在执行删除...")
            result = conn.execute(text(_make_delete_sql()), {"stage": stage})
            conn.commit()
            _log(f"删除完成，共移除 {result.rowcount} 条记录")
        elif dry_run and dedup_count > 0:
            _log("预览模式，未执行删除。如需删除请去掉 --dry-run")
        else:
            _log("没有需要删除的记录")

    engine.dispose()
    _log("完成!")


if __name__ == "__main__":
    main()
