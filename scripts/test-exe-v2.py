r"""Verify V2 API and exports using the built Windows executable and an isolated DB.

Usage: .venv\Scripts\python.exe scripts/test-exe-v2.py --exe release/v2026.10.02/DefenseScheduler.exe
The copied executable, database and logs remain under .tmp/exe-v2 for inspection.
"""
import argparse
from contextlib import closing
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

from openpyxl import Workbook
import psutil


ROOT = Path(__file__).resolve().parents[1]


def spreadsheet(rows, size=None):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    if size is not None:
        # A legitimate ZIP member pads a valid XLSX without adding roster rows.
        original = stream.getvalue()
        padding_name = 'acceptance-padding.bin'
        overhead = 30 + 46 + 2 * len(padding_name)
        padding = size - len(original) - overhead
        assert padding >= 0
        with zipfile.ZipFile(stream, 'a', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(padding_name, b'0' * padding)
        assert len(stream.getvalue()) == size
    return stream.getvalue()


def multipart(fields, files):
    boundary = secrets.token_hex(24)
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for key, name, content in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        parts.extend((content, b'\r\n'))
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def stop_test_process(pid, executable):
    """Terminate only the onefile process tree started from this test copy."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    expected = executable.resolve()
    assert expected.is_relative_to(ROOT / '.tmp'), expected
    assert Path(parent.exe()).resolve() == expected
    # Windows may attach a conhost child. Terminating the verified EXE parent
    # releases its console; only terminate descendants from this same EXE copy.
    owned = [p for p in parent.children(recursive=True) if Path(p.exe()).resolve() == expected] + [parent]
    for child in owned:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(owned, timeout=15)
    assert not alive, 'Isolated EXE test processes did not stop'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    args = parser.parse_args()
    source = args.exe.resolve()
    assert source.is_file(), source
    output = (ROOT / '.tmp' / 'exe-v2' / time.strftime('%Y%m%d-%H%M%S')).resolve()
    assert output.is_relative_to(ROOT / '.tmp')
    output.mkdir(parents=True, exist_ok=False)
    executable = output / 'DefenseScheduler.exe'
    shutil.copyfile(source, executable)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    username, password = 'packaged-v2-reviewer', secrets.token_urlsafe(24)
    env = dict(os.environ)
    # Let the executable find its own bundled frontend, rather than source dist.
    env.pop('FRONTEND_DIST_DIR', None)
    env.update({
        'DJANGO_DB_PATH': str(output / 'app-data' / 'db.sqlite3'),
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(48), 'DJANGO_DEBUG': 'false',
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1',
        'DEFENSE_SCHEDULER_HOST': '127.0.0.1', 'DEFENSE_SCHEDULER_PORT': str(port),
        'DEFENSE_SCHEDULER_OPEN_BROWSER': 'false',
        'INITIAL_ADMIN_USERNAME': username, 'INITIAL_ADMIN_PASSWORD': password,
    })
    token = None

    def request(path, data=None, *, method=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Token {token}'
        req = urllib.request.Request(base + path, data=body, headers=headers,
            method=method or ('POST' if body is not None else 'GET'))
        with urllib.request.urlopen(req, timeout=180) as response:
            contents = response.read()
            if 'application/json' in response.headers.get('Content-Type', ''):
                result = json.loads(contents)
                if isinstance(result, dict) and 'success' in result and 'data' in result:
                    assert result['success'], result
                    return result['data']
                return result
            return contents

    with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
        process = subprocess.Popen([str(executable)], cwd=output, env=env, stdout=stdout,
            stderr=stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 240
            while True:
                assert process.poll() is None, f'EXE exited; inspect logs under {output}'
                try:
                    home = request('/')
                    assert b'type="module"' in home and b'/assets/' in home
                    break
                except (urllib.error.URLError, TimeoutError):
                    assert time.monotonic() < deadline, f'EXE startup timed out; inspect {output}'
                    time.sleep(1)
            assert b'<svg' in request('/favicon.svg')
            login = request('/api/auth/login/', {'username': username, 'password': password})
            assert login['isAdmin'] is True
            token = login['token']

            # Exercise the real Waitress listener, not Django's in-process test
            # client. Exactly 20 MiB of valid files must reach application code.
            teacher_file = spreadsheet([['姓名', '所在学院', '职称', ''],
                ['上传合成导师', '软件学院', '教授', '组长、组员']])
            student_rows = lambda i: [['学号', '姓名', '导师', '答辩地点'],
                [f'UPLOAD-{i}', f'上传合成学生{i}', '上传合成导师', '创新港']]
            files = [('teacherFile', 'teacher.xlsx', teacher_file)] + [
                ('studentFiles', f'student-{i}.xlsx', spreadsheet(student_rows(i),
                    5 * 1024 * 1024 - (len(teacher_file) if i == 3 else 0)))
                for i in range(4)]
            assert sum(len(content) for _, _, content in files) == 20 * 1024 * 1024

            def upload(files, expected_status, expected_text=None):
                body, content_type = multipart({'preview': 'true', 'defenseTypes': '["中期答辩"]'}, files)
                req = urllib.request.Request(base + '/api/students/import-cohort/', body,
                    {'Content-Type': content_type, 'Authorization': f'Token {token}'})
                try:
                    response = urllib.request.urlopen(req, timeout=90)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    payload = response.read().decode('utf-8')
                    assert response.code == expected_status, (response.code, payload[:1000])
                    if expected_text:
                        assert expected_text in payload, payload[:1000]
                    return json.loads(payload)

            preview = upload(files, 200)
            assert preview['data']['canImport'], preview
            assert request('/api/students/') == [], 'Upload preview must not write students'
            assert request('/api/teachers/') == [], 'Upload preview must not write teachers'
            # Preserve the per-file limit while testing total=20 MiB+1.
            too_large = list(files)
            key, name, content = too_large[-1]
            too_large[-1] = (key, name, content + b'0')
            upload(too_large, 400, '本批文件合计不能超过 20 MB')
            upload([files[0], ('studentFiles', 'oversize.xlsx', b'0' * (5 * 1024 * 1024 + 1))],
                400, '每份文件不能超过 5 MB')
            # Waitress rejects an excessive Content-Length before reading the
            # body. Read that response first: sending the entire rejected body
            # can make Windows abort the client socket before it sees the 413.
            with closing(http.client.HTTPConnection('127.0.0.1', port, timeout=30)) as connection:
                connection.request('POST', '/api/students/import-cohort/', headers={
                    'Content-Length': str(21 * 1024 * 1024 + 1),
                    'Content-Type': 'application/octet-stream',
                    'Authorization': f'Token {token}'})
                response = connection.getresponse()
                assert response.status == 413, (response.status, response.read())
                response.read()

            defaults = request('/api/rule-config/?defense_type=formal')
            assert defaults['policyVersion'] == 2 and defaults['expertCount']['target'] == 5, defaults
            teachers = [request('/api/teachers/', {
                'name': f'EXE教师{i + 1}', 'title': '教授', 'college': '软件学院',
                'roles': ['主席', '组长', '普通专家', '秘书'], 'isSoftwareTeacher': True,
                'availableTypes': ['预答辩', '正式答辩', '中期答辩'],
            }) for i in range(14)]
            for i in range(12):
                student = request('/api/students/', {
                    'name': f'EXE学生{i + 1}', 'studentNo': f'EXE{i + 1:03}',
                    'mentorId': teachers[i]['id'], 'campus': '创新港', 'studentType': '学硕',
                    'defenseTypes': ['预答辩', '正式答辩', '中期答辩'], 'remark': '打包验证备注 <仅文本>',
                })
                assert student['mentorId'] == teachers[i]['id']
            for i in range(2):
                request('/api/rooms/', {'name': f'EXE教室{i + 1}', 'campus': '创新港', 'capacity': 40})
            # Mid-term is a separate cohort workflow; run it before linked
            # generation establishes two different pre-defense secretaries.
            mid = request('/api/schedule/generate/', {'rules': {'defense_type': 'mid',
                'start_date': '2026-10-14', 'end_date': '2026-10-14'},
                'request_key': 'packaged-mid'})
            assert not [c for c in mid['conflicts'] if c['level'] == 'error'], mid['conflicts']
            assert sum(len(g['students']) for g in mid['groups']) == 12
            request('/api/schedule/publish/', {'version_id': mid['versionId'],
                'expected_revision': mid['revision']})
            formal_rules = {'start_date': '2026-10-13', 'end_date': '2026-10-13', 'expert_count': 6}
            linked = request('/api/schedule/generate-linked/', {
                'pre_rules': {'start_date': '2026-10-12', 'end_date': '2026-10-12'},
                'formal_rules': formal_rules,
                'request_key': 'packaged-v2-linked',
            })
            pre, formal = linked['pre'], linked['formal']
            assert formal['sourcePreVersionId'] == pre['versionId']
            mapping = lambda result: {s['id']: (g['groupName'], g['secretaryId'])
                for g in result['groups'] for s in g['students']}
            assert mapping(pre) == mapping(formal)
            assert len(formal['groups']) == 2
            assert not [c for stage in (pre, formal) for c in stage['conflicts'] if c['level'] == 'error']
            assert len({(g['date'], g['timeRange']) for g in formal['groups']}) == 1
            for group in formal['groups']:
                reviewers = {group['chairId'], *[t['id'] for t in group['teachers']]}
                assert len(reviewers) == 6
                mentors = {s['mentorId'] for s in group['students']}
                assert not mentors & reviewers
                peer = next(g for g in formal['groups'] if g['id'] != group['id'])
                assert mentors <= {peer['chairId'], *[t['id'] for t in peer['teachers']]}
            repeated = request('/api/schedule/generate-linked/', {
                'pre_rules': {'start_date': '2026-10-12', 'end_date': '2026-10-12'},
                'formal_rules': formal_rules,
                'request_key': 'packaged-v2-linked',
            })
            assert repeated['formal']['versionId'] == formal['versionId']
            published = request('/api/schedule/publish/', {
                'version_id': formal['versionId'], 'expected_revision': formal['revision'],
            })
            assert published['status'] == 'published'
            for suffix, endpoint, part in (
                ('xlsx', 'export-excel', 'xl/workbook.xml'),
                ('docx', 'export_word', 'word/document.xml'),
            ):
                data = request(f'/api/schedule/{endpoint}/?defense_type=formal&version_id={formal["versionId"]}')
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert part in archive.namelist()
                (output / f'formal-v1.{suffix}').write_bytes(data)

            # More than eight formal groups enters the SciPy/HiGHS exact-cover
            # path. A missing native dependency fails this actual EXE request.
            for student in request('/api/students/'):
                request(f'/api/students/{student["id"]}/', method='DELETE')
            # Ten mentor-only student groups need additional reviewers who do
            # not have students in another session, plus separate secretaries.
            for i in range(10):
                request('/api/teachers/', {'name': f'求解合成专家{i + 1}', 'title': '教授',
                    'college': '软件学院', 'roles': ['主席', '组长', '普通专家', '秘书'],
                    'isSoftwareTeacher': True, 'availableTypes': ['正式答辩']})
            for i in range(60):
                request('/api/students/', {'name': f'求解合成学生{i + 1}',
                    'studentNo': f'SOLVER-{i + 1:03}', 'mentorId': teachers[i // 6]['id'],
                    'campus': '创新港', 'studentType': '学硕', 'defenseTypes': ['正式答辩']})
            large = request('/api/schedule/generate/', {'rules': {'defense_type': 'formal',
                'start_date': '2026-10-19', 'end_date': '2026-10-23',
                'group_size': 6, 'group_min': 6, 'group_max': 6,
                'preserve_pre_defense_groups': False, 'random_seed': 20261026},
                'request_key': 'packaged-scipy-cover'})
            assert len(large['groups']) == 10, len(large['groups'])
            assert not [c for c in large['conflicts'] if c['level'] == 'error'], large['conflicts']
            assert sorted(s['studentNo'] for g in large['groups'] for s in g['students']) == [
                f'SOLVER-{i + 1:03}' for i in range(60)]
            request('/api/schedule/publish/', {'version_id': large['versionId'],
                'expected_revision': large['revision']})
            with sqlite3.connect(output / 'app-data' / 'db.sqlite3') as database:
                assert database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert not list(database.execute('PRAGMA foreign_key_check'))
                assert database.execute("SELECT COUNT(*) FROM django_migrations WHERE app='api' AND name='0009_reference_data_v2'").fetchone()[0] == 1
            result = {'executable': str(source), 'sha256': digest, 'startup_and_bundled_frontend': 'passed',
                'v2_migration_and_policy': 'passed', 'stable_teacher_student_ids': 'passed',
                'linked_same_session_avoidance_and_idempotency': 'passed',
                'publish_excel_word_exports': 'passed', 'database_integrity': 'passed'}
            result['real_http_upload_20mib_and_rejection_boundaries'] = 'passed'
            result['mid_generation_and_publish'] = 'passed'
            result['scipy_native_solver_10_group_formal_generation'] = 'passed'
            (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        finally:
            # PyInstaller onefile starts a child. Stop only this test's process tree.
            if process.poll() is None:
                stop_test_process(process.pid, executable)
                process.wait(timeout=15)
    with socket.socket() as probe:
        probe.settimeout(1)
        assert probe.connect_ex(('127.0.0.1', port)) != 0, 'EXE test port was not released'
    print('PASS packaged V2 executable and isolated process cleanup.', flush=True)


if __name__ == '__main__':
    main()
