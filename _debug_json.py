import os, sys, re, time, json
sys.path.insert(0, '.')
from backend.executor import TaskExecutor

executor = TaskExecutor()

with open('data/outputs/task_1/perf_20260509_131336.txt', encoding='utf-8') as f:
    log_output = f.read()

result = executor._parse_perf_json('evalscope_outputs/task_1', log_output)
print(f'result={result}')
if result:
    for k, v in result.items():
        print(f'  {k}: {v}')
