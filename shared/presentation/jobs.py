"""后台任务。任务对象留在界面线程，计算在普通线程里，只通过信号送回结果。

这个模块不知道具体功能。功能自己的任务继承 BaseJob。
"""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

from shared.domain.errors import Cancelled


class BaseJob(QObject):
    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cancel_event = threading.Event()
        self.gen = 0

    @Slot()
    def run(self) -> None:
        try:
            self._check_cancel()
            result = self.execute()
            self._check_cancel()
            self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def execute(self):
        raise NotImplementedError

    def report(self, done: int, total: int, message: str) -> None:
        self.progress.emit(done, total, message)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()


class JobRunner(QObject):
    """同时只跑一个任务。新任务会取消正在跑的那个，并在它结束后启动。"""

    busy = Signal()
    idle = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._gen = 0
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: BaseJob | None = None
        self._current: BaseJob | None = None
        self._running = False

    def start(self, worker: BaseJob) -> None:
        self._gen += 1
        worker.gen = self._gen
        self._cancel.set()
        self._cancel = threading.Event()
        worker.cancel_event = self._cancel
        self._replace_pending(worker)
        self.busy.emit()
        if not self._running:
            self._launch_pending()

    def cancel(self) -> None:
        self._gen += 1
        self._replace_pending(None)
        self._cancel.set()

    def shutdown(self) -> None:
        self.cancel()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=30)
        self._running = False
        self._thread = None

    def _replace_pending(self, worker: BaseJob | None) -> None:
        previous = self._pending
        self._pending = worker
        if previous is not None:
            previous.deleteLater()

    def _launch_pending(self) -> None:
        worker = self._pending
        self._pending = None
        if worker is None:
            self._running = False
            self._current = None
            self.idle.emit()
            return
        self._running = True
        self._current = worker
        worker.finished.connect(self._on_worker_finished)
        thread = threading.Thread(target=worker.run, name="dahu-image-job", daemon=True)
        self._thread = thread
        thread.start()

    def _on_worker_finished(self) -> None:
        current = self._current
        self._current = None
        self._thread = None
        if current is not None:
            current.deleteLater()
        self._running = False
        self._launch_pending()
