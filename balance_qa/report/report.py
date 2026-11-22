"""진단 리포트 생성 (Markdown + JSON, 문서 12장 형식 축소판)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if hasattr(obj, "to_dict"):
        return _jsonable(obj.to_dict())
    return obj


class ReportBuilder:
    def __init__(self, title: str, out_root: Union[str, Path] = "reports", run_id: Optional[str] = None) -> None:
        self.title = title
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(out_root) / self.run_id
        self._md: List[str] = ["# %s" % title, "", "- run_id: `%s`" % self.run_id]
        self._data: Dict[str, Any] = {"title": title, "run_id": self.run_id}

    # ----- 내용 추가 -----
    def meta(self, **items: Any) -> "ReportBuilder":
        for k, v in items.items():
            self._md.append("- %s: `%s`" % (k, v))
            self._data.setdefault("meta", {})[k] = _jsonable(v)
        return self

    def section(self, heading: str, text: str = "") -> "ReportBuilder":
        self._md += ["", "## %s" % heading, ""]
        if text:
            self._md += [text, ""]
        return self

    def text(self, text: str) -> "ReportBuilder":
        self._md += [text, ""]
        return self

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> "ReportBuilder":
        self._md.append("| " + " | ".join(headers) + " |")
        self._md.append("|" + "|".join("---" for _ in headers) + "|")
        for r in rows:
            self._md.append("| " + " | ".join(str(c) for c in r) + " |")
        self._md.append("")
        return self

    def dict_table(self, rows: Sequence[Dict[str, Any]]) -> "ReportBuilder":
        if not rows:
            return self
        headers = list(rows[0].keys())
        return self.table(headers, [[r.get(h, "") for h in headers] for r in rows])

    def data(self, key: str, value: Any) -> "ReportBuilder":
        self._data[key] = _jsonable(value)
        return self

    def curve(self, label: str, ys: Sequence[float], width: int = 40) -> "ReportBuilder":
        """학습 곡선 텍스트 스파크라인."""
        if not ys:
            return self
        bars = "▁▂▃▄▅▆▇█"
        y = np.asarray(ys, float)
        if len(y) > width:
            idx = np.linspace(0, len(y) - 1, width).astype(int)
            y = y[idx]
        lo, hi = float(y.min()), float(y.max())
        span = hi - lo or 1.0
        line = "".join(bars[int((v - lo) / span * (len(bars) - 1))] for v in y)
        self._md.append("`%s` %s  (%.3f → %.3f)" % (line, label, ys[0], ys[-1]))
        self._md.append("")
        return self

    # ----- 저장 -----
    def save(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "report.md").write_text("\n".join(self._md) + "\n", encoding="utf-8")
        with (self.dir / "summary.json").open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        return self.dir
