import type { ScheduleConflict } from '../types/conflict'
import type { ScheduleResult } from '../types/schedule'

interface LocalConflictRecord {
  checkedAt: string
  conflicts: ScheduleConflict[]
}

const parseTime = (value: string) => {
  if (!value) return 0
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const formatTime = (timestamp: number) => {
  return timestamp ? new Date(timestamp).toLocaleString() : '-'
}

const isGeneratedResult = (result: ScheduleResult) => {
  return parseTime(result.generatedAt) > 0
}

export const summarizeScheduleOverview = (results: ScheduleResult[]) => {
  const generated = results.filter(isGeneratedResult)
  const latest = generated.reduce((max, result) => {
    return Math.max(max, parseTime(result.generatedAt))
  }, 0)

  return {
    typeCount: generated.length,
    totalGroups: generated.reduce((sum, result) => sum + result.groups.length, 0),
    latestGeneratedAt: formatTime(latest)
  }
}

export const summarizeConflictOverview = (
  results: ScheduleResult[],
  localRecords: LocalConflictRecord[] = []
) => {
  let latest = 0
  let latestConflicts: ScheduleConflict[] = []

  for (const record of localRecords) {
    const timestamp = parseTime(record.checkedAt)
    if (!timestamp) continue
    if (timestamp >= latest) {
      latest = timestamp
      latestConflicts = record.conflicts
    }
  }

  for (const result of results.filter(isGeneratedResult)) {
    if (!Array.isArray(result.conflicts)) continue
    const timestamp = parseTime(result.generatedAt)
    if (timestamp >= latest) {
      latest = timestamp
      latestConflicts = result.conflicts
    }
  }

  return {
    errorCount: latestConflicts.filter(conflict => conflict.level === 'error').length,
    warningCount: latestConflicts.filter(conflict => conflict.level === 'warning').length,
    checkedAt: formatTime(latest)
  }
}
