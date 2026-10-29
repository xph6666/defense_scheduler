"""Deterministic synthetic benchmark. No Django, database, or browser access."""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from algorithm import generate_schedule, parse_time_range


def verify(result, cohort, expert_count, stage):
    """Independently check coverage, headcount, affiliation and attendance overlap."""
    assigned = [sid for group in result['groups'] for sid in group['student_ids']]
    pending = [student['id'] for student in result['unassigned_students']]
    assert sorted(assigned + pending) == [s['id'] for s in cohort]
    assert len(assigned) == len(set(assigned))
    students = {s['id']: s for s in cohort}
    attendance = []
    for group in result['groups']:
        reviewers = {group['chair_id'], *group['expert_ids']}
        assert len(reviewers) == expert_count
        assert group['chair_id'] not in group['expert_ids']
        assert group['secretary_id'] not in reviewers
        assert group['room_id'] is None
        mentors = {students[sid]['supervisor_id'] for sid in group['student_ids']}
        assert group['secretary_id'] not in mentors
        assert mentors <= reviewers if stage == 'pre' else not mentors & reviewers
        assert sum(tid > 25 for tid in reviewers) <= 1
        slot = parse_time_range(group['time'])
        people = reviewers | mentors | {group['secretary_id']}
        assert all(not slot.overlaps(other) or not people & occupied for other, occupied in attendance)
        attendance.append((slot, people))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--students', nargs='+', type=int, default=[100, 300])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if any(not 1 <= count <= 3000 for count in args.students):
        parser.error('students must be between 1 and 3000')
    staff = [{'id': i, 'name': f'T{i}', 'title': '教授', 'roles': ['组长', '专家', '秘书'],
              'availability_confirmed': True, 'is_external': i > 25} for i in range(1, 36)]
    rows = []
    for size in args.students:
        cohort = [{'id': i, 'name': f'S{i}', 'supervisor_id': (i - 1) % 25 + 1,
                   'campus': '创新港'} for i in range(1, size + 1)]
        for stage in ('pre', 'formal'):
            for experts in (3, 5):
                start = date(2026, 11, 2)
                rules = {'policy_version': 3, 'defense_type': stage,
                    'start_date': start.isoformat(), 'end_date': (start + timedelta(days=27)).isoformat(),
                    'group_size': 6, 'group_min': 1, 'group_max': 6, 'expert_count': experts,
                    'expert_min': experts, 'need_chair': True, 'chair_title': '教授',
                    'secretary_title': '讲师', 'avoid_weekend': True, 'avoid_supervisor': stage == 'formal'}
                began = perf_counter()
                result = generate_schedule(staff, cohort, [], rules)
                elapsed = perf_counter() - began
                verify(result, cohort, experts, stage)
                row = {'students': size, 'teachers': len(staff), 'stage': stage, 'experts': experts,
                       'elapsed_seconds': round(elapsed, 4), 'groups': len(result['groups']),
                       'unassigned': len(result['unassigned_students']), 'independent_checks': 'passed',
                       **result['diagnostics']}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'date_range': ['2026-11-02', '2026-11-29'], 'synthetic': True, 'cases': rows}
    root = Path(__file__).resolve().parents[1]
    report['code_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ('algorithm.py', 'scheduling/personnel_first.py', 'scheduling/current.py',
                     'scheduling/policies.py', 'scripts/benchmark-personnel.py')}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
