from dataclasses import dataclass


@dataclass
class OCRBlock:
    text: str
    confidence: float
    bbox: list[list[float]]
    reading_order: int = 0

    @property
    def x_min(self) -> float:
        return min(point[0] for point in self.bbox)

    @property
    def y_min(self) -> float:
        return min(point[1] for point in self.bbox)

    @property
    def x_max(self) -> float:
        return max(point[0] for point in self.bbox)

    @property
    def y_max(self) -> float:
        return max(point[1] for point in self.bbox)

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2