import type { DefenseType, ScheduleGroup, ScheduleTeacher } from '../types/schedule'

export const STANDARD_TIME_OPTIONS = ['09:00-12:00', '14:00-17:00'] as const

const SENIOR_TITLES = new Set(['教授', '研究员', '正高', '正高级', 'professor'])
const DEPUTY_SENIOR_TITLES = new Set([
  ...SENIOR_TITLES,
  '副教授', '副研究员', '副高', '副高级', 'associate professor'
])

export function isSeniorTitle(title: string) {
  return SENIOR_TITLES.has((title || '').trim().toLowerCase())
}

export function isDeputySeniorOrAboveTitle(title: string) {
  return DEPUTY_SENIOR_TITLES.has((title || '').trim().toLowerCase())
}

/** Pre-defense chair eligibility follows title; no extra chair-role checkbox. */
export function isPreDefenseChairEligible(title: string, policyVersion = 4) {
  return policyVersion >= 4 ? isSeniorTitle(title) : isDeputySeniorOrAboveTitle(title)
}

export function buildAdjustTimeOptions(currentTimeRange?: string): string[] {
  const options: string[] = [...STANDARD_TIME_OPTIONS]
  const current = (currentTimeRange || '').trim()
  if (current && !options.includes(current)) {
    options.push(current)
  }
  return options
}

export function isChairOptionEligible(
  teacher: Pick<ScheduleTeacher, 'id' | 'title' | 'roles' | 'isActive' | 'expertOnly'>,
  defenseType: DefenseType,
  policyVersion = 4,
  currentChairId?: number
) {
  if (currentChairId !== undefined && teacher.id === currentChairId) return true
  if (teacher.isActive === false || teacher.expertOnly === true) return false
  if (defenseType === '预答辩') return isPreDefenseChairEligible(teacher.title, policyVersion)
  const roles = teacher.roles || []
  const roleAllowed = (expected: string) => roles.length === 0 || roles.includes(expected)
  if (defenseType === '正式答辩') {
    if (!isSeniorTitle(teacher.title)) return false
    return policyVersion >= 3
      ? roleAllowed('普通专家') || roles.includes('主席') || roles.includes('组长')
      : roleAllowed('主席')
  }
  const titleOk = policyVersion >= 4
    ? isSeniorTitle(teacher.title)
    : isDeputySeniorOrAboveTitle(teacher.title)
  return titleOk && roleAllowed('组长')
}

export function isSecretaryOptionEligible(
  teacher: Pick<ScheduleTeacher, 'id' | 'title' | 'roles' | 'isActive' | 'expertOnly'>,
  currentSecretaryId?: number
) {
  if (currentSecretaryId !== undefined && teacher.id === currentSecretaryId) return true
  if (teacher.isActive === false || teacher.expertOnly === true) return false
  const roles = teacher.roles || []
  if (roles.includes('秘书')) return true
  return roles.length === 0 && teacher.title !== '其他' && teacher.title !== '助教'
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
