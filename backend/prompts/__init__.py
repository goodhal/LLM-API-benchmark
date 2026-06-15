"""
Prompt 数据模型

借鉴 llm-test-platform 的 Prompt 库设计：
- Prompt 与测试逻辑解耦，定义一次多处复用
- 每个 Prompt 自带评估标准（keyword_match / llm_judge + criteria）
- 支持变量模板、标签分类
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Prompt:
    """可复用的 Prompt 定义"""
    id: str
    name: str
    template: str
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_keywords(self) -> List[str]:
        """获取 primary 级别的关键词列表（用于 keyword_match 评估）"""
        primary = self.evaluation.get("primary", {})
        if primary.get("type") == "keyword_match":
            return primary.get("keywords", [])
        return []

    def get_eval_type(self) -> str:
        """获取主要评估类型"""
        return self.evaluation.get("primary", {}).get("type", "keyword_match")


@dataclass
class PromptLibrary:
    """Prompt 库"""
    name: str
    description: str = ""
    version: str = "1.0"
    prompts: List[Prompt] = field(default_factory=list)

    def get_prompt(self, prompt_id: str) -> Optional[Prompt]:
        for p in self.prompts:
            if p.id == prompt_id:
                return p
        return None

    def list_categories(self) -> List[str]:
        return sorted(set(p.category for p in self.prompts))
