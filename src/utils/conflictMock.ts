import type { ScheduleResult } from '../types/schedule'
import type { ScheduleConflict, ConflictLevel, ConflictType } from '../types/conflict'

let nextConflictId = 1

const makeConflict = (input: Omit<ScheduleConflict, 'id' | 'createdAt'>): ScheduleConflict => ({
  id: nextConflictId++,
  createdAt: new Date().toISOString(),
  ...input
})

const add = (list: ScheduleConflict[], input: Omit<ScheduleConflict, 'id' | 'createdAt'>) => {
  list.push(makeConflict(input))
}

const getTimeKey = (date: string, timeRange: string) => `${date}__${timeRange}`

const unique = <T>(arr: T[]) => Array.from(new Set(arr))

export const checkConflictsMock = (result: ScheduleResult) => {
  const conflicts: ScheduleConflict[] = []
  const groups = result.groups

  const classroomMap = new Map<string, number[]>()
  for (const g of groups) {
    const key = `${g.campus}__${g.classroom}__${getTimeKey(g.date, g.timeRange)}`
    const list = classroomMap.get(key) || []
    list.push(g.id)
    classroomMap.set(key, list)
  }
  for (const [key, groupIds] of classroomMap) {
    if (groupIds.length < 2) continue
    const relatedGroupIds = unique(groupIds)
    const [campus, classroom, timeKey] = key.split('__')
    add(conflicts, {
      defenseType: result.defenseType,
      type: '教室冲突',
      level: 'error',
      target: `${campus} ${classroom}`,
      reason: `同一时间段 ${timeKey.replace('__', ' ')} 使用相同教室`,
      suggestion: '调整其中一组的教室或时间段',
      relatedGroupIds
    })
  }

  const peopleMap = new Map<string, { name: string; groupId: number; groupName: string }[]>()
  for (const g of groups) {
    const timeKey = getTimeKey(g.date, g.timeRange)
    const people: string[] = []
    if (g.leader) people.push(g.leader)
    if (g.chairman) people.push(g.chairman)
    if (g.secretary) people.push(g.secretary)
    for (const t of g.teachers) people.push(t.name)

    for (const name of unique(people).filter(Boolean)) {
      const key = `${timeKey}__${name}`
      const list = peopleMap.get(key) || []
      list.push({ name, groupId: g.id, groupName: g.groupName })
      peopleMap.set(key, list)
    }
  }
  for (const [key, list] of peopleMap) {
    if (list.length < 2) continue
    const timeKey = key.split('__')[0]
    const name = key.split('__')[1]
    add(conflicts, {
      defenseType: result.defenseType,
      type: '人员冲突',
      level: 'error',
      target: name,
      reason: `同一时间段 ${timeKey.replace('__', ' ')} 重复出现在多个组`,
      suggestion: '调整其中一组的时间段或替换人员',
      relatedGroupIds: unique(list.map(x => x.groupId))
    })
  }

  for (const g of groups) {
    if (!g.secretary) continue
    const hit = g.students.find(s => s.secretaryName && s.secretaryName === g.secretary)
    if (hit) {
      add(conflicts, {
        defenseType: result.defenseType,
        groupId: g.id,
        groupName: g.groupName,
        type: '秘书学生冲突',
        level: 'error',
        target: `秘书 ${g.secretary}`,
        reason: `秘书“${g.secretary}”负责的学生“${hit.name}”出现在该秘书所在组。`,
        suggestion: '调整学生分组或更换秘书'
      })
    }
  }

  for (const g of groups) {
    const count = g.students.length
    const dt = result.defenseType
    let warn = false
    let rangeText = ''
    if (dt === '中期答辩') {
      rangeText = '允许 10-13 人/组'
      warn = count < 10 || count > 13
    } else {
      rangeText = '建议约 6 人/组'
      warn = count < 4 || count > 8
    }
    if (warn) {
      add(conflicts, {
        defenseType: result.defenseType,
        groupId: g.id,
        groupName: g.groupName,
        type: '人数规则提示',
        level: 'warning',
        target: `${g.groupName} 学生人数`,
        reason: `当前人数 ${count}，${rangeText}`,
        suggestion: '通过人工调整学生所属组平衡人数'
      })
    }
  }

  for (const g of groups) {
    if (result.defenseType === '正式答辩') {
      if (!g.chairman) {
        add(conflicts, {
          defenseType: result.defenseType,
          groupId: g.id,
          groupName: g.groupName,
          type: '人员冲突',
          level: 'error',
          target: g.groupName,
          reason: '正式答辩组缺少主席',
          suggestion: '为该组选择主席'
        })
      }
    } else {
      if (!g.leader) {
        add(conflicts, {
          defenseType: result.defenseType,
          groupId: g.id,
          groupName: g.groupName,
          type: '人员冲突',
          level: 'error',
          target: g.groupName,
          reason: '该组缺少组长',
          suggestion: '为该组选择组长'
        })
      }
    }

    if (!g.secretary) {
      add(conflicts, {
        defenseType: result.defenseType,
        groupId: g.id,
        groupName: g.groupName,
        type: '人员冲突',
        level: 'error',
        target: g.groupName,
        reason: '该组缺少秘书',
        suggestion: '为该组选择秘书'
      })
    }
  }

  return conflicts
}

export const getGroupStatus = (groupId: number, conflicts: ScheduleConflict[]) => {
  const groupConflicts = conflicts.filter(item => item.groupId === groupId || item.relatedGroupIds?.includes(groupId))
  if (groupConflicts.some(item => item.level === 'error')) return 'error'
  if (groupConflicts.some(item => item.level === 'warning')) return 'warning'
  return 'normal'
}

export const getGroupConflictCount = (groupId: number, conflicts: ScheduleConflict[]) => {
  return conflicts.filter(item => item.groupId === groupId || item.relatedGroupIds?.includes(groupId)).length
}

export const getConflictCounts = (conflicts: ScheduleConflict[]) => {
  const count = (level: ConflictLevel) => conflicts.filter(c => c.level === level).length
  return {
    error: count('error'),
    warning: count('warning'),
    info: count('info')
  }
}

export const getLevelLabel = (level: ConflictLevel) => {
  if (level === 'error') return '错误'
  if (level === 'warning') return '警告'
  return '提示'
}

export const getTypeLabel = (type: ConflictType) => type

