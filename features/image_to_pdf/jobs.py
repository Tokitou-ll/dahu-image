"""图片转 PDF 的估算和导出任务。"""

from __future__ import annotations

from pathlib import Path

from features.image_to_pdf.service import (
    ExportOutcome,
    Plan,
    plan_pages,
    write_pdf,
)
from features.image_to_pdf.settings import ExportSettings
from shared.presentation.jobs import BaseJob


class EstimateJob(BaseJob):
    def __init__(self, paths: list[str], settings: ExportSettings) -> None:
        super().__init__()
        self.paths = list(paths)
        self.settings = settings

    def execute(self) -> Plan:
        return plan_pages(self.paths, self.settings, self.report, self.cancel_event.is_set)


class ExportJob(BaseJob):
    def __init__(
        self,
        paths: list[str],
        settings: ExportSettings,
        output_path: str,
        plan: Plan | None = None,
    ) -> None:
        super().__init__()
        self.paths = list(paths)
        self.settings = settings
        self.output_path = output_path
        self.plan = plan

    def execute(self) -> ExportOutcome:
        plan = self.plan
        if plan is None:
            plan = plan_pages(self.paths, self.settings, self.report, self.cancel_event.is_set)
        self._check_cancel()
        self.report(plan.page_count, plan.page_count, "正在写入 PDF")
        size = write_pdf(plan.jpeg_pages, self.settings, Path(self.output_path))
        return ExportOutcome(
            output_path=str(self.output_path),
            output_bytes=size,
            page_count=plan.page_count,
            note=plan.note,
            source_bytes=plan.source_bytes,
            hit_target=plan.hit_target,
            quality=plan.quality,
            scale=plan.scale,
        )
