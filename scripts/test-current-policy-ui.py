"""Current rules UI against the isolated ui-fixture-server, never the business DB."""
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8769'
OUT = Path(__file__).resolve().parents[1] / '.tmp'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    login = page.request.post(BASE + '/api/auth/login/', data={
        'username': 'ui-reviewer', 'password': 'Ui-Review-Only-4926'}).json()['data']
    page.add_init_script('localStorage.setItem("authToken", ' + repr(login['token']) + ');'
        'localStorage.setItem("username", "ui-reviewer"); localStorage.setItem("isAdmin", "true");')
    page.goto(BASE + '/rule-config?type=' + quote('中期答辩'))
    page.wait_for_load_state('networkidle')
    form = page.locator('.rule-config-form')
    expect(form).to_be_visible()
    students = form.locator('.el-form-item').filter(has_text='每组学生总人数目标').get_by_role('spinbutton')
    experts = form.locator('.el-form-item').filter(has_text='专家人数（含组长）').get_by_role('spinbutton')
    expect(students).to_have_value('10')
    expect(students).to_be_disabled()
    expect(experts).to_have_value('5')
    expect(experts).to_be_disabled()
    expect(form).to_contain_text('导师不回避')
    form.locator('.advanced-rules summary').click()
    expect(form).to_contain_text('导师可评审自己的学生')
    with page.expect_response(lambda response: '/api/rule-config/' in response.url and response.request.method == 'POST') as saved:
        form.get_by_role('button', name='保存要求', exact=True).click()
    assert saved.value.ok, saved.value.text()
    config = saved.value.json()['data']
    assert config['policyVersion'] == 4
    assert config['studentCount'] == dict(target=10, min=10, max=10)
    OUT.mkdir(exist_ok=True)
    page.screenshot(path=str(OUT / 'policy-mid.png'), full_page=True)

    page.goto(BASE + '/rule-config?type=' + quote('预答辩'))
    page.wait_for_load_state('networkidle')
    form.locator('.advanced-rules summary').click()
    leader = form.locator('.el-form-item').filter(has_text='组长最低职称').locator('.el-select')
    leader.click()
    expect(page.get_by_role('option', name='教授', exact=True)).to_be_visible()
    expect(page.get_by_role('option', name='副教授', exact=True)).to_have_count(0)
    page.keyboard.press('Escape')
    expect(form).to_contain_text('尽量使外院少于本院')
    expect(form).to_contain_text('创新港与兴庆分开编排')
    page.screenshot(path=str(OUT / 'policy-pre.png'), full_page=True)

    headers = {'Authorization': 'Token ' + login['token']}
    for i in range(4):
        response = page.request.post(BASE + '/api/students/', headers=headers, data={
            'name': f'平移学生{i}', 'studentNo': f'POLICY{i}', 'studentType': '学硕',
            'mentorName': '测试教师1', 'campus': '创新港', 'defenseTypes': ['预答辩', '正式答辩']})
        assert response.ok, response.text()
    for i in range(6):
        response = page.request.post(BASE + '/api/teachers/', headers=headers, data={
            'name': f'轮换教师{i}', 'title': '教授', 'roles': ['普通专家'],
            'availabilityConfirmed': True, 'availableTypes': ['预答辩', '正式答辩']})
        assert response.ok, response.text()
    response = page.request.post(BASE + '/api/schedule/generate-linked/', headers=headers, data={
        'pre_rules': dict(policy_version=4, campus_scope='创新港', start_date='2026-11-02', end_date='2026-11-02'),
        'formal_rules': dict(policy_version=4, campus_scope='创新港', start_date='2026-11-04', end_date='2026-11-05')})
    assert response.ok, response.text()
    formal = response.json()['data']['formal']
    assert len(formal['groups']) == 1, formal
    assert formal['unassignedStudents'] == [], formal
    page.goto(BASE + '/schedule-results?type=' + quote('正式答辩'))
    page.wait_for_load_state('networkidle')
    expect(page.get_by_text('关联预答辩 v1', exact=False)).to_be_visible()
    page.screenshot(path=str(OUT / 'policy-formal-mapping.png'), full_page=True)
    assert not errors, errors
    browser.close()
    print('Current policy UI passed: fixed mid counts and saved policy 4; pre senior chair; actual linked generation and formal source mapping.')
