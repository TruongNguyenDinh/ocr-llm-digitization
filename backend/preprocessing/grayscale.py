import cv2
import numpy as np


def to_grayscale(image: np.ndarray) -> np.ndarray:

    if len(image.shape) == 2:
        return image

    return cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )