"""Read saved input snapshots without mutating the database; verify both stages."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from algorithm import generate_schedule, GroupDraft, parse_teacher, parse_student, parse_time_range
from scheduling.translation import translate_panels


def verify(result, payload, rules):
    students = {s['id']: s for s in payload['students']}
    teachers = {t['id']: t for t in payload['teachers']}
    covered, visits, loads = [], defaultdict(list), Counter()
    for group in result['groups']:
        ids = group['student_ids']
        reviewers = {group['chair_id'], *group['expert_ids']}
        assert len(reviewers) == rules['expert_count']
        assert group['secretary_id'] not in reviewers
        assert rules['group_min'] <= len(ids) <= rules['group_max']
        assert sum(teachers[t]['is_external'] for t in reviewers) <= rules.get('external_expert_max', 1)
        mentors = {students[s]['supervisor_id'] for s in ids}
        assert mentors <= reviewers
        if sum(teachers[t]['is_external'] for t in reviewers) > 1:
            assert all(t in mentors for t in reviewers if teachers[t]['is_external'])
        assert group['secretary_id'] not in mentors
        slot = parse_time_range(group['time'])
        people = reviewers | {group['secretary_id']}
        for tid in people:
            teacher = teachers[tid]
            assert teacher.get('is_active', True) and not teacher.get('availability_invalid')
            assert teacher.get('availability_confirmed') or teacher.get('availability_assumed')
            assert not set(teacher.get('forbidden_with', [])) & (people - {tid})
            assert not any(slot.overlaps(parse_time_range(t)) for t in teacher.get('available_time', []))
            if teacher.get('availability_restricted'):
                assert any(parse_time_range(t).start <= slot.start and slot.end <= parse_time_range(t).end
                           for t in teacher.get('available_windows', []))
            assert not any(slot.overlaps(t) for t in visits[tid])
            visits[tid].append(slot)
            loads[tid] += len(ids)
        covered.extend(ids)
    assert len(covered) == len(set(covered))
    assert sorted(covered + [s['id'] for s in result['unassigned_students']]) == sorted(students)
    return {'groups': len(result['groups']), 'students': len(covered),
            'unassigned': len(result['unassigned_students']),
            'sizes': dict(sorted(Counter(len(g['student_ids']) for g in result['groups']).items())),
            'two_external_panels': sum(sum(teachers[t]['is_external'] for t in {g['chair_id'], *g['expert_ids']}) > 1
                                       for g in result['groups']),
            'time_assumptions': sum(bool(t.get('availability_assumed')) for t in teachers.values()),
            'independent_checks': 'passed',
            'workloads': [{'id': tid, 'appearances': len(visits[tid]), 'students': loads[tid],
                'days': len({t.start.date() for t in visits[tid]}),
                'paired_days': sum({t.start.hour >= 12 for t in visits[tid] if t.start.date() == day} == {False, True}
                    for day in {t.start.date() for t in visits[tid]})}
                for tid in sorted(teachers)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-saved', action='store_true', help='Read saved current groups without generating or writing a draft')
    parser.add_argument('--group-min', type=int, choices=(4, 5), default=5,
                        help='Use 5 for new schedules; 4 is retained for historical reproduction')
    parser.add_argument('--expert-count', type=int, choices=(3, 5),
                        help='Override pre-defense committee size for a read-only scenario comparison')
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        snapshots = {stage: (json.loads(rules), json.loads(payload)) for stage, rules, payload
                     in connection.execute('SELECT defense_type, rules_snapshot, input_snapshot '
                                           'FROM api_scheduleversion WHERE is_current=1')}
        if args.verify_saved:
            panels, summary = {}, {}
            for stage, (rules, payload) in snapshots.items():
                if stage not in ('pre', 'formal'):
                    continue
                assert rules['group_min'] >= 4 and rules['group_max'] <= 7
                version = connection.execute('SELECT id FROM api_scheduleversion WHERE defense_type=? AND is_current=1', (stage,)).fetchone()[0]
                groups = []
                for gid, name, campus, when, chair, secretary in connection.execute(
                        'SELECT id,group_id,campus,time,chair_id,secretary_id FROM api_group WHERE schedule_version_id=?', (version,)):
                    groups.append({'group_id': name, 'campus': campus, 'time': when, 'chair_id': chair,
                        'secretary_id': secretary,
                        'expert_ids': [r[0] for r in connection.execute('SELECT teacher_id FROM api_group_experts WHERE group_id=?', (gid,))],
                        'student_ids': [r[0] for r in connection.execute('SELECT student_id FROM api_group_students WHERE group_id=?', (gid,))]})
                covered = {sid for g in groups for sid in g['student_ids']}
                result = {'groups': groups, 'unassigned_students': [s for s in payload['students'] if s['id'] not in covered]}
                summary[stage] = {'version': version, **verify(result, payload, rules)}
                panels[stage] = {g['group_id']: g for g in groups}
            assert panels['pre'].keys() == panels['formal'].keys()
            for gid, source in panels['pre'].items():
                target = panels['formal'][gid]
                assert set(source['student_ids']) == set(target['student_ids'])
                assert source['chair_id'] == target['chair_id'] and source['secretary_id'] == target['secretary_id']
                assert set(source['expert_ids']) <= set(target['expert_ids'])
            summary['translation'] = 'passed'
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({stage: {k: v for k, v in row.items() if k != 'workloads'}
                              for stage, row in summary.items() if isinstance(row, dict)}), flush=True)
            return
    rules, payload = snapshots['pre']
    rules.update(group_min=args.group_min, group_size=6, group_max=7, external_expert_max=2)
    if args.expert_count:
        rules.update(expert_count=args.expert_count, expert_min=args.expert_count)
    started = perf_counter()
    pre = generate_schedule(**payload, rules=rules)
    summary = {'pre': verify(pre, payload, rules)}
    summary['pre']['seconds'] = round(perf_counter() - started, 3)
    summary['pre']['diagnostics'] = pre.get('diagnostics', {})
    summary['pre']['unassigned_students'] = pre['unassigned_students']
    summary['pre']['groups_detail'] = pre['groups']
    print(json.dumps({k: v for k, v in summary['pre'].items() if k not in ('workloads', 'groups_detail', 'diagnostics')}), flush=True)
    rules, payload = snapshots['formal']
    rules.update(group_min=args.group_min, group_size=6, group_max=7, external_expert_max=2,
                 linked_translation=True, avoid_supervisor=False,
                 source_chair_title=snapshots['pre'][0]['chair_title'])
    if args.expert_count:
        rules['expert_count'] = max(rules['expert_count'], args.expert_count)
    source = [GroupDraft(g['group_id'], g['campus'], g['student_ids'], parse_time_range(g['time']),
                        None, g['chair_id'], g['expert_ids'], g['secretary_id']) for g in pre['groups']]
    started = perf_counter()
    formal = translate_panels(source, [parse_teacher(t) for t in payload['teachers']],
                              [parse_student(s) for s in payload['students']], rules)
    summary['formal'] = verify(formal, payload, rules)
    summary['formal']['seconds'] = round(perf_counter() - started, 3)
    summary['formal']['groups_detail'] = formal['groups']
    by_id = {g['group_id']: g for g in pre['groups']}
    for group in formal['groups']:
        original = by_id[group['group_id']]
        for key in ('student_ids', 'chair_id', 'secretary_id'):
            assert original[key] == group[key]
        assert set(original['expert_ids']) <= set(group['expert_ids'])
    summary['translation'] = 'fixed group numbers, students, chairs, original experts and secretaries retained'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary['formal'].items() if k not in ('workloads', 'groups_detail')}), flush=True)


if __name__ == '__main__':
    main()
