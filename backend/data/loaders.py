"""
数据集加载器，支持本地 JSONL/CSV 文件
"""
import csv
import json
from pathlib import Path
from typing import Any

from .schema import EvalSample


class DatasetLoadError(RuntimeError):
    pass


class DatasetLoader:
    """加载本地数据集，支持 JSONL 和 CSV 格式"""

    def load(self, path: str, input_column: str = "prompt",
             answer_column: str = "answer", limit: int | None = None) -> list[EvalSample]:
        file_path = Path(path)
        if not file_path.exists():
            raise DatasetLoadError(f"Dataset file not found: {path}")

        rows = self._load_file(file_path)
        if limit:
            rows = rows[:limit]
        return self._map_rows(rows, input_column, answer_column)

    def _load_file(self, path: Path) -> list[dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        else:
            raise DatasetLoadError("Only .jsonl and .csv formats are supported")

    @staticmethod
    def _map_rows(rows: list[dict[str, Any]], input_column: str,
                  answer_column: str) -> list[EvalSample]:
        reserved = {input_column, answer_column}
        samples: list[EvalSample] = []
        for idx, row in enumerate(rows):
            answer_val = row.get(answer_column)
            answer = _extract_answer(answer_val)
            samples.append(EvalSample(
                sample_id=str(row.get("id", idx)),
                prompt=str(row.get(input_column, "")),
                answer=answer,
                metadata={k: v for k, v in row.items() if k not in reserved},
            ))
        return samples


def _extract_answer(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, list) and text:
            return str(text[0])
        if text is not None:
            return str(text)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)
