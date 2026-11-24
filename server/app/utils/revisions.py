import hashlib
import json


def content_revision(content: object) -> str:
    payload = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def template_revision(template) -> str:
    return content_revision([template.name, template.choice_questions])


def is_paper_draft(config: object) -> bool:
    return isinstance(config, dict) and bool(config.get("paper_draft"))
