#!/usr/bin/env python3
"""
通过 LLM API 批量生成记忆金句（巧记口诀）并导入 database

用法:
    python scripts/generate_mnemonics.py [--count 100] [--stage 2]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings

SCRIPT_DIR = Path(__file__).parent
BATCH_SIZE = 50

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def generate_mnemonics_for_words(words_batch, llm_config):
    """调用 LLM API 为一组单词生成记忆金句"""
    import requests

    api_base = llm_config["api_base"]
    api_key = llm_config["api_key"]
    model = llm_config["model"]

    if not api_key:
        log("LLM_API_KEY 为空，使用内置简易记忆方法")
        return fallback_mnemonics(words_batch)

    word_list = "\n".join(f"- {w['word']} ({w.get('translation','')[:30]})" for w in words_batch)
    
    prompt = f"""你是一位专业的英语单词记忆法专家。请为以下每个单词创作一个"巧记口诀"（记忆辅助）。

要求：
1. 可以结合谐音、联想、词根拆分、故事等任何记忆技巧
2. 用中文写"巧记辅助"（50字以内）
3. 提供一个英文例句（10个词左右，适合学习者水平）
4. 提供英文例句的中文翻译
5. 尽量有趣、好记、有画面感

输出格式为 JSON 数组：
[
  {{
    "word": "abandon",
    "mnemonic": "a+band+on → 一个乐队在台上，主唱却放弃了 → 放弃",
    "en": "Don't abandon your dreams.",
    "zh": "不要放弃你的梦想。"
  }}
]

单词列表：
{word_list}
"""

    try:
        resp = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4000,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            log(f"LLM API 调用失败: {resp.status_code} {resp.text[:200]}")
            return fallback_mnemonics(words_batch)
        
        content = resp.json()["choices"][0]["message"]["content"]
        # 提取 JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        results = json.loads(content)
        log(f"LLM 生成成功: {len(results)} 条")
        return results
    except Exception as e:
        log(f"LLM 调用异常: {e}")
        return fallback_mnemonics(words_batch)


def fallback_mnemonics(words_batch):
    """LLM 不可用时返回基于词根的简易助记"""
    fn = Path(__file__).parent / "seed_data" / "mnemonics_base.json"
    if fn.exists():
        with open(fn, "r", encoding="utf-8") as f:
            builtin = json.load(f)
        builtin_map = {b["word"].lower(): b for b in builtin}
        
        results = []
        for w in words_batch:
            b = builtin_map.get(w["word"].lower())
            if b:
                results.append(b)
            else:
                results.append({
                    "word": w["word"],
                    "mnemonic": f"{w['word']} — {w.get('translation','')[:20]}",
                    "en": f"Please look up '{w['word']}' in your dictionary.",
                    "zh": f"请查词典了解 '{w['word']}' 的用法。",
                })
        log(f"使用内置助记数据: {len(results)} 条（含未匹配的兜底）")
        return results
    return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成并导入记忆金句")
    parser.add_argument("--count", type=int, default=200, help="要处理的单词数量")
    parser.add_argument("--stage", type=int, default=2, help="学习阶段（1=小学, 2=初中, 3=高中, 4=四六级）")
    parser.add_argument("--skip-llm", action="store_true", help="跳过LLM，只使用内置数据")
    parser.add_argument("--word-file", type=str, default="", help="从文件读取单词列表")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)

    # 获取单词列表
    if args.word_file:
        word_file = Path(args.word_file)
        with open(word_file, "r", encoding="utf-8") as f:
            word_texts = [line.strip() for line in f if line.strip()]
        log(f"从文件读取 {len(word_texts)} 个单词")

        # 查询词义
        words_batch = []
        with engine.connect() as conn:
            for wt in word_texts:
                row = conn.execute(
                    text(f"SELECT word, translation FROM dict_word WHERE word = {escape_sql(wt)} LIMIT 1")
                ).fetchone()
                if row:
                    words_batch.append({"word": row[0], "translation": row[1] or ""})
    else:
        # 从指定阶段中取高频词
        log(f"从阶段 {args.stage} 获取前 {args.count} 个高频单词...")
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"""SELECT dw.word, dw.translation
                        FROM dict_word dw
                        JOIN stage_word sw ON dw.id = sw.word_id
                        WHERE sw.stage = {args.stage}
                        ORDER BY sw.mastery_order
                        LIMIT {args.count}""")
            ).fetchall()
            words_batch = [{"word": r[0], "translation": r[1] or ""} for r in rows]

    log(f"待处理单词数: {len(words_batch)}")

    # 查询 word → id 映射
    word_id_map = {}
    with engine.connect() as conn:
        words = conn.execute(text("SELECT id, word FROM dict_word")).fetchall()
        for w in words:
            word_id_map[w[1].lower()] = w[0]

    # 分批生成并导入
    llm_config = {
        "api_base": settings.LLM_API_BASE,
        "api_key": settings.LLM_API_KEY,
        "model": settings.LLM_MODEL,
    }

    use_llm = llm_config["api_key"] and not args.skip_llm
    if use_llm:
        log(f"将使用 LLM (model={llm_config['model']}) 生成记忆金句")
    else:
        log("使用内置助记数据（可在 scripts/seed_data/mnemonics_base.json 中扩展）")

    updated = 0
    for i in range(0, len(words_batch), BATCH_SIZE):
        batch = words_batch[i:i + BATCH_SIZE]
        mnemonics = generate_mnemonics_for_words(batch, llm_config) if use_llm else fallback_mnemonics(batch)

        for m in mnemonics:
            word_text = m.get("word", "")
            word_id = word_id_map.get(word_text.lower())
            if word_id is None:
                continue

            idiom_data = {
                "en": m.get("en", ""),
                "zh": m.get("zh", ""),
                "mnemonic": m.get("mnemonic", ""),
            }
            idiom_json = json.dumps(idiom_data, ensure_ascii=False)

            sql = (
                f"UPDATE dict_word SET "
                f"detail_json = CASE "
                f"  WHEN detail_json IS NULL THEN JSON_OBJECT('idiom', '{escape_json(idiom_json)}') "
                f"  ELSE JSON_SET(detail_json, '$.idiom', '{escape_json(idiom_json)}') "
                f"END "
                f"WHERE id = {word_id};"
            )
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                updated += 1
            except Exception as e:
                pass

        progress = min(i + BATCH_SIZE, len(words_batch))
        log(f"进度: {progress}/{len(words_batch)}, 已更新 {updated} 条")

    log(f"记忆金句导入完成: 共更新 {updated} 个单词")
    engine.dispose()


def escape_sql(val):
    if val is None: return "NULL"
    s = str(val).replace("\\", "\\\\").replace("'", "\\'").replace("\0", "\\0")
    return "'" + s + "'"

def escape_json(val):
    return val.replace("\\", "\\\\").replace("'", "\\'")


if __name__ == "__main__":
    main()
