"""Derive stage relationships from versioned student membership, never group numbers."""
from collections import defaultdict
from ..schedule_integrity import export_groups


def build_stage_mapping(pre, formal):
    records = {}
    scope = (formal.campus_scope if formal else '') or (pre.campus_scope if pre else '')
    for stage, version in (('pre', pre), ('formal', formal)):
        if not version:
            continue
        # Include unassigned participants saved in the input, too.
        for student in version.input_snapshot.get('students', []):
            if scope and student.get('campus') != scope:
                continue
            records.setdefault(student['id'], {'studentId': student['id'], 'studentNo': student.get('student_no', ''),
                'name': student['name'], 'preGroups': [], 'formalGroups': []})
        for group in export_groups(version):
            if scope and group.campus != scope:
                continue
            for student in group.students.all():
                row = records.setdefault(student.id, {'studentId': student.id, 'studentNo': student.student_no or '',
                    'name': student.name, 'preGroups': [], 'formalGroups': []})
                row['studentNo'] = row['studentNo'] or student.student_no or ''
                row[f'{stage}Groups'].append({'id': group.id, 'name': group.group_id, 'campus': group.campus})
    links = defaultdict(set)
    for row in records.values():
        counts = (len(row['preGroups']), len(row['formalGroups']))
        row['status'] = ('duplicate' if max(counts) > 1 else 'missing_pre' if not counts[0]
                         else 'pending_formal' if not counts[1] else 'matched')
        for left in row['preGroups']:
            for right in row['formalGroups']:
                links[left['id'], left['name'], right['id'], right['name']].add(row['studentId'])
    rows = sorted(records.values(), key=lambda row: (row['studentNo'], row['studentId']))
    return {'preVersionId': pre.pk if pre else None, 'preVersion': pre.version if pre else None,
            'formalVersionId': formal.pk if formal else None, 'formalVersion': formal.version if formal else None,
            'rows': rows, 'links': [dict(preGroupId=key[0], preGroup=key[1], formalGroupId=key[2],
                formalGroup=key[3], studentCount=len(ids)) for key, ids in sorted(links.items())],
            'summary': {status: sum(row['status'] == status for row in rows)
                        for status in ('matched', 'pending_formal', 'missing_pre', 'duplicate')}}
