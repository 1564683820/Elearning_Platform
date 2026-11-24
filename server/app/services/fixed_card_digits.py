"""Read boxed handwritten digits from a registered, aligned answer card."""
import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock

import cv2
import numpy as np


logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _model(path: Path):
    return cv2.dnn.readNetFromONNX(np.frombuffer(path.read_bytes(), dtype=np.uint8)), Lock()


def _predict(path: Path, digits: list[np.ndarray]) -> np.ndarray | None:
    try:
        net, lock = _model(path)
        with lock:
            net.setInput(np.asarray(digits, dtype=np.float32)[:, None, :, :] / 255)
            output = np.asarray(net.forward())
    except (OSError, cv2.error):
        logger.warning("Fixed card digit model is unavailable")
        return None
    if output.shape != (len(digits), 10) or not np.isfinite(output).all():
        logger.warning("Fixed card digit model returned invalid logits")
        return None
    weights = np.exp(output - output.max(axis=1, keepdims=True))
    return weights / weights.sum(axis=1, keepdims=True)


def _ink(photo: np.ndarray, reference: np.ndarray) -> np.ndarray:
    def dark_pixels(image):
        return cv2.adaptiveThreshold(
            image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 12,
        )

    printed = cv2.dilate(dark_pixels(reference), np.ones((3, 3), dtype=np.uint8))
    return cv2.bitwise_and(dark_pixels(photo), cv2.bitwise_not(printed))


def _digit_tensor(mask: np.ndarray) -> np.ndarray:
    x, y, width, height = cv2.boundingRect(mask)
    scale = 20 / max(width, height)
    width_out, height_out = max(1, round(width * scale)), max(1, round(height * scale))
    resized = cv2.resize(mask[y:y + height, x:x + width], (width_out, height_out), interpolation=cv2.INTER_AREA)
    digit = np.zeros((28, 28), dtype=np.uint8)
    left, top = (28 - width_out) // 2, (28 - height_out) // 2
    digit[top:top + height_out, left:left + width_out] = resized
    return digit


def _ambiguous_ink(ink: np.ndarray, area: int) -> bool:
    edge = min(ink.shape[1] // 2, max(3, ink.shape[1] // 10))
    if cv2.countNonZero(ink[:, :edge]) >= 3 or cv2.countNonZero(ink[:, -edge:]) >= 3:
        return True
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    substantial = sorted((int(x), int(x + width)) for x, _, width, _, pixels in stats[1:]
                         if pixels >= max(5, area * 0.18))
    return any(right + 1 < next_left for (_, right), (next_left, _) in zip(substantial, substantial[1:]))


def read_digits(
    crops: list[tuple[np.ndarray, np.ndarray]],
    overflow_crop: tuple[np.ndarray, np.ndarray] | None,
    model: Path | None,
    min_confidence: float,
) -> tuple[str, list[dict], bool]:
    cells: list[dict] = []
    pending = []
    for index, (photo, reference) in enumerate(crops):
        ink = _ink(photo, reference)
        area = cv2.countNonZero(ink)
        state = "empty"
        if area >= max(5, int(ink.size * 0.012)):
            if _ambiguous_ink(ink, area):
                state = "ambiguous"
            else:
                state = "unavailable"
                pending.append((index, _digit_tensor(ink)))
        cells.append({"position": index + 1, "state": state})

    if model and pending:
        probabilities = _predict(model, [image for _, image in pending])
        if probabilities is not None:
            for (index, _image), distribution in zip(pending, probabilities):
                candidate = int(distribution.argmax())
                confidence = float(distribution[candidate])
                cells[index].update(
                    digit=str(candidate), confidence=confidence,
                    state="read" if confidence >= min_confidence else "ambiguous",
                )

    overflow = False
    if overflow_crop is not None:
        outside = _ink(*overflow_crop)
        overflow = cv2.countNonZero(outside) >= max(5, int(outside.size * 0.012))
    number = ""
    if not overflow and cells and all(cell["state"] == "read" for cell in cells):
        number = "".join(cell["digit"] for cell in cells)
    return number, cells, overflow
