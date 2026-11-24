"""SKILL.md 解析器 — 从 Markdown 文件中提取设计令牌和生成 Agent 提示词片段

支持的 SKILL.md 格式：
  ---
  name: Figma
  description: "..."
  skill_type: ppt           # ppt 或 exam
  colors: {...}
  typography: {...}
  rounded: {...}
  spacing: {...}
  components: {...}
  ---
  ## Overview
  ... (Markdown prose describing design philosophy)

skill_type 说明：
  ppt  - PPT课件设计技能（控制PPT生成的颜色/字体/布局/组件）
  exam - 试卷设计技能（控制试卷排版/题型结构/分值分布/题目格式）
"""

import re
import json
import yaml
import logging

logger = logging.getLogger(__name__)

# Token预算: prompt_snippet 控制在 ~2500 字符以内，避免消耗过多 LLM context
MAX_SNIPPET_CHARS = 2500

# 合法的技能类型
VALID_SKILL_TYPES = {"ppt", "exam"}
QA_SKILL_TYPE = "qa"
MAX_QA_SKILL_BYTES = 48 * 1024


def parse_qa_skill(raw_content: str) -> tuple[str, str]:
    """Read the teacher's Skill metadata without building a model prompt."""
    frontmatter = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", raw_content, re.DOTALL)
    if frontmatter is None:
        raise ValueError("请在文件开头的 YAML 配置中填写 name")
    try:
        metadata = yaml.safe_load(frontmatter.group(1))
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError("无法解析文件开头的 YAML 配置") from error
    if not isinstance(metadata, dict):
        raise ValueError("无法解析文件开头的 YAML 配置")
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("SKILL.md 缺少有效的 name 字段")
    name = name.strip()
    if len(name) > 128 or any(ord(char) < 32 for char in name):
        raise ValueError("Skill 名称应为 1 至 128 字，且不得包含换行或控制字符")
    description = metadata.get("description")
    return name, description if isinstance(description, str) else ""


def parse_skill_md(raw_content: str) -> dict:
    """解析 SKILL.md 完整内容，返回结构化令牌和压缩提示词

    Returns:
        {
            "name": str,              # 技能名称
            "description": str,       # 技能描述
            "skill_type": str,        # 技能类型: "ppt" 或 "exam"
            "design_tokens": dict,    # 完整设计令牌 (JSON)
            "prompt_snippet": str,    # 压缩版 Agent 提示词（注入到 system prompt）
        }
    """
    result = {
        "name": "",
        "description": "",
        "skill_type": "ppt",  # 默认PPT类型
        "design_tokens": {},
        "prompt_snippet": "",
    }

    # 1. 提取 YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", raw_content, re.DOTALL)
    frontmatter_text = ""
    if fm_match:
        frontmatter_text = fm_match.group(1)
        try:
            fm = yaml.safe_load(frontmatter_text)
            if isinstance(fm, dict):
                result["name"] = str(fm.get("name", "")).strip()
                result["description"] = str(fm.get("description", "")).strip()
                # 提取 skill_type 并验证
                raw_type = str(fm.get("skill_type", "ppt")).strip().lower()
                result["skill_type"] = raw_type if raw_type in VALID_SKILL_TYPES else "ppt"
                result["design_tokens"] = fm
        except yaml.YAMLError as e:
            logger.warning(f"SKILL.md frontmatter 解析失败: {e}")
            # 尝试用 JSON 作为 fallback
            try:
                fm = json.loads(frontmatter_text)
                if isinstance(fm, dict):
                    result["name"] = str(fm.get("name", "")).strip()
                    result["description"] = str(fm.get("description", "")).strip()
                    raw_type = str(fm.get("skill_type", "ppt")).strip().lower()
                    result["skill_type"] = raw_type if raw_type in VALID_SKILL_TYPES else "ppt"
                    result["design_tokens"] = fm
            except (json.JSONDecodeError, TypeError):
                pass

    # 2. 提取正文内容（去除 frontmatter 后的 Markdown）
    body = raw_content
    if fm_match:
        body = raw_content[fm_match.end():].strip()

    # 3. 根据技能类型生成不同的 prompt_snippet
    result["prompt_snippet"] = _build_prompt_snippet(result, body)

    return result


def _build_prompt_snippet(parsed: dict, body: str) -> str:
    """从解析结果构建压缩版 Agent 提示词（按技能类型分类生成）"""
    skill_type = parsed.get("skill_type", "ppt")

    if skill_type == "exam":
        return _build_exam_snippet(parsed, body)
    else:
        return _build_ppt_snippet(parsed, body)


def _build_ppt_snippet(parsed: dict, body: str) -> str:
    """构建PPT设计技能的压缩提示词"""
    tokens = parsed.get("design_tokens", {})
    name = parsed.get("name", "自定义")
    desc = parsed.get("description", "")

    parts = []
    parts.append(f"## 🎨 当前激活的PPT设计技能: {name}")

    if desc:
        parts.append(f"> {desc[:200]}")

    # 色彩系统 (最多 12 色)
    colors = tokens.get("colors", {})
    if colors and isinstance(colors, dict):
        color_list = []
        for k, v in list(colors.items())[:12]:
            color_list.append(f"- {k}: {v}")
        if color_list:
            parts.append(f"\n### 色彩系统\n" + "\n".join(color_list))
            parts.append("请在所有PPT视觉内容中使用这些颜色值。")

    # 字体系统
    typography = tokens.get("typography", {})
    if typography and isinstance(typography, dict):
        type_lines = []
        for role, spec in list(typography.items())[:8]:
            if isinstance(spec, dict):
                ff = spec.get("fontFamily", "")
                fs = spec.get("fontSize", "")
                fw = spec.get("fontWeight", "")
                type_lines.append(f"- {role}: {ff} {fs}/{fw}")
        if type_lines:
            parts.append(f"\n### 字体层级\n" + "\n".join(type_lines))

    # 间距系统
    spacing = tokens.get("spacing", {})
    if spacing and isinstance(spacing, dict):
        sp_lines = []
        for k, v in list(spacing.items())[:10]:
            sp_lines.append(f"- {k}: {v}")
        if sp_lines:
            parts.append(f"\n### 间距系统\n" + "\n".join(sp_lines))

    # 形状（圆角）
    rounded = tokens.get("rounded", {})
    if rounded and isinstance(rounded, dict):
        r_lines = []
        for k, v in list(rounded.items())[:6]:
            r_lines.append(f"- {k}: {v}")
        if r_lines:
            parts.append(f"\n### 圆角系统\n" + "\n".join(r_lines))

    # 提取关键设计原则
    key_principles = _extract_key_principles(body)
    if key_principles:
        parts.append(f"\n### 设计原则\n{key_principles}")

    # 组件规范（精简）
    components = tokens.get("components", {})
    if components and isinstance(components, dict):
        comp_names = list(components.keys())[:6]
        parts.append(f"\n### 可用组件\n" + ", ".join(comp_names))
        parts.append("请在生成PPT内容时参考这些组件规范。")

    # 生成指令
    parts.append("\n### PPT生成指令")
    parts.append("在生成PPT内容时，你必须严格遵循以上设计技能的色彩、字体、间距、"
                 "圆角和组件规范。这是用户自定义的设计系统，优先级最高。")

    snippet = "\n\n".join(parts)

    # 截断到预算
    if len(snippet) > MAX_SNIPPET_CHARS:
        snippet = snippet[:MAX_SNIPPET_CHARS - 3] + "..."

    return snippet


def _build_exam_snippet(parsed: dict, body: str) -> str:
    """构建试卷设计技能的压缩提示词

    试卷SKILL.md关注：题型结构、分值分布、题目格式、排版规范、难度控制等
    """
    tokens = parsed.get("design_tokens", {})
    name = parsed.get("name", "自定义")
    desc = parsed.get("description", "")

    parts = []
    parts.append(f"## 📝 当前激活的试卷设计技能: {name}")

    if desc:
        parts.append(f"> {desc[:200]}")

    # 题型结构
    question_types = tokens.get("question_types", [])
    if question_types:
        if isinstance(question_types, list):
            parts.append(f"\n### 题型结构\n" + "\n".join(f"- {qt}" for qt in question_types[:10]))
        elif isinstance(question_types, dict):
            parts.append(f"\n### 题型与分值\n" + "\n".join(
                f"- {k}: {v}" for k, v in list(question_types.items())[:10]
            ))

    # 分值分布
    score_distribution = tokens.get("score_distribution", {})
    if score_distribution and isinstance(score_distribution, dict):
        parts.append(f"\n### 分值分布\n" + "\n".join(
            f"- {k}: {v}" for k, v in list(score_distribution.items())[:10]
        ))

    # 难度控制
    difficulty = tokens.get("difficulty", {})
    if difficulty and isinstance(difficulty, dict):
        parts.append(f"\n### 难度控制\n" + "\n".join(
            f"- {k}: {v}" for k, v in list(difficulty.items())[:6]
        ))

    # 色彩（试卷也需要配色，如标题强调色）
    colors = tokens.get("colors", {})
    if colors and isinstance(colors, dict):
        color_list = [f"- {k}: {v}" for k, v in list(colors.items())[:8]]
        if color_list:
            parts.append(f"\n### 试卷配色\n" + "\n".join(color_list))

    # 字体
    typography = tokens.get("typography", {})
    if typography and isinstance(typography, dict):
        type_lines = []
        for role, spec in list(typography.items())[:6]:
            if isinstance(spec, dict):
                ff = spec.get("fontFamily", "")
                fs = spec.get("fontSize", "")
                fw = spec.get("fontWeight", "")
                type_lines.append(f"- {role}: {ff} {fs}/{fw}")
        if type_lines:
            parts.append(f"\n### 字体层级\n" + "\n".join(type_lines))

    # 排版格式
    formatting = tokens.get("formatting", {})
    if formatting and isinstance(formatting, dict):
        fmt_lines = [f"- {k}: {v}" for k, v in list(formatting.items())[:8]]
        if fmt_lines:
            parts.append(f"\n### 排版格式\n" + "\n".join(fmt_lines))

    # 提取关键原则
    key_principles = _extract_key_principles(body)
    if key_principles:
        parts.append(f"\n### 设计原则\n{key_principles}")

    # 试卷生成指令
    parts.append("\n### 试卷生成指令")
    parts.append("在生成试卷时，你必须严格遵循以上试卷设计技能的题型结构、分值分布、"
                 "难度控制和排版格式。这是用户自定义的设计系统，优先级最高。")

    snippet = "\n\n".join(parts)

    if len(snippet) > MAX_SNIPPET_CHARS:
        snippet = snippet[:MAX_SNIPPET_CHARS - 3] + "..."

    return snippet


def _extract_key_principles(body: str) -> str:
    """从 body 文本中提取关键设计原则"""
    principles = []

    # 查找 "Key Characteristics:" 段落
    kc_match = re.search(
        r"\*\*Key Characteristics:\*\*\s*\n((?:\s*- .+\n?)+)",
        body, re.IGNORECASE
    )
    if kc_match:
        characteristics = kc_match.group(1).strip()
        # 取前 6 条
        lines = [l.strip() for l in characteristics.split("\n") if l.strip()][:6]
        principles.extend(lines)

    # 查找 "Do" 段落
    do_match = re.search(
        r"### Do\s*\n((?:\s*- .+\n?)+)",
        body, re.IGNORECASE
    )
    if do_match:
        do_items = do_match.group(1).strip()
        do_lines = [l.strip() for l in do_items.split("\n") if l.strip()][:4]
        if do_lines:
            principles.append("\n**应该做的:**")
            principles.extend(do_lines)

    return "\n".join(principles) if principles else ""
