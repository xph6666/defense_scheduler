"""Isolated UI test server. Creates disposable test data, never uses the business database."""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
data_dir = tempfile.TemporaryDirectory(prefix='defense-workflow-')
os.environ['DJANGO_DB_PATH'] = str(Path(data_dir.name) / 'ui.sqlite3')
os.environ['DJANGO_SETTINGS_MODULE'] = 'defense_scheduler.settings'
os.environ['DJANGO_SECRET_KEY'] = 'isolated-ui-test-only-' * 4
os.environ['DJANGO_ENV'] = 'local'
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)
from django.contrib.auth.models import User
from api.models import Teacher, Student, Room
User.objects.create_user(username='ui-reviewer', password='Ui-Review-Only-4926', is_staff=True)
User.objects.create_user(username='ui-reader', password='Ui-Review-Only-4926')
for i in range(7):
    Teacher.objects.create(name=f'测试教师{i+1}', title='教授', college='测试学院',
                           roles=['专家', '主席', '组长', '秘书'],
                           available_types=['预答辩', '正式答辩', '中期答辩'])
for i in range(2):
    Student.objects.create(name=f'测试学生{i+1}', student_no=f'UI00{i+1}',
                           mentor_name='测试教师1', campus='创新港',
                           defense_types=['预答辩', '正式答辩', '中期答辩'])
Room.objects.create(campus='创新港', name='测试教室101', capacity=30, available_times='')
from django.core.wsgi import get_wsgi_application
from waitress import serve
serve(get_wsgi_application(), host='127.0.0.1', port=8769, threads=4)
