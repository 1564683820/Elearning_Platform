#!/usr/bin/env python3
"""
基于 ECDICT 的自动出题脚本（路径 B）

从 dict_word + stage_word 读取数据，为每个阶段的单词生成多种类型题目，
批量写入 question_bank 表（主库 elearningtest）。

生成的题型（对齐 question_bank.type）：
  type=1  单词选择题（英译中）— 显示英文单词，选中文释义
  type=2  单词选择题（中译英）— 显示中文释义，选英文单词
  type=4  短语语法题 — 从定义中提取例句，选词填空
  type=5  句子翻译题 — 显示英文句子，选中文释义

用法：
    # 为所有阶段生成（默认每阶段 3000 词）
    python scripts/generate_questions.py

    # 为指定阶段生成，每阶段 5000 词
    python scripts/generate_questions.py --stage 5 --words-per-stage 5000

    # 跳过已存在的题目（不覆盖已有数据）
    python scripts/generate_questions.py --skip-exist

    # 仅生成某几种题型
    python scripts/generate_questions.py --types 1,2

数据流：
  elearnword.dict_word  ──词义提取──▶  candidate_words
  elearnword.stage_word ──阶段筛选──▶  stage_word_ids
       │                                     │
       └─────────── JOIN ─────────────────────┘
                         │
                         ▼
             生成题目（每词 2~3 题）
                         │
                         ▼
           elearningtest.question_bank  ◀── 批量 INSERT
"""
import argparse
import random
import re
import sys
import time
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

from app.core.config import get_settings

# ── 题型常量 ──────────────────────────────────
TYPE_EN2CN = 1  # 英译中：英文 → 中文释义
TYPE_CN2EN = 2  # 中译英：中文释义 → 英文
TYPE_GRAMMAR = 4  # 短语语法：例句选词填空
TYPE_TRANSLATE = 5  # 句子翻译：英文句子 → 中文释义

# ── 配置 ───────────────────────────────────────
BATCH_SIZE = 500          # 每批插入条数
DISTRACTOR_COUNT = 3      # 每道题的干扰项数量（共 4 个选项）
MAX_DEFINITION_LEN = 500  # 定义做填空题的最大字符数
MIN_STAGE_WORDS = 20      # 阶段最少单词数（不足则跳过该阶段出题）


def log(msg: str):
    """带时间戳的日志输出"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def extract_first_cn_meaning(translation: str) -> str:
    """
    从 ECDICT 的中文释义中提取第一条有意义的短释义。

    ECDICT 的翻译格式如：
      "n. 苹果；苹果树"
      "vt. 放弃；遗弃；离开"
      "adj. 重要的；有意义的；显著的"
      "abandon 了；[法] 遗弃"
    取第一个分号/句号前的纯中文部分，去除非中文字符开头的词性标注。
    同时剥离 [xxx] 类别标签（如 [网络] [地名] [化] 等）。
    """
    if not translation:
        return ""

    # 去掉开头的词性标记，如 "n. ", "vt. ", "adj. ", "adv. " 等
    cleaned = re.sub(r'^[a-zA-Z]+\.\s*', '', translation.strip())
    # 如果清理后以英文开头，说明整段都是英文/特殊内容，跳过
    if cleaned and cleaned[0].isascii() and cleaned[0].isalpha():
        return ""

    # 剥离所有 [xxx] 类别标签（可能出现在任何位置）
    # 如 "[网络]现象"、"n. 1. [网络]现象"、"放弃；[法] 遗弃"、"[地名][国家]杜布纳"
    cleaned = re.sub(r'\s*\[[^\[\]]*\]\s*', ' ', cleaned).strip()
    # 压缩多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # 取第一个定义（分号/句号/逗号分隔）
    for sep in ['；', ';', '。', '. ', ', ']:
        if sep in cleaned:
            cleaned = cleaned.split(sep)[0].strip()
            break

    # 去掉尾部的括号注释如（正式）【医】
    cleaned = re.sub(r'[（(][^）)]*[）)]$', '', cleaned).strip()

    # 过滤：纯英文、太短、含特殊字符的视为无效
    if len(cleaned) < 2:
        return ""
    # 检查是否含有中文字符
    if not re.search(r'[\u4e00-\u9fff]', cleaned):
        return ""
    # 检查是否包含特殊符号（化学式、乱码等）
    if re.search(r'[{}#$^_~]', cleaned):
        return ""

    return cleaned


def extract_example_sentence(definition: str, word: str) -> str | None:
    """
    从英文定义中提取或构造一个例句。

    ECDICT 的 definition 格式通常为：
      "a feeling of being grateful 感谢之情；感激"
    如果定义中包含单词本身，直接使用；
    如果不含，则构造 "The word '{word}' means {definition}." 句型。
    """
    if not definition:
        return None
    if len(definition) > MAX_DEFINITION_LEN:
        definition = definition[:MAX_DEFINITION_LEN]

    # 去除中文部分
    eng_part = re.sub(r'[\u4e00-\u9fff（）()，,。.；;：:！!？?]+', '', definition).strip()
    if len(eng_part) < 10:
        return None

    word_lower = word.lower()

    # 如果定义中包含单词本身，直接使用定义片段
    if word_lower in eng_part.lower():
        # 尝试找到包含该单词的句子（以句号结束）
        sentences = re.split(r'(?<=[.!?])\s+', eng_part)
        for s in sentences:
            if word_lower in s.lower():
                s = s.strip()
                if not s.endswith('.'):
                    s += '.'
                return s
        return eng_part.strip()

    # 定义中不含单词 → 构造 "The word '{word}' means {definition}." 句型
    # 清理定义开头的词性标记
    cleaned_def = re.sub(r'^[a-zA-Z]+\.?\s*', '', eng_part).strip()
    # 如果清理后内容太短，跳过
    if len(cleaned_def) < 10:
        # 直接用 definition 的英文部分（去掉中文）
        cleaned_def = eng_part.strip()
        cleaned_def = re.sub(r'^[a-zA-Z]+\.?\s*', '', cleaned_def).strip()
        if len(cleaned_def) < 10:
            return None

    # 如果清理后以英文小写单词开头，首字母大写
    if cleaned_def and cleaned_def[0].islower():
        cleaned_def = cleaned_def[0].upper() + cleaned_def[1:]

    # 确保以句号结尾
    if not cleaned_def.endswith('.'):
        cleaned_def += '.'

    sentence = f"{cleaned_def} The word \"{word}\" is used to describe this concept."
    return sentence


def escape_sql(val):
    """转义 SQL 字符串值"""
    if val is None:
        return "NULL"
    s = str(val)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\0", "\\0")
    return "'" + s + "'"


def json_escape(val):
    """将 Python 值转为 JSON 字符串（用于 content 字段）"""
    import json
    return escape_sql(json.dumps(val, ensure_ascii=False))


def assign_difficulty(stage: int, master_order: int, total_in_stage: int) -> int:
    """
    根据单词在阶段内的掌握顺序位置分配难度。
    前 1/3 → difficulty=1（基础）, 中 1/3 → 2（进阶）, 后 1/3 → 3（挑战）
    同时考虑阶段因素：小学（stage=1）整体难度 1-2
    """
    if stage == 1:
        # 小学阶段最高难度 2
        ratio = master_order / max(total_in_stage, 1)
        if ratio <= 0.5:
            return 1
        else:
            return 2
    else:
        ratio = master_order / max(total_in_stage, 1)
        if ratio <= 0.33:
            return 1
        elif ratio <= 0.67:
            return 2
        else:
            return 3


def get_question_type_description(q_type: int) -> str:
    """题型中文描述"""
    desc = {1: "英译中", 2: "中译英", 4: "短语语法", 5: "句子翻译"}
    return desc.get(q_type, "其他")


# ═══════════════════════════════════════════════════
# 核心：从 ECDICT 单词生成题目
# ═══════════════════════════════════════════════════

def load_stage_words(words_engine, main_engine, stage: int, words_per_stage: int):
    """
    加载指定阶段的有效单词列表。
    从 stage_word 读取（阶段 1-4）。
    
    返回: list[dict] — 每个元素包含 word_id, word, translation, definition, master_order
    """
    sql = text("""
        SELECT 
            dw.id, dw.word, dw.translation, dw.definition,
            sw.mastery_order
        FROM stage_word sw
        JOIN dict_word dw ON sw.word_id = dw.id
        WHERE sw.stage = :stage
          AND dw.translation IS NOT NULL
          AND dw.translation != ''
          AND dw.translation NOT LIKE '[%'
          AND ASCII(dw.word) BETWEEN 97 AND 122
          AND dw.word NOT LIKE '% %'
          AND dw.word NOT LIKE '-%'
          AND dw.word NOT LIKE '%%/%%'
          -- 质量门槛：排除低频词和生僻词
          AND (
              dw.collins > 0
              OR (dw.bnc > 0 AND dw.bnc < 15000)
              OR dw.oxford = 1
              OR (dw.frq > 0 AND dw.frq < 15000)
          )
        ORDER BY sw.mastery_order ASC
        LIMIT :limit
    """)
    params = {"stage": stage, "limit": words_per_stage}

    with words_engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        word_id, word, translation, definition, master_order = row
        cn_meaning = extract_first_cn_meaning(translation)
        if not cn_meaning:
            continue
        results.append({
            "word_id": word_id,
            "word": word,
            "translation": translation,
            "cn_meaning": cn_meaning,
            "definition": definition or "",
            "master_order": master_order or 0,
        })

    return results


def build_distractor_pool(words_engine, stage: int):
    """
    为指定阶段构建干扰项池。
    从 stage_word 读取（阶段 1-4）。
    
    返回: list[dict] — 每个元素包含 word, cn_meaning, word_id
    """
    # 所有阶段共用干扰项池（无阶段过滤）
    if stage == 0:
        sql = text("""
            SELECT 
                dw.id, dw.word, dw.translation
            FROM dict_word dw
            WHERE dw.translation IS NOT NULL
              AND dw.translation != ''
              AND dw.translation NOT LIKE '[%'
              AND ASCII(dw.word) BETWEEN 97 AND 122
              AND dw.word NOT LIKE '% %'
              -- 质量门槛：排除低频词和生僻词
              AND (
                  dw.collins > 0
                  OR (dw.bnc > 0 AND dw.bnc < 15000)
                  OR dw.oxford = 1
                  OR (dw.frq > 0 AND dw.frq < 15000)
              )
            ORDER BY dw.frq ASC
        """)
    else:
        sql = text("""
            SELECT 
                dw.id, dw.word, dw.translation
            FROM stage_word sw
            JOIN dict_word dw ON sw.word_id = dw.id
            WHERE sw.stage = :stage
              AND dw.translation IS NOT NULL
              AND dw.translation != ''
              AND dw.translation NOT LIKE '[%'
              AND ASCII(dw.word) BETWEEN 97 AND 122
              AND dw.word NOT LIKE '% %'
              -- 质量门槛：排除低频词和生僻词
              AND (
                  dw.collins > 0
                  OR (dw.bnc > 0 AND dw.bnc < 15000)
                  OR dw.oxford = 1
                  OR (dw.frq > 0 AND dw.frq < 15000)
              )
            ORDER BY dw.frq ASC
        """)

    with words_engine.connect() as conn:
        rows = conn.execute(sql, {"stage": stage}).fetchall()

    pool = []
    for row in rows:
        word_id, word, translation = row
        cn = extract_first_cn_meaning(translation)
        if cn:
            pool.append({"word_id": word_id, "word": word, "cn_meaning": cn})

    return pool


def pick_distractors(pool: list[dict], correct_item: dict, count: int = DISTRACTOR_COUNT) -> list[dict]:
    """
    从干扰项池中随机选取 count 个不同的干扰项。
    如果池子不够大，用 None 填充。
    """
    # 先过滤掉与正确答案相同或过于相似的内容
    candidates = [
        item for item in pool
        if item["word_id"] != correct_item["word_id"]
        and item["cn_meaning"] != correct_item["cn_meaning"]
        and item["word"].lower() != correct_item["word"].lower()
    ]

    # 去重：确保中文释义不重复
    seen_meanings = {correct_item["cn_meaning"]}
    unique_candidates = []
    for c in candidates:
        if c["cn_meaning"] not in seen_meanings:
            seen_meanings.add(c["cn_meaning"])
            unique_candidates.append(c)

    if len(unique_candidates) < count:
        return []

    selected = random.sample(unique_candidates, min(count, len(unique_candidates)))
    return selected


def generate_questions_for_word(word_info: dict, distractor_pool: list[dict],
                                 q_types: list[int]) -> list[dict]:
    """
    为一个单词生成题目。
    
    返回: list[dict] — 每个 dict 对应一条 question_bank 记录
    """
    questions = []

    word = word_info["word"]
    cn_meaning = word_info["cn_meaning"]
    word_id = word_info["word_id"]
    master_order = word_info["master_order"]
    definition = word_info["definition"]

    # ── Type 1: 英译中 ──
    if TYPE_EN2CN in q_types:
        distractors = pick_distractors(distractor_pool, word_info)
        if len(distractors) == DISTRACTOR_COUNT:
            options = [d["cn_meaning"] for d in distractors]
            correct_idx = random.randint(0, DISTRACTOR_COUNT)
            options.insert(correct_idx, cn_meaning)

            # 从 translation 中取完整的释义作为解析
            explanation = f"「{word}」{word_info['translation']}"

            questions.append({
                "type": TYPE_EN2CN,
                "difficulty": 0,  # 下文中再统一填充
                "content": {
                    "stem": f'"{word}" 的中文意思是？',
                    "options": options,
                    "answer": correct_idx,
                    "explanation": explanation.strip(),
                    "knowledge_point": word,
                },
                "word_id": word_id,
            })

    # ── Type 2: 中译英 ──
    if TYPE_CN2EN in q_types:
        distractors = pick_distractors(distractor_pool, word_info, DISTRACTOR_COUNT)
        if len(distractors) == DISTRACTOR_COUNT:
            options = [d["word"] for d in distractors]
            correct_idx = random.randint(0, DISTRACTOR_COUNT)
            options.insert(correct_idx, word)

            explanation = f"「{word}」{word_info['translation']}"

            questions.append({
                "type": TYPE_CN2EN,
                "difficulty": 0,
                "content": {
                    "stem": f'"{cn_meaning}" 对应的英文单词是？',
                    "options": options,
                    "answer": correct_idx,
                    "explanation": explanation.strip(),
                    "knowledge_point": word,
                },
                "word_id": word_id,
            })

    # ── Type 5: 句子翻译（英文句子 → 选中文释义）──
    if TYPE_TRANSLATE in q_types and definition:
        example = extract_example_sentence(definition, word)
        if example:
            distractors = pick_distractors(distractor_pool, word_info, DISTRACTOR_COUNT)
            if len(distractors) == DISTRACTOR_COUNT:
                cn_options = [d["cn_meaning"] for d in distractors]
                correct_idx = random.randint(0, DISTRACTOR_COUNT)
                cn_options.insert(correct_idx, cn_meaning)

                explanation = f"「{word}」{word_info['translation']}"

                questions.append({
                    "type": TYPE_TRANSLATE,
                    "difficulty": 0,
                    "content": {
                        "stem": f"请翻译以下句子：{example}",
                        "options": cn_options,
                        "answer": correct_idx,
                        "explanation": explanation.strip(),
                        "knowledge_point": word,
                        "sentence": example,
                    },
                    "word_id": word_id,
                })

    # ── Type 4: 短语语法（例句选词填空）──
    if TYPE_GRAMMAR in q_types and definition:
        example = extract_example_sentence(definition, word)
        if example:
            # 将 word 替换为 ______
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            stem = pattern.sub("______", example, count=1)

            # 干扰项：从同阶段单词池中选 3 个
            distractors = pick_distractors(distractor_pool, word_info, DISTRACTOR_COUNT)
            if len(distractors) == DISTRACTOR_COUNT:
                options = [d["word"] for d in distractors]
                correct_idx = random.randint(0, DISTRACTOR_COUNT)
                options.insert(correct_idx, word)

                explanation = f"答案：{word}。{word_info['translation']}"

                questions.append({
                    "type": TYPE_GRAMMAR,
                    "difficulty": 0,
                    "content": {
                        "stem": f"请选择正确的单词填入空白处：{stem}",
                        "options": options,
                        "answer": correct_idx,
                        "explanation": explanation.strip(),
                        "knowledge_point": word,
                        "sentence": example,
                    },
                    "word_id": word_id,
                })

    return questions


def insert_questions(main_engine, stage: int, all_questions: list[dict],
                      total_in_stage: int, skip_exist: bool):
    """
    批量插入题目到 question_bank 表。
    """
    if not all_questions:
        log(f"  阶段 {stage}：没有可插入的题目")
        return

    # 填充 difficulty
    for i, q in enumerate(all_questions):
        q["difficulty"] = assign_difficulty(stage, i, len(all_questions))

    batch_values = []
    inserted = 0
    skipped = 0
    start_time = time.time()

    for q in all_questions:
        content_json = json_escape(q["content"])
        difficulty = q["difficulty"]
        word_id = q["word_id"]
        q_type = q["type"]

        source_str = f"ECDICT自动生成-{get_question_type_description(q_type)}"

        if skip_exist:
            # 先检查是否已存在（相同 stage + type + word_id）
            check_sql = text(
                "SELECT id FROM question_bank WHERE stage = :stage AND type = :type AND word_id = :word_id LIMIT 1"
            )
            with main_engine.connect() as chk_conn:
                existing = chk_conn.execute(
                    check_sql,
                    {"stage": stage, "type": q_type, "word_id": word_id}
                ).fetchone()
                if existing:
                    skipped += 1
                    continue

        batch_values.append(
            f"({stage},{q_type},{difficulty},{content_json},{escape_sql(source_str)},'',NULL,{word_id},1)"
        )

        if len(batch_values) >= BATCH_SIZE:
            inserted += _flush_batch(main_engine, batch_values)
            batch_values = []
            elapsed = time.time() - start_time
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"\r  已插入: {inserted} 题, 跳过: {skipped}, 速度: {rate:.0f}题/秒",
                  end="", flush=True)

    # 剩余批次
    if batch_values:
        inserted += _flush_batch(main_engine, batch_values)

    elapsed = time.time() - start_time
    print()
    log(f"  阶段 {stage} 完成：插入 {inserted} 题, 跳过 {skipped}（已有）, "
        f"耗时 {elapsed:.1f}s")


def _flush_batch(main_engine, batch_values: list[str]) -> int:
    """执行一批 INSERT"""
    sql = (
        "INSERT IGNORE INTO question_bank "
        "(stage, type, difficulty, content, source, audio_url, reading_id, word_id, is_active) VALUES "
        + ",".join(batch_values) + ";"
    )
    try:
        with main_engine.connect() as conn:
            conn.exec_driver_sql(sql)
            conn.commit()
        return len(batch_values)
    except Exception as e:
        log(f"  批次写入失败: {e}")
        # 逐条重试
        success = 0
        for single_val in batch_values:
            single_sql = (
                "INSERT IGNORE INTO question_bank "
                "(stage, type, difficulty, content, source, audio_url, reading_id, word_id, is_active) VALUES "
                + single_val + ";"
            )
            try:
                with main_engine.connect() as conn:
                    conn.exec_driver_sql(single_sql)
                    conn.commit()
                success += 1
            except Exception:
                pass
        return success


def count_existing(main_engine, stage: int) -> dict:
    """查询该阶段已有题量"""
    sql = text("""
        SELECT type, COUNT(*) as cnt
        FROM question_bank
        WHERE stage = :stage
        GROUP BY type
    """)
    with main_engine.connect() as conn:
        rows = conn.execute(sql, {"stage": stage}).fetchall()
    return {row[0]: row[1] for row in rows}


# ═══════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ECDICT 自动出题脚本（路径 B）")
    parser.add_argument("--stage", type=int, default=0,
                        help="学习阶段 1-10（0=所有阶段）")
    parser.add_argument("--words-per-stage", type=int, default=3000,
                        help="每个阶段选取的单词数（默认 3000）")
    parser.add_argument("--types", type=str, default="1,2,4,5",
                        help="题型列表，逗号分隔（1=英译中,2=中译英,4=短语语法,5=句子翻译）")
    parser.add_argument("--skip-exist", action="store_true",
                        help="跳过已存在的题目")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅统计不写入")
    args = parser.parse_args()

    q_types = [int(t.strip()) for t in args.types.split(",") if t.strip().isdigit()]
    if not q_types:
        log("错误：请指定至少一种有效题型")
        sys.exit(1)

    # 阶段 1-4: 从 stage_word 读取单词
    stages = list(range(1, 5)) if args.stage == 0 else [args.stage]

    settings = get_settings()

    # 创建两个数据库的连接
    log("连接数据库...")
    words_engine = create_engine(
        settings.SYNC_WORDS_DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    main_engine = create_engine(
        settings.SYNC_DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )

    random.seed(int(time.time()))

    total_questions = 0

    for stage in stages:
        log(f"\n{'='*60}")
        log(f"阶段 {stage} 开始处理...")

        # 1. 查询已有题量
        existing_counts = count_existing(main_engine, stage)
        if existing_counts:
            log(f"  已有题目: {', '.join(f'type{k}={v}' for k, v in existing_counts.items())}")

        # 2. 加载该阶段的单词
        words = load_stage_words(words_engine, main_engine, stage, args.words_per_stage)
        if len(words) < MIN_STAGE_WORDS:
            log(f"  阶段 {stage} 可用单词不足（{len(words)} < {MIN_STAGE_WORDS}），跳过")
            continue
        log(f"  加载单词: {len(words)} 个")

        # 3. 构建干扰项池（包含该阶段所有可用词，出题时按词过滤）
        distractor_pool = build_distractor_pool(words_engine, stage)
        log(f"  干扰项池: {len(distractor_pool)} 个候选词")

        if len(distractor_pool) < DISTRACTOR_COUNT:
            log(f"  干扰项不足（{len(distractor_pool)} < {DISTRACTOR_COUNT}），跳过")
            continue

        # 4. 为每个单词生成题目
        all_questions = []
        for word_info in words:
            qs = generate_questions_for_word(word_info, distractor_pool, q_types)
            all_questions.extend(qs)

        total_in_stage = len(words)
        log(f"  生成题目: {len(all_questions)} 道（来自 {total_in_stage} 个单词）")

        if args.dry_run:
            log(f"  [DRY RUN] 跳过写入")
        else:
            # 5. 批量插入
            insert_questions(main_engine, stage, all_questions, total_in_stage, args.skip_exist)

        total_questions += len(all_questions)

    log(f"\n{'='*60}")
    log(f"全部完成！共处理 {len(stages)} 个阶段，生成约 {total_questions} 道题目")
    log(f"（实际写入数可能因去重而减少）")

    words_engine.dispose()
    main_engine.dispose()


if __name__ == "__main__":
    main()
