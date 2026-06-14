"""
评测指标管理器

llm_judge 为特殊指标，需要调用评价模型 API，
在 MetricsManager 中注册占位函数（始终返回 nan），
实际评分在 executor 中异步完成。
"""
from collections import defaultdict
from .text_metrics import contains_match, exact_match, rouge_l, token_f1


def _llm_judge_placeholder(prediction: str, reference: str) -> float:
    """llm_judge 占位函数，实际评分在 executor 中异步完成"""
    return float('nan')


class MetricsManager:
    def __init__(self, metric_names: list[str]):
        self.metric_names = metric_names
        self._impls = {
            "exact_match": exact_match,
            "token_f1": token_f1,
            "rouge_l": rouge_l,
            "contains_match": contains_match,
            "llm_judge": _llm_judge_placeholder,
        }

    def score_sample(self, prediction: str, reference: str | None) -> dict[str, float]:
        if reference is None:
            return {name: float("nan") for name in self.metric_names}
        scores: dict[str, float] = {}
        for name in self.metric_names:
            if name not in self._impls:
                continue  # 跳过不支持的指标（如已移除的 char_f1）
            scores[name] = self._impls[name](prediction, reference)
        return scores

    def aggregate(self, sample_scores: list[dict[str, float]]) -> dict[str, float]:
        buckets: dict[str, list[float]] = defaultdict(list)
        for item in sample_scores:
            for k, v in item.items():
                if k == 'judge_details':
                    continue  # judge_details 是嵌套字典，在 executor 中单独聚合
                if v == v:  # skip nan
                    buckets[k].append(v)
        return {k: (sum(vs) / len(vs) if vs else float("nan")) for k, vs in buckets.items()}
