import cv2
import numpy as np


def resize_if_needed(
    image: np.ndarray,
    min_width: int = 1600,
) -> np.ndarray:

    height, width = image.shape[:2]

    if width >= min_width:
        return image

    scale = min_width / width

    new_width = int(width * scale)
    new_height = int(height * scale)

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_CUBIC,
    )