"""
维度化评判器

借鉴 llm-test-platform 的评估设计：
- 支持 keyword_match 快速筛选（primary 层）
- 支持 llm_judge 深度评判（primary/secondary 层，使用自定义 criteria）
- 支持无参考答案的主观评判
- 支持可配置的通过阈值
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.prompts import Prompt


# ============================================================
# 维度化 LLM Judge Prompt 模板
# ============================================================

DIMENSIONAL_JUDGE_TEMPLATE = """你是一个严格的专业评审系统，请根据以下维度对回答进行评分。

【问题】
{question}

【回答】
{answer}

【评审维度】
{criteria_text}

【评分规则】
每个维度 1-5 分，综合评分取各维度平均分。
5分：完全符合维度要求，表现优秀
4分：基本符合，有小瑕疵
3分：部分符合，有明显不足
2分：勉强相关，存在较大问题
1分：完全不符合或无关

必须严格返回 JSON（不要任何多余文字，不要 markdown 代码块）：
{{
  "dimensions": {{
    "dim_name_1": score1,
    "dim_name_2": score2
  }},
  "overall_score": float (1-5),
  "reason": "综合评审理由",
  "is_correct": boolean
}}

只输出纯 JSON，不要解释。"""


# ============================================================
# 维度化评判器
# ============================================================

class DimensionalJudgeEvaluator:
    """维度化 LLM Judge 评判器：按自定义维度评判，不需要参考答案"""

    def __init__(self, judge_url: str, judge_api_key: str, judge_model: str):
        self.judge_url = judge_url.rstrip("/")
        self.judge_api_key = judge_api_key
        self.judge_model = judge_model

    def evaluate(self, question: str, answer: str, criteria: List[str]) -> Dict[str, Any]:
        """按自定义维度评判，返回结构化的评分结果"""
        if not criteria:
            criteria = ["整体质量"]

        criteria_text = "\n".join(f"- {c}" for c in criteria)
        prompt = DIMENSIONAL_JUDGE_TEMPLATE.format(
            question=question,
            answer=answer[:8000],  # 截断过长回答
            criteria_text=criteria_text,
        )

        judge_response = self._call_judge(prompt)
        return self._parse_result(judge_response, criteria)

    def _call_judge(self, prompt: str) -> str:
        import requests
        try:
            resp = requests.post(
                f"{self.judge_url}/chat/completions",
                json={
                    "model": self.judge_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.judge_api_key}",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Judge API call failed: {e}")

    @staticmethod
    def _parse_result(text: str, criteria: List[str]) -> Dict[str, Any]:
        # 提取 JSON
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            text = code_block.group(1)
        else:
            json_match = re.search(r"(\{.*\})", text, re.DOTALL)
            if json_match:
                text = json_match.group(1)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {
                "success": False,
                "score": 0.0,
                "reason": f"Judge JSON parse failed: {text[:200]}",
                "dimensions": {},
                "raw": text,
            }

        overall = float(data.get("overall_score", data.get("score", 0)))
        dimensions = data.get("dimensions", {})

        # 归一化到 0-1
        normalized = (overall - 1) / 4.0
        success = bool(data.get("is_correct", normalized >= 0.6))

        return {
            "success": success,
            "score": round(max(0.0, min(1.0, normalized)), 4),
            "score_raw": round(overall, 2),
            "reason": data.get("reason", ""),
            "dimensions": dimensions,
            "criteria": criteria,
        }


# ============================================================
# 分层评估器：primary + secondary
# ============================================================

class LayeredEvaluator:
    """分层评估器：primary 快筛 + secondary 深度评判

    primary 层：keyword_match（快速，零成本）或 llm_judge
    secondary 层：llm_judge（仅 primary 通过时执行，节省 API 成本）
    """

    def __init__(
        self,
        judge_url: Optional[str] = None,
        judge_api_key: Optional[str] = None,
        judge_model: Optional[str] = None,
    ):
        self._judge = None
        if judge_url and judge_api_key and judge_model:
            self._judge = DimensionalJudgeEvaluator(judge_url, judge_api_key, judge_model)

    def evaluate(
        self,
        prompt: "Prompt",
        response: str,
        pass_threshold: float = 0.6,
    ) -> Dict[str, Any]:
        """对模型响应进行分层评估"""
        result = {
            "prompt_id": prompt.id,
            "prompt_name": prompt.name,
            "primary": None,
            "secondary": None,
            "overall_score": 0.0,
            "passed": False,
        }

        # Primary 层评估
        primary_config = prompt.evaluation.get("primary", {})
        primary_type = primary_config.get("type", "keyword_match")

        if primary_type == "keyword_match":
            keywords = primary_config.get("keywords", [])
            if keywords:
                matched = sum(1 for kw in keywords if str(kw).lower() in response.lower())
                score = matched / len(keywords)
            else:
                score = 1.0  # 无关键词默认通过
            result["primary"] = {
                "type": "keyword_match",
                "score": round(score, 4),
                "matched": matched if keywords else 0,
                "total": len(keywords),
            }
        elif primary_type == "llm_judge" and self._judge:
            criteria = primary_config.get("criteria", ["整体质量"])
            judge_result = self._judge.evaluate(prompt.template, response, criteria)
            result["primary"] = {"type": "llm_judge", **judge_result}
            score = judge_result["score"]
        else:
            result["primary"] = {"type": "none", "score": 1.0}
            score = 1.0

        # Primary 不通过则直接失败
        if score < pass_threshold:
            result["overall_score"] = round(score, 4)
            result["passed"] = False
            return result

        # Secondary 层评估（深度评判）
        secondary_config = prompt.evaluation.get("secondary", {})
        if secondary_config and self._judge:
            secondary_type = secondary_config.get("type")
            if secondary_type == "llm_judge":
                criteria = secondary_config.get("criteria", ["整体质量"])
                judge_result = self._judge.evaluate(prompt.template, response, criteria)
                result["secondary"] = {"type": "llm_judge", **judge_result}
                score = judge_result["score"]
            elif secondary_type == "keyword_match":
                keywords = secondary_config.get("keywords", [])
                if keywords:
                    matched = sum(1 for kw in keywords if str(kw).lower() in response.lower())
                    score = matched / len(keywords)
                else:
                    score = 1.0
                result["secondary"] = {
                    "type": "keyword_match",
                    "score": round(score, 4),
                    "matched": matched if keywords else 0,
                    "total": len(keywords),
                }

        result["overall_score"] = round(score, 4)
        result["passed"] = score >= pass_threshold
        return result


# ============================================================
# 语义相似度计算（用于一致性测试）
# ============================================================

def compute_similarity(texts: List[str]) -> Tuple[float, float, List[float]]:
    """
    计算文本集合的语义相似度（基于 Jaccard 字符 trigram 近似）

    返回: (mean_similarity, min_similarity, pairwise_scores)
    """
    if len(texts) < 2:
        return 1.0, 1.0, [1.0]

    pairwise = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = _jaccard_trigram(texts[i], texts[j])
            pairwise.append(sim)

    if not pairwise:
        return 1.0, 1.0, [1.0]

    return sum(pairwise) / len(pairwise), min(pairwise), pairwise


def _jaccard_trigram(text_a: str, text_b: str) -> float:
    """基于字符 trigram 的 Jaccard 相似度"""
    def trigrams(s):
        s = s.lower().strip()
        return {s[i:i+3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}

    set_a = trigrams(text_a)
    set_b = trigrams(text_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
