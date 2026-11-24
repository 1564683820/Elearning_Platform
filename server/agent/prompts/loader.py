"""Prompt template loader.
Supports loading .txt files and named prompt constants.
"""

import os


_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_prompt(name: str, subdir: str = "") -> str:
    """Load a prompt from a .txt file in the prompts directory.

    Args:
        name: Prompt file name (with or without .txt extension)
        subdir: Optional subdirectory (e.g., "ppt_agent")
    Returns:
        Prompt text content
    """
    if not name.endswith('.txt'):
        name += '.txt'
    parts = [_PROMPTS_DIR]
    if subdir:
        parts.append(subdir)
    parts.append(name)
    path = os.path.join(*parts)
    if not os.path.exists(path):
        return ""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
