"""
任务执行器
"""
import subprocess
import os
import sys
import re
import json
import traceback
import time as time_module
from datetime import datetime
from pathlib import Path
from threading import Thread, Lock, Event
from ..models import db, Task, PerfTestResult, QualityTestResult
from ..config import config


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self):
        self.running_tasks = {}
        self.lock = Lock()
        # 自研引擎的实时指标存储 {task_id: LLMPerfEngine}
        self._live_engines = {}
        # 自研引擎的停止事件 {task_id: threading.Event}
        self._stop_events = {}
    
    def execute_async(self, task, app):
        """异步执行任务"""
        thread = Thread(target=self._execute_task, args=(task.id, app), daemon=True)
        thread.start()
    
    def execute_scheduled(self, task_id):
        """调度执行任务"""
        from .. import create_app
        app = create_app()
        with app.app_context():
            task = db.session.get(Task, task_id)
            if task and task.is_enabled:
                self._execute_task(task_id, app)
    
    def stop(self, task):
        # 优先停止自研引擎
        if task.id in self._stop_events:
            self._stop_events[task.id].set()
        
        with self.lock:
            if task.id in self.running_tasks:
                process = self.running_tasks[task.id]
                if process:
                    process.terminate()
                del self.running_tasks[task.id]
        
        # 清理自研引擎引用
        self._live_engines.pop(task.id, None)
        self._stop_events.pop(task.id, None)
        
        # 更新任务状态
        task.status = 'idle'
        db.session.commit()
    
    def _safe_commit(self):
        """带重试的数据库提交，解决线程 SQLite 锁冲突"""
        for retry in range(10):
            try:
                db.session.commit()
                return
            except Exception as e:
                if 'database is locked' in str(e).lower():
                    time_module.sleep(0.5 * (retry + 1))
                else:
                    raise
        db.session.commit()

    def _update_next_run_time(self, task):
        """更新下次执行时间"""
        from .. import scheduler
        
        job_id = f'task_{task.id}'
        job = scheduler.get_job(job_id)
        
        if job and job.next_run_time:
            task.next_run_time = job.next_run_time.replace(tzinfo=None) if job.next_run_time.tzinfo else job.next_run_time
            self._safe_commit()

    def _execute_task(self, task_id, app):
        """执行任务（在线程中运行）"""
        with app.app_context():
            task = db.session.get(Task, task_id)
            if not task:
                print(f"[TaskExecutor] Task {task_id} not found", file=sys.stderr)
                return
            
            try:
                task.status = 'running'
                task.last_run_time = datetime.now()
                self._safe_commit()
                app.logger.info(f"[Task {task_id}] Starting: {task.name}")
                print(f"[TaskExecutor] Task {task_id} started: {task.name}", file=sys.stderr, flush=True)

                if task.task_type == 'perf_test':
                    result = self._execute_perf_test(task, app)
                elif task.task_type == 'quality_test':
                    result = self._execute_quality_test(task, app)
                elif task.task_type == 'availability_test':
                    result = self._execute_availability_test(task, app)
                else:
                    raise ValueError(f"Unknown task type: {task.task_type}")

                task = db.session.get(Task, task_id)
                has_failed = result and hasattr(result, 'status') and result.status == 'failed'
                task.status = 'failed' if has_failed else 'success'
                self._safe_commit()
                if has_failed:
                    app.logger.warning(f"[Task {task_id}] Process exited with error, marked as failed")
                else:
                    app.logger.info(f"[Task {task_id}] Completed successfully")
                    print(f"[TaskExecutor] Task {task_id} completed successfully", file=sys.stderr, flush=True)
                self._update_next_run_time(task)

            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                app.logger.error(f"[Task {task_id}] Failed: {str(e)}\n{traceback.format_exc()}")
                print(f"[TaskExecutor] Task {task_id} FAILED: {e}", file=sys.stderr, flush=True)
                try:
                    task.status = 'failed'
                    self._safe_commit()
                except:
                    pass
                self._update_next_run_time(task)
    
    def _execute_perf_test(self, task, app):
        """执行服务压力测试"""
        config = json.loads(task.config)

        # 简化日志，只记录关键信息
        app.logger.info(f"[Task {task.id}] Perf test - model: {config.get('model')}, parallel: {config.get('parallel')}")

        # 根据配置选择引擎：native=自研引擎，evalscope=默认CLI
        engine_type = config.get('engine', 'evalscope')
        if engine_type == 'native':
            return self._execute_perf_test_native(task, app, config)
        
        # 以下是原有的 evalscope 逻辑
        
        # 生成唯一的输出目录名（使用任务ID和时间戳）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_output_dir = f"evalscope_outputs/task_{task.id}"
        
        # 构建命令
        cmd = [
            sys.executable, '-m', 'evalscope.cli.cli', 'perf',
            '--model', config['model'],
            '--api', config.get('api', 'openai'),
            '--url', config['url'],
            '--api-key', config['api_key'],
            '--tokenizer-path', config.get('tokenizer_path', 'Qwen/Qwen2-1.5B-Instruct'),
            '--parallel', str(config.get('parallel', 8)),
            '-n', str(config.get('number', 50)),
            '--dataset', config.get('dataset', 'random'),
            '--min-prompt-length', str(config.get('min_prompt_length', 10)),
            '--max-prompt-length', str(config.get('max_prompt_length', 20)),
            '--min-tokens', str(config.get('min_tokens', 128)),
            '--max-tokens', str(config.get('max_tokens', 128)),
            '--connect-timeout', str(config.get('connect_timeout', 60)),
            '--read-timeout', str(config.get('read_timeout', 120)),
            '--outputs-dir', unique_output_dir,  # 使用唯一输出目录
            '--stream'
        ]
        
        # 格式化命令为多行显示
        cmd_str = ' \\\n  '.join([f'{sys.executable} -m evalscope.cli.cli perf'] + [
            f'--model {config["model"]}',
            f"--api {config.get('api', 'openai')}",
            f"--url {config['url']}",
            f"--api-key {config['api_key'][:10]}...",  # 隐藏部分密钥
            f"--tokenizer-path {config.get('tokenizer_path', 'Qwen/Qwen2-1.5B-Instruct')}",
            f"--parallel {config.get('parallel', 8)}",
            f"-n {config.get('number', 50)}",
            f"--dataset {config.get('dataset', 'random')}",
            f"--min-prompt-length {config.get('min_prompt_length', 10)}",
            f"--max-prompt-length {config.get('max_prompt_length', 20)}",
            f"--min-tokens {config.get('min_tokens', 128)}",
            f"--max-tokens {config.get('max_tokens', 128)}",
            f"--connect-timeout {config.get('connect_timeout', 60)}",
            f"--read-timeout {config.get('read_timeout', 120)}",
            f"--outputs-dir {unique_output_dir}",
            '--stream'
        ])

        # 检查是否使用模拟器（用于测试）
        use_mock = app.config.get('USE_MOCK_EVALSCOPE', False)
        if use_mock:
            cmd = ['./mock_evalscope.sh'] + cmd[1:]
        
        # 创建输出目录和文件
        output_dir = Path(app.config['UPLOAD_FOLDER']) / f"task_{task.id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"perf_{timestamp}.txt"
        filepath = output_dir / filename
        output_file = str(filepath)
        
        # 构造环境变量
        env = os.environ.copy()
        env['MODELSCOPE_CREDENTIALS_PATH'] = os.path.abspath(app.config.get('MODELSCOPE_CREDENTIALS_PATH', 'data/modelscope/credentials'))
        env['MODELSCOPE_CACHE'] = os.path.abspath(app.config.get('MODELSCOPE_CACHE', 'data/modelscope_cache'))
        env['MODELSCOPE_HOME'] = os.path.dirname(env['MODELSCOPE_CREDENTIALS_PATH'])
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['NO_COLOR'] = '1'
        env['CLICOLOR'] = '0'
        env['TERM'] = 'dumb'
        os.makedirs(os.path.dirname(env['MODELSCOPE_CREDENTIALS_PATH']), exist_ok=True)
        os.makedirs(env['MODELSCOPE_CACHE'], exist_ok=True)
        
        # 执行命令，stdout 直接写入文件
        timeout = app.config.get('TASK_TIMEOUT', 3600)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    timeout=timeout
                )
        except subprocess.TimeoutExpired:
            app.logger.error(f"Task {task.id} timed out after {timeout}s")
            return None
        
        # 读取输出用于解析
        with open(filepath, 'r', encoding='utf-8') as f:
            output = f.read()

        app.logger.info(f"[Task {task.id}] Process exited with rc={result.returncode}, output length={len(output)}")

        # 检查进程返回码
        if result.returncode != 0:
            app.logger.warning(f"Process terminated with return code: {result.returncode}, stderr preview: {output[-500:] if output else 'EMPTY'}")

        # 从 evalscope JSON 输出中解析结果
        metrics = self._parse_perf_json(unique_output_dir, output)

        if not metrics:
            app.logger.warning("Could not parse detailed metrics from JSON, trying text fallback")
            metrics = self._parse_perf_output(output)

        if not metrics:
            app.logger.warning("Could not parse detailed metrics, using summary only")

        # 保存结果到数据库
        perf_result = PerfTestResult(
            task_id=task.id,
            execution_time=datetime.now(),
            command=cmd_str,
            output_file=output_file,
            status='success'
        )
        
        if metrics:
            perf_result.concurrency = metrics.get('concurrency')
            perf_result.avg_latency = metrics.get('avg_latency')
            perf_result.p99_latency = metrics.get('p99_latency')
            perf_result.avg_ttft = metrics.get('avg_ttft')
            perf_result.p99_ttft = metrics.get('p99_ttft')
            perf_result.avg_tpot = metrics.get('avg_tpot')
            perf_result.p99_tpot = metrics.get('p99_tpot')
            perf_result.rps = metrics.get('rps')
            perf_result.gen_toks = metrics.get('gen_toks')
            perf_result.success_rate = metrics.get('success_rate')
        
        db.session.add(perf_result)
        self._safe_commit()
        
        app.logger.info(f"Perf test result saved: {perf_result.id}")
        
        return perf_result
    
    def _execute_perf_test_native(self, task, app, config):
        """使用自研引擎执行服务压力测试"""
        from .llm_engine import run_llm_perf_test, LLMPerfEngine
        
        app.logger.info(f"[Task {task.id}] Using native engine for perf test")
        
        # 创建停止事件
        stop_event = Event()
        self._stop_events[task.id] = stop_event
        
        # 构建引擎配置
        engine_config = {
            'url': config['url'],
            'api_key': config['api_key'],
            'model': config['model'],
            'api': config.get('api', 'openai'),
            'parallel': config.get('parallel', 8),
            'number': config.get('number', 50),
            'stream': True,  # 自研引擎始终使用流式以精确测量 TTFT/TPOT
            'max_tokens': config.get('max_tokens', 128),
            'connect_timeout': config.get('connect_timeout', 60),
            'read_timeout': config.get('read_timeout', 120),
        }
        
        # 如果有自定义 prompt
        if config.get('prompt'):
            engine_config['prompt'] = config['prompt']
        
        # 创建引擎实例并注册到实时指标存储
        engine = LLMPerfEngine(engine_config)
        self._live_engines[task.id] = engine
        
        # 创建输出目录（保存实时日志）
        output_dir = Path(app.config['UPLOAD_FOLDER']) / f"task_{task.id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"perf_{timestamp}.txt"
        filepath = output_dir / filename
        output_file = str(filepath)
        
        # 构建命令字符串（用于记录，自研引擎无实际命令）
        cmd_str = f"[Native Engine] model={config['model']}, parallel={engine_config['parallel']}, number={engine_config['number']}, stream=True"
        
        # 先写入头部信息，让前端可以立即看到日志
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"=== Native Engine Performance Test ===\n")
            f.write(f"Model: {config['model']}\n")
            f.write(f"API: {engine_config.get('api', 'openai')}\n")
            f.write(f"URL: {config['url']}\n")
            f.write(f"Concurrency: {engine_config['parallel']}\n")
            f.write(f"Total Requests: {engine_config['number']}\n")
            f.write(f"Stream: True\n")
            f.write(f"Max Tokens: {engine_config['max_tokens']}\n")
            f.write(f"\n=== Running... ===\n")
            f.flush()
        
        try:
            # 运行压测（在独立线程中，同时实时写日志）
            import threading
            
            def _run_test():
                return run_llm_perf_test(engine_config, stop_event=stop_event)
            
            test_result = [None]
            test_error = [None]
            
            def _test_thread():
                try:
                    test_result[0] = _run_test()
                except Exception as e:
                    test_error[0] = e
            
            t = threading.Thread(target=_test_thread, daemon=True)
            t.start()
            
            # 实时写入日志：等待测试完成，同时定期追加指标快照
            last_count = 0
            while t.is_alive():
                t.join(timeout=2.0)
                # 追加实时指标到日志文件
                try:
                    snap = engine.metrics.snapshot()
                    count = snap.get('request_count', 0)
                    if count > last_count:
                        avg_ttft = snap.get('avg_ttft')
                        ttft_str = f"{avg_ttft:.0f}ms" if avg_ttft else '-'
                        with open(filepath, 'a', encoding='utf-8') as f:
                            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] "
                                    f"requests={count}, "
                                    f"success={snap.get('success_count', 0)}, "
                                    f"error={snap.get('error_count', 0)}, "
                                    f"rps={snap.get('rps', 0)}, "
                                    f"avg_latency={snap.get('avg_latency', 0):.3f}s, "
                                    f"avg_ttft={ttft_str}, "
                                    f"success_rate={snap.get('success_rate', 0):.1f}%\n")
                            f.flush()
                        last_count = count
                except Exception:
                    pass
            
            if test_error[0]:
                raise test_error[0]
            
            result_data = test_result[0]
            
            # 追加最终结果到日志文件
            try:
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== Results ===\n")
                    f.write(f"Concurrency: {result_data.get('concurrency')}\n")
                    f.write(f"Total Requests: {result_data.get('total_requests')}\n")
                    f.write(f"Success Requests: {result_data.get('success_requests')}\n")
                    f.write(f"Error Requests: {result_data.get('error_requests')}\n")
                    f.write(f"Elapsed: {result_data.get('elapsed_seconds')}s\n")
                    f.write(f"RPS: {result_data.get('rps')}\n")
                    f.write(f"Avg Latency: {result_data.get('avg_latency')}s\n")
                    f.write(f"P99 Latency: {result_data.get('p99_latency')}s\n")
                    f.write(f"Avg TTFT: {result_data.get('avg_ttft')}ms\n")
                    f.write(f"P99 TTFT: {result_data.get('p99_ttft')}ms\n")
                    f.write(f"Avg TPOT: {result_data.get('avg_tpot')}ms\n")
                    f.write(f"P99 TPOT: {result_data.get('p99_tpot')}ms\n")
                    f.write(f"Gen Tok/s: {result_data.get('gen_toks')}\n")
                    f.write(f"Success Rate: {result_data.get('success_rate')}%\n")
                    f.write(f"Prompt Tokens: {result_data.get('prompt_tokens')}\n")
                    f.write(f"Completion Tokens: {result_data.get('completion_tokens')}\n")
                    f.write(f"Total Tokens: {result_data.get('total_tokens')}\n")
                    if result_data.get('error_types'):
                        f.write(f"Error Types: {json.dumps(result_data['error_types'])}\n")
            except Exception as e:
                app.logger.warning(f"Failed to write native engine output: {e}")
            
            # 保存结果到数据库（字段与 PerfTestResult 完全对齐）
            perf_result = PerfTestResult(
                task_id=task.id,
                execution_time=datetime.now(),
                command=cmd_str,
                output_file=output_file,
                status='success'
            )
            
            perf_result.concurrency = result_data.get('concurrency')
            perf_result.avg_latency = result_data.get('avg_latency')
            perf_result.p99_latency = result_data.get('p99_latency')
            perf_result.avg_ttft = result_data.get('avg_ttft')
            perf_result.p99_ttft = result_data.get('p99_ttft')
            perf_result.avg_tpot = result_data.get('avg_tpot')
            perf_result.p99_tpot = result_data.get('p99_tpot')
            perf_result.rps = result_data.get('rps')
            perf_result.gen_toks = result_data.get('gen_toks')
            perf_result.success_rate = result_data.get('success_rate')
            
            db.session.add(perf_result)
            self._safe_commit()
            
            app.logger.info(f"Native engine perf test result saved: {perf_result.id}")
            return perf_result
            
        except Exception as e:
            app.logger.error(f"[Task {task.id}] Native engine failed: {e}")
            traceback.print_exc(file=sys.stderr)
            
            # 保存失败结果
            perf_result = PerfTestResult(
                task_id=task.id,
                execution_time=datetime.now(),
                command=cmd_str,
                output_file=output_file,
                status='failed',
                error_message=str(e)
            )
            db.session.add(perf_result)
            self._safe_commit()
            return perf_result
            
        finally:
            # 清理实时引用
            self._live_engines.pop(task.id, None)
            self._stop_events.pop(task.id, None)
    
    def get_live_metrics(self, task_id: int):
        """获取任务的实时指标（自研引擎）"""
        engine = self._live_engines.get(task_id)
        if engine and engine.is_running():
            return engine.metrics.snapshot()
        return None
    
    def _execute_quality_test(self, task, app):
        """执行模型质量测试"""
        config = json.loads(task.config)
        
        app.logger.info(f"Executing quality test with config: {config}")
        
        # 始终使用项目根目录下的 audit.py
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        audit_script = os.path.join(project_root, 'audit.py')
        work_dir = project_root
        
        app.logger.info(f"Audit script path: {audit_script}")
        app.logger.info(f"Working directory: {work_dir}")
        
        # 创建输出目录和文件（提前创建，支持实时写入）
        output_dir = Path(app.config['UPLOAD_FOLDER']) / f"task_{task.id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"quality_{timestamp}.txt"
        filepath = output_dir / filename
        output_file = str(filepath)
        
        # 报告文件路径（与日志文件同目录，命名为 quality_{timestamp}_report.md）
        report_path = str(output_dir / f"quality_{timestamp}_report.md")
        
        # 构建命令
        model_name = config.get('model', 'claude-opus-4-6')
        cmd = [
            sys.executable, audit_script,
            '--key', config['api_key'],
            '--url', config['url'],
            '--model', model_name,
            '--output', report_path
        ]
        
        # 格式化命令为多行显示
        cmd_str = ' \\\n  '.join([
            f'{sys.executable} {audit_script}',
            f"--key {config['api_key'][:10]}...",
            f"--url {config['url']}",
            f"--model {model_name}",
            f"--output {report_path}"
        ])

        # 构造环境变量
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['NO_COLOR'] = '1'
        env['CLICOLOR'] = '0'
        env['TERM'] = 'dumb'

        # 执行命令，stdout 直接写入文件
        timeout = app.config.get('TASK_TIMEOUT', 3600)
        with open(filepath, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=work_dir,
                env=env,
                timeout=timeout
            )
        
        # 读取输出用于解析
        with open(filepath, 'r', encoding='utf-8') as f:
            output = f.read()

        # 检查进程返回码
        if result.returncode != 0:
            app.logger.warning(f"Process terminated with return code: {result.returncode}")

        # 从报告文件中解析结果
        risk_summary = {}
        if os.path.exists(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                report_content = f.read()
            risk_summary = self._parse_quality_report(report_content)
        else:
            app.logger.warning(f"Report file not found: {report_path}")
            # 尝试从命令行输出解析（兼容旧逻辑）
            risk_summary = self._parse_quality_output(output)
        
        app.logger.info(f"Parsed risk summary: {risk_summary}")
        
        # 保存结果到数据库
        result_status = 'success' if result.returncode == 0 else 'failed'
        result = QualityTestResult(
            task_id=task.id,
            execution_time=datetime.now(),
            command=cmd_str,
            output_file=output_file,
            status=result_status
        )
        
        if risk_summary:
            result.infrastructure_recon = risk_summary.get('item_1')
            result.models_enumerated = risk_summary.get('item_2')
            result.token_injection = risk_summary.get('item_3')
            result.prompt_extraction = risk_summary.get('item_4')
            result.instruction_override = risk_summary.get('item_5')
            result.jailbreak_test = risk_summary.get('item_6')
            result.context_boundary = risk_summary.get('item_7')
            result.tool_call_substitution = risk_summary.get('item_8')
            result.error_response_leakage = risk_summary.get('item_9')
            result.stream_integrity = risk_summary.get('item_10')
            result.overall_rating = risk_summary.get('overall_rating')
            # 保存完整的 Risk Summary JSON
            result.risk_summary_json = json.dumps(risk_summary, ensure_ascii=False)
        
        # 保存报告文件路径
        if os.path.exists(report_path):
            result.report_file = report_path
        
        db.session.add(result)
        db.session.commit()
        
        app.logger.info(f"Quality test result saved: {result.id}")
        
        return result
    
    def _save_output_file(self, task, output, test_type, app):
        """保存输出文件"""
        # 创建输出目录
        output_dir = Path(app.config['UPLOAD_FOLDER']) / f"task_{task.id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{test_type}_{timestamp}.txt"
        filepath = output_dir / filename
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output)
        
        app.logger.info(f"Output saved to: {filepath}")
        
        return str(filepath)
    
    _ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')
    
    def _strip_ansi(self, text):
        return self._ANSI_PATTERN.sub('', text)
    
    def _parse_perf_json(self, output_dir, log_output=''):
        """从 evalscope 生成的 JSON 文件中解析性能指标"""
        import time
        
        match = re.search(r"Save the summary to:\s*(\S+)", log_output or '')
        if match:
            log_dir = match.group(1)
            log_dir = re.sub(r'[\\/][^\\/]*$', '', log_dir)
        
        base_path = Path(output_dir).resolve()
        print(f"[TaskExecutor] _parse_perf_json: output_dir={output_dir}, resolved={base_path}, exists={base_path.exists()}, cwd={os.getcwd()}", file=sys.stderr, flush=True)
        if not base_path.exists():
            print(f"[TaskExecutor] _parse_perf_json: base_path does not exist, returning None", file=sys.stderr, flush=True)
            return None
        
        for attempt in range(3):
            summary_files = sorted(base_path.rglob('benchmark_summary.json'), reverse=True)
            
            if not summary_files and match:
                alt_path = Path(log_dir)
                if alt_path.exists():
                    summary_files = sorted(alt_path.rglob('benchmark_summary.json'), reverse=True)
            
            print(f"[TaskExecutor] _parse_perf_json attempt={attempt}: found {len(summary_files)} summary files", file=sys.stderr, flush=True)
            if summary_files:
                break
            time.sleep(1)
        
        if not summary_files:
            print(f"[TaskExecutor] _parse_perf_json: no summary files after {attempt+1} attempts", file=sys.stderr, flush=True)
            return None
        
        summary_path = summary_files[0]
        percentile_path = summary_path.parent / 'benchmark_percentile.json'
        
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            
            p99_latency = None
            p99_ttft = None
            p99_tpot = None
            if percentile_path.exists():
                with open(percentile_path, 'r', encoding='utf-8') as f:
                    percentiles = json.load(f)
                p99 = next((p for p in percentiles if p.get('Percentiles') == '99%'), None)
                if p99:
                    p99_latency = p99.get('Latency (s)')
                    p99_ttft = p99.get('TTFT (ms)')
                    p99_tpot = p99.get('TPOT (ms)')
            
            total = summary.get('Total Requests', 1)
            success = summary.get('Success Requests', 0)
            success_rate = round(success / total * 100, 1) if total > 0 else 0
            
            return {
                'concurrency': summary.get('Concurrency'),
                'rps': summary.get('Req Throughput (req/s)'),
                'avg_latency': summary.get('Avg Latency (s)'),
                'p99_latency': p99_latency or summary.get('Avg Latency (s)'),
                'avg_ttft': summary.get('TTFT (ms)'),
                'p99_ttft': p99_ttft or summary.get('TTFT (ms)'),
                'avg_tpot': summary.get('TPOT (ms)'),
                'p99_tpot': p99_tpot or summary.get('TPOT (ms)'),
                'gen_toks': summary.get('Output Throughput (tok/s)'),
                'success_rate': success_rate,
            }
        except Exception as e:
            print(f"[TaskExecutor] JSON parse error: {e}", file=sys.stderr, flush=True)
            return None

    def _parse_perf_output(self, output):
        """解析 evalscope perf 输出"""
        output = self._strip_ansi(output)
        
        result = {
            'concurrency': None,
            'rate': None,
            'rps': None,
            'avg_latency': None,
            'p99_latency': None,
            'avg_ttft': None,
            'p99_ttft': None,
            'avg_tpot': None,
            'p99_tpot': None,
            'gen_toks': None,
            'success_rate': None
        }
        
        # 方法1：尝试解析新的 Unicode 表格格式
        # Performance Overview 表格（支持 ┃ 和 │ 混合）
        # 表头使用 ┃，数据使用 │
        perf_pattern = re.compile(
            r'┃?\s*(\d+)\s*[┃│]\s*(\S+)\s*[┃│]\s*(\d+)\s*[┃│]\s*'
            r'([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)%\s*[┃│]?'
        )
        perf_match = perf_pattern.search(output)
        if perf_match:
            result['concurrency'] = int(perf_match.group(1))
            result['rate'] = perf_match.group(2)
            result['rps'] = float(perf_match.group(4))
            result['gen_toks'] = float(perf_match.group(5))
            result['success_rate'] = float(perf_match.group(6))
        
        # Per-Request Metrics 表格（Latency 和 TTFT）
        # 查找 Latency 行
        latency_pattern = re.compile(
            r'┃?\s*(\d+)\s*[┃│]\s*(\S+)\s*[┃│]\s*Latency \(s\)\s*[┃│]\s*'
            r'([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]?'
        )
        latency_match = latency_pattern.search(output)
        if latency_match:
            result['avg_latency'] = float(latency_match.group(3))
            result['p99_latency'] = float(latency_match.group(5))
        
        # 查找 TTFT 行（可能是 TTFT (ms) 或 Time To First Token (ms)）
        # 注意：Per-Request Metrics 表格的前两列可能为空
        ttft_pattern = re.compile(
            r'[┃│]\s*[┃│]\s*[┃│]\s*(?:TTFT|Time To First Token)\s*\(ms\)\s*[┃│]\s*'
            r'([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]?'
        )
        ttft_match = ttft_pattern.search(output)
        if ttft_match:
            result['avg_ttft'] = float(ttft_match.group(1))
            result['p99_ttft'] = float(ttft_match.group(3))
        
        # 查找 TPOT 行
        tpot_pattern = re.compile(
            r'[┃│]\s*[┃│]\s*[┃│]\s*(?:TPOT|Time Per Output Token)\s*\(ms\)\s*[┃│]\s*'
            r'([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]\s*([\d.]+)\s*[┃│]?'
        )
        tpot_match = tpot_pattern.search(output)
        if tpot_match:
            result['avg_tpot'] = float(tpot_match.group(1))
            result['p99_tpot'] = float(tpot_match.group(3))
        
        # 方法2：备用解析 - 尝试解析旧的纯 ASCII 表格格式
        if result['rps'] is None:
            old_pattern = re.compile(
                r'│\s*(\d+)\s*│\s*(\S+)\s*│\s*(\d+)\s*│\s*'
                r'([\d.]+)\s*│\s*([\d.]+)\s*│\s*'
                r'([\d.]+)\s*│\s*([\d.]+)\s*│\s*'
                r'([\d.]+)\s*│\s*([\d.]+)\s*│\s*'
                r'([\d.]+)\s*│\s*([\d.]+)%\s*│'
            )
            for line in output.split('\n'):
                match = old_pattern.search(line)
                if match:
                    result['concurrency'] = int(match.group(1))
                    result['rate'] = match.group(2)
                    result['rps'] = float(match.group(4))
                    result['avg_latency'] = float(match.group(5))
                    result['p99_latency'] = float(match.group(6))
                    result['avg_ttft'] = float(match.group(7))
                    result['p99_ttft'] = float(match.group(8))
                    result['avg_tpot'] = float(match.group(9))
                    result['p99_tpot'] = float(match.group(10))
                    result['gen_toks'] = float(match.group(11))
                    result['success_rate'] = float(match.group(12))
                    break
        
        # 检查是否有足够的数据
        if result['rps'] is not None or result['gen_toks'] is not None:
            return result
        
        return None
    
    def _parse_quality_output(self, output):
        """解析 audit.py 输出"""
        risk_summary = {}
        
        # 解析 Risk Summary 部分
        patterns = {
            'infrastructure_recon': r'Infrastructure recon (\S+)',
            'models_enumerated': r'(\d+) models enumerated',
            'token_injection': r'No token injection detected',
            'extraction_attempts': r'All extraction attempts failed',
            'cat_test': r'Cat test passed',
            'context_boundary': r'Context boundary: ([^\n]+)',
            'tool_call_substitution': r'No tool-call package substitution detected',
            'error_response_leakage': r'Error response leaks ([^\(]+)',
            'stream_integrity': r'Stream integrity ([^\n]+)',
            'overall_rating': r'## (\d+)\. Overall Rating\s+### ([^\n]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                if key == 'overall_rating':
                    risk_summary[key] = match.group(2).strip()
                elif key == 'context_boundary':
                    risk_summary[key] = match.group(1).strip()
                elif key in ['infrastructure_recon', 'error_response_leakage', 'stream_integrity']:
                    risk_summary[key] = match.group(1).strip()
                elif key == 'models_enumerated':
                    risk_summary[key] = f"{match.group(1)} models"
                else:
                    risk_summary[key] = 'passed'
        
        return risk_summary
    
    def _parse_quality_report(self, report_content):
        """从报告文件中解析 Risk Summary"""
        risk_summary = {}
        
        # 提取风险摘要部分（支持中英文）
        risk_section_match = re.search(r'## (?:Risk Summary|风险摘要)\s*\n(.*?)(?=\n---|\n## \d)', report_content, re.DOTALL)
        if not risk_section_match:
            return risk_summary
        
        risk_section = risk_section_match.group(1)
        
        # 提取所有列表项（以 "- " 开头的行）
        items = re.findall(r'^-\s+(.+)$', risk_section, re.MULTILINE)
        
        # 将列表项存入 risk_summary（保留完整内容，包括图标）
        for i, item in enumerate(items):
            risk_summary[f'item_{i+1}'] = item.strip()
        
        # 同时提取总体评级（支持中英文）
        rating_match = re.search(r'(🔴|🟡|🟢).*?(HIGH|MEDIUM|LOW|CRITICAL|高风险|中风险|低风险)', report_content, re.IGNORECASE)
        if rating_match:
            risk_summary['overall_rating'] = f"{rating_match.group(1)} {rating_match.group(2).upper()}"
        else:
            # 根据红色和黄色标记数量推断评级
            red_count = risk_section.count('🔴')
            yellow_count = risk_section.count('🟡')
            if red_count >= 2:
                risk_summary['overall_rating'] = '🔴 高风险'
            elif red_count == 1 or yellow_count >= 2:
                risk_summary['overall_rating'] = '🟡 中风险'
            else:
                risk_summary['overall_rating'] = '🟢 低风险'
        
        return risk_summary
    
    def _execute_availability_test(self, task, app):
        """执行服务可用性测试"""
        from ..models import AvailabilityTestResult
        
        config = json.loads(task.config)
        model_name = config.get('model', '')
        channels = config.get('channels', [])
        
        # 测试参数
        parallel = config.get('parallel', 1)
        number = config.get('number', 10)
        connect_timeout = config.get('connect_timeout', 60)
        read_timeout = config.get('read_timeout', 120)
        
        app.logger.info(f"[Task {task.id}] Availability test - model: {model_name}, channels: {len(channels)}")
        
        # 对每个渠道执行测试
        results = []
        for channel in channels:
            channel_name = channel.get('name', '')
            channel_url = channel.get('url', '')
            channel_api_key = channel.get('api_key', '')
            
            if not channel_url or not channel_api_key:
                app.logger.warning(f"[Task {task.id}] Channel {channel_name} missing URL or API Key, skipping")
                continue
            
            app.logger.info(f"[Task {task.id}] Testing channel: {channel_name}")
            
            # 执行性能测试
            try:
                perf_result = self._test_single_channel(
                    task, app, channel_name, channel_url, channel_api_key, 
                    model_name, parallel, number, connect_timeout, read_timeout
                )
                
                # 保存结果
                result = AvailabilityTestResult(
                    task_id=task.id,
                    execution_time=datetime.now(),
                    channel_name=channel_name,
                    model_name=model_name,
                    concurrency=parallel,
                    avg_latency=perf_result.get('avg_latency'),
                    p99_latency=perf_result.get('p99_latency'),
                    avg_ttft=perf_result.get('avg_ttft'),
                    p99_ttft=perf_result.get('p99_ttft'),
                    rps=perf_result.get('rps'),
                    gen_toks=perf_result.get('gen_toks'),
                    success_rate=perf_result.get('success_rate'),
                    status='success'
                )
                db.session.add(result)
                self._safe_commit()
                results.append(result)
                
                app.logger.info(f"[Task {task.id}] Channel {channel_name} test completed: success_rate={perf_result.get('success_rate')}")
                
            except Exception as e:
                app.logger.error(f"[Task {task.id}] Channel {channel_name} test failed: {str(e)}")
                
                # 保存失败结果
                result = AvailabilityTestResult(
                    task_id=task.id,
                    execution_time=datetime.now(),
                    channel_name=channel_name,
                    model_name=model_name,
                    concurrency=parallel,
                    status='failed',
                    error_message=str(e)
                )
                db.session.add(result)
                self._safe_commit()
                results.append(result)
        
        app.logger.info(f"[Task {task.id}] Availability test completed: {len(results)} channels tested")
        
        # 返回最后一个结果（用于判断整体状态）
        if results:
            failed_count = sum(1 for r in results if r.status == 'failed')
            if failed_count > 0:
                # 如果有失败的渠道，返回一个失败状态的结果
                return results[-1] if results[-1].status == 'failed' else None
            else:
                return results[-1]
        return None
    
    def _test_single_channel(self, task, app, channel_name, channel_url, channel_api_key, 
                             model_name, parallel, number, connect_timeout, read_timeout):
        """测试单个渠道的性能"""
        
        # 获取任务配置中的引擎类型
        task_config = json.loads(task.config) if isinstance(task.config, str) else task.config
        engine_type = task_config.get('engine', 'evalscope')
        
        if engine_type == 'native':
            return self._test_single_channel_native(
                task, app, channel_name, channel_url, channel_api_key,
                model_name, parallel, number, connect_timeout, read_timeout
            )
        
        # 以下是原有的 evalscope 逻辑
        
        # 生成唯一的输出目录名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_output_dir = f"evalscope_outputs/task_{task.id}_channel_{channel_name}"
        
        # 构建命令
        cmd = [
            sys.executable, '-m', 'evalscope.cli.cli', 'perf',
            '--model', model_name,
            '--api', 'openai',
            '--url', channel_url,
            '--api-key', channel_api_key,
            '--tokenizer-path', 'Qwen/Qwen2-1.5B-Instruct',
            '--parallel', str(parallel),
            '-n', str(number),
            '--dataset', 'random',
            '--min-prompt-length', '10',
            '--max-prompt-length', '20',
            '--min-tokens', '128',
            '--max-tokens', '128',
            '--connect-timeout', str(connect_timeout),
            '--read-timeout', str(read_timeout),
            '--outputs-dir', unique_output_dir,
            '--stream'
        ]
        
        # 创建输出目录和文件
        output_dir = Path(app.config['UPLOAD_FOLDER']) / f"task_{task.id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"availability_{channel_name}_{timestamp}.txt"
        filepath = output_dir / filename
        
        # 构造环境变量
        env = os.environ.copy()
        env['MODELSCOPE_CREDENTIALS_PATH'] = os.path.abspath(app.config.get('MODELSCOPE_CREDENTIALS_PATH', 'data/modelscope/credentials'))
        env['MODELSCOPE_CACHE'] = os.path.abspath(app.config.get('MODELSCOPE_CACHE', 'data/modelscope_cache'))
        env['MODELSCOPE_HOME'] = os.path.dirname(env['MODELSCOPE_CREDENTIALS_PATH'])
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['NO_COLOR'] = '1'
        env['CLICOLOR'] = '0'
        env['TERM'] = 'dumb'
        os.makedirs(os.path.dirname(env['MODELSCOPE_CREDENTIALS_PATH']), exist_ok=True)
        os.makedirs(env['MODELSCOPE_CACHE'], exist_ok=True)
        
        # 执行命令
        timeout = app.config.get('TASK_TIMEOUT', 3600)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    timeout=timeout
                )
        except subprocess.TimeoutExpired:
            app.logger.error(f"Channel {channel_name} test timed out after {timeout}s")
            raise Exception(f"Test timed out after {timeout}s")
        
        # 读取输出并解析性能指标
        with open(filepath, 'r', encoding='utf-8') as f:
            output = f.read()
        
        # 解析性能指标
        perf_result = self._parse_perf_output(output)
        
        if not perf_result:
            raise Exception("Failed to parse performance metrics from output")
        
        return perf_result
    
    def _test_single_channel_native(self, task, app, channel_name, channel_url, channel_api_key,
                                     model_name, parallel, number, connect_timeout, read_timeout):
        """使用自研引擎测试单个渠道的性能"""
        from .llm_engine import run_llm_perf_test
        
        engine_config = {
            'url': channel_url,
            'api_key': channel_api_key,
            'model': model_name,
            'api': 'openai',
            'parallel': parallel,
            'number': number,
            'stream': True,
            'max_tokens': 128,
            'connect_timeout': connect_timeout,
            'read_timeout': read_timeout,
        }
        
        result_data = run_llm_perf_test(engine_config)
        
        # 返回与 _parse_perf_output 相同格式的字典
        return {
            'concurrency': result_data.get('concurrency', parallel),
            'rps': result_data.get('rps'),
            'avg_latency': result_data.get('avg_latency'),
            'p99_latency': result_data.get('p99_latency'),
            'avg_ttft': result_data.get('avg_ttft'),
            'p99_ttft': result_data.get('p99_ttft'),
            'avg_tpot': result_data.get('avg_tpot'),
            'p99_tpot': result_data.get('p99_tpot'),
            'gen_toks': result_data.get('gen_toks'),
            'success_rate': result_data.get('success_rate'),
        }
