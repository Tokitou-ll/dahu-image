"""可以跨层传递的错误。这里没有界面依赖。"""

from __future__ import annotations

from pathlib import Path


class Cancelled(Exception):
    """协作式取消。调用方应停止当前任务，不要当成失败。"""


class ImagePrepareError(Exception):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"无法读取「{self.path.name}」：{reason}")
