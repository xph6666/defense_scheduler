import { STORAGE_KEYS } from './storageKeys'
import { mockTeachers, mockStudents, mockClassrooms } from './mockData'

const defenseTypes = ['预答辩', '正式答辩', '中期答辩'] as const

export function resetDemoData() {
  seedTeachers()
  seedStudents()
  seedClassrooms()
  clearScheduleResults()
  clearConflictChecks()
  localStorage.removeItem(STORAGE_KEYS.lastExportTime)
}

export function seedTeachers() {
  localStorage.setItem(STORAGE_KEYS.teachers, JSON.stringify(mockTeachers))
}

export function seedStudents() {
  localStorage.setItem(STORAGE_KEYS.students, JSON.stringify(mockStudents))
}

export function seedClassrooms() {
  localStorage.setItem(STORAGE_KEYS.classrooms, JSON.stringify(mockClassrooms))
}

export function clearScheduleResults() {
  defenseTypes.forEach(type => {
    localStorage.removeItem(STORAGE_KEYS.scheduleResult(type))
    localStorage.removeItem(STORAGE_KEYS.scheduleConflicts(type))
  })
}

export function clearConflictChecks() {
  defenseTypes.forEach(type => {
    localStorage.removeItem(`schedule_conflicts_checked_at_${type}`)
  })
}
