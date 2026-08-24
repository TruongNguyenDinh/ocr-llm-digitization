import cv2
import numpy as np
from typing import List, Dict


def build_text_mask(
    image_shape,
    blocks: List[Dict],
):
    mask = np.zeros(
        image_shape[:2],
        dtype=np.uint8,
    )

    for block in blocks:
        bbox = block.get("bbox")

        if not bbox:
            continue

        points = np.array(
            bbox,
            dtype=np.int32,
        )

        cv2.fillPoly(
            mask,
            [points],
            255,
        )

    return mask


def detect_visual_regions(
    image_path: str,
    blocks: List[Dict],
    min_area: int = 1000,
):
    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(
            image_path
        )

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    # Tách các vùng không gần trắng.
    foreground = cv2.threshold(
        gray,
        245,
        255,
        cv2.THRESH_BINARY_INV,
    )[1]

    # Mask OCR text.
    text_mask = build_text_mask(
        image.shape,
        blocks,
    )

    # Loại bỏ vùng OCR.
    visual_mask = cv2.bitwise_and(
        foreground,
        cv2.bitwise_not(
            text_mask
        ),
    )

    # Loại noise nhỏ.
    kernel = np.ones(
        (3, 3),
        np.uint8,
    )

    visual_mask = cv2.morphologyEx(
        visual_mask,
        cv2.MORPH_OPEN,
        kernel,
    )

    contours, _ = cv2.findContours(
        visual_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    regions = []

    for contour in contours:

        area = cv2.contourArea(
            contour
        )

        if area < min_area:
            continue

        x, y, w, h = cv2.boundingRect(
            contour
        )

        regions.append(
            {
                "type": "visual_candidate",
                "bbox": [
                    [x, y],
                    [x + w, y],
                    [x + w, y + h],
                    [x, y + h],
                ],
                "area": int(area),
                "source": "opencv",
            }
        )

    regions.sort(
        key=lambda region:
        region["area"],
        reverse=True,
    )

    return regions