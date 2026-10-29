export interface StudentCountRules {
  policy_version?: number
  group_size?: number
  group_min?: number
  group_max?: number
  studentCount?: { target?: number; min?: number; max?: number }
}

export function summarizeStudentCounts(groups: { students: unknown[] }[], rules?: StudentCountRules) {
  const savedTarget = rules?.group_size ?? rules?.studentCount?.target
  const target = typeof savedTarget === 'number' && Number.isInteger(savedTarget) && savedTarget > 0 ? savedTarget : null
  const counts = new Map<number, number>()
  for (const group of groups) counts.set(group.students.length, (counts.get(group.students.length) ?? 0) + 1)
  const preferredMinimum = target === null ? null : rules?.policy_version === 3 ? Math.max(1, target - 1) : target
  const preferredMaximum = target === null ? null : rules?.policy_version === 3 ? Math.min(rules.group_max ?? 7, target + 1) : target
  return {
    target,
    preferredMinimum,
    preferredMaximum,
    preferredGroupCount: target === null ? null : [...counts].reduce((total, [size, count]) => total + (size >= preferredMinimum! && size <= preferredMaximum! ? count : 0), 0),
    groupCount: groups.length,
    targetGroupCount: target === null ? null : counts.get(target) ?? 0,
    buckets: [...counts].sort(([left], [right]) => left - right).map(([size, count]) => ({ size, count, isTarget: size === target }))
  }
}
