"""
自研 LLM API 压测引擎

替代 subprocess 调用 evalscope CLI，直接使用 aiohttp 发送 HTTP 请求。
优势：
- 实时指标收集（无需等进程结束）
- 精确测量 TTFT/TPOT（流式响应逐 chunk 计时）
- 支持动态调整并发数
- 无 SQLite 锁冲突（不依赖子进程写文件）
- 多种调度策略（固定并发、固定速率、泊松分布）
- 合成数据生成（可配置 prompt 长度分布）
- 完整百分位统计（p0.1 ~ p99.9）
"""

import asyncio
import json
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# 导入合成数据生成器
try:
    from ..data.synthetic import SyntheticDataConfig, SyntheticPromptGenerator
except ImportError:
    SyntheticPromptGenerator = None
    SyntheticDataConfig = None


@dataclass
class RequestMetric:
    """单次请求的指标"""
    success: bool
    response_time: float  # 总响应时间（秒）
    ttft: Optional[float] = None  # 首字延迟（秒）
    tpot: Optional[float] = None  # 每 Token 时间（秒）
    tokens_per_second: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_type: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """线程安全的指标收集器"""

    def __init__(self, max_history=600):
        self._lock = Lock()
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_response_time = 0.0
        self._response_times: List[float] = []
        self._ttft_list: List[float] = []
        self._tpot_list: List[float] = []
        self._tps_list: List[float] = []  # tokens per second (per request)
        self._completion_tokens_list: List[int] = []  # completion tokens per request
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._error_types: Dict[str, int] = {}
        self._start_time: Optional[float] = None
        self._snapshots: deque = deque(maxlen=max_history)
        self._last_snapshot_time: Optional[float] = None
        self._last_snapshot_count = 0

    def record(self, metric: RequestMetric):
        """记录一次请求的指标"""
        with self._lock:
            if self._start_time is None:
                self._start_time = metric.timestamp

            self._request_count += 1
            self._total_response_time += metric.response_time
            self._response_times.append(metric.response_time)

            if metric.success:
                self._success_count += 1
                if metric.ttft is not None:
                    self._ttft_list.append(metric.ttft)
                if metric.tpot is not None:
                    self._tpot_list.append(metric.tpot)
                if metric.tokens_per_second is not None:
                    self._tps_list.append(metric.tokens_per_second)
                if metric.completion_tokens > 0:
                    self._completion_tokens_list.append(metric.completion_tokens)
                self._prompt_tokens += metric.prompt_tokens
                self._completion_tokens += metric.completion_tokens
                self._total_tokens += metric.total_tokens
            else:
                self._error_count += 1
                if metric.error_type:
                    self._error_types[metric.error_type] = self._error_types.get(metric.error_type, 0) + 1

    def snapshot(self) -> Dict:
        """生成当前指标的快照"""
        with self._lock:
            now = time.time()
            elapsed = now - self._start_time if self._start_time else 0

            # 计算增量 RPS
            if self._last_snapshot_time and self._last_snapshot_time > 0:
                delta_t = now - self._last_snapshot_time
                delta_count = self._request_count - self._last_snapshot_count
                rps = delta_count / delta_t if delta_t > 0 else 0
            else:
                rps = self._request_count / elapsed if elapsed > 0 else 0

            self._last_snapshot_time = now
            self._last_snapshot_count = self._request_count

            snap = {
                'timestamp': now,
                'request_count': self._request_count,
                'success_count': self._success_count,
                'error_count': self._error_count,
                'rps': round(rps, 2),
                'avg_response_time': round(self._total_response_time / self._request_count, 4) if self._request_count > 0 else 0,
                'success_rate': round(self._success_count / self._request_count * 100, 1) if self._request_count > 0 else 0,
                'prompt_tokens': self._prompt_tokens,
                'completion_tokens': self._completion_tokens,
                'total_tokens': self._total_tokens,
            }

            # 百分位计算
            if self._response_times:
                snap['p50_latency'] = round(self._percentile(self._response_times, 50), 4)
                snap['p90_latency'] = round(self._percentile(self._response_times, 90), 4)
                snap['p95_latency'] = round(self._percentile(self._response_times, 95), 4)
                snap['p99_latency'] = round(self._percentile(self._response_times, 99), 4)
                snap['avg_latency'] = round(sum(self._response_times) / len(self._response_times), 4)

            if self._ttft_list:
                snap['avg_ttft'] = round(sum(self._ttft_list) / len(self._ttft_list) * 1000, 2)  # ms
                snap['p99_ttft'] = round(self._percentile(self._ttft_list, 99) * 1000, 2)

            if self._tpot_list:
                snap['avg_tpot'] = round(sum(self._tpot_list) / len(self._tpot_list) * 1000, 2)  # ms
                snap['p99_tpot'] = round(self._percentile(self._tpot_list, 99) * 1000, 2)

            # gen_toks = 整体输出吞吐量 (总输出token数 / 总耗时)
            total_completion_tokens = sum(self._completion_tokens_list) if self._completion_tokens_list else 0
            snap['gen_toks'] = round(total_completion_tokens / elapsed, 2) if elapsed > 0 and total_completion_tokens > 0 else 0

            if self._error_types:
                snap['error_types'] = dict(self._error_types)

            self._snapshots.append(snap)
            return snap

    def get_final_result(self) -> Dict:
        """获取最终汇总结果，字段与 PerfTestResult 模型对齐"""
        with self._lock:
            elapsed = time.time() - self._start_time if self._start_time else 0

            result = {
                'concurrency': None,  # 由调用方设置
                'rps': round(self._request_count / elapsed, 2) if elapsed > 0 else 0,
                'avg_latency': round(sum(self._response_times) / len(self._response_times), 4) if self._response_times else None,
                'p99_latency': round(self._percentile(self._response_times, 99), 4) if self._response_times else None,
                'avg_ttft': round(sum(self._ttft_list) / len(self._ttft_list) * 1000, 2) if self._ttft_list else None,
                'p99_ttft': round(self._percentile(self._ttft_list, 99) * 1000, 2) if self._ttft_list else None,
                'avg_tpot': round(sum(self._tpot_list) / len(self._tpot_list) * 1000, 2) if self._tpot_list else None,
                'p99_tpot': round(self._percentile(self._tpot_list, 99) * 1000, 2) if self._tpot_list else None,
                'gen_toks': round(sum(self._completion_tokens_list) / elapsed, 2) if elapsed > 0 and self._completion_tokens_list else None,
                'success_rate': round(self._success_count / self._request_count * 100, 1) if self._request_count > 0 else 0,
                'total_requests': self._request_count,
                'success_requests': self._success_count,
                'error_requests': self._error_count,
                'elapsed_seconds': round(elapsed, 2),
                'prompt_tokens': self._prompt_tokens,
                'completion_tokens': self._completion_tokens,
                'total_tokens': self._total_tokens,
            }

            if self._error_types:
                result['error_types'] = dict(self._error_types)

            # 扩展百分位统计（参考 GuideLLM 的 Percentiles 设计）
            if self._response_times:
                result['percentiles_latency'] = {
                    'p0.1': round(self._percentile(self._response_times, 0.1), 4),
                    'p1': round(self._percentile(self._response_times, 1), 4),
                    'p5': round(self._percentile(self._response_times, 5), 4),
                    'p10': round(self._percentile(self._response_times, 10), 4),
                    'p25': round(self._percentile(self._response_times, 25), 4),
                    'p50': round(self._percentile(self._response_times, 50), 4),
                    'p75': round(self._percentile(self._response_times, 75), 4),
                    'p90': round(self._percentile(self._response_times, 90), 4),
                    'p95': round(self._percentile(self._response_times, 95), 4),
                    'p99': round(self._percentile(self._response_times, 99), 4),
                    'p99.9': round(self._percentile(self._response_times, 99.9), 4),
                }

            if self._ttft_list:
                result['percentiles_ttft'] = {
                    'p50': round(self._percentile(self._ttft_list, 50) * 1000, 2),
                    'p90': round(self._percentile(self._ttft_list, 90) * 1000, 2),
                    'p95': round(self._percentile(self._ttft_list, 95) * 1000, 2),
                    'p99': round(self._percentile(self._ttft_list, 99) * 1000, 2),
                    'p99.9': round(self._percentile(self._ttft_list, 99.9) * 1000, 2),
                }

            if self._tpot_list:
                result['percentiles_tpot'] = {
                    'p50': round(self._percentile(self._tpot_list, 50) * 1000, 2),
                    'p90': round(self._percentile(self._tpot_list, 90) * 1000, 2),
                    'p95': round(self._percentile(self._tpot_list, 95) * 1000, 2),
                    'p99': round(self._percentile(self._tpot_list, 99) * 1000, 2),
                    'p99.9': round(self._percentile(self._tpot_list, 99.9) * 1000, 2),
                }

            # 响应时间分布统计（均值、中位数、标准差、最小/最大值）
            if self._response_times:
                mean_lat = sum(self._response_times) / len(self._response_times)
                sorted_lat = sorted(self._response_times)
                median_lat = self._percentile(sorted_lat, 50)
                variance = sum((x - mean_lat) ** 2 for x in self._response_times) / len(self._response_times)
                result['latency_stats'] = {
                    'mean': round(mean_lat, 4),
                    'median': round(median_lat, 4),
                    'std_dev': round(math.sqrt(variance), 4),
                    'min': round(min(self._response_times), 4),
                    'max': round(max(self._response_times), 4),
                    'count': len(self._response_times),
                }

            return result

    def get_snapshots(self) -> List[Dict]:
        """获取历史快照列表"""
        with self._lock:
            return list(self._snapshots)

    @staticmethod
    def _percentile(sorted_data: List[float], pct: int) -> float:
        """计算百分位数"""
        if not sorted_data:
            return 0
        data = sorted(sorted_data)
        k = (len(data) - 1) * pct / 100
        f = int(k)
        c = f + 1
        if c >= len(data):
            return data[f]
        return data[f] + (k - f) * (data[c] - data[f])


class LLMPerfEngine:
    """
    自研 LLM API 压测引擎

    使用 aiohttp + asyncio 直接向 LLM API 发送请求，
    支持流式响应解析，精确测量 TTFT/TPOT。
    支持多种调度策略和合成数据生成。
    """

    def __init__(self, config: Dict):
        """
        Args:
            config: 测试配置，包含以下字段：
                - url: API URL
                - api_key: API Key
                - model: 模型名称
                - api: API 类型（openai/anthropic），默认 openai
                - parallel: 并发数，默认 8
                - number: 总请求数，默认 50
                - stream: 是否流式，默认 True
                - max_tokens: 最大生成 token 数，默认 128
                - prompt: 自定义 prompt，默认随机生成
                - connect_timeout: 连接超时（秒），默认 60
                - read_timeout: 读取超时（秒），默认 120
                # 以下为新增配置（参考 GuideLLM）
                - schedule_mode: 调度模式 'concurrent'(默认) / 'constant_rate' / 'poisson'
                - rate: 请求速率（QPS），用于 constant_rate 和 poisson 模式
                - max_duration: 最大测试时长（秒），约束条件
                - max_error_rate: 最大错误率（百分比），超过则停止
                - synthetic_data: 合成数据配置 dict，包含 prompt_tokens, output_tokens 等
        """
        self.config = config
        self.url = config['url'].rstrip('/')
        self.api_key = config['api_key']
        self.model = config['model']
        self.api_type = config.get('api', 'openai')
        self.concurrency = config.get('parallel', 8)
        self.total_requests = config.get('number', 50)
        self.stream = config.get('stream', True)
        self.max_tokens = config.get('max_tokens', 128)
        self.prompt = config.get('prompt')
        self.connect_timeout = config.get('connect_timeout', 60)
        self.read_timeout = config.get('read_timeout', 120)

        # 调度策略配置
        self.schedule_mode = config.get('schedule_mode', 'concurrent')
        self.rate = config.get('rate', 0)  # QPS for constant_rate/poisson

        # 约束条件
        self.max_duration = config.get('max_duration')  # 最大时长（秒）
        self.max_error_rate = config.get('max_error_rate')  # 最大错误率（%）

        self.metrics = MetricsCollector()
        self._stop_event = asyncio.Event()
        self._running = False

        # 合成数据生成器
        self._synthetic_generator = None
        if config.get('synthetic_data') and SyntheticPromptGenerator:
            try:
                synth_config = SyntheticDataConfig(**config['synthetic_data'])
                self._synthetic_generator = SyntheticPromptGenerator(synth_config)
            except Exception:
                pass

        # 默认 prompt 列表（当无合成数据配置时使用）
        self._default_prompts = [
            "请用一句话介绍人工智能。",
            "什么是机器学习？",
            "请解释深度学习的概念。",
            "自然语言处理有哪些应用？",
            "请简述大语言模型的工作原理。",
            "什么是 Transformer 架构？",
            "请解释什么是注意力机制。",
            "什么是 RAG 技术？",
            "请简述强化学习的基本原理。",
            "什么是联邦学习？",
        ]

    def stop(self):
        """停止测试"""
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._running

    async def run(self) -> Dict:
        """
        执行压测，返回最终结果。

        支持六种调度策略（参考 GuideLLM）：
        - concurrent: 固定并发数（默认，与原有行为一致）
        - constant_rate: 固定 QPS 速率发送请求
        - poisson: 泊松分布随机间隔发送请求
        - throughput: 最大化吞吐量，不限并发
        - sweep: 自适应扫描，自动发现最佳性能区间
        - replay: 追踪回放，按时间戳复现负载

        支持约束条件：
        - max_duration: 最大测试时长（秒）
        - max_error_rate: 最大错误率（%）
        - over_saturation: 过饱和检测（基于斜率分析）

        返回结果字段与 PerfTestResult 模型对齐，
        可直接用于创建 PerfTestResult 对象。
        """
        self._running = True
        self._stop_event.clear()
        self.metrics = MetricsCollector()

        connector = aiohttp.TCPConnector(
            limit=max(100, min(5000, self.concurrency * 3)),
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(
            total=self.read_timeout + self.connect_timeout + 30,
            connect=self.connect_timeout,
            sock_read=self.read_timeout,
        )

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            req_url, headers = self._build_request_config()

            if self.schedule_mode == 'throughput':
                await self._run_throughput(session, req_url, headers)
            elif self.schedule_mode == 'sweep':
                await self._run_sweep(session, req_url, headers)
            elif self.schedule_mode == 'replay':
                await self._run_replay(session, req_url, headers)
            elif self.schedule_mode == 'constant_rate' and self.rate > 0:
                await self._run_constant_rate(session, req_url, headers)
            elif self.schedule_mode == 'poisson' and self.rate > 0:
                await self._run_poisson(session, req_url, headers)
            else:
                await self._run_concurrent(session, req_url, headers)

        self._running = False

        result = self.metrics.get_final_result()
        result['concurrency'] = self.concurrency

        # 包含 sweep 扫描结果
        if hasattr(self, '_sweep_results') and self._sweep_results:
            result['sweep_results'] = self._sweep_results
            # 使用最大吞吐量阶段的结果作为汇总指标
            for sr in self._sweep_results:
                if sr.get('phase') == 'throughput' and sr.get('rps', 0) > result.get('rps', 0):
                    result['rps'] = sr['rps']
                    result['avg_latency'] = sr.get('avg_latency') or result.get('avg_latency')
                    result['p99_latency'] = sr.get('p99_latency') or result.get('p99_latency')

        return result

    async def _run_concurrent(self, session, url, headers):
        """固定并发数调度（原有模式）"""
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = []
        for i in range(self.total_requests):
            if self._should_stop():
                break
            task = asyncio.create_task(
                self._send_request(session, url, headers, semaphore, i)
            )
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_constant_rate(self, session, url, headers):
        """固定速率调度：按固定间隔发送请求"""
        interval = 1.0 / self.rate  # 请求间隔（秒）
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = []
        for i in range(self.total_requests):
            if self._should_stop():
                break
            task = asyncio.create_task(
                self._send_request(session, url, headers, semaphore, i)
            )
            tasks.append(task)
            # 等待间隔时间再发送下一个请求
            await asyncio.sleep(interval)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_poisson(self, session, url, headers):
        """泊松分布调度：按随机间隔发送请求，模拟真实流量"""
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = []
        rng = random.Random()
        for i in range(self.total_requests):
            if self._should_stop():
                break
            task = asyncio.create_task(
                self._send_request(session, url, headers, semaphore, i)
            )
            tasks.append(task)
            # 泊松分布间隔：指数分布
            interval = rng.expovariate(self.rate)
            await asyncio.sleep(interval)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_throughput(self, session, url, headers):
        """
        最大化吞吐量调度（参考 GuideLLM ThroughputStrategy）。
        不限制并发数，所有请求同时发出以测试系统最大处理能力。
        """
        # 使用较大的并发限制，避免资源耗尽
        max_conc = self.concurrency if self.concurrency > 0 else self.total_requests
        semaphore = asyncio.Semaphore(max_conc)
        tasks = []
        for i in range(self.total_requests):
            if self._should_stop():
                break
            task = asyncio.create_task(
                self._send_request(session, url, headers, semaphore, i)
            )
            tasks.append(task)
            # 极短间隔，让并发信号量来控制节奏
            if i % max_conc == 0 and i > 0:
                await asyncio.sleep(0.001)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_sweep(self, session, url, headers):
        """
        自适应扫描调度（参考 GuideLLM SweepProfile）。
        自动发现最佳性能区间：
        1. 先以并发=1运行，得到基线速率
        2. 再以最大并发运行，得到最大吞吐量
        3. 在两者之间等间隔插值，逐步加压
        结果中包含各阶段的详细指标。
        """
        sweep_results = []

        # 构建子引擎基础配置（清除 sweep 相关设置，避免子引擎误用）
        base_config = {k: v for k, v in self.config.items()
                       if k not in ('schedule_mode', 'over_saturation', 'rate', 'max_duration',
                                    'sweep_data', 'trace_data', 'max_error_rate')}

        # 覆盖已用 session/headers 的原始值
        base_config['schedule_mode'] = 'concurrent'
        base_config['over_saturation'] = False

        # 阶段1: 基线测试（并发=1）
        logger.info("[Sweep] Phase 1: Baseline test (concurrency=1)")
        baseline_engine = LLMPerfEngine({
            **base_config,
            'parallel': 1,
            'number': max(5, self.total_requests // 10),
        })
        baseline_result = await baseline_engine.run()
        baseline_rps = baseline_result.get('rps', 0) or 0
        sweep_results.append({'phase': 'baseline', 'concurrency': 1, 'rps': baseline_rps})

        if self._should_stop():
            self._sweep_results = sweep_results
            return

        # 阶段2: 最大吞吐量测试
        logger.info("[Sweep] Phase 2: Max throughput test")
        max_conc = max(self.concurrency, 16)
        throughput_engine = LLMPerfEngine({
            **base_config,
            'parallel': max_conc,
            'number': max(10, self.total_requests // 5),
            'schedule_mode': 'throughput',
        })
        throughput_result = await throughput_engine.run()
        max_rps = throughput_result.get('rps', 0) or 0
        sweep_results.append({
            'phase': 'throughput',
            'concurrency': max_conc,
            'rps': max_rps,
            'avg_latency': throughput_result.get('avg_latency'),
            'p99_latency': throughput_result.get('p99_latency'),
        })

        if self._should_stop():
            self._sweep_results = sweep_results
            return

        # 阶段3: 中间点扫描
        if baseline_rps > 0 and max_rps > baseline_rps:
            sweep_steps = max(3, min(8, self.total_requests // 10))
            rates = []
            step = (max_rps - baseline_rps) / (sweep_steps + 1)
            for s in range(1, sweep_steps + 1):
                rates.append(baseline_rps + step * s)

            for target_rate in rates:
                if self._should_stop():
                    break
                target_conc = max(2, int(target_rate / max(baseline_rps, 1)))
                target_conc = min(target_conc, max_conc)
                logger.info(f"[Sweep] Phase 3: Rate={target_rate:.1f} RPS, Concurrency={target_conc}")
                sweep_engine = LLMPerfEngine({
                    **base_config,
                    'parallel': target_conc,
                    'number': max(5, self.total_requests // (sweep_steps + 2)),
                    'schedule_mode': 'constant_rate',
                    'rate': target_rate,
                })
                sweep_res = await sweep_engine.run()
                actual_rps = sweep_res.get('rps', 0) or 0
                sweep_results.append({
                    'phase': 'sweep',
                    'concurrency': target_conc,
                    'target_rps': round(target_rate, 2),
                    'actual_rps': round(actual_rps, 2),
                    'avg_latency': sweep_res.get('avg_latency'),
                    'p99_latency': sweep_res.get('p99_latency'),
                })

        self._sweep_results = sweep_results
        logger.info(f"[Sweep] Completed {len(sweep_results)} phases")

    async def _run_replay(self, session, url, headers):
        """
        追踪回放调度（参考 GuideLLM TraceReplayStrategy）。
        按 trace 文件中的时间戳复现负载。
        trace_data 格式: list[{"timestamp": float, "prompt": str, "max_tokens": int}]
        """
        trace_data = self.config.get('trace_data', [])
        if not trace_data:
            logger.warning("[Replay] No trace data provided, falling back to concurrent")
            await self._run_concurrent(session, url, headers)
            return

        time_scale = self.config.get('time_scale', 1.0)
        semaphore = asyncio.Semaphore(self.concurrency)
        start_time = time.time()
        tasks = []

        for i, entry in enumerate(trace_data):
            if self._should_stop():
                break

            # 计算相对时间戳并等待
            target_time = entry.get('timestamp', 0) * time_scale
            elapsed = time.time() - start_time
            wait_time = target_time - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            task = asyncio.create_task(
                self._send_request_with_data(
                    session, url, headers, semaphore, i,
                    prompt=entry.get('prompt'),
                    max_tokens_override=entry.get('max_tokens'),
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    def _should_stop(self) -> bool:
        """
        检查是否应该停止测试（约束条件检查）。
        包含过饱和检测（参考 GuideLLM OverSaturationConstraint）。
        """
        if self._stop_event.is_set():
            return True

        # 最大时长约束
        if self.max_duration and self.metrics._start_time:
            elapsed = time.time() - self.metrics._start_time
            if elapsed >= self.max_duration:
                return True

        # 最大错误率约束
        if self.max_error_rate and self.metrics._request_count > 0:
            error_rate = self.metrics._error_count / self.metrics._request_count * 100
            if error_rate >= self.max_error_rate:
                return True

        # 过饱和检测：检查 TTFT 和延迟是否持续恶化
        if self.config.get('over_saturation') and self.metrics._request_count > 10:
            if self._check_over_saturation():
                logger.warning("[OverSaturation] Detected sustained performance degradation, stopping")
                return True

        return False

    def _check_over_saturation(self) -> bool:
        """
        过饱和检测（参考 GuideLLM OSD 算法）。
        使用简化的斜率分析：检查最近的 TTFT 是否呈现显著上升趋势。
        """
        with self.metrics._lock:
            ttft_list = self.metrics._ttft_list

        # 需要足够的数据点
        min_window = 10
        if len(ttft_list) < min_window:
            return False

        # 取最近的窗口数据
        window_size = min(50, len(ttft_list))
        recent = ttft_list[-window_size:]
        n = len(recent)

        # 计算线性回归斜率
        sum_x = sum(range(n))
        sum_y = sum(recent)
        sum_xy = sum(i * v for i, v in enumerate(recent))
        sum_x2 = sum(i * i for i in range(n))

        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-12:
            return False

        slope = (n * sum_xy - sum_x * sum_y) / denom
        mean_y = sum_y / n

        # 计算残差和标准误差
        if mean_y <= 0:
            return False

        # 斜率相对于均值的比例
        slope_ratio = slope / mean_y

        # 如果斜率持续为正且显著（每样本 TTFT 增长超过 1%），判定为过饱和
        return slope_ratio > 0.01

    def _build_request_config(self) -> tuple:
        """构建请求 URL 和 headers"""
        if self.api_type == 'anthropic':
            url = self.url
            if not url.endswith('/messages'):
                if '/v1/' in url:
                    url = url.rsplit('/', 1)[0] + '/messages'
                else:
                    url = url.rstrip('/') + '/v1/messages'
            headers = {
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            }
        else:
            # OpenAI 兼容 API
            url = self.url
            if not url.endswith('/chat/completions'):
                if url.endswith('/v1'):
                    url += '/chat/completions'
                elif '/v1/' not in url:
                    url += '/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
        return url, headers

    def _get_prompt(self, index: int) -> str:
        """获取请求使用的 prompt，优先使用合成数据生成器"""
        if self.prompt:
            return self.prompt
        if self._synthetic_generator:
            return self._synthetic_generator.generate_prompt(index)
        return self._default_prompts[index % len(self._default_prompts)]

    def _get_max_tokens(self, index: int) -> int:
        """获取 max_tokens，支持合成数据生成器的可变 output_tokens"""
        if self._synthetic_generator:
            sampled = self._synthetic_generator.sample_output_tokens()
            return max(1, sampled)
        return self.max_tokens

    async def _send_request_with_data(self, session, url, headers, semaphore, index,
                                       prompt=None, max_tokens_override=None):
        """发送单次请求（支持自定义 prompt 和 max_tokens，用于 replay 策略）"""
        async with semaphore:
            if self._stop_event.is_set() or self._should_stop():
                return

            actual_prompt = prompt or self._get_prompt(index)
            actual_max_tokens = max_tokens_override or self._get_max_tokens(index)

            if self.api_type == 'anthropic':
                payload = {
                    'model': self.model,
                    'max_tokens': actual_max_tokens,
                    'messages': [{'role': 'user', 'content': actual_prompt}],
                    'stream': self.stream,
                }
            else:
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': actual_prompt}],
                    'max_tokens': actual_max_tokens,
                    'stream': self.stream,
                }

            start_time = time.time()
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if self.stream:
                        metric = await self._handle_stream_response(resp, start_time)
                    else:
                        metric = await self._handle_non_stream_response(resp, start_time)
                    self.metrics.record(metric)
            except asyncio.CancelledError:
                raise
            except aiohttp.ClientError as e:
                elapsed = time.time() - start_time
                self.metrics.record(RequestMetric(
                    success=False, response_time=elapsed,
                    error_type=self._classify_error(e),
                ))
            except Exception as e:
                elapsed = time.time() - start_time
                self.metrics.record(RequestMetric(
                    success=False, response_time=elapsed,
                    error_type=f'unknown:{type(e).__name__}',
                ))

    async def _send_request(self, session: aiohttp.ClientSession, url: str,
                            headers: dict, semaphore: asyncio.Semaphore, index: int):
        """发送单次请求"""
        async with semaphore:
            if self._stop_event.is_set() or self._should_stop():
                return

            prompt = self._get_prompt(index)
            max_tokens = self._get_max_tokens(index)

            if self.api_type == 'anthropic':
                payload = {
                    'model': self.model,
                    'max_tokens': max_tokens,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': self.stream,
                }
            else:
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': max_tokens,
                    'stream': self.stream,
                }

            start_time = time.time()

            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if self.stream:
                        metric = await self._handle_stream_response(resp, start_time)
                    else:
                        metric = await self._handle_non_stream_response(resp, start_time)

                    self.metrics.record(metric)

            except asyncio.CancelledError:
                raise
            except aiohttp.ClientError as e:
                elapsed = time.time() - start_time
                self.metrics.record(RequestMetric(
                    success=False,
                    response_time=elapsed,
                    error_type=self._classify_error(e),
                ))
            except Exception as e:
                elapsed = time.time() - start_time
                self.metrics.record(RequestMetric(
                    success=False,
                    response_time=elapsed,
                    error_type=f'unknown:{type(e).__name__}',
                ))

    async def _handle_stream_response(self, resp: aiohttp.ClientResponse, start_time: float) -> RequestMetric:
        """处理流式响应，精确测量 TTFT/TPOT"""
        ttft = None
        first_content_time = None
        chunk_count = 0
        completion_tokens = 0
        prompt_tokens = 0
        total_tokens = 0
        content_parts = []

        if resp.status != 200:
            body = await resp.text()
            elapsed = time.time() - start_time
            error_type = self._classify_http_error(resp.status, body)
            return RequestMetric(
                success=False,
                response_time=elapsed,
                error_type=error_type,
            )

        # Anthropic 流式
        if self.api_type == 'anthropic':
            async for line in resp.content:
                if self._stop_event.is_set():
                    break
                line_text = line.decode('utf-8').strip()
                if not line_text.startswith('data: '):
                    continue
                data_str = line_text[6:]
                if data_str == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = data.get('type', '')

                if event_type == 'message_start':
                    usage = data.get('message', {}).get('usage', {})
                    prompt_tokens = usage.get('input_tokens', 0)
                    # TTFT：收到 message_start 的时间
                    if ttft is None:
                        ttft = time.time() - start_time

                elif event_type == 'content_block_delta':
                    delta = data.get('delta', {})
                    delta_type = delta.get('type', '')
                    # 支持 text_delta 和 thinking_delta（推理模型）
                    if delta_type in ('text_delta', 'thinking_delta'):
                        text = delta.get('text', '')
                        if text:
                            chunk_count += 1
                            if first_content_time is None:
                                first_content_time = time.time()
                            content_parts.append(text)

                elif event_type == 'message_delta':
                    usage = data.get('usage', {})
                    completion_tokens = usage.get('output_tokens', 0)
                    total_tokens = prompt_tokens + completion_tokens

        else:
            # OpenAI 兼容流式
            async for line in resp.content:
                if self._stop_event.is_set():
                    break
                line_text = line.decode('utf-8').strip()
                if not line_text.startswith('data: '):
                    continue
                data_str = line_text[6:]
                if data_str == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # 提取 usage（部分 API 在最后一个 chunk 返回）
                if 'usage' in data and data['usage']:
                    u = data['usage']
                    prompt_tokens = u.get('prompt_tokens', prompt_tokens)
                    completion_tokens = u.get('completion_tokens', completion_tokens)
                    total_tokens = u.get('total_tokens', prompt_tokens + completion_tokens)

                if 'choices' in data and data['choices']:
                    # TTFT：收到第一个 choices chunk 的时间（与 evalscope 口径一致）
                    if ttft is None:
                        ttft = time.time() - start_time

                    delta = data['choices'][0].get('delta', {})
                    content = delta.get('content')  # 可能是 None 或字符串
                    # 支持推理模型（如 deepseek-r1/v4-flash）的 reasoning_content
                    reasoning_content = delta.get('reasoning_content')  # 可能是 None 或字符串

                    # 合并 content 和 reasoning_content（优先 content）
                    actual_content = content if content else reasoning_content
                    if actual_content:
                        chunk_count += 1
                        if first_content_time is None:
                            first_content_time = time.time()
                        content_parts.append(actual_content)

        elapsed = time.time() - start_time

        # 如果 API 没有返回 usage，从内容估算 token 数
        if completion_tokens == 0 and content_parts:
            # 粗略估算：中文约 1.5 字/token，英文约 4 字符/token
            full_content = ''.join(content_parts)
            completion_tokens = max(1, len(full_content) // 3)
            total_tokens = prompt_tokens + completion_tokens

        # 计算 TPOT
        tpot = None
        tokens_per_second = None
        if first_content_time and completion_tokens > 1:
            generation_time = time.time() - first_content_time
            tpot = generation_time / (completion_tokens - 1)
            tokens_per_second = (completion_tokens - 1) / generation_time if generation_time > 0 else 0
        elif completion_tokens > 0 and elapsed > 0:
            tokens_per_second = completion_tokens / elapsed

        return RequestMetric(
            success=True,
            response_time=elapsed,
            ttft=ttft,
            tpot=tpot,
            tokens_per_second=tokens_per_second,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def _handle_non_stream_response(self, resp: aiohttp.ClientResponse, start_time: float) -> RequestMetric:
        """处理非流式响应"""
        elapsed = time.time() - start_time

        if resp.status != 200:
            body = await resp.text()
            error_type = self._classify_http_error(resp.status, body)
            return RequestMetric(
                success=False,
                response_time=elapsed,
                error_type=error_type,
            )

        data = await resp.json()

        # 提取内容
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        if self.api_type == 'anthropic':
            usage = data.get('usage', {})
            prompt_tokens = usage.get('input_tokens', 0)
            completion_tokens = usage.get('output_tokens', 0)
        else:
            usage = data.get('usage', {})
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)

        # 非流式没有 TTFT，用总时间近似
        tokens_per_second = completion_tokens / elapsed if elapsed > 0 and completion_tokens > 0 else 0

        return RequestMetric(
            success=True,
            response_time=elapsed,
            ttft=elapsed,  # 非流式 TTFT 等于总延迟
            tokens_per_second=tokens_per_second,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _classify_http_error(status: int, body: str) -> str:
        """分类 HTTP 错误"""
        if status == 429:
            return 'rate_limit'
        elif status == 401:
            return 'auth_error'
        elif status == 403:
            return 'forbidden'
        elif status == 404:
            return 'not_found'
        elif status == 500:
            return 'server_error'
        elif status == 502:
            return 'bad_gateway'
        elif status == 503:
            return 'service_unavailable'
        elif status >= 400:
            return f'http_{status}'
        return f'http_{status}'

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """分类异常"""
        if isinstance(exc, asyncio.TimeoutError):
            return 'timeout'
        elif isinstance(exc, aiohttp.ClientConnectorError):
            return 'connection_error'
        elif isinstance(exc, aiohttp.ClientResponseError):
            return f'http_{exc.status}'
        return f'client_error:{type(exc).__name__}'


def run_llm_perf_test(config: Dict, stop_event=None) -> Dict:
    """
    同步入口：在独立线程中运行 asyncio 事件循环执行压测。

    Args:
        config: 测试配置（同 LLMPerfEngine.__init__）
        stop_event: 可选的 threading.Event，用于从外部停止测试

    Returns:
        最终结果字典，字段与 PerfTestResult 模型对齐
    """
    engine = LLMPerfEngine(config)

    async def _run_with_stop():
        if stop_event:
            # 启动后台任务轮询 stop_event
            async def _poll_stop():
                while not stop_event.is_set():
                    await asyncio.sleep(0.5)
                engine.stop()
            asyncio.create_task(_poll_stop())
        return await engine.run()

    return asyncio.run(_run_with_stop())
