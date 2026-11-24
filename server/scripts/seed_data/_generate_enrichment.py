#!/usr/bin/env python3
"""
批量生成近义词 + 衍生词数据，通过 LLM API 扩展 enrichment 数据。

从数据库中读取指定阶段的单词，分批调用 LLM 生成：
1. 近义词辨析数据（tag=区别）→ synonyms.json
2. 衍生词/派生词（tag=衍生）→ synonyms.json（与近义词共用格式）
3. 记忆金句（可选）→ mnemonics.json

然后保存到 seed_data 目录，可用 import_enrichment.py 导入。

用法:
    python scripts/seed_data/_generate_enrichment.py [--count 500] [--stage 8] [--include-mnemonics] [--skip-synonyms] [--skip-derivatives]
"""
import json
import sys
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy import create_engine, text
from app.core.config import get_settings

SCRIPT_DIR = Path(__file__).parent
SEED_DIR = SCRIPT_DIR
BATCH_SIZE_MNEMONICS = 30   # 每批生成记忆金句的单词数
BATCH_SIZE_SYNONYMS = 20    # 每批生成近义词的单词数
BATCH_SIZE_DERIVATIVES = 20 # 每批生成衍生词的单词数


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def call_llm(prompt: str, llm_config: dict) -> str:
    """调用 LLM API 获取回答"""
    api_base = llm_config["api_base"]
    api_key = llm_config["api_key"]
    model = llm_config["model"]

    if not api_key:
        log("错误: LLM_API_KEY 未配置")
        return ""

    try:
        resp = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 8000,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            log(f"LLM API 调用失败: {resp.status_code} {resp.text[:300]}")
            return ""
        content = resp.json()["choices"][0]["message"]["content"]
        # 清理代码块标记
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()
    except Exception as e:
        log(f"LLM 调用异常: {e}")
        return ""


def generate_mnemonics_batch(words_batch, llm_config):
    """为一组单词生成记忆金句"""
    word_list = "\n".join(f"- {w['word']} ({w.get('translation','')[:50]})" for w in words_batch)
    
    prompt = f"""你是一位专业的英语单词记忆法专家。请为以下每个单词创作一个"巧记口诀"（记忆辅助）。

要求：
1. 可以结合谐音、联想、词根拆分、故事等任何记忆技巧
2. 用中文写"巧记辅助"（50字以内）
3. 提供一个英文例句（10个词左右，适合学习者水平）
4. 提供英文例句的中文翻译
5. 尽量有趣、好记、有画面感

输出格式为 JSON 数组，不要加任何额外说明：
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
    content = call_llm(prompt, llm_config)
    if not content:
        return []
    
    try:
        results = json.loads(content)
        if isinstance(results, list):
            log(f"  成功生成 {len(results)} 条记忆金句")
            return results
    except json.JSONDecodeError as e:
        log(f"  JSON 解析失败: {e}")
        # 尝试从文本中提取 JSON
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                results = json.loads(match.group())
                if isinstance(results, list):
                    log(f"  恢复解析: {len(results)} 条")
                    return results
            except:
                pass
    return []


def generate_synonyms_batch(words_batch, llm_config):
    """为一组单词生成近义词辨析数据"""
    word_list = "\n".join(f"- {w['word']} ({w.get('translation','')[:50]})" for w in words_batch)
    
    prompt = f"""你是一位英语词汇学专家。请为以下每个单词配 2 个常用近义词（同义词），并写出辨析区别。

要求：
1. 每个单词配 2 个近义词，不要配原词本身
2. 近义词必须是真正的同义词/近义词，不要编造
3. 用中文写辨析（40字以内），说明两个词的微妙区别
4. tag 统一用 "区别"
5. 如果没有合适的近义词，就配 1 个

输出格式为 JSON 数组，不要加任何额外说明：
[
  {{
    "word": "abandon",
    "synonyms": [
      {{"word": "desert", "tag": "区别", "usage_desc": "abandon 强调彻底放弃控制或责任；desert 强调违背承诺或职责离开"}},
      {{"word": "quit", "tag": "区别", "usage_desc": "quit 多指主动停止做某事；abandon 更强调被迫放弃"}}
    ]
  }}
]

单词列表：
{word_list}
"""
    content = call_llm(prompt, llm_config)
    if not content:
        return []
    
    try:
        results = json.loads(content)
        if isinstance(results, list):
            log(f"  成功生成 {len(results)} 组近义词")
            return results
    except json.JSONDecodeError as e:
        log(f"  JSON 解析失败: {e}")
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                results = json.loads(match.group())
                if isinstance(results, list):
                    log(f"  恢复解析: {len(results)} 组")
                    return results
            except:
                pass
    return []


def generate_derivatives_batch(words_batch, llm_config):
    """为一组单词生成衍生词/派生词数据"""
    word_list = "\n".join(f"- {w['word']} ({w.get('translation','')[:50]})" for w in words_batch)
    
    prompt = f"""你是一位英语构词法专家。请为以下每个单词列出其常用"衍生词/派生词"（word family）。

要求：
1. 列出该单词最常见的 3-5 个衍生词（如动词→名词/形容词/副词等不同词形）
2. 每条用中文简注词性和衍生关系（15字以内）
3. tag 统一用 "衍生"
4. 如果是复合词或同源异形词也可以包含
5. 确保衍生的关系真实可靠

输出格式为 JSON 数组，不要加任何额外说明：
[
  {{
    "word": "act",
    "synonyms": [
      {{"word": "action", "tag": "衍生", "usage_desc": "名词，act 的名词形式，指行动"}},
      {{"word": "active", "tag": "衍生", "usage_desc": "形容词，指活跃积极的"}},
      {{"word": "activity", "tag": "衍生", "usage_desc": "名词，指活动"}},
      {{"word": "actor", "tag": "衍生", "usage_desc": "名词，指演员（act+or）"}},
      {{"word": "activate", "tag": "衍生", "usage_desc": "动词，使激活"}}
    ]
  }}
]

单词列表：
{word_list}
"""
    content = call_llm(prompt, llm_config)
    if not content:
        return []
    
    try:
        results = json.loads(content)
        if isinstance(results, list):
            log(f"  成功生成 {len(results)} 组衍生词")
            return results
    except json.JSONDecodeError as e:
        log(f"  JSON 解析失败: {e}")
        import re
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                results = json.loads(match.group())
                if isinstance(results, list):
                    log(f"  恢复解析: {len(results)} 组")
                    return results
            except:
                pass
    return []


def load_existing_json(filepath: Path):
    """加载已有的 JSON 文件，如果不存在则返回空列表"""
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(filepath: Path, data: list, merge_existing: bool = True):
    """保存 JSON 文件，可选择合并已有的数据"""
    existing = {}
    if merge_existing and filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            for item in existing_data:
                existing[item["word"].lower()] = item
            log(f"已加载 {len(existing)} 条现有数据")
        except:
            pass
    
    for item in data:
        key = item["word"].lower() if isinstance(item, dict) else ""
        if key:
            existing[key] = item
    
    result = list(existing.values())
    # 按 word 排序
    result.sort(key=lambda x: x.get("word", "").lower())
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log(f"已保存 {len(result)} 条数据到 {filepath.name}")
    return len(result)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="批量生成近义词和衍生词数据")
    parser.add_argument("--count", type=int, default=500, help="要处理的单词数量")
    parser.add_argument("--stage", type=int, default=8, help="学习阶段（默认8=CET-4）")
    parser.add_argument("--include-mnemonics", action="store_true", help="同时生成记忆金句（默认跳过）")
    parser.add_argument("--skip-synonyms", action="store_true", help="跳过近义词生成")
    parser.add_argument("--skip-derivatives", action="store_true", help="跳过衍生词生成")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.SYNC_WORDS_DATABASE_URL, echo=False)
    
    llm_config = {
        "api_base": settings.LLM_API_BASE,
        "api_key": settings.LLM_API_KEY,
        "model": settings.LLM_MODEL,
    }
    log(f"LLM 配置: model={llm_config['model']}, base={llm_config['api_base']}")

    # 读取单词列表（从指定阶段取前 N 个）
    log(f"从阶段 {args.stage} 获取前 {args.count} 个单词...")
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT dw.word, dw.translation
            FROM dict_word dw
            JOIN stage_word sw ON dw.id = sw.word_id
            WHERE sw.stage = {args.stage}
            ORDER BY sw.mastery_order
            LIMIT {args.count}
        """)).fetchall()
    
    words = [{"word": r[0], "translation": r[1] or ""} for r in rows]
    log(f"待处理单词数: {len(words)}")
    
    if not words:
        log("没有找到单词，退出")
        return

    # ===== 生成记忆金句（可选） =====
    if args.include_mnemonics:
        log("\n=== 开始生成记忆金句 ===")
        all_mnemonics = []
        
        mnemonic_path = SEED_DIR / "mnemonics.json"
        existing_mnemonics = load_existing_json(mnemonic_path)
        existing_words = {m["word"].lower() for m in existing_mnemonics}
        log(f"已有 {len(existing_words)} 个单词的记忆金句")
        
        words_needed = [w for w in words if w["word"].lower() not in existing_words]
        log(f"需要生成记忆金句的单词: {len(words_needed)} 个")
        
        if words_needed:
            for i in range(0, len(words_needed), BATCH_SIZE_MNEMONICS):
                batch = words_needed[i:i + BATCH_SIZE_MNEMONICS]
                log(f"  记忆金句批次 {i//BATCH_SIZE_MNEMONICS + 1}/{(len(words_needed)-1)//BATCH_SIZE_MNEMONICS + 1} ({len(batch)} 个单词)...")
                
                results = generate_mnemonics_batch(batch, llm_config)
                if results:
                    all_mnemonics.extend(results)
                    log(f"  本批成功: {len(results)} 条")
                else:
                    log(f"  本批失败，重试一次...")
                    time.sleep(2)
                    results = generate_mnemonics_batch(batch, llm_config)
                    if results:
                        all_mnemonics.extend(results)
                
                if all_mnemonics:
                    save_json(mnemonic_path, all_mnemonics, merge_existing=True)
                
                if i + BATCH_SIZE_MNEMONICS < len(words_needed):
                    time.sleep(1)
            
            log(f"记忆金句生成完成: 新增 {len(all_mnemonics)} 条")
        else:
            log("所有单词已有记忆金句，跳过")
    else:
        log("跳过记忆金句生成")

    # ===== 生成近义词（tag=区别） =====
    if not args.skip_synonyms:
        log("\n=== 开始生成近义词数据 ===")
        all_synonyms = []
        
        syn_path = SEED_DIR / "synonyms.json"
        existing_data = load_existing_json(syn_path)
        # 只检查已有 tag="区别" 的单词
        existing_syn_words = set()
        for item in existing_data:
            for syn in item.get("synonyms", []):
                if syn.get("tag") == "区别":
                    existing_syn_words.add(item["word"].lower())
                    break
        log(f"已有 {len(existing_syn_words)} 个单词含有近义词（区别）")
        
        words_needed = [w for w in words if w["word"].lower() not in existing_syn_words]
        log(f"需要生成近义词的单词: {len(words_needed)} 个")
        
        if words_needed:
            for i in range(0, len(words_needed), BATCH_SIZE_SYNONYMS):
                batch = words_needed[i:i + BATCH_SIZE_SYNONYMS]
                log(f"  近义词批次 {i//BATCH_SIZE_SYNONYMS + 1}/{(len(words_needed)-1)//BATCH_SIZE_SYNONYMS + 1} ({len(batch)} 个单词)...")
                
                results = generate_synonyms_batch(batch, llm_config)
                if results:
                    all_synonyms.extend(results)
                    log(f"  本批成功: {len(results)} 组")
                else:
                    log(f"  本批失败，重试一次...")
                    time.sleep(2)
                    results = generate_synonyms_batch(batch, llm_config)
                    if results:
                        all_synonyms.extend(results)
                
                if all_synonyms:
                    save_json(syn_path, all_synonyms, merge_existing=True)
                
                if i + BATCH_SIZE_SYNONYMS < len(words_needed):
                    time.sleep(1)
            
            log(f"近义词生成完成: 新增 {len(all_synonyms)} 组")
        else:
            log("所有目标单词已有近义词，跳过")
    else:
        log("跳过近义词生成")

    # ===== 生成衍生词（tag=衍生） =====
    if not args.skip_derivatives:
        log("\n=== 开始生成衍生词数据 ===")
        all_derivatives = []
        
        deriv_path = SEED_DIR / "synonyms.json"
        existing_data = load_existing_json(deriv_path)
        # 只检查已有 tag="衍生" 的单词
        existing_deriv_words = set()
        for item in existing_data:
            for syn in item.get("synonyms", []):
                if syn.get("tag") == "衍生":
                    existing_deriv_words.add(item["word"].lower())
                    break
        log(f"已有 {len(existing_deriv_words)} 个单词含有衍生词")
        
        words_needed = [w for w in words if w["word"].lower() not in existing_deriv_words]
        log(f"需要生成衍生词的单词: {len(words_needed)} 个")
        
        if words_needed:
            for i in range(0, len(words_needed), BATCH_SIZE_DERIVATIVES):
                batch = words_needed[i:i + BATCH_SIZE_DERIVATIVES]
                log(f"  衍生词批次 {i//BATCH_SIZE_DERIVATIVES + 1}/{(len(words_needed)-1)//BATCH_SIZE_DERIVATIVES + 1} ({len(batch)} 个单词)...")
                
                results = generate_derivatives_batch(batch, llm_config)
                if results:
                    all_derivatives.extend(results)
                    log(f"  本批成功: {len(results)} 组")
                else:
                    log(f"  本批失败，重试一次...")
                    time.sleep(2)
                    results = generate_derivatives_batch(batch, llm_config)
                    if results:
                        all_derivatives.extend(results)
                
                if all_derivatives:
                    save_json(deriv_path, all_derivatives, merge_existing=True)
                
                if i + BATCH_SIZE_DERIVATIVES < len(words_needed):
                    time.sleep(1)
            
            log(f"衍生词生成完成: 新增 {len(all_derivatives)} 组")
        else:
            log("所有目标单词已有衍生词，跳过")
    else:
        log("跳过衍生词生成")

    engine.dispose()
    log("\n=== 全部完成! ===")
    log(f"近义词/衍生词文件: {SEED_DIR / 'synonyms.json'}")
    log("运行以下命令导入数据到数据库:")
    log("  python scripts/import_enrichment.py")


if __name__ == "__main__":
    main()
