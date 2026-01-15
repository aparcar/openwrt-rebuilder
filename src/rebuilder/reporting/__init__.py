"""Reporting and output generation."""

from rebuilder.reporting.html import HTMLReportGenerator, generate_reports
from rebuilder.reporting.json_output import (
    load_rbvf_output,
    merge_rbvf_outputs,
    write_rbvf_output,
)

__all__ = [
    "write_rbvf_output",
    "load_rbvf_output",
    "merge_rbvf_outputs",
    "HTMLReportGenerator",
    "generate_reports",
]
