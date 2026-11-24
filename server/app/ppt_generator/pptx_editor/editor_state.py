# 编辑器状态管理器
# 在内存中维护每个 PPT 的 SVG 内容、待提交编辑、注解及最后访问时间

import time
import threading
from typing import Optional


class EditorState:
    """线程安全的编辑器状态单例"""

    def __init__(self):
        self._lock = threading.Lock()
        # {ppt_id: {page_index: svg_content_str}}
        self._svgs: dict[int, dict[int, str]] = {}
        # {ppt_id: {page_index: [{element_id, text?, attrs?, changes}]}}
        self._pending_edits: dict[int, dict[int, list[dict]]] = {}
        # {ppt_id: {page_index: {element_id: annotation_text}}}
        self._annotations: dict[int, dict[int, dict[str, str]]] = {}
        # {ppt_id: last_access_time}
        self._last_access: dict[int, float] = {}
        # PDF/画布尺寸等信息
        self._svg_info: dict[int, dict[int, dict]] = {}

    # ---- 生命周期 ----

    def load_ppt(self, ppt_id: int, svgs: dict[int, str],
                 info: Optional[dict[int, dict]] = None) -> None:
        """加载一个 PPT 的所有幻灯片 SVG"""
        with self._lock:
            self._svgs[ppt_id] = dict(svgs)
            self._svg_info[ppt_id] = dict(info or {})
            self._pending_edits[ppt_id] = {i: [] for i in svgs}
            self._annotations[ppt_id] = {i: {} for i in svgs}
            self._touch(ppt_id)

    def has_ppt(self, ppt_id: int) -> bool:
        with self._lock:
            return ppt_id in self._svgs

    def clear_ppt(self, ppt_id: int) -> None:
        """保存完成或关闭编辑器后清理状态"""
        with self._lock:
            self._svgs.pop(ppt_id, None)
            self._pending_edits.pop(ppt_id, None)
            self._annotations.pop(ppt_id, None)
            self._svg_info.pop(ppt_id, None)
            self._last_access.pop(ppt_id, None)

    # ---- SVG 访问 ----

    def get_svg(self, ppt_id: int, page: int) -> Optional[str]:
        with self._lock:
            self._touch(ppt_id)
            return self._svgs.get(ppt_id, {}).get(page)

    def get_svg_info(self, ppt_id: int, page: int) -> Optional[dict]:
        with self._lock:
            return self._svg_info.get(ppt_id, {}).get(page)

    # ---- 待提交编辑 ----

    def get_edits(self, ppt_id: int, page: int) -> list[dict]:
        with self._lock:
            self._touch(ppt_id)
            edits = self._pending_edits.get(ppt_id, {}).get(page, [])
            return list(edits)

    def add_edit(self, ppt_id: int, page: int, record: dict) -> None:
        with self._lock:
            self._touch(ppt_id)
            stack = (self._pending_edits.setdefault(ppt_id, {})
                     .setdefault(page, []))
            # 连续同特征编辑合并
            if stack and _edit_signature(stack[-1]) == _edit_signature(record):
                _coalesce_into(stack[-1], record)
            else:
                stack.append(record)

    def undo_edit(self, ppt_id: int, page: int) -> bool:
        """撤销最近一次编辑，返回 False 表示无可撤销"""
        with self._lock:
            self._touch(ppt_id)
            stack = self._pending_edits.get(ppt_id, {}).get(page, [])
            if not stack:
                return False
            stack.pop()
            return True

    def get_edit_depth(self, ppt_id: int, page: int) -> int:
        with self._lock:
            return len(self._pending_edits.get(ppt_id, {}).get(page, []))

    def get_all_edits(self, ppt_id: int) -> dict[int, list[dict]]:
        with self._lock:
            return dict(self._pending_edits.get(ppt_id, {}))

    # ---- 注解 ----

    def get_annotations(self, ppt_id: int, page: int) -> dict[str, str]:
        with self._lock:
            self._touch(ppt_id)
            return dict(self._annotations.get(ppt_id, {}).get(page, {}))

    def set_annotation(self, ppt_id: int, page: int,
                       element_id: str, annotation: str) -> None:
        with self._lock:
            self._touch(ppt_id)
            anns = (self._annotations.setdefault(ppt_id, {})
                    .setdefault(page, {}))
            anns[element_id] = annotation

    def delete_annotation(self, ppt_id: int, page: int,
                          element_id: str) -> None:
        with self._lock:
            self._touch(ppt_id)
            anns = self._annotations.get(ppt_id, {}).get(page, {})
            anns.pop(element_id, None)

    def get_all_annotations(self, ppt_id: int) -> dict[int, dict[str, str]]:
        with self._lock:
            return dict(self._annotations.get(ppt_id, {}))

    # ---- 空闲超时 ----

    def _touch(self, ppt_id: int) -> None:
        self._last_access[ppt_id] = time.time()

    def cleanup_idle(self, timeout: int = 900) -> list[int]:
        """清理超时 PPT 状态，返回被清理的 ppt_id 列表"""
        now = time.time()
        idle = []
        with self._lock:
            for pid, t in list(self._last_access.items()):
                if now - t > timeout:
                    idle.append(pid)
            for pid in idle:
                self._svgs.pop(pid, None)
                self._pending_edits.pop(pid, None)
                self._annotations.pop(pid, None)
                self._svg_info.pop(pid, None)
                self._last_access.pop(pid, None)
        return idle


# ---- 编辑合并辅助 ----

def _edit_signature(record: dict) -> tuple:
    attr_keys = tuple(sorted((record.get("attrs") or {}).keys()))
    promote_keys = tuple(sorted((record.get("promote_tspan") or {}).keys()))
    return (record.get("element_id"), "text" in record, attr_keys, promote_keys)


def _coalesce_into(prev: dict, cur: dict) -> None:
    if "text" in cur:
        prev["text"] = cur["text"]
    if cur.get("attrs"):
        merged = dict(prev.get("attrs") or {})
        merged.update(cur["attrs"])
        prev["attrs"] = merged
    if cur.get("promote_tspan"):
        prev["promote_tspan"] = cur["promote_tspan"]
    old_by_field = {(c["kind"], c["key"]): c["old"]
                    for c in prev.get("changes", [])}
    prev["changes"] = [
        {"kind": c["kind"], "key": c["key"],
         "old": old_by_field.get((c["kind"], c["key"]), c["old"]),
         "new": c["new"]}
        for c in cur.get("changes", [])
    ]


# 全局单例
editor_state = EditorState()
