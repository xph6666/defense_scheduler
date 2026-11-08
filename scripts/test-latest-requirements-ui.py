"""Run against scripts/latest-requirements-ui-server.py's disposable DB."""
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8769'
OUT = Path(__file__).resolve().parents[1] / '.tmp'


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    login = page.request.post(BASE + '/api/auth/login/', data={
        'username': 'ui-reviewer', 'password': 'Ui-Review-Only-4926'}).json()['data']
    headers = {'Authorization': 'Token ' + login['token']}
    page.add_init_script('localStorage.setItem("authToken", ' + repr(login['token']) + ');'
        'localStorage.setItem("username", "ui-reviewer"); localStorage.setItem("isAdmin", "true");')

    def api(path, data=None, method='post'):
        response = getattr(page.request, method)(BASE + '/api/' + path, headers=headers, **({'data': data} if data is not None else {}))
        assert response.ok, response.text()
        return response.json()['data']

    for teacher in api('teachers/', method='get'):
        api(f'teachers/{teacher["id"]}/', {'availabilityConfirmed': True}, 'patch')
    for i in range(6):
        api('teachers/', {'name': f'轮换教师{i}', 'title': '教授', 'roles': ['普通专家'], 'availabilityConfirmed': True})
    for campus, count in [('创新港', 4), ('兴庆', 6)]:
        for i in range(count):
            api('students/', {'name': f'{campus}流程学生{i}', 'studentNo': f'LATEST-{campus}-{i}',
                'campus': campus, 'mentorName': '测试教师1', 'defenseTypes': ['预答辩', '正式答辩']})
    for stage, start, end in [('pre', '2026-11-02', '2026-11-03'), ('formal', '2026-11-04', '2026-11-05')]:
        config = api('rule-config/?defense_type=' + stage, method='get')
        api('rule-config/', {**config, 'defense_type': stage, 'startDate': start, 'endDate': end, 'avoidHoliday': False})

    progress = []
    def record(response):
        if '/generation-progress/' in response.url and response.ok:
            progress.append(response.json()['data'])
    page.on('response', record)
    page.goto(BASE + '/schedule-results?type=' + quote('预答辩'))
    page.wait_for_load_state('networkidle')
    expect(page.get_by_role('radiogroup', name='选择排期校区批次')).to_be_visible()
    page.get_by_role('button', name='生成预答辩草稿', exact=True).click()
    dialog = page.get_by_role('dialog', name='创新港 · 生成前确认')
    expect(dialog).to_be_visible()
    with page.expect_response(lambda response: '/schedule/generate/' in response.url and response.request.method == 'POST', timeout=30000) as generated:
        dialog.get_by_role('button', name='确认生成草稿', exact=True).click()
        expect(page.locator('.generation-progress-card')).to_be_visible()
        expect(page.locator('.generation-progress-card')).to_contain_text('编排阶段进度')
        expect(page.locator('.generation-progress-card').get_by_role('progressbar')).to_be_visible()
        expect(page.locator('.generation-progress-card')).to_contain_text('正在求解')
        page.screenshot(path=str(OUT / 'latest-progress.png'), full_page=True, animations='disabled')
    assert generated.value.ok, generated.value.text()
    pre = generated.value.json()['data']
    expect(page.get_by_role('button', name='查看两阶段学生去向')).to_be_visible()
    assert any(item['stage'] == 'solving' for item in progress), progress
    assert all(item['percent'] < 100 for item in progress if item['status'] == 'running')

    formal = api('schedule/generate/', {'rules': dict(policy_version=4, defense_type='formal',
        campus_scope='创新港', start_date='2026-11-04', end_date='2026-11-05'), 'request_key': 'ui-formal'})
    assert formal['sourcePreVersionId'] == pre['versionId']
    page.get_by_role('button', name='查看两阶段学生去向').click()
    mapping = page.get_by_role('dialog', name='预答辩 ↔ 正式答辩 · 学生去向')
    expect(mapping).to_contain_text('已关联 6')
    expect(mapping.locator('.el-table').first).to_be_visible()
    page.screenshot(path=str(OUT / 'latest-stage-mapping.png'), full_page=True, animations='disabled')
    mapping.get_by_role('button', name='关闭', exact=True).click()
    page.get_by_role('radiogroup', name='选择排期校区批次').get_by_text('兴庆', exact=True).click()
    expect(page.get_by_role('button', name='查看两阶段学生去向')).to_have_count(0)
    expect(page.get_by_text('总组数：').locator('..')).to_contain_text('0')

    page.goto(BASE + '/teachers')
    page.wait_for_load_state('networkidle')
    page.get_by_role('button', name='导入课表', exact=True).click()
    timetable = page.get_by_role('dialog', name='导入课表（生成教师不可用时间）')
    with page.expect_download() as downloaded:
        timetable.get_by_role('button', name='下载模板与教师编号目录').click()
    assert downloaded.value.suggested_filename.endswith('.xlsx')
    date_input = timetable.get_by_placeholder('选择第一教学周的周一')
    date_input.fill('2026-11-02'); date_input.press('Enter')
    timetable.locator('input[type=file]').set_input_files({
        'name': '课表.csv', 'mimeType': 'text/csv',
        'buffer': '主讲教师,时间地点\n测试教师1,第1-4周 单周 星期一 上1\n张乙,第1-2周 星期二 下5\n测试教师2,无法解析\n'.encode('utf-8')})
    timetable.get_by_role('button', name='解析并预览', exact=True).click()
    expect(timetable).to_contain_text('时间无法解析')
    expect(timetable).to_contain_text('张乙')
    expect(timetable.get_by_role('button', name='确认导入有效记录')).to_be_enabled()
    page.screenshot(path=str(OUT / 'latest-timetable-preview.png'), full_page=True, animations='disabled')
    with page.expect_response(lambda response: '/import_timetable/' in response.url and response.request.method == 'POST') as confirmed:
        timetable.get_by_role('button', name='确认导入有效记录').click()
    assert confirmed.value.ok, confirmed.value.text()
    assert confirmed.value.json()['data']['updatedTeachers'] == 1
    timetable.get_by_role('button', name='关闭', exact=True).click()
    page.get_by_role('button', name='导入课表', exact=True).click()
    timetable.get_by_role('button', name='解析并预览', exact=True).click()
    expect(page.get_by_text('请先选择课表文件', exact=True)).to_be_visible()
    assert not errors, errors
    browser.close()
    print('Browser flows passed: actual solving progress, campus selection, live stage mapping, template download, timetable preview and confirmation.')
