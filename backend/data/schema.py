"""
评测数据样本 Schema
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalSample:
    sample_id: str
    prompt: str
    answer: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
