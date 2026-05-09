import os, sys
os.chdir(r'E:\code\LLM-API-benchmark')
sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'development'

from backend import create_app, db
from backend.models import Task

app = create_app('development')
with app.app_context():
    task = db.session.get(Task, 1)
    task.status = 'running'
    db.session.commit()
    
    from backend.executor import TaskExecutor
    executor = TaskExecutor()
    try:
        executor._execute_task(task.id, app)
    except Exception as e:
        import traceback
        traceback.print_exc()
    
    task2 = db.session.get(Task, 1)
    print(f'Final status: {task2.status}')
