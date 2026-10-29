import type { ScheduleGroup } from '../types/schedule'
import { getScheduleExperts } from './scheduleExperts'

export interface MentorShares {
  counts: Record<string, number>
  pattern: string
  kind: 'balanced' | 'explained' | 'unbalanced'
  reason: string
}

/** Only a complete roster can establish that a mentor has just one student. */
export function buildMentorShares(groups: ScheduleGroup[], complete: boolean): Record<number, MentorShares> {
  const totals = new Map<string, Set<number>>()
  const key = (g: ScheduleGroup, name: string) => `${g.campus}\u0000${name.trim()}`
  for (const group of groups) for (const student of group.students) {
    const k = key(group, student.mentorName)
    if (!totals.has(k)) totals.set(k, new Set())
    totals.get(k)!.add(student.id)
  }
  const result: Record<number, MentorShares> = {}
  for (const group of groups) {
    const names = getScheduleExperts(group).map(t => t.name.trim())
    const counts = Object.fromEntries(names.map(name => [name, group.students.filter(s => s.mentorName.trim() === name).length]))
    const values = Object.values(counts).sort((a, b) => b - a)
    const balanced = values.length > 0 && values[0] - values[values.length - 1] <= 1
    const singletons = names.filter(name => counts[name] === 1 && totals.get(key(group, name))?.size === 1)
    const explained = complete && group.defenseType === '预答辩' && group.students.length === 6
      && values.join(',') === '3,2,1' && singletons.length > 0
    result[group.id] = {
      counts, pattern: values.join('＋'), kind: balanced ? 'balanced' : explained ? 'explained' : 'unbalanced',
      reason: explained ? `${singletons.join('、')}在本校区本次仅有 1 名学生；按“六人为主”保留 3＋2＋1。`
        : balanced ? '' : '导师带入学生数仍有差距，需继续均衡或核对限制原因。'
    }
  }
  return result
}
