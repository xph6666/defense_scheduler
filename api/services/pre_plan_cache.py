"""Retain verified complete pre-defense plans across bounded solver runs."""
from copy import deepcopy
from hashlib import sha256
import json
import logging
import os
from pathlib import Path

from django.conf import settings


def fingerprint(payload, rules):
    data = deepcopy(payload)
    # Pre-defense assigns secretaries after grouping. Persisting those derived
    # bindings must not make the same planning input appear to be new input.
    for student in data['students']:
        student.pop('secretary_id', None)
    return sha256(json.dumps({'input': data, 'rules': rules}, sort_keys=True,
                             ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def validated(payload, rules, result):
    if rules.get('defense_type') != 'pre' or rules.get('policy_version') != 3:
        return None
    from algorithm import GroupDraft, parse_student, parse_teacher, parse_time_range
    from scheduling.current import validate
    try:
        groups = [GroupDraft(g['group_id'], g.get('campus'), list(g['student_ids']), parse_time_range(g['time']),
                             None, g['chair_id'], list(g['expert_ids']), g['secretary_id']) for g in result['groups']]
        if len({g.group_id for g in groups}) != len(groups):
            return None
        from scheduling.group_order import finalize_pre_group_numbers
        groups, names = finalize_pre_group_numbers(groups)
        students = [parse_student(s) for s in payload['students']]
        teachers = [parse_teacher(t) for t in payload['teachers']]
        by_id = {s.id: s for s in students}
        if any(sid not in by_id or by_id[sid].campus != g.campus for g in groups for sid in g.student_ids):
            return None
        conflicts = validate(groups, students, teachers, {**rules, 'pre_group_order': True})
        warnings = {'mentor_student_imbalance', 'mentor_share_exception', 'half_day_coverage', 'external_distribution', 'student_group_exception'}
        if any(c['type'] not in warnings for c in conflicts):
            return None
        candidate = deepcopy(result)
        by_final_name = {names[row['group_id']]: row for row in candidate['groups']}
        candidate['groups'] = [{**by_final_name[g.group_id], 'group_id': g.group_id} for g in groups]
        candidate['conflicts'] = conflicts
        candidate['unassigned_students'] = []
        from scheduling.fairness import distribution_metrics, mentor_share_excess
        metrics = distribution_metrics(groups, students, teachers)
        diagnostics = candidate.setdefault('diagnostics', {})
        diagnostics['fairness'] = metrics
        # Raw appearance squares also grow when more groups are created. They
        # cannot compare a 39-group plan with a 42-group plan fairly. Compare
        # dimensionless size, concentration and relative workload dispersion.
        size_scale = max(1, (rules['group_max'] - rules['group_size']) ** 2,
                         (rules['group_min'] - rules['group_size']) ** 2)
        size_cost = sum((len(g.student_ids) - rules['group_size']) ** 2 / size_scale for g in groups) / max(1, len(groups))
        share_cost = sum(p['share_excess'] / max(1, mentor_share_excess({0: len(g.student_ids)}, rules['expert_count']))
                         for p, g in zip(metrics['panels'], groups)) / max(1, len(groups))
        visits = list(metrics['appearances'].values())
        visit_total = sum(visits)
        visit_cost = max(0, len(visits) * sum(n * n for n in visits) / visit_total ** 2 - 1) if visit_total else 0
        diagnostics['quality_components'] = {'size': size_cost, 'mentor_shares': share_cost, 'appearance_cv_squared': visit_cost}
        diagnostics['quality'] = size_cost + share_cost + visit_cost
        return candidate
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def read_pre_plan(payload, rules):
    directory = getattr(settings, 'PRE_PLAN_CACHE_DIR', '')
    if not directory or rules.get('defense_type') != 'pre':
        return None
    path = Path(directory) / (fingerprint(payload, rules) + '.json')
    try:
        result = validated(payload, rules, json.loads(path.read_text(encoding='utf8')))
        if result is not None:
            result.setdefault('diagnostics', {})['retained_complete_pre_plan'] = True
        return result
    except (OSError, ValueError):
        return None


def remember_pre_plan(payload, rules, result):
    directory = getattr(settings, 'PRE_PLAN_CACHE_DIR', '')
    if not directory or result.get('unassigned_students'):
        return False
    candidate = validated(payload, rules, result)
    if candidate is None:
        return False
    existing = read_pre_plan(payload, rules)
    if existing is not None and existing['diagnostics']['quality'] <= candidate['diagnostics']['quality']:
        return False
    path = Path(directory) / (fingerprint(payload, rules) + '.json')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(candidate, ensure_ascii=False), encoding='utf8')
        os.replace(temporary, path)
        return True
    except OSError:
        logging.getLogger(__name__).warning('Could not retain the verified complete pre-defense plan')
        return False
