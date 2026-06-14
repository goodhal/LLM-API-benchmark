"""
LLM-as-Judge 评测指标

使用评价模型对目标模型的输出进行评分，适用于开放式问答、
创意写作等难以用文本匹配评分的场景。

评分方式：1-5 分制，归一化为 0-1 用于与其他指标统一展示。
"""
import re

# 默认评判 Prompt 模板
JUDGE_PROMPT_TEMPLATE = """你是一个专业的答案评判助手。请根据以下标准对模型的回答进行评分。

【问题】
{prompt}

【参考答案】
{reference}

【模型回答】
{prediction}

【评分标准】
1分：完全错误或无关
2分：部分相关但存在重大错误
3分：基本正确但不够完整或有轻微错误
4分：正确且较为完整，仅有小瑕疵
5分：完全正确且完整

【输出格式】
请先简要分析，然后在最后一行严格按以下格式输出评分（不要输出其他内容）：
SCORE:1 ~ SCORE:5

示例：
模型回答包含了参考答案的核心内容，且补充了相关信息。
SCORE:5"""


def build_judge_prompt(prompt: str, reference: str, prediction: str) -> str:
    """构建评判 Prompt"""
    return JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt,
        reference=reference,
        prediction=prediction,
    )


def parse_judge_score(response: str) -> float:
    """
    解析 judge 模型的评分响应，返回归一化到 0-1 的分数。

    优先匹配约定的 SCORE:N 格式，其次从后往前匹配其他格式。
    """
    if not response or not response.strip():
        return float('nan')

    text = response.strip()
    lines = text.split('\n')

    # 最高优先级：匹配约定的 SCORE:N 格式（从后往前）
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        match = re.match(r'SCORE\s*[：:]\s*([1-5])', line, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            return (score - 1) / 4.0

    # 次优先级：从后往前匹配其他评分模式
    score_patterns = [
        r'[评打]分[：:]\s*([1-5])',      # 评分：5 / 打分：3
        r'[Ss]core\s*[：:]\s*([1-5])',   # Score: 5
        r'([1-5])\s*分',                   # 5分
        r'^([1-5])\s*$',                   # 纯数字（整行）
    ]

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        for pattern in score_patterns:
            match = re.search(pattern, line)
            if match:
                score = int(match.group(1))
                return (score - 1) / 4.0

    # 中文数字映射（从后往前）
    cn_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5}
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        for cn, num in cn_map.items():
            if cn in line:
                return (num - 1) / 4.0

    # 最后兜底：找最后一个 1-5 数字
    all_matches = list(re.finditer(r'[1-5]', text))
    if all_matches:
        score = int(all_matches[-1].group())
        return (score - 1) / 4.0

    return float('nan')
