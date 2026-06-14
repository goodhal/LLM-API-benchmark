"""
文本评测指标实现

改进说明：
- token_f1 / rouge_l 使用字符级分词（每个非空格字符作为一个 token），
  解决中文按空格分词后整句变成一个 token 导致指标失效的问题。
- token_f1 / rouge_l / char_f1 使用 recall-biased F-beta 评分（beta=2），
  当参考答案较短而模型输出包含正确答案但附带解释时，recall 更重要，
  避免 precision 稀释导致评分过低。
- contains_match 检查参考答案是否被模型输出包含，适用于短答案 QA / 数学数据集。
"""
import re
from collections import Counter

# F-beta 中的 beta 参数，beta>1 偏向 recall
_BETA = 2.0
_BETA_SQ = _BETA ** 2


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _char_tokenize(text: str) -> list[str]:
    """字符级分词：每个非空格字符作为一个 token，中英文通用"""
    return [ch for ch in text if ch.strip()]


def _fbeta(precision: float, recall: float) -> float:
    """计算 F-beta 分数，beta>1 时偏向 recall"""
    if precision + recall == 0:
        return 0.0
    return (1 + _BETA_SQ) * precision * recall / (_BETA_SQ * precision + recall)


def exact_match(prediction: str, reference: str) -> float:
    return float(normalize_text(prediction) == normalize_text(reference))


def contains_match(prediction: str, reference: str) -> float:
    """检查参考答案是否包含在模型输出中（适用于短答案QA/数学数据集）"""
    return float(normalize_text(reference) in normalize_text(prediction))


def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = _char_tokenize(normalize_text(prediction))
    ref_tokens = _char_tokenize(normalize_text(reference))
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    overlap = Counter(pred_tokens) & Counter(ref_tokens)
    shared = sum(overlap.values())
    if shared == 0:
        return 0.0
    precision = shared / len(pred_tokens)
    recall = shared / len(ref_tokens)
    return _fbeta(precision, recall)


def rouge_l(prediction: str, reference: str) -> float:
    pred_tokens = _char_tokenize(normalize_text(prediction))
    ref_tokens = _char_tokenize(normalize_text(reference))
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    lcs = _lcs_len(pred_tokens, ref_tokens)
    precision = lcs / len(pred_tokens)
    recall = lcs / len(ref_tokens)
    return _fbeta(precision, recall)


def char_f1(prediction: str, reference: str) -> float:
    pred_chars = list(normalize_text(prediction).replace(" ", ""))
    ref_chars = list(normalize_text(reference).replace(" ", ""))
    if not pred_chars and not ref_chars:
        return 1.0
    if not pred_chars or not ref_chars:
        return 0.0
    overlap = Counter(pred_chars) & Counter(ref_chars)
    shared = sum(overlap.values())
    if shared == 0:
        return 0.0
    precision = shared / len(pred_chars)
    recall = shared / len(ref_chars)
    return _fbeta(precision, recall)


def _lcs_len(a: list[str], b: list[str]) -> int:
    dp = [0] * (len(b) + 1)
    for token_a in a:
        prev = 0
        for j, token_b in enumerate(b, start=1):
            cur = dp[j]
            if token_a == token_b:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    return dp[-1]
