"""V2 UI smoke test. Build first, then run: python scripts/test-v2-ui.py --run

The direct subprocess runner also cleans up correctly on Windows (no intermediary shell).
The server uses a disposable database under .tmp and never opens the business database.
"""
import os
import sys
import tempfile
import json
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp' / 'v2-ui'
OUT.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get('V2_UI_PORT', '8791'))
BASE = f'http://127.0.0.1:{PORT}'
USERNAME = 'v2-ui-reviewer'
PASSWORD = 'V2-Fixture-Only-4926'


def serve_fixture():
    sys.path.insert(0, str(ROOT))
    data_dir = tempfile.TemporaryDirectory(prefix='fixture-', dir=OUT)
    os.environ.update({
        'DJANGO_DB_PATH': str(Path(data_dir.name) / 'ui.sqlite3'),
        'DJANGO_SETTINGS_MODULE': 'defense_scheduler.settings',
        'DJANGO_SECRET_KEY': 'isolated-v2-ui-fixture-only-' * 4,
        'DJANGO_ENV': 'local',
    })
    import django
    django.setup()
    from django.core.management import call_command
    from django.contrib.auth.models import User
    from api.models import Teacher, Student, Room, RuleConfig
    from scheduling.policies import scenario_policy
    call_command('migrate', verbosity=0)
    User.objects.create_user(username=USERNAME, password=PASSWORD, is_staff=True)
    teachers = [Teacher.objects.create(
        name=f'V2教师{i + 1}', title='教授', college='软件学院', is_software_teacher=True,
        roles=['普通专家', '主席', '组长', '秘书'],
        available_types=['预答辩', '正式答辩', '中期答辩'],
    ) for i in range(14)]
    for index in range(12):
        mentor = teachers[index // 6]
        Student.objects.create(
            name=f'V2学生{index + 1}', student_no=f'V2UI{index + 1:03}',
            mentor=mentor, mentor_name=mentor.name, campus='创新港',
            defense_types=['预答辩', '正式答辩', '中期答辩'],
            remark='PDF 学生备注 <仅文本>' if index == 0 else '',
        )
    for index in range(2):
        Room.objects.create(campus='创新港', name=f'V2教室{index + 1}', capacity=40)
    for kind, date in [('pre', '2026-10-12'), ('formal', '2026-10-13'), ('mid', '2026-10-14')]:
        config = scenario_policy(kind)
        config.update(startDate=date, endDate=date, policyVersion=2)
        RuleConfig.objects.create(defense_type=kind, config=config)
    from django.core.wsgi import get_wsgi_application
    from waitress import serve
    serve(get_wsgi_application(), host='127.0.0.1', port=PORT, threads=4)


def smoke_test():
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1050})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)

        def api(path):
            token = page.evaluate("localStorage.getItem('authToken')")
            response = page.request.get(BASE + '/api/' + path, headers={'Authorization': f'Token {token}'})
            assert response.ok, (response.status, response.text())
            body = response.json()
            return body.get('data', body)

        def current(kind, version_id=None):
            return api(f'schedule/current/?defense_type={kind}' + (f'&version_id={version_id}' if version_id else ''))

        def choose_option(select, name):
            select.click()
            page.get_by_role('option', name=name, exact=True).click()

        def move_student(choice_label, target_name, secretary_name=None):
            page.get_by_role('button', name='移动学生', exact=True).click()
            dialog = page.get_by_role('dialog', name='移动学生', exact=True)
            expect(dialog.get_by_role('checkbox', name='保留该学生的秘书关系')).to_be_checked()
            choose_option(dialog.locator('.el-select').nth(0), choice_label)
            choose_option(dialog.locator('.el-select').nth(1), target_name)
            if secretary_name:
                dialog.locator('.el-checkbox').filter(has_text='保留该学生的秘书关系').click()
                expect(dialog.get_by_role('checkbox', name='保留该学生的秘书关系')).not_to_be_checked()
                choose_option(dialog.locator('.el-select').nth(2), secretary_name)
            with page.expect_response(lambda response: '/api/schedule/adjust/' in response.url and response.request.method == 'POST') as response:
                dialog.get_by_role('button', name='确认移动', exact=True).click()
            assert response.value.ok, response.value.text()
            expect(dialog).not_to_be_visible()
            page.wait_for_load_state('networkidle')

        try:
            page.goto(BASE + '/login')
            page.get_by_placeholder('请输入账号').fill(USERNAME)
            page.get_by_placeholder('请输入密码').fill(PASSWORD)
            page.get_by_role('button', name='登录', exact=True).click()
            page.wait_for_url('**/dashboard')
            page.wait_for_load_state('networkidle')
            page.goto(BASE + '/teachers')
            page.wait_for_load_state('networkidle')
            page.get_by_role('button', name='编辑', exact=True).first.click()
            teacher_dialog = page.get_by_role('dialog', name='编辑教师', exact=True)
            expect(teacher_dialog.get_by_text('适合担任组员', exact=True)).to_be_visible()
            expect(teacher_dialog.get_by_text('计为软件学院导师', exact=True)).to_be_visible()
            teacher_dialog.get_by_role('button', name='取消', exact=True).click()
            page.goto(BASE + '/students')
            page.wait_for_load_state('networkidle')
            page.get_by_role('button', name='编辑', exact=True).first.click()
            student_dialog = page.get_by_role('dialog', name='编辑学生', exact=True)
            expect(student_dialog.locator('.el-select').filter(has_text='V2教师1').first).to_be_visible()
            student_dialog.get_by_role('button', name='取消', exact=True).click()

            page.goto(BASE + '/rule-config?type=正式答辩')
            page.wait_for_load_state('networkidle')
            expert_input = page.locator('.rule-config-form .el-form-item').filter(has_text='专家总人数').get_by_role('spinbutton')
            expect(expert_input).to_have_value('5')
            expect(expert_input).to_be_disabled()
            expect(page.get_by_text('正式答辩固定 5 位专家（主席 1 位、组员 4 位）；主席/组长计入专家总数，秘书单独 1 人。', exact=True)).to_be_visible()

            page.goto(BASE + '/schedule-results?type=预答辩')
            page.wait_for_load_state('networkidle')
            page.get_by_role('button', name='生成排期草稿', exact=True).click()
            preview = page.get_by_role('dialog', name='生成前，确认这次安排', exact=True)
            expect(preview).to_contain_text('专家 4 人')
            preview.get_by_role('button', name='确认生成草稿', exact=True).click()
            expect(page.get_by_role('button', name='校验并发布', exact=True)).to_be_enabled(timeout=60000)
            generated_pre = current('pre')
            assert len(generated_pre['groups']) == 2, generated_pre
            assert not [conflict for conflict in generated_pre['conflicts'] if conflict['level'] == 'error'], generated_pre['conflicts']
            assert all(len({group['chairId'], *[teacher['id'] for teacher in group['teachers']]}) == 4 for group in generated_pre['groups'])
            page.get_by_role('button', name='校验并发布', exact=True).click()
            expect(page.get_by_text('已发布 · 内容已锁定', exact=True)).to_be_visible()
            published_pre = current('pre')
            assert published_pre['status'] == 'published'
            page.screenshot(path=str(OUT / 'pre-published.png'), full_page=True)

            page.get_by_role('button', name='联合生成预答辩与正式答辩', exact=True).click()
            linked_dialog = page.get_by_role('dialog', name='联合生成两阶段答辩安排', exact=True)
            expect(linked_dialog).to_contain_text('专家 5 人')
            with page.expect_response(lambda response: '/api/schedule/generate-linked/' in response.url and response.request.method == 'POST') as linked_response:
                linked_dialog.get_by_role('button', name='确认联合生成', exact=True).click()
            linked_http = linked_response.value
            expect(page.get_by_role('button', name='校验并发布', exact=True)).to_be_enabled(timeout=60000)
            linked_pre = current('pre')
            formal = current('formal')
            (OUT / 'generated-linked.json').write_text(json.dumps({'pre': linked_pre, 'formal': formal}, ensure_ascii=False, indent=2), encoding='utf-8')
            evidence_dir = ROOT / '.tmp' / 'architecture-v2'
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / 'ui-linked-failure.json').write_text(json.dumps({
                'request': linked_http.request.post_data_json,
                'response': linked_http.json(), 'currentPre': linked_pre, 'currentFormal': formal,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            assert len(formal['groups']) == 2
            assert not [conflict for conflict in formal['conflicts'] if conflict['level'] == 'error'], formal['conflicts']
            mapping = lambda result: {student['id']: (group['groupName'], group['secretaryId']) for group in result['groups'] for student in group['students']}
            assert mapping(linked_pre) == mapping(formal)
            assert len({(group['date'], group['timeRange']) for group in formal['groups']}) == 1
            for group in formal['groups']:
                reviewers = {group['chairId'], *[teacher['id'] for teacher in group['teachers']]}
                assert len(reviewers) == 5
                own_mentors = {student['mentorId'] for student in group['students']}
                assert not own_mentors & reviewers
                other = next(candidate for candidate in formal['groups'] if candidate['id'] != group['id'])
                assert own_mentors <= {other['chairId'], *[teacher['id'] for teacher in other['teachers']]}

            page.goto(BASE + '/schedule-results?type=正式答辩')
            page.wait_for_load_state('networkidle')
            source, target = formal['groups']
            student = source['students'][0]
            move_student(f"{student['name']}（{source['groupName']}）", target['groupName'])
            moved = current('formal')
            moved_student = next(item for group in moved['groups'] for item in group['students'] if item['id'] == student['id'])
            assert moved_student['secretaryId'] == student['secretaryId']
            assert any('秘书' in conflict['type'] for conflict in moved['conflicts']), moved['conflicts']
            move_student(f"{student['name']}（{target['groupName']}）", source['groupName'], source['secretary'])
            restored = current('formal')
            restored_student = next(item for group in restored['groups'] for item in group['students'] if item['id'] == student['id'])
            assert restored_student['secretaryId'] == source['secretaryId']
            assert not any('秘书连续性' in conflict['type'] for conflict in restored['conflicts'])
            page.screenshot(path=str(OUT / 'formal-linked.png'), full_page=True)

            page.goto(BASE + '/schedule-results?type=预答辩')
            page.wait_for_load_state('networkidle')
            page.get_by_text('当前版本（下拉可查看历史）', exact=True).click()
            page.get_by_role('option', name='v1 · 已发布', exact=True).click()
            page.wait_for_load_state('networkidle')
            page.get_by_role('button', name='导出 Excel/Word/PDF', exact=True).click()
            export_dialog = page.get_by_role('dialog', name='导出确认', exact=True)
            export_dialog.locator('.el-radio').filter(has_text='PDF · 打印或保存为 PDF').click()
            with page.expect_popup() as popup_event:
                export_dialog.get_by_role('button', name='继续导出', exact=True).click()
            popup = popup_event.value
            popup.on('pageerror', lambda error: errors.append(str(error)))
            expect(popup.get_by_role('button', name='打印或保存为 PDF', exact=True)).to_be_visible()
            expect(popup.locator('.meta')).to_contain_text('版本 1 · 已发布')
            expect(popup.locator('.group')).to_have_count(2)
            expect(popup.locator('body')).to_contain_text('共 4 人')
            expect(popup.locator('body')).to_contain_text('PDF 学生备注 <仅文本>')
            assert popup.locator('img,script').count() == 0
            popup.evaluate('window.print = () => { window.__printRequested = true }')
            popup.get_by_role('button', name='打印或保存为 PDF', exact=True).click()
            assert popup.evaluate('window.__printRequested === true')
            popup.pdf(path=str(OUT / 'pre-published.pdf'), print_background=True, prefer_css_page_size=True)
            assert (OUT / 'pre-published.pdf').stat().st_size > 1000
            popup.close()

            mid_preview = context.new_page()
            mid_preview.goto((OUT / 'mid-print.html').as_uri())
            expect(mid_preview.locator('h2')).to_have_css('color', 'rgb(255, 255, 255)')
            expect(mid_preview.locator('h2')).to_have_css('background-color', 'rgb(46, 117, 182)')
            mid_preview.screenshot(path=str(OUT / 'mid-print.png'), full_page=True)
            mid_preview.close()

            page.goto(BASE + '/schedule-wizard?step=1&type=中期答辩')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.wait_for_load_state('networkidle')
            expect(page.get_by_role('heading', name='先选本次答辩类型')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUT / 'mobile-wizard.png'), full_page=True)
            assert not errors, errors
            print('PASS V2 UI: resource flags and stable relations; fixed five-reviewer policy; pre generation/publish; linked groups and formal same-session mentors; default secretary retention and explicit rebind; historical PDF preview/print with student remarks; mobile; zero browser errors.', flush=True)
        except Exception:
            page.screenshot(path=str(OUT / 'failure.png'), full_page=True)
            print('BROWSER ERRORS:', errors, flush=True)
            raise
        finally:
            browser.close()


def run_with_fixture():
    def listening():
        with socket.socket() as sock:
            sock.settimeout(1)
            return sock.connect_ex(('127.0.0.1', PORT)) == 0

    if listening():
        raise RuntimeError(f'Test port {PORT} is already occupied; choose a different V2_UI_PORT.')
    subprocess.run(['node', 'scripts/test-frontend-domain.cjs', '--print-fixture'], cwd=ROOT, check=True)
    with (OUT / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), '--serve'],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        try:
            deadline = time.monotonic() + 40
            while not listening():
                if process.poll() is not None:
                    raise RuntimeError(f'Fixture server exited with {process.returncode}; see {OUT / "server.log"}')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Fixture server did not become ready within 40 seconds')
                time.sleep(0.2)
            smoke_test()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    assert not listening(), 'fixture server must release its port when the test finishes'
    print('PASS fixture lifecycle: direct child stopped and test port released.', flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    if '--serve' in sys.argv:
        serve_fixture()
    elif '--run' in sys.argv:
        run_with_fixture()
    else:
        smoke_test()
