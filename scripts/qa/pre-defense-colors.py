"""Read-only UI checks for teacher colors and explained pre-defense exceptions."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.mentor_colors import _lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1600, 'height': 1200})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url.rstrip('/') + '/schedule-results')
        page.wait_for_load_state('networkidle')
        response = page.request.get(args.url.rstrip('/') + '/api/schedule/current/?defense_type=pre')
        assert response.ok
        data = response.json()['data']
        assert data['rules']['expert_count'] == 3 and data['allocationStatus'] == 'scheduled'
        assert not data['unassignedStudents']
        page.locator('.el-radio-button').filter(has_text='卡片视图').click()
        expect(page.locator('[data-group-name]')).to_have_count(len(data['groups']))
        def collect():
            return page.locator('[data-group-name]').evaluate_all('''cards => cards.map(card => ({
              group: card.dataset.groupName, kind: card.querySelector('[data-share-kind]')?.dataset.shareKind,
              tags: [...card.querySelectorAll('[data-mentor]')].map(tag => ({mentor:tag.dataset.mentor,
              background:getComputedStyle(tag).backgroundColor, color:getComputedStyle(tag).color}))}))''')
        cards = collect()
        global_colors = defaultdict(set)
        minimum_gap = 1e6
        for card in cards:
            unique = {}
            for tag in card['tags']:
                if tag['mentor'] in unique:
                    assert unique[tag['mentor']] == tag['background'], 'teacher/student colors differ'
                unique[tag['mentor']] = tag['background']
                global_colors[tag['mentor']].add(tag['background'])
            names = list(unique)
            assert len(set(unique.values())) == len(names), card
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    def lab(rgb):
                        return _lab(''.join(f'{int(v):02X}' for v in re.findall(r'\d+', rgb)[:3]))
                    gap = sum((x - y) ** 2 for x, y in zip(lab(unique[a]), lab(unique[b]))) ** .5
                    minimum_gap = min(minimum_gap, gap)
                    assert gap >= 20 - 1e-5, (card['group'], a, b, gap)
        for name in ('G009', 'G010'):
            card = page.locator(f'[data-group-name="{name}"]')
            expect(card.locator('[data-share-kind="explained"]')).to_be_visible()
            expect(card.get_by_text('按“六人为主”保留 3＋2＋1。', exact=False)).to_be_visible()
            card.scroll_into_view_if_needed()
            card.screenshot(path=str(args.output / f'{name}-导师分色.png'))
        first_date = sorted({g['date'] for g in data['groups'] if g.get('date')})[0]
        date_filter = page.locator('.el-select').filter(has=page.get_by_role('combobox', name='按日期筛选', exact=True))
        date_filter.click()
        page.get_by_role('option', name=first_date, exact=True).click()
        for card in collect():
            for tag in card['tags']:
                assert tag['background'] in global_colors[tag['mentor']], 'filtering changed a teacher color'
        assert not errors, errors
        summary = {'version': data['versionId'], 'groups_checked': len(cards), 'min_same_group_delta_e': round(minimum_gap, 2),
                   'teachers_with_local_color_overrides': sum(len(colors) > 1 for colors in global_colors.values()),
                   'explained_groups': sum(card.get('kind') == 'explained' for card in cards),
                   'remaining_imbalance_groups': sum(card.get('kind') == 'unbalanced' for card in cards), 'page_errors': errors}
        (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(summary))
        browser.close()


if __name__ == '__main__':
    main()
