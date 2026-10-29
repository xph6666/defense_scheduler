"""Read and inspect only the current pre-defense page; never generate another stage."""
import argparse
import json
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1600, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url.rstrip('/') + '/schedule-results')
        page.wait_for_load_state('networkidle')
        response = page.request.get(args.url.rstrip('/') + '/api/schedule/current/?defense_type=pre')
        assert response.ok
        data = response.json()['data']
        assert data['defenseType'] == '预答辩' and data['rules']['expert_count'] == 3
        assert not data['unassignedStudents']
        assert not [c for c in data['conflicts'] if c['level'] == 'error']
        groups = data['groups']
        assigned = [student['id'] for group in groups for student in group['students']]
        assert len(assigned) == len(set(assigned)) == data['totalStudents']
        assert all(5 <= len(group['students']) <= 7 for group in groups)
        page.locator('.el-radio-button').filter(has_text='卡片视图').click()
        expect(page.get_by_text('G001', exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / '预答辩概览.png'), full_page=False)
        warnings = [c for c in data['conflicts'] if c['type'] == '组内导师学生数不均衡']
        if warnings:
            warning = warnings[0]
            ids = warning.get('relatedGroupIds') or [warning.get('groupId')]
            group = next(group for group in groups if group['id'] in ids)
            card = page.locator('.el-card').filter(has=page.get_by_text(group['groupName'], exact=True)).first
            card.scroll_into_view_if_needed()
            # A skewed panel must not retain the "normal" badge.
            expect(card.get_by_text('正常', exact=True)).to_have_count(0)
            page.screenshot(path=str(args.output / '预答辩不均衡提示.png'), full_page=False)
        assert not errors, errors
        summary = {'version': data['versionId'], 'experts': 3, 'assigned': len(assigned),
                   'unassigned': 0, 'hard_errors': 0, 'groups': len(groups),
                   'sizes': dict(Counter(len(g['students']) for g in groups)),
                   'imbalance_warnings': len(warnings), 'page_errors': errors}
        (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(summary, ensure_ascii=True))
        browser.close()


if __name__ == '__main__':
    main()
