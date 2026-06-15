"""
Prompt 库加载器

借鉴 llm-test-platform 的设计：
- 从 YAML 文件加载 Prompt 库
- 支持 ref 格式引用：'qa/general.yaml#qa_001'
- 自动扫描 data/prompts/ 目录
"""
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from . import Prompt, PromptLibrary


class PromptLoader:
    """Prompt 库加载器"""

    def __init__(self, base_path: str = "data/prompts"):
        self.base_path = Path(base_path)

    def load_library(self, file_path: str) -> PromptLibrary:
        """加载单个 Prompt 库 YAML 文件"""
        full_path = self.base_path / file_path
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt library not found: {file_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        prompts = [self._parse_prompt(item) for item in data.get("prompts", [])]

        return PromptLibrary(
            name=data.get("library", Path(file_path).stem),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            prompts=prompts,
        )

    def load_all(self) -> Dict[str, PromptLibrary]:
        """加载所有 Prompt 库"""
        libraries = {}
        if not self.base_path.exists():
            return libraries

        for yaml_file in self.base_path.rglob("*.yaml"):
            rel_path = str(yaml_file.relative_to(self.base_path))
            try:
                library = self.load_library(rel_path)
                libraries[library.name] = library
            except Exception:
                continue
        return libraries

    def get_prompt(self, ref: str) -> Optional[Prompt]:
        """根据引用获取 Prompt，格式: 'path/to/file.yaml#prompt_id'"""
        if "#" not in ref:
            return None
        file_path, prompt_id = ref.rsplit("#", 1)
        library = self.load_library(file_path)
        return library.get_prompt(prompt_id)

    def list_prompts(self) -> List[Dict]:
        """列出所有 Prompt 的元信息（供前端使用）"""
        results = []
        if not self.base_path.exists():
            return results

        for yaml_file in sorted(self.base_path.rglob("*.yaml")):
            rel_path = str(yaml_file.relative_to(self.base_path))
            try:
                library = self.load_library(rel_path)
                for p in library.prompts:
                    results.append({
                        "id": p.id,
                        "ref": f"{rel_path}#{p.id}",
                        "name": p.name,
                        "category": p.category,
                        "tags": p.tags,
                        "template_preview": p.template[:80] + ("..." if len(p.template) > 80 else ""),
                        "eval_type": p.get_eval_type(),
                        "library": library.name,
                    })
            except Exception:
                continue
        return results

    @staticmethod
    def _parse_prompt(data: Dict) -> Prompt:
        return Prompt(
            id=data["id"],
            name=data.get("name", data["id"]),
            template=data["template"],
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            variables=data.get("variables", {}),
            evaluation=data.get("evaluation", {}),
            metadata=data.get("metadata", {}),
        )
