"""Recognize fixed cards only from an explicitly registered reference image and regions."""
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from app.core.paths import SERVER_DIR
from app.services.private_document_files import validate_private_file


class FixedLayoutError(Exception):
    pass


class Region(BaseModel):
    cx: int = Field(ge=0)
    cy: int = Field(ge=0)
    w: int = Field(ge=4)
    h: int = Field(ge=4)

    def within(self, width: int, height: int) -> bool:
        return self.w // 2 <= self.cx <= width - self.w // 2 and self.h // 2 <= self.cy <= height - self.h // 2

    def slices(self) -> tuple[slice, slice]:
        return (slice(self.cy - self.h // 2, self.cy + self.h // 2),
                slice(self.cx - self.w // 2, self.cx + self.w // 2))


class CardLayout(BaseModel):
    question_regions: dict[int, dict[Literal["A", "B", "C", "D", "E", "F", "G", "H"], Region]] = Field(min_length=1, max_length=300)
    identity_regions: list[Region] = Field(min_length=2, max_length=12)
    exam_number_columns: list[dict[Literal["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], Region]] = Field(default_factory=list, max_length=16)
    exam_number_cells: list[Region] = Field(default_factory=list, max_length=64)
    name_region: Region | None = None
    exam_number_overflow_region: Region | None = None
    digit_model_min_confidence: float | None = Field(None, gt=0.5, le=1)
    fill_threshold: float = Field(default=0.42, gt=0, lt=1)
    faint_threshold: float = Field(default=0.2, gt=0, lt=1)
    _reference_size: tuple[int, int] = PrivateAttr()

    @property
    def capture_aspect_ratio(self) -> float:
        width, height = self._reference_size
        return width / height


def _directory(layout_id: str, version: str) -> Path | None:
    if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) for value in (layout_id, version)):
        return None
    root = Path(os.environ.get("PAPER_FIXED_CARD_LAYOUT_DIR") or SERVER_DIR / "data" / "fixed_card_layouts").resolve()
    directory = (root / layout_id / version).resolve()
    return directory if directory.is_relative_to(root) else None


def layout_available(layout_id: str, version: str) -> bool:
    directory = _directory(layout_id, version)
    return bool(directory and (directory / "layout.json").is_file() and (directory / "reference.png").is_file())


def default_binding() -> dict:
    parts = os.environ.get("PAPER_FIXED_CARD_DEFAULT_LAYOUT", "").split("/")
    if len(parts) != 2 or not layout_available(*parts):
        return {}
    return {"mode": "provided_fixed", "layout_id": parts[0], "layout_version": parts[1]}


def load_registered_layout(layout_id: str, version: str) -> tuple[CardLayout, bytes]:
    directory = _directory(layout_id, version)
    if not directory:
        raise FixedLayoutError("固定答题卡版式未配置")
    try:
        layout = CardLayout.model_validate_json((directory / "layout.json").read_bytes())
        reference = (directory / "reference.png").read_bytes()
        with Image.open(BytesIO(reference)) as image:
            if image.format != "PNG":
                raise FixedLayoutError("固定答题卡样张须为 PNG")
            width, height = image.size
            image.verify()
    except FileNotFoundError as error:
        raise FixedLayoutError("固定答题卡版式未配置") from error
    except (OSError, ValidationError, Image.DecompressionBombError) as error:
        raise FixedLayoutError("固定答题卡版式配置无效") from error
    if max(width, height) > 2400 or layout.faint_threshold >= layout.fill_threshold:
        raise FixedLayoutError("固定答题卡版式配置无效")
    number_columns = layout.exam_number_columns
    if any(len(column) != 10 for column in number_columns):
        raise FixedLayoutError("固定答题卡考号区配置无效")
    cells = layout.exam_number_cells
    if cells and (number_columns or layout.name_region is None or any(
        left.cx + (left.w + 1) // 2 > right.cx - right.w // 2 for left, right in zip(cells, cells[1:])
    )):
        raise FixedLayoutError("手写考号格须从左到右排列且互不重叠，并配置姓名区域")
    overflow = layout.exam_number_overflow_region
    if overflow and (not cells or overflow.cx - overflow.w // 2 < cells[-1].cx + cells[-1].w // 2):
        raise FixedLayoutError("考号格外检查区须位于最后一格右侧")
    if layout.digit_model_min_confidence is not None and (not overflow or not (directory / "digits.onnx").is_file()):
        raise FixedLayoutError("启用手写考号识别须配置考号格外检查区与 digits.onnx")
    regions = [region for row in (*layout.question_regions.values(), *number_columns) for region in row.values()]
    regions.extend(cells)
    if layout.name_region is not None:
        regions.append(layout.name_region)
    if overflow:
        regions.append(overflow)
    if any(not region.within(width, height) for region in (*regions, *layout.identity_regions)):
        raise FixedLayoutError("固定答题卡版式区域越界")
    layout._reference_size = (width, height)
    return layout, reference


def check_question_mapping(layout: CardLayout, required: dict[int, list[str]]) -> None:
    for number, options in required.items():
        regions = layout.question_regions.get(number)
        if not regions:
            raise FixedLayoutError(f"固定答题卡未配置第 {number} 题")
        missing = set(options) - regions.keys()
        if missing:
            raise FixedLayoutError(f"固定答题卡第 {number} 题缺少 {'、'.join(sorted(missing))} 选项")


def recognize(layout_id: str, version: str, required: dict[int, list[str]], data: bytes, filename: str) -> dict:
    import cv2
    import numpy as np

    from app.services.omr_scanner import _sample_gray_fill

    validate_private_file(filename, data)
    layout, reference_data = load_registered_layout(layout_id, version)
    check_question_mapping(layout, required)
    reference = cv2.imdecode(np.frombuffer(reference_data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if reference is None:
        raise FixedLayoutError("固定答题卡版式配置无效")
    number_columns = layout.exam_number_columns

    photo = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if photo is None or min(photo.shape) < 256:
        return {"state": "retake"}
    scale = 1800 / max(photo.shape)
    if scale < 1:
        photo = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if cv2.Laplacian(photo, cv2.CV_32F).var() < 18:
        return {"state": "retake"}
    registration = _align(photo, reference, cv2, np)
    if registration is None:
        if layout.exam_number_cells:
            return {"state": "retake"}
        return {"state": "layout_mismatch"}
    aligned, coverage = registration
    required_regions = [
        region for row in (*(layout.question_regions[number] for number in required), *number_columns)
        for region in row.values()
    ]
    required_regions.extend(layout.exam_number_cells)
    if layout.name_region is not None:
        required_regions.append(layout.name_region)
    if layout.exam_number_overflow_region is not None:
        required_regions.append(layout.exam_number_overflow_region)
    for region in (*required_regions, *layout.identity_regions):
        if not coverage[region.slices()].all():
            return {"state": "retake"}
    for region in layout.identity_regions:
        indices = region.slices()
        signature = reference[indices]
        if signature.std() < 12:
            raise FixedLayoutError("固定答题卡版式特征区域缺少印刷内容")
        score = cv2.matchTemplate(aligned[indices], signature, cv2.TM_CCOEFF_NORMED)[0, 0]
        if score < 0.65:
            return {"state": "layout_mismatch"}

    def sample(region: Region) -> float:
        before = _sample_gray_fill(reference, region.cx, region.cy, region.w, region.h)
        after = _sample_gray_fill(aligned, region.cx, region.cy, region.w, region.h)
        return max(0., (before - after) / max(before, 0.25))

    def marks(row: dict[str, Region]):
        scores = {label: sample(region) for label, region in row.items()}
        selected = [label for label, score in scores.items() if score >= layout.fill_threshold]
        faint = any(layout.faint_threshold <= score < layout.fill_threshold for score in scores.values())
        return selected, faint

    raw_answers = []
    uncertain = []
    for number, options in required.items():
        selected, faint = marks(layout.question_regions[number])
        raw_answers.append({"question_number": number, "student_answer": selected})
        if faint or len(selected) > 1 or any(label not in options for label in selected):
            uncertain.append(number)
    digits = []
    for column in number_columns:
        selected, faint = marks(column)
        if len(selected) != 1 or faint:
            digits = []
            break
        digits.extend(selected)
    result = {
        "state": "review", "exam_number": "".join(digits), "raw_answers": raw_answers,
        "uncertain_questions": uncertain, "exam_number_length": len(layout.exam_number_cells) or None,
    }
    if layout.exam_number_cells:
        from app.services.fixed_card_digits import read_digits

        def crop(region: Region):
            indices = region.slices()
            return aligned[indices], reference[indices]

        confidence = layout.digit_model_min_confidence
        directory = _directory(layout_id, version)
        model = directory / "digits.onnx" if confidence is not None and directory else None
        overflow = layout.exam_number_overflow_region
        number, cells, extra = read_digits(
            [crop(cell) for cell in layout.exam_number_cells], crop(overflow) if overflow else None,
            model, confidence if confidence is not None else 1,
        )
        result.update(exam_number=number, exam_number_cells=cells, exam_number_overflow=extra)
    return result


def _align(photo, reference, cv2, np):
    detector = cv2.ORB_create(nfeatures=2400)
    source_keys, source = detector.detectAndCompute(photo, None)
    target_keys, target = detector.detectAndCompute(reference, None)
    if source is None or target is None or len(target) < 2:
        return None
    matches = [pair[0] for pair in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(source, target, k=2)
               if len(pair) == 2 and pair[0].distance < 0.74 * pair[1].distance]
    if len(matches) < 24:
        return None
    source_points = np.float32([source_keys[match.queryIdx].pt for match in matches])
    target_points = np.float32([target_keys[match.trainIdx].pt for match in matches])
    matrix, mask = cv2.findHomography(source_points, target_points, cv2.RANSAC, 3.5)
    if matrix is None or mask is None or mask.sum() < max(18, len(matches) * 0.5):
        return None
    height, width = reference.shape
    if cv2.contourArea(cv2.convexHull(target_points[mask.ravel() > 0])) < width * height * 0.22:
        return None
    aligned = cv2.warpPerspective(photo, matrix, (width, height), borderValue=255)
    coverage = cv2.warpPerspective(np.full(photo.shape, 255, dtype=np.uint8), matrix, (width, height))
    return aligned, coverage == 255
