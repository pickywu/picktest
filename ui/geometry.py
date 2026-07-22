"""與 Arcade 無關的 UI 幾何工具，供繪圖與點擊區共用。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: float
    bottom: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def top(self) -> float:
        return self.bottom + self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def center_y(self) -> float:
        return self.bottom + self.height / 2

    def inset(self, horizontal: float, vertical: float | None = None) -> "Rect":
        vertical = horizontal if vertical is None else vertical
        return Rect(
            self.left + horizontal,
            self.bottom + vertical,
            max(0.0, self.width - horizontal * 2),
            max(0.0, self.height - vertical * 2),
        )

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.bottom <= y <= self.top


def centered_row(count: int, item_width: float, gap: float,
                 center_x: float) -> tuple[float, ...]:
    """回傳一列物件的中心 X，避免每個畫面各寫一套置中公式。"""
    if count <= 0:
        return ()
    total = count * item_width + (count - 1) * gap
    first = center_x - total / 2 + item_width / 2
    return tuple(first + index * (item_width + gap) for index in range(count))
