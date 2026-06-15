"""
Prompt 变换器框架 --- 借鉴 PyRIT 的 PromptConverter 设计

提供可组合的 prompt 攻击变换链，用于安全审计时的攻击面扩展。
每个 Converter 接收原始 prompt，返回变换后的 prompt。
多个 Converter 可以链式组合。
"""

from .text_converters import (
    PromptConverter,
    ConverterRegistry,
    Base64Converter,
    ROT13Converter,
    UnicodeConverter,
    LeetspeakConverter,
    SuffixAppendConverter,
    CharacterSpaceConverter,
    FlipConverter,
    AsciiArtConverter,
    BinaryConverter,
    AtbashConverter,
    DiacriticConverter,
    RolePlayConverter,
    build_converter_chain,
    list_available_converters,
)
