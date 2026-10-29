"""Exercise pre-first generation against a running ISOLATED real-data server."""
import argparse
from collections import Counter
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url.rstrip('/') + '/schedule-results')
        page.wait_for_load_state('networkidle')

        def generate(button):
            page.get_by_role('button', name=button, exact=True).click()
            dialog = page.get_by_role('dialog')
            expect(dialog).to_be_visible()
            with page.expect_response(lambda response: '/api/schedule/preflight/' in response.url) as check:
                dialog.get_by_role('button', name='确认生成草稿', exact=True).click()
            assert check.value.status == 200, check.value.text()
            assert check.value.json()['data']['canGenerate']
            # Real legacy data has explicit unconfirmed-time warnings.
            expect(dialog.get_by_role('button', name='继续生成草稿', exact=True)).to_be_visible()
            with page.expect_response(lambda response: '/api/schedule/generate/' in response.url, timeout=240000) as created:
                dialog.get_by_role('button', name='继续生成草稿', exact=True).click()
            assert created.value.status == 200, created.value.text()
            result = created.value.json()['data']
            assert result['allocationStatus'] == 'scheduled'
            assert result['unassignedStudents'] == []
            assert not any(c['level'] == 'error' for c in result['conflicts'])
            assert all(4 <= len(g['students']) <= 7 for g in result['groups'])
            page.wait_for_load_state('networkidle')
            return result

        pre = generate('生成预答辩草稿')
        page.screenshot(path=str(args.output / 'pre.png'), full_page=False)
        page.locator('.el-radio-button').filter(has_text='表格视图').click()
        expect(page.get_by_text('固定组号', exact=True)).to_be_visible()
        expect(page.get_by_text('展示序号', exact=True)).to_have_count(0)
        page.locator('.el-radio-button').filter(has_text='正式答辩').click()
        page.wait_for_load_state('networkidle')
        formal = generate('沿用预答辩生成正式答辩')
        page.screenshot(path=str(args.output / 'formal.png'), full_page=False)
        assert formal['sourcePreVersionId'] == pre['versionId']
        original = {g['groupName']: g for g in pre['groups']}
        assert set(original) == {g['groupName'] for g in formal['groups']}
        for group in formal['groups']:
            source = original[group['groupName']]
            assert {s['id'] for s in source['students']} == {s['id'] for s in group['students']}
            assert source['chairId'] == group['chairId']
            assert source['secretaryId'] == group['secretaryId']
            assert {t['id'] for t in source['teachers']} <= {t['id'] for t in group['teachers']}
        assert not errors, errors
        summary = {stage: {'version': result['versionId'], 'groups': len(result['groups']),
            'students': sum(len(g['students']) for g in result['groups']),
            'sizes': dict(Counter(len(g['students']) for g in result['groups'])),
            'unassigned': len(result['unassignedStudents']),
            'errors': sum(c['level'] == 'error' for c in result['conflicts'])}
            for stage, result in [('pre', pre), ('formal', formal)]}
        summary['page_errors'] = errors
        (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
        browser.close()


if __name__ == '__main__':
    main()
