import type { DefenseType, ScheduleGroup, ScheduleResult } from '../types/schedule'

const getStorageKey = (defenseType: DefenseType) => `schedule_result_${defenseType}`

export const saveScheduleResult = (result: ScheduleResult) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(getStorageKey(result.defenseType), JSON.stringify(result))
}

export const getScheduleResult = (defenseType: DefenseType) => {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(getStorageKey(defenseType))
  if (!raw) return null
  try {
    return JSON.parse(raw) as ScheduleResult
  } catch {
    return null
  }
}

export const updateScheduleGroupInStorage = (defenseType: DefenseType, groupId: number, groupData: ScheduleGroup) => {
  const current = getScheduleResult(defenseType)
  if (!current) return null
  const exists = current.groups.some(g => g.id === groupId)
  if (!exists) return null
  const updated = {
    ...current,
    groups: current.groups.map(g => (g.id === groupId ? { ...groupData } : g))
  }
  saveScheduleResult(updated)
  return updated
}

export const getAllScheduleResults = () => {
  const defenseTypes: DefenseType[] = ['预答辩', '正式答辩', '中期答辩']
  const results: ScheduleResult[] = []
  for (const dt of defenseTypes) {
    const r = getScheduleResult(dt)
    if (r) results.push(r)
  }
  return results
}

