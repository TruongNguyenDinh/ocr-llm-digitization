import cv2
import numpy as np

MAX_DESKEW_ANGLE = 15.0


def estimate_skew_angle(
    image: np.ndarray,
) -> float:

    if len(image.shape) == 3:
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )
    else:
        gray = image.copy()

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV
        + cv2.THRESH_OTSU,
    )

    coords = np.column_stack(
        np.where(binary > 0)
    )

    if len(coords) < 100:
        return 0.0

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # A document deskew operation corrects small capture skew.
    # Angles near 90 degrees mean minAreaRect selected the page
    # orientation, not the baseline angle, and would crop the page.
    if abs(angle) > MAX_DESKEW_ANGLE:
        return 0.0


    return float(angle)


def rotate(
    image: np.ndarray,
    angle: float,
) -> np.ndarray:

    if abs(angle) < 0.1:
        return image

    height, width = image.shape[:2]

    center = (
        width // 2,
        height // 2,
    )

    matrix = cv2.getRotationMatrix2D(
        center,
        angle,
        1.0,
    )

    rotated = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    return rotated


def deskew(
    image: np.ndarray,
) -> tuple[np.ndarray, float]:

    angle = estimate_skew_angle(image)

    corrected = rotate(
        image,
        angle,
    )

    return corrected, angle