import type { ScheduleGroup } from '../types/schedule'

/** Share presentation sequence across views without changing business IDs. */
export function orderScheduleGroups(groups: ScheduleGroup[]): ScheduleGroup[] {
  return [...groups]
    .sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999')
      || a.timeRange.localeCompare(b.timeRange, 'zh-CN', { numeric: true })
      || a.groupName.localeCompare(b.groupName, 'zh-CN', { numeric: true }) || a.id - b.id)
    .map((group, index) => ({ ...group, displayOrder: index + 1 }))
}
