"""Check repository documentation links and required collaboration entry points.

Uses only the standard library. Run from any directory with Python 3.12.
Scans tracked and non-ignored untracked Markdown; ignores missing old paths
while a file move is still unstaged. External URLs are not fetched.
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'README.md', 'STATUS.md', 'CONTRIBUTING.md', '.editorconfig', '.gitattributes', '.nvmrc', '.python-version',
    'docs/README.md', 'docs/archive/README.md', 'docs/api/README.md',
    'docs/requirements/README.md', 'docs/requirements/业务规则与验收.md',
    '.github/workflows/ci.yml', '.github/pull_request_template.md',
    '.github/ISSUE_TEMPLATE/task.md', '.github/ISSUE_TEMPLATE/bug.md',
    'tests/fixtures/README.md',
    'tests/fixtures/批量测试_教师_30人.xlsx',
    'tests/fixtures/批量测试_学生_100人.xlsx',
    'tests/fixtures/批量测试_教室_10间.xlsx',
)
FENCED = re.compile(r'^\s*(```|~~~)[^\n]*\n.*?^\s*\1[^\n]*$', re.M | re.S)
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^)\n]*)\)')
HEADING = re.compile(r'^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$', re.M)


def prose(content):
    return FENCED.sub('', content)


def heading_anchors(content):
    anchors = set()
    counts = {}
    for heading in HEADING.findall(prose(content)):
        heading = re.sub(r'!?\[([^]]+)\]\([^)]+\)', r'\1', heading)
        heading = re.sub(r'<[^>]*>', '', heading)
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        anchors.add(f'{slug}-{index}' if index else slug)
    anchors.update(re.findall(r'<(?:a|[a-z][a-z0-9]*)\b[^>]*(?:id|name)=[\"\']([^\"\']+)', content, re.I))
    return anchors


def main():
    errors = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f'Missing entry point or fixture: {relative}')
    for relative in REQUIRED[-3:]:
        ignored = subprocess.run(
            ['git', 'check-ignore', '--no-index', '-q', relative], cwd=ROOT,
            check=False, capture_output=True,
        )
        if ignored.returncode == 0:
            errors.append(f'Fixture is ignored by Git: {relative}')
        elif ignored.returncode != 1:
            errors.append(f'Cannot check Git ignore rules for {relative}')

    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT, check=True, capture_output=True,
    )
    paths = sorted({
        ROOT / name.decode('utf-8') for name in result.stdout.split(b'\0')
        if name and name.decode('utf-8').endswith('.md')
    })
    contents = {}
    checked = 0
    for path in paths:
        if not path.is_file():
            continue
        contents[path] = path.read_text(encoding='utf-8-sig')
        checked += 1
        for match in LINK.finditer(prose(contents[path])):
            raw = match.group(1).strip()
            if raw.startswith('<'):
                raw = raw[1:raw.index('>')]
            else:
                raw = re.split(r'\s+[\"\']', raw, maxsplit=1)[0]
            if not raw:
                continue
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc:
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            location = f'{path.relative_to(ROOT).as_posix()}: {raw}'
            if not target.is_relative_to(ROOT):
                errors.append(f'Link leaves repository: {location}')
            elif not target.exists():
                errors.append(f'Broken local link: {location}')
            elif parsed.fragment and target.suffix.lower() == '.md':
                target_content = contents.setdefault(target, target.read_text(encoding='utf-8-sig'))
                if unquote(parsed.fragment) not in heading_anchors(target_content):
                    errors.append(f'Broken heading anchor: {location}')
    if errors:
        print('\n'.join(errors))
        raise SystemExit(1)
    print(f'Project documents passed: {checked} Markdown files; entry points, fixtures and local links.')


if __name__ == '__main__':
    main()
