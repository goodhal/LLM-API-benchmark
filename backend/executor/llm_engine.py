"""
自研 LLM API 压测引擎

替代 subprocess 调用 evalscope CLI，直接使用 aiohttp 发送 HTTP 请求。
优势：
- 实时指标收集（无需等进程结束）
- 精确测量 TTFT/TPOT（流式响应逐 chunk 计时）
- 支持动态调整并发数
- 无 SQLite 锁冲突（不依赖子进程写文件）
"""

import asyncio
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


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

        self.metrics = MetricsCollector()
        self._stop_event = asyncio.Event()
        self._running = False

        # 默认 prompt 列表（随机选择）
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

        返回结果字段与 PerfTestResult 模型对齐，
        可直接用于创建 PerfTestResult 对象。
        """
        self._running = True
        self._stop_event.clear()
        self.metrics = MetricsCollector()

        connector = aiohttp.TCPConnector(
            limit=max(100, min(2000, self.concurrency * 2)),
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(
            total=self.read_timeout + self.connect_timeout + 30,
            connect=self.connect_timeout,
            sock_read=self.read_timeout,
        )

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 构建请求 URL 和 headers
            req_url, headers = self._build_request_config()

            # 使用信号量控制并发
            semaphore = asyncio.Semaphore(self.concurrency)

            # 分发请求任务
            tasks = []
            for i in range(self.total_requests):
                if self._stop_event.is_set():
                    break
                task = asyncio.create_task(
                    self._send_request(session, req_url, headers, semaphore, i)
                )
                tasks.append(task)

            # 等待所有请求完成
            await asyncio.gather(*tasks, return_exceptions=True)

        self._running = False

        # 生成最终结果
        result = self.metrics.get_final_result()
        result['concurrency'] = self.concurrency
        return result

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
        """获取请求使用的 prompt"""
        if self.prompt:
            return self.prompt
        return self._default_prompts[index % len(self._default_prompts)]

    async def _send_request(self, session: aiohttp.ClientSession, url: str,
                            headers: dict, semaphore: asyncio.Semaphore, index: int):
        """发送单次请求"""
        async with semaphore:
            if self._stop_event.is_set():
                return

            prompt = self._get_prompt(index)

            if self.api_type == 'anthropic':
                payload = {
                    'model': self.model,
                    'max_tokens': self.max_tokens,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': self.stream,
                }
            else:
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': self.max_tokens,
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
