import type { ScheduleConflict } from '../types/conflict'
import type { ScheduleResult } from '../types/schedule'

interface LocalConflictRecord {
  checkedAt: string
  defenseType?: string
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
  const byType = new Map<string, { timestamp: number; conflicts: ScheduleConflict[] }>()
  for (const result of results.filter(isGeneratedResult)) {
    if (!Array.isArray(result.conflicts)) continue
    const timestamp = parseTime(result.generatedAt)
    latest = Math.max(latest, timestamp)
    byType.set(result.defenseType, { timestamp, conflicts: result.conflicts })
  }
  for (const record of localRecords) {
    const timestamp = parseTime(record.checkedAt)
    if (!timestamp) continue
    const type = record.defenseType || record.conflicts[0]?.defenseType
    if (!type || !byType.has(type)) continue
    latest = Math.max(latest, timestamp)
    if (timestamp >= (byType.get(type)?.timestamp || 0)) byType.set(type, { timestamp, conflicts: record.conflicts })
  }
  const conflicts = [...byType.values()].flatMap(record => record.conflicts)
  return {
    errorCount: conflicts.filter(conflict => conflict.level === 'error').length,
    warningCount: conflicts.filter(conflict => conflict.level === 'warning').length,
    checkedAt: formatTime(latest)
  }
}
