"""
合成数据生成器

参考 GuideLLM 的 SyntheticTextDataset 设计，为压测引擎提供可配置的
合成 prompt 生成能力，替代硬编码的默认 prompt 列表。

特性：
- 可配置 prompt 长度（平均值 + 标准差 + 最小/最大值）
- 支持正态分布采样，模拟真实场景的 token 长度分布
- 使用内置模板 + 随机组合生成多样化文本
- 支持指定自定义 prompt 模板
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SyntheticDataConfig:
    """合成数据配置"""
    # prompt token 长度控制
    prompt_tokens: int = 256
    prompt_tokens_stdev: Optional[int] = None
    prompt_tokens_min: Optional[int] = None
    prompt_tokens_max: Optional[int] = None

    # output token 长度控制（用于 payload 的 max_tokens 参数）
    output_tokens: int = 128
    output_tokens_stdev: Optional[int] = None
    output_tokens_min: Optional[int] = None
    output_tokens_max: Optional[int] = None

    # 自定义 prompt 模板列表（可选）
    templates: Optional[List[str]] = None

    # 数据源：'builtin' 使用内置模板，'templates' 使用自定义模板
    source: str = 'builtin'

    random_seed: Optional[int] = None


class TokenLengthSampler:
    """
    Token 长度采样器，支持正态分布采样。

    通过字符数近似 token 数（中文约 1.5 字符/token，英文约 4 字符/token），
    使用混合文本确保长度分布合理。
    """

    def __init__(
        self,
        average: int,
        stdev: Optional[int] = None,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        random_seed: Optional[int] = None,
    ):
        self.average = average
        self.stdev = stdev
        self.min_value = max(1, min_value) if min_value else 1
        self.max_value = max_value if max_value else average * 5
        self._rng = random.Random(random_seed)

    def sample(self) -> int:
        """采样一个 token 长度值"""
        if self.stdev and self.stdev > 0:
            value = self._rng.gauss(self.average, self.stdev)
        else:
            value = self.average

        value = max(self.min_value, min(self.max_value, int(round(value))))
        return value


# 内置 prompt 模板，按主题分类
_BUILTIN_TEMPLATES = {
    'technology': [
        "请用{length}字左右介绍{topic}的核心原理和应用场景。",
        "详细解释{topic}的工作机制，包括其主要组件和数据流。",
        "{topic}在实际生产环境中的最佳实践是什么？请从架构设计、性能优化、安全防护等多个角度进行分析。",
        "对比分析{topic}与{alternative}的优缺点，包括性能、可扩展性、易用性和社区生态等方面。",
        "如何设计一个高可用的{topic}系统？请详细描述架构方案和关键决策点。",
    ],
    'science': [
        "请解释{topic}的基本概念和发展历程。",
        "{topic}在现代科学研究中有哪些重要应用？请举例说明。",
        "从物理学/化学/生物学的角度分析{topic}的本质特征。",
        "描述{topic}实验的设计方案，包括变量控制和数据分析方法。",
    ],
    'business': [
        "分析{topic}行业的市场现状和发展趋势。",
        "如何制定{topic}的商业化策略？请给出具体的执行计划。",
        "从财务、运营、市场三个维度评估{topic}项目的风险和收益。",
        "设计一个{topic}的用户增长方案，包括获客渠道和留存策略。",
    ],
    'general': [
        "请详细阐述以下主题：{topic}",
        "针对{topic}这个话题，请给出你的分析和见解。",
        "从多个角度讨论{topic}的重要性和影响。",
        "请用通俗易懂的语言解释{topic}，让非专业人士也能理解。",
    ],
}

# 主题词库
_TOPICS = {
    'technology': [
        '大语言模型', 'Transformer架构', '注意力机制', '分布式计算',
        '微服务架构', '容器编排', '深度学习', '强化学习',
        '联邦学习', '图神经网络', '自然语言处理', '计算机视觉',
        'RAG技术', '向量数据库', '模型量化', '推理优化',
        'KV Cache', 'FlashAttention', 'MoE架构', 'Agent框架',
        '知识蒸馏', '模型并行', '流水线并行', '梯度累积',
    ],
    'science': [
        '量子计算', '基因编辑', '暗物质', '超导材料',
        '核聚变', '黑洞', '引力波', 'CRISPR',
        '纳米技术', '光合作用', '蛋白质折叠', '表观遗传学',
    ],
    'business': [
        'SaaS产品', '跨境电商', '数字营销', '供应链管理',
        '用户增长', '商业模式创新', '数据驱动决策', '敏捷开发',
        'DevOps实践', '技术团队管理', '产品定价策略', '市场竞争分析',
    ],
    'general': [
        '人工智能的未来发展', '数字化转型', '可持续发展', '教育创新',
        '远程办公', '数据隐私保护', '技术伦理', '终身学习',
        '创新思维', '跨文化交流', '决策科学', '复杂系统',
    ],
}

# 指令前缀（模拟真实用户提问风格）
_INSTRUCTION_PREFIXES = [
    "",
    "请回答以下问题：",
    "我需要你的帮助来理解：",
    "能否详细说明：",
    "请从专业角度分析：",
    "帮我解答这个问题：",
    "请提供详细的分析：",
    "",
]


class SyntheticPromptGenerator:
    """
    合成 prompt 生成器。

    根据配置生成指定长度的 prompt 文本，支持：
    - 基于模板的文本生成
    - Token 长度的正态分布采样
    - 多样化的主题和表述方式
    """

    def __init__(self, config: SyntheticDataConfig):
        self.config = config
        self._rng = random.Random(config.random_seed or int(time.time()))

        # 初始化 token 长度采样器
        self._prompt_sampler = TokenLengthSampler(
            average=config.prompt_tokens,
            stdev=config.prompt_tokens_stdev,
            min_value=config.prompt_tokens_min,
            max_value=config.prompt_tokens_max,
            random_seed=config.random_seed,
        )
        self._output_sampler = TokenLengthSampler(
            average=config.output_tokens,
            stdev=config.output_tokens_stdev,
            min_value=config.output_tokens_min,
            max_value=config.output_tokens_max,
            random_seed=(config.random_seed or 0) + 1,
        )

        # 预计算所有主题词列表
        self._all_topics = []
        for topics in _TOPICS.values():
            self._all_topics.extend(topics)

    def generate_prompt(self, index: int = 0) -> str:
        """
        生成一个 prompt 文本。

        Args:
            index: 请求序号，用于确保生成的 prompt 有差异

        Returns:
            生成的 prompt 文本
        """
        if self.config.source == 'templates' and self.config.templates:
            return self._generate_from_templates(index)

        return self._generate_builtin(index)

    def sample_output_tokens(self) -> int:
        """采样一个 output token 数值"""
        return self._output_sampler.sample()

    def _generate_builtin(self, index: int) -> str:
        """使用内置模板生成 prompt"""
        target_chars = self._estimate_chars(self._prompt_sampler.sample())

        # 选择主题类别和模板
        category = self._rng.choice(list(_BUILTIN_TEMPLATES.keys()))
        template = self._rng.choice(_BUILTIN_TEMPLATES[category])
        topic = self._rng.choice(_TOPICS[category])
        alternative = self._rng.choice(self._all_topics)

        # 填充模板
        prefix = self._rng.choice(_INSTRUCTION_PREFIXES)
        prompt = prefix + template.format(
            topic=topic,
            alternative=alternative,
            length=max(100, target_chars // 2),
        )

        # 如果 prompt 不够长，追加更多上下文
        prompt = self._extend_to_length(prompt, target_chars, index)
        return prompt

    def _generate_from_templates(self, index: int) -> str:
        """使用自定义模板生成 prompt"""
        templates = self.config.templates or []
        if not templates:
            return self._generate_builtin(index)

        template = templates[index % len(templates)]
        target_chars = self._estimate_chars(self._prompt_sampler.sample())

        # 追加填充文本使 prompt 达到目标长度
        return self._extend_to_length(template, target_chars, index)

    def _estimate_chars(self, token_count: int) -> int:
        """
        估算 token 数对应的字符数。

        中文约 1.5 字符/token，英文约 4 字符/token，
        混合场景取约 2.5 字符/token。
        """
        return int(token_count * 2.5)

    def _extend_to_length(self, text: str, target_chars: int, index: int) -> str:
        """将文本扩展到目标长度"""
        if len(text) >= target_chars:
            return text[:target_chars]

        # 追加额外的问题和上下文
        fillers = [
            "\n\n请确保回答全面、准确，并提供具体的例子来支持你的观点。",
            "\n\n请从理论和实践两个层面进行分析。",
            "\n\n如果涉及到技术实现，请简要描述核心算法或架构。",
            "\n\n请考虑该领域的最新进展和未来发展方向。",
            "\n\n在回答时请注意区分概念、分类和层次。",
            f"\n\n上下文编号：{index}。请基于最新的知识进行回答。",
        ]

        while len(text) < target_chars:
            filler = self._rng.choice(fillers)
            text += filler

        return text[:target_chars]

    def generate(self, count: int) -> List[dict]:
        """
        批量生成 prompt 数据。

        Args:
            count: 生成数量

        Returns:
            包含 prompt 和 output_tokens 的字典列表
        """
        results = []
        for i in range(count):
            results.append({
                'prompt': self.generate_prompt(i),
                'output_tokens': self.sample_output_tokens(),
            })
        return results
