import type { ScheduleGroup, ScheduleTeacher } from '../types/schedule'

/** Pre-defense chair eligibility follows title; no extra chair-role checkbox. */
export function isPreDefenseChairEligible(title: string) {
  return ['教授', '副教授', '研究员', '副研究员', '正高', '正高级', '副高', '副高级'].includes(title.trim())
}

/** API member lists can exclude the chair; legacy/demo responses can include the chair. */
export function getScheduleExperts(group: ScheduleGroup): ScheduleTeacher[] {
  const people = new Map<string, ScheduleTeacher>()
  const key = (teacher: ScheduleTeacher) => teacher.id ? `id:${teacher.id}` : `name:${teacher.name}`
  for (const teacher of group.teachers) people.set(key(teacher), teacher)
  const chairName = group.chairman || group.leader
  if ((group.chairId || chairName) && !group.teachers.some(teacher => group.chairId ? teacher.id === group.chairId : teacher.name === chairName)) {
    const chair: ScheduleTeacher = {
      id: group.chairId || 0,
      name: chairName || '主席/组长',
      title: (group.chairTitle as ScheduleTeacher['title']) || '其他',
      isExternal: group.chairIsExternal,
      roles: [group.defenseType === '正式答辩' ? '主席' : '组长']
    }
    people.set(key(chair), chair)
  }
  return [...people.values()]
}
