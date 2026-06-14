"""
模型对比测试路由
"""
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_login import login_required
import json
import time
import requests as http_requests
import psutil
import os
import re
from ..models import db


compare_bp = Blueprint('compare', __name__)


# 预设测试用例库
TEST_CASES = [
    {
        "id": "knowledge_qa",
        "name": "知识问答",
        "description": "测试模型的知识储备和准确性",
        "prompt": "在《三国演义》里，被诸葛亮用空城计吓退的魏国大将是谁？",
        "expected": "司马懿",
        "category": "知识能力"
    },
    {
        "id": "logic_reasoning",
        "name": "逻辑推理",
        "description": "测试模型的逻辑推理能力",
        "prompt": "有三个人，A说B在说谎，B说C在说谎，C说A和B都在说谎。请问谁在说谎？",
        "expected": "A和C说谎，B说真话",
        "category": "推理能力"
    },
    {
        "id": "language_understanding",
        "name": "语言理解",
        "description": "测试模型对语言深层含义的理解",
        "prompt": "解释成语\"画蛇添足\"的字面意思和比喻意义。",
        "expected": "字面：画蛇时多画了脚；比喻：做多余的事反而弄巧成拙",
        "category": "语言能力"
    },
    {
        "id": "sentence_generation",
        "name": "句子生成",
        "description": "测试模型的文本生成能力",
        "prompt": "以\"春天\"开头，生成5个不同的完整句子。",
        "expected": "5个语法正确、内容各异的句子",
        "category": "生成能力"
    },
    {
        "id": "code_generation",
        "name": "代码生成",
        "description": "测试模型的编程能力",
        "prompt": "编写一个Python程序，实现快速排序算法，并对列表 [5, 3, 8, 4, 2] 进行排序。",
        "expected": "正确的快速排序实现",
        "category": "编程能力"
    },
    {
        "id": "translation",
        "name": "翻译能力",
        "description": "测试模型的中英翻译能力",
        "prompt": "把\"不到长城非好汉\"翻译成英文。",
        "expected": "He who has never been to the Great Wall is not a true hero",
        "category": "语言能力"
    },
    {
        "id": "math_calculation",
        "name": "数学计算",
        "description": "测试模型的数学推理和计算能力",
        "prompt": "便利店搞促销：买 2 瓶可乐送 1 瓶，每瓶可乐 5 元。小王想给 4 个朋友每人带 1 瓶（包括自己共 5 人），最实惠的买法最少要花多少钱？",
        "expected": "20元（买4瓶送2瓶，满足5人需求）",
        "category": "推理能力"
    },
    {
        "id": "sentiment_analysis",
        "name": "情感分析",
        "description": "测试模型的情感理解能力",
        "prompt": "判断\"我本来以为能中大奖，结果连个安慰奖都没有，真是倒霉透顶了！\"这句话的情感倾向。",
        "expected": "负面情感",
        "category": "理解能力"
    },
    {
        "id": "creative_thinking",
        "name": "创意联想",
        "description": "测试模型的创意和想象力",
        "prompt": "如果云朵可以吃，会是什么味道？为什么？",
        "expected": "富有想象力和合理性的回答",
        "category": "生成能力"
    },
    {
        "id": "common_sense",
        "name": "常识判断",
        "description": "测试模型的常识知识储备",
        "prompt": "骆驼的驼峰储存的是水吗？",
        "expected": "不是，储存的是脂肪",
        "category": "知识能力"
    },
    {
        "id": "summarization",
        "name": "摘要总结",
        "description": "测试模型的文本摘要能力",
        "prompt": "请用一句话总结以下内容：人工智能（AI）是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。这些任务包括学习、推理、问题解决、感知和语言理解。AI技术已经广泛应用于医疗诊断、自动驾驶、金融分析等领域，正在深刻改变人类社会的运作方式。",
        "expected": "简洁准确的摘要",
        "category": "理解能力"
    },
    {
        "id": "role_play",
        "name": "角色扮演",
        "description": "测试模型的上下文理解和角色扮演能力",
        "prompt": "请你扮演一位经验丰富的中医，给一位经常失眠的白领提三条建议。",
        "expected": "专业且贴合角色的建议",
        "category": "生成能力"
    }
]


def detect_anomalies(text):
    """检测输出异常（重复/截断）"""
    anomalies = []

    # 1. 检测重复段落
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    seen = {}
    for s in sentences:
        if s in seen:
            anomalies.append({
                "type": "repetition",
                "severity": "warning",
                "message": f"检测到重复内容: \"{s[:50]}...\""
            })
        else:
            seen[s] = True

    # 2. 检测连续重复字符（如 aaaaa）
    repeat_pattern = re.compile(r'(.)\1{4,}')
    matches = repeat_pattern.findall(text)
    if matches:
        anomalies.append({
            "type": "char_repetition",
            "severity": "warning",
            "message": f"检测到连续重复字符: '{matches[0]}'"
        })

    # 3. 检测重复词组模式（如 "这是一个这是一个"）
    phrase_pattern = re.compile(r'(.{3,10}?)\1{2,}')
    phrase_matches = phrase_pattern.findall(text)
    for pm in phrase_matches:
        anomalies.append({
            "type": "phrase_repetition",
            "severity": "warning",
            "message": f"检测到重复词组: \"{pm}\""
        })

    # 4. 检测截断（末尾不完整）
    text_stripped = text.strip()
    if text_stripped and text_stripped[-1] not in '。！？.!?…\n}】）)':
        # 检查是否像是被截断的
        if len(text_stripped) > 20:
            last_sentence = text_stripped.split('。')[-1] if '。' in text_stripped else text_stripped.split('.')[-1]
            if len(last_sentence) > 30 and not last_sentence.endswith(('）', ')', '】', ']', '}', '。', '！', '？', '.', '!', '?', '…')):
                anomalies.append({
                    "type": "truncation",
                    "severity": "info",
                    "message": "输出可能被截断，末尾缺少标点"
                })

    # 5. 检测异常编码或乱码
    garbled_pattern = re.compile(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s\.,;:!?\'\"()\[\]{}<>@#$%^&*\-_=+\\/|~`。，；：！？、""''（）【】《》…—\n\r\t]')
    garbled_matches = garbled_pattern.findall(text)
    if len(garbled_matches) > 10:
        anomalies.append({
            "type": "garbled",
            "severity": "error",
            "message": f"检测到可能的乱码内容（{len(garbled_matches)}个异常字符）"
        })

    return anomalies


@compare_bp.route('/test-cases', methods=['GET'])
@login_required
def get_test_cases():
    """获取预设测试用例库"""
    category = request.args.get('category')
    if category:
        cases = [c for c in TEST_CASES if c['category'] == category]
    else:
        cases = TEST_CASES
    return jsonify({'cases': cases}), 200


@compare_bp.route('/test-cases/categories', methods=['GET'])
@login_required
def get_test_categories():
    """获取测试用例分类"""
    categories = list(set(c['category'] for c in TEST_CASES))
    return jsonify({'categories': sorted(categories)}), 200


@compare_bp.route('/run', methods=['POST'])
@login_required
def run_compare():
    """运行模型对比测试（流式响应）"""
    data = request.get_json()
    models = data.get('models', [])
    prompt = data.get('prompt', '')
    test_case_id = data.get('test_case_id', '')

    if not models:
        return jsonify({'error': '请至少选择一个模型'}), 400
    if not prompt:
        return jsonify({'error': '请输入测试文本'}), 400

    # 查找测试用例信息
    test_case = None
    if test_case_id:
        test_case = next((c for c in TEST_CASES if c['id'] == test_case_id), None)

    def generate():
        results = {}
        for model_config in models:
            model_name = model_config.get('name', 'unknown')
            model_type = model_config.get('type', 'openai')
            results[model_name] = {
                'status': 'pending',
                'output': '',
                'anomalies': [],
                'latency_ms': 0
            }

            # 发送开始信号
            yield f"data: {json.dumps({'type': 'start', 'model': model_name}, ensure_ascii=False)}\n\n"

            start_time = time.time()
            try:
                if model_type == 'ollama':
                    output = _call_ollama(model_config, prompt)
                else:
                    output = _call_openai_compatible(model_config, prompt)

                elapsed = (time.time() - start_time) * 1000

                # 异常检测
                anomalies = detect_anomalies(output)

                results[model_name] = {
                    'status': 'completed',
                    'output': output,
                    'anomalies': anomalies,
                    'latency_ms': round(elapsed, 1)
                }

                # 流式发送输出
                chunk_size = 20
                for i in range(0, len(output), chunk_size):
                    chunk = output[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'model': model_name, 'text': chunk}, ensure_ascii=False)}\n\n"
                    time.sleep(0.02)

                # 发送完成信号
                yield f"data: {json.dumps({'type': 'complete', 'model': model_name, 'latency_ms': round(elapsed, 1), 'anomalies': anomalies}, ensure_ascii=False)}\n\n"

            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                results[model_name] = {
                    'status': 'error',
                    'output': '',
                    'error': str(e),
                    'anomalies': [],
                    'latency_ms': round(elapsed, 1)
                }
                yield f"data: {json.dumps({'type': 'error', 'model': model_name, 'error': str(e)}, ensure_ascii=False)}\n\n"

        # 发送测试用例信息
        if test_case:
            yield f"data: {json.dumps({'type': 'test_case', 'test_case': test_case}, ensure_ascii=False)}\n\n"

        # 发送汇总
        yield f"data: {json.dumps({'type': 'summary', 'results': results}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


def _call_openai_compatible(config, prompt):
    """调用 OpenAI 兼容 API"""
    url = config.get('url', '').rstrip('/')
    if not url.endswith('/chat/completions'):
        if url.endswith('/v1'):
            url += '/chat/completions'
        elif '/v1/' not in url:
            url += '/v1/chat/completions'

    headers = {
        'Authorization': f"Bearer {config.get('api_key', '')}",
        'Content-Type': 'application/json'
    }

    payload = {
        'model': config.get('model', ''),
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': config.get('temperature', 0.7),
        'max_tokens': config.get('max_tokens', 2000),
        'stream': False
    }

    resp = http_requests.post(url, headers=headers, json=payload, timeout=config.get('timeout', 120))
    if resp.status_code != 200:
        raise Exception(f"API 调用失败: HTTP {resp.status_code} - {resp.text[:200]}")

    data = resp.json()
    if 'choices' in data and len(data['choices']) > 0:
        return data['choices'][0]['message']['content']
    raise Exception("API 返回数据格式无效")


def _call_ollama(config, prompt):
    """调用 Ollama 本地模型"""
    url = config.get('url', 'http://localhost:11434')
    model_name = config.get('model', '')

    resp = http_requests.post(
        f"{url.rstrip('/')}/api/generate",
        json={
            'model': model_name,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': config.get('temperature', 0.7),
                'num_predict': config.get('max_tokens', 2000)
            }
        },
        timeout=config.get('timeout', 120)
    )

    if resp.status_code != 200:
        raise Exception(f"Ollama 调用失败: HTTP {resp.status_code}")

    data = resp.json()
    return data.get('response', '')


@compare_bp.route('/system-metrics', methods=['GET'])
@login_required
def get_system_metrics():
    """获取系统资源监控数据"""
    metrics = {}

    # CPU
    metrics['cpu_percent'] = psutil.cpu_percent(interval=0.5)
    metrics['cpu_count'] = psutil.cpu_count()

    # 内存
    mem = psutil.virtual_memory()
    metrics['memory_total_gb'] = round(mem.total / (1024 ** 3), 2)
    metrics['memory_used_gb'] = round(mem.used / (1024 ** 3), 2)
    metrics['memory_percent'] = mem.percent

    # 磁盘
    disk = psutil.disk_usage('/')
    metrics['disk_total_gb'] = round(disk.total / (1024 ** 3), 2)
    metrics['disk_used_gb'] = round(disk.used / (1024 ** 3), 2)
    metrics['disk_percent'] = disk.percent

    # 进程信息
    process = psutil.Process(os.getpid())
    proc_mem = process.memory_info()
    metrics['process_memory_mb'] = round(proc_mem.rss / (1024 ** 2), 1)

    # GPU（如果可用）
    gpu_info = _get_gpu_info()
    metrics['gpu'] = gpu_info

    # 系统运行时间
    boot_time = psutil.boot_time()
    metrics['uptime_seconds'] = round(time.time() - boot_time)

    return jsonify(metrics), 200


def _get_gpu_info():
    """获取 GPU 信息（多种检测方式）"""

    # 方式1: PyTorch
    try:
        import torch
        if torch.cuda.is_available():
            gpu_list = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                allocated = torch.cuda.memory_allocated(i) / (1024 ** 3)
                reserved = torch.cuda.memory_reserved(i) / (1024 ** 3)
                total = props.total_memory / (1024 ** 3)
                gpu_list.append({
                    'index': i,
                    'name': props.name,
                    'total_memory_gb': round(total, 2),
                    'allocated_gb': round(allocated, 2),
                    'reserved_gb': round(reserved, 2),
                    'utilization_percent': round(allocated / total * 100, 1) if total > 0 else 0
                })
            return gpu_list
    except ImportError:
        pass
    except Exception:
        pass

    # 方式2: pynvml
    try:
        from pynvml import nvmlInit, nvmlShutdown, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex, nvmlDeviceGetName, nvmlDeviceGetMemoryInfo, nvmlDeviceGetUtilizationRates
        nvmlInit()
        count = nvmlDeviceGetCount()
        gpu_list = []
        for i in range(count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = nvmlDeviceGetMemoryInfo(handle)
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                util_pct = util.gpu
            except Exception:
                util_pct = round(mem.used / mem.total * 100, 1) if mem.total > 0 else 0
            gpu_list.append({
                'index': i,
                'name': name,
                'total_memory_gb': round(mem.total / (1024 ** 3), 2),
                'used_memory_gb': round(mem.used / (1024 ** 3), 2),
                'free_memory_gb': round(mem.free / (1024 ** 3), 2),
                'utilization_percent': util_pct
            })
        nvmlShutdown()
        return gpu_list
    except ImportError:
        pass
    except Exception:
        pass

    # 方式3: ctypes 直接调用 libnvidia-ml.so
    try:
        import ctypes

        class NvmlMemory(ctypes.Structure):
            _fields_ = [('total', ctypes.c_ulonglong), ('free', ctypes.c_ulonglong), ('used', ctypes.c_ulonglong)]

        class NvmlUtilization(ctypes.Structure):
            _fields_ = [('gpu', ctypes.c_uint), ('memory', ctypes.c_uint)]

        # 搜索 libnvidia-ml.so 路径
        nvml_paths = [
            'libnvidia-ml.so.1',
            '/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1',
            '/usr/lib64/libnvidia-ml.so.1',
            '/usr/lib/libnvidia-ml.so.1',
        ]
        nvml = None
        for p in nvml_paths:
            try:
                nvml = ctypes.CDLL(p)
                break
            except OSError:
                continue

        if nvml:
            ret = nvml.nvmlInit_v2()
            if ret == 0:
                count = ctypes.c_uint()
                nvml.nvmlDeviceGetCount_v2(ctypes.byref(count))
                gpu_list = []
                for i in range(count.value):
                    handle = ctypes.c_void_p()
                    nvml.nvmlDeviceGetHandleByIndex_v2(ctypes.c_uint(i), ctypes.byref(handle))

                    name_buf = ctypes.create_string_buffer(256)
                    nvml.nvmlDeviceGetName(handle, name_buf, 256)
                    gpu_name = name_buf.value.decode('utf-8', errors='replace')

                    mem = NvmlMemory()
                    nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))

                    util = NvmlUtilization()
                    nvml.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util))

                    gpu_list.append({
                        'index': i,
                        'name': gpu_name,
                        'total_memory_gb': round(mem.total / (1024 ** 3), 2),
                        'used_memory_gb': round(mem.used / (1024 ** 3), 2),
                        'free_memory_gb': round(mem.free / (1024 ** 3), 2),
                        'utilization_percent': util.gpu
                    })
                nvml.nvmlShutdown()
                return gpu_list
    except Exception:
        pass

    # 方式4: nvidia-smi（搜索常见路径）
    try:
        import subprocess
        smi_paths = [
            'nvidia-smi',
            '/usr/bin/nvidia-smi',
            '/usr/local/bin/nvidia-smi',
            '/usr/lib/nvidia/bin/nvidia-smi',
            '/usr/lib/nvidia-current/bin/nvidia-smi',
        ]
        smi_cmd = None
        for p in smi_paths:
            if os.path.isfile(p) or os.system(f'which {p} > /dev/null 2>&1') == 0:
                smi_cmd = p
                break

        if smi_cmd:
            result = subprocess.run(
                [smi_cmd, '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                gpu_list = []
                for line in result.stdout.strip().split('\n'):
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 6:
                        gpu_list.append({
                            'index': int(parts[0]),
                            'name': parts[1],
                            'total_memory_gb': round(float(parts[2]) / 1024, 2),
                            'used_memory_gb': round(float(parts[3]) / 1024, 2),
                            'free_memory_gb': round(float(parts[4]) / 1024, 2),
                            'utilization_percent': float(parts[5])
                        })
                return gpu_list
    except Exception:
        pass

    return None
