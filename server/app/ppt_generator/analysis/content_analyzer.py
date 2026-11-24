"""内容分析器 — 分析 pages_json 内容特征，推荐视觉风格和布局策略

参考 ppt-master (https://github.com/hugohe3/ppt-master) 的 Strategist 设计：

  工作流:
    pages_json → 内容分析 → ContentProfile → 风格推荐 → 布局推荐

典型用法:
    analyzer = ContentAnalyzer()
    profile = analyzer.analyze(pages)
    style = analyzer.recommend_style(profile)
    layouts = analyzer.recommend_layout_strategy(profile)
    candidates = analyzer.generate_style_candidates(profile)
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ContentProfile:
    """内容分析结果 — 描述一份 PPT 页面集合的内容特征"""

    # ——— 基本统计 ———
    page_count: int = 0
    """总页数"""

    total_word_count: int = 0
    """总中文字数 + 英文单词数（粗略）"""

    avg_words_per_page: float = 0.0
    """平均每页字数"""

    # ——— 内容密度 ———
    content_density: str = "medium"
    """sparse（稀疏） / medium（适中） / dense（密集） — 基于平均字数"""

    # ——— 类型分布 ———
    type_distribution: Dict[str, int] = field(default_factory=dict)
    """各页面类型的计数，如 {"vocabulary": 3, "dialogue": 2, ...}"""

    dominant_type: str = "content"
    """出现最多的页面类型"""

    # ——— 特定元素统计 ———
    image_count: int = 0
    """图片数量（粗略）"""

    vocabulary_count: int = 0
    """词汇表中单词总数"""

    dialogue_count: int = 0
    """对话条总数"""

    question_count: int = 0
    """练习题总数"""

    # ——— 特殊页面检测 ———
    has_ai_interaction: bool = False
    """是否包含人机互动页"""

    has_listening: bool = False
    """是否包含听力练习页"""

    has_speaking: bool = False
    """是否包含口语跟读页"""

    has_catalog: bool = False
    """是否包含目录页"""

    # ——— 估算 ———
    estimated_duration_minutes: int = 0
    """预估授课时长（分钟，~1min/页）"""

    def to_dict(self) -> dict:
        """转为纯字典（便于 JSON 序列化）"""
        return {
            "pageCount": self.page_count,
            "totalWordCount": self.total_word_count,
            "avgWordsPerPage": round(self.avg_words_per_page, 1),
            "contentDensity": self.content_density,
            "typeDistribution": self.type_distribution,
            "dominantType": self.dominant_type,
            "imageCount": self.image_count,
            "vocabularyCount": self.vocabulary_count,
            "dialogueCount": self.dialogue_count,
            "questionCount": self.question_count,
            "hasAiInteraction": self.has_ai_interaction,
            "hasListening": self.has_listening,
            "hasSpeaking": self.has_speaking,
            "hasCatalog": self.has_catalog,
            "estimatedDurationMinutes": self.estimated_duration_minutes,
        }

    def describe(self) -> str:
        """生成可读的内容描述文本（用于日志/提示词上下文）"""
        parts = [
            f"共 {self.page_count} 页",
            f"总字数约 {self.total_word_count}",
            f"内容密度: {self.content_density}",
            f"主要类型: {self.dominant_type}",
        ]
        if self.vocabulary_count:
            parts.append(f"词汇: {self.vocabulary_count} 个")
        if self.dialogue_count:
            parts.append(f"对话: {self.dialogue_count} 条")
        if self.question_count:
            parts.append(f"题目: {self.question_count} 道")
        if self.has_ai_interaction:
            parts.append("含 AI 互动")
        if self.has_listening:
            parts.append("含听力")
        if self.has_speaking:
            parts.append("含口语")
        return " · ".join(parts)


class ContentAnalyzer:
    """内容分析器 — 分析页面内容特征，辅助设计决策

    参考 ppt-master Strategist 设计：
    - 分析 pages_json 的内容维度
    - 推荐匹配的视觉风格
    - 推荐每种页面类型的布局策略
    - 生成 Top-N 风格候选项（供前端选择器使用）
    """

    # 内容密度阈值（基于平均每页字数）
    DENSITY_THRESHOLDS: Dict[str, int] = {
        "sparse": 20,
        "medium": 50,
    }

    # 布局推荐规则 — 基于元素数量切换布局变体
    LAYOUT_RULES: Dict[str, Dict] = {
        "vocabulary": {
            "thresholds": [
                (8, "waterfall"),   # ≥8 词用瀑布流
                (4, "grid"),        # ≥4 词用网格
            ],
            "default": "cards",     # <4 词用大卡片
        },
        "dialogue": {
            "thresholds": [
                (6, "chat"),        # ≥6 条用聊天布局
                (3, "cards"),       # ≥3 条用卡片布局
            ],
            "default": "list",      # <3 条用列表
        },
        "practice": {
            "thresholds": [
                (5, "list"),        # ≥5 题用紧凑列表
            ],
            "default": "cards",     # <5 题用宽松卡片
        },
    }

    # ==================== 核心分析 ====================

    def analyze(self, pages: List[Dict]) -> ContentProfile:
        """分析 pages_json 内容特征

        Args:
            pages: PPT 页面数据列表（与 PPTGenerationService 输入格式一致）

        Returns:
            内容分析结果 ContentProfile
        """
        profile = ContentProfile()
        profile.page_count = len(pages)

        total_words = 0
        type_dist: Dict[str, int] = {}
        image_count = 0
        vocab_count = 0
        dialogue_count = 0
        question_count = 0

        for page in pages:
            page_type = page.get("type", "content")
            content = page.get("content", {})

            # ——— 类型计数 ———
            type_dist[page_type] = type_dist.get(page_type, 0) + 1

            # ——— 字数统计 ———
            words = self._extract_text(page)
            total_words += len(words)

            # ——— 特定元素统计 ———
            if page_type == "vocabulary":
                vocab_count += len(content.get("words", []))
            elif page_type == "dialogue":
                dialogue_count += len(content.get("dialogues", []))
            elif page_type in ("practice", "listening"):
                question_count += len(content.get("questions", []))

            # ——— 图片统计 ———
            if (content.get("image_url") or content.get("images")):
                image_count += len(content.get("images", [content.get("image_url")]))

            # ——— 特殊页面检测 ———
            if page_type == "ai_interaction":
                profile.has_ai_interaction = True
            if page_type == "listening":
                profile.has_listening = True
            if page_type == "speaking":
                profile.has_speaking = True
            if page_type == "catalog":
                profile.has_catalog = True

        # ——— 汇总 ———
        profile.total_word_count = total_words
        profile.avg_words_per_page = total_words / max(len(pages), 1)
        profile.image_count = image_count
        profile.vocabulary_count = vocab_count
        profile.dialogue_count = dialogue_count
        profile.question_count = question_count
        profile.type_distribution = type_dist

        # ——— 内容密度 ———
        avg_words = profile.avg_words_per_page
        if avg_words <= self.DENSITY_THRESHOLDS["sparse"]:
            profile.content_density = "sparse"
        elif avg_words <= self.DENSITY_THRESHOLDS["medium"]:
            profile.content_density = "medium"
        else:
            profile.content_density = "dense"

        # ——— 主导类型 ———
        if type_dist:
            profile.dominant_type = max(type_dist, key=type_dist.get)

        # ——— 预估时长 ———
        profile.estimated_duration_minutes = max(1, len(pages))

        logger.info(f"内容分析完成: {profile.describe()}")
        return profile

    # ==================== 文本提取 ====================

    @staticmethod
    def _extract_text(page: Dict) -> List[str]:
        """递归提取页面中所有文本片段

        Args:
            page: 单页数据

        Returns:
            文本片段列表（每个字符串是连续文本块）
        """
        texts: List[str] = []
        stack: list = [page]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, val in item.items():
                    # 跳过元数据字段
                    if key in ("type", "_layout", "_index", "layout",
                               "image_url", "audio_url", "icon", "url"):
                        continue
                    if isinstance(val, str) and val.strip():
                        texts.append(val.strip())
                    elif isinstance(val, (list, dict)):
                        stack.append(val)
            elif isinstance(item, list):
                stack.extend(item)
        return texts

    # ==================== 风格推荐 ====================

    def recommend_style(self, profile: ContentProfile) -> str:
        """根据内容特征推荐最佳视觉风格

        推荐规则:
        - 词汇/对话为主 → soft-rounded（圆润亲和）
        - 语法/练习为主 → editorial（杂志风）
        - 含 AI 互动页 → dark-tech（暗色科技）
        - 目录/目标页多 → swiss-minimal（瑞士极简）
        - 内容密集 → swiss-minimal（干净高效）
        - 内容稀疏 → soft-rounded（留白亲和）
        - 默认 → warm-simple（温暖通用）

        Args:
            profile: 内容分析结果

        Returns:
            推荐的视觉风格名称
        """
        # ——— 类型倾向推荐 ———
        dominant = profile.dominant_type
        if dominant in ("vocabulary", "dialogue"):
            return "soft-rounded"
        if dominant in ("grammar", "practice"):
            return "editorial"
        if profile.has_ai_interaction:
            return "dark-tech"
        if dominant in ("catalog", "objective", "title"):
            return "swiss-minimal"

        # ——— 内容密度推荐 ———
        if profile.content_density == "dense":
            return "swiss-minimal"
        if profile.content_density == "sparse":
            return "soft-rounded"

        # ——— 综合推荐 ———
        if profile.has_listening or profile.has_speaking:
            return "soft-rounded"
        if profile.question_count >= 5:
            return "editorial"
        if profile.image_count >= 3:
            return "editorial"
        if profile.page_count >= 10:
            return "chalkboard"
        if profile.page_count <= 5:
            return "warm-simple"

        return "warm-simple"

    def recommend_layout_strategy(self, profile: ContentProfile) -> Dict[str, str]:
        """根据内容特征推荐各页面类型的布局变体

        布局规则:
        - vocabulary: 词数多→waterfall, 中等→grid, 少→cards
        - dialogue: 对话多→chat, 中等→cards, 少→list
        - practice: 题目多→list, 少→cards

        Args:
            profile: 内容分析结果

        Returns:
            页面类型到布局名称的映射，如 {"vocabulary": "waterfall", "dialogue": "chat"}
        """
        strategy: Dict[str, str] = {}

        # ——— 词汇布局 ———
        count_map = {
            "vocabulary": profile.vocabulary_count,
            "dialogue": profile.dialogue_count,
            "practice": profile.question_count,
        }
        for page_type, count in count_map.items():
            rules = self.LAYOUT_RULES.get(page_type)
            if rules is None:
                continue
            assigned = rules["default"]
            for threshold, layout_name in rules["thresholds"]:
                if count >= threshold:
                    assigned = layout_name
            strategy[page_type] = assigned

        logger.info(f"布局策略推荐: {strategy}")
        return strategy

    def generate_style_candidates(
        self,
        profile: ContentProfile,
        top_n: int = 3,
    ) -> List[Tuple[str, str]]:
        """生成推荐风格候选项列表（带简短理由）

        返回 Top-N 候选风格及其推荐理由，供前端选择器展示。

        Args:
            profile: 内容分析结果
            top_n: 返回候选项数量（默认 3）

        Returns:
            [(风格名, 推荐理由), ...]
        """
        primary = self.recommend_style(profile)
        candidates: List[str] = [primary]
        reasons: Dict[str, str] = {
            primary: self._style_reason(primary, profile),
        }

        # ——— 追加备选 ———
        if profile.has_listening or profile.has_speaking:
            self._add_if_missing(candidates, "soft-rounded")
            reasons.setdefault("soft-rounded", "含听说练习，适合亲和圆润风格")
        if profile.has_ai_interaction:
            self._add_if_missing(candidates, "dark-tech")
            reasons.setdefault("dark-tech", "含 AI 互动，适合科技感风格")
        if profile.image_count > 0:
            self._add_if_missing(candidates, "editorial")
            reasons.setdefault("editorial", "含图片内容，适合杂志风排版")
        if profile.page_count >= 8:
            self._add_if_missing(candidates, "sketch-notes")
            reasons.setdefault("sketch-notes", "长课件适合手绘风格增加趣味性")
        if profile.content_density == "dense":
            self._add_if_missing(candidates, "swiss-minimal")
            reasons.setdefault("swiss-minimal", "内容密集，适合极简清晰风格")

        # ——— 补全到 top_n ———
        fallback_order = [
            "warm-simple", "swiss-minimal", "soft-rounded",
            "editorial", "dark-tech", "chalkboard",
            "glassmorphism", "paper-cut", "sketch-notes",
        ]
        for fb in fallback_order:
            if len(candidates) >= top_n:
                break
            if fb not in candidates:
                candidates.append(fb)
                reasons[fb] = self._style_reason(fb, profile)

        result = [(s, reasons.get(s, "")) for s in candidates[:top_n]]
        logger.info(f"风格候选推荐: {[s for s, _ in result]}")
        return result

    # ==================== 辅助方法 ====================

    @staticmethod
    def _add_if_missing(lst: list, item: str):
        """如果列表中不存在则追加"""
        if item not in lst:
            lst.append(item)

    @staticmethod
    def _style_reason(style: str, profile: ContentProfile) -> str:
        """生成风格的简短推荐理由"""
        reasons = {
            "swiss-minimal": "干净清晰的极简风格，适合教研/学术场景",
            "soft-rounded": "圆润亲和风格，适合少儿/培训场景",
            "editorial": "杂志风设计，适合阅读/分析内容",
            "dark-tech": "暗色科技风格，适合 AI/数据展示",
            "sketch-notes": "手绘笔记风格，增加课堂趣味性",
            "chalkboard": "黑板风格，适合课堂教学场景",
            "glassmorphism": "玻璃拟态风格，现代科技感",
            "paper-cut": "剪纸风格，适合文化/节日主题",
            "warm-simple": "温暖简洁的通用风格，适合日常使用",
        }
        return reasons.get(style, "通用推荐风格")


# ==================== 便捷函数 ====================


def analyze_pages(pages: List[Dict]) -> ContentProfile:
    """便捷函数 — 单次分析

    Args:
        pages: PPT 页面数据列表

    Returns:
        内容分析结果
    """
    analyzer = ContentAnalyzer()
    return analyzer.analyze(pages)


def recommend_for_pages(
    pages: List[Dict],
    top_n: int = 3,
) -> dict:
    """便捷函数 — 一站式分析 + 推荐

    返回可直接返回给前端的完整推荐结果。

    Args:
        pages: PPT 页面数据列表
        top_n: 风格候选项数量

    Returns:
        {
            "profile": {...},
            "recommendedStyle": "soft-rounded",
            "layoutStrategy": {"vocabulary": "waterfall", ...},
            "styleCandidates": [("soft-rounded", "理由"), ...],
        }
    """
    analyzer = ContentAnalyzer()
    profile = analyzer.analyze(pages)
    return {
        "profile": profile.to_dict(),
        "recommendedStyle": analyzer.recommend_style(profile),
        "layoutStrategy": analyzer.recommend_layout_strategy(profile),
        "styleCandidates": [
            {"style": s, "reason": r}
            for s, r in analyzer.generate_style_candidates(profile, top_n)
        ],
    }
