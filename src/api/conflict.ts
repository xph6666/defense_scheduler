import request from './request'
import type { DefenseType } from '../types/schedule'
import type { ScheduleConflict } from '../types/conflict'
import { getScheduleResult } from '../utils/scheduleStorage'
import { checkConflictsMock } from '../utils/conflictMock'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

const getConflictsKey = (defenseType: DefenseType) => `schedule_conflicts_${defenseType}`
const getCheckedAtKey = (defenseType: DefenseType) => `schedule_conflicts_checked_at_${defenseType}`

const writeLocal = (defenseType: DefenseType, conflicts: ScheduleConflict[]) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(getConflictsKey(defenseType), JSON.stringify(conflicts))
  window.localStorage.setItem(getCheckedAtKey(defenseType), new Date().toISOString())
}

export const readLocalConflicts = (defenseType: DefenseType) => {
  if (typeof window === 'undefined') return { conflicts: [], checkedAt: '' }
  const raw = window.localStorage.getItem(getConflictsKey(defenseType))
  const checkedAt = window.localStorage.getItem(getCheckedAtKey(defenseType)) || ''
  if (!raw) return { conflicts: [], checkedAt }
  try {
    return { conflicts: JSON.parse(raw) as ScheduleConflict[], checkedAt }
  } catch {
    return { conflicts: [], checkedAt }
  }
}

export const checkScheduleConflicts = async (defenseType: DefenseType) => {
  if (!USE_MOCK) {
    return request.post('/schedule/check-conflicts/', { defenseType }) as Promise<ScheduleConflict[]>
  }

  const result = getScheduleResult(defenseType)
  if (!result) {
    writeLocal(defenseType, [])
    return []
  }
  const conflicts = checkConflictsMock(result)
  writeLocal(defenseType, conflicts)
  return conflicts
}

