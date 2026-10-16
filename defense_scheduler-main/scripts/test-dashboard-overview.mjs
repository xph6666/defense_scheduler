import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'

const modulePath = process.argv[2]
if (!modulePath) {
  throw new Error('Usage: node scripts/test-dashboard-overview.mjs <compiled-dashboardOverview.js>')
}

const {
  summarizeConflictOverview,
  summarizeScheduleOverview
} = await import(pathToFileURL(modulePath).href)

const staleLocalConflict = {
  id: 1,
  defenseType: '预答辩',
  type: '时间冲突',
  level: 'error',
  target: '旧数据',
  reason: 'localStorage 中的旧冲突',
  createdAt: '2025-05-01T08:00:00.000Z'
}

const backendConflict = {
  id: 2,
  defenseType: '正式答辩',
  type: '人员冲突',
  level: 'warning',
  target: '当前后端数据',
  reason: '后端冲突快照',
  createdAt: '2025-05-11T08:00:00.000Z'
}

const generatedResults = [
  {
    defenseType: '预答辩',
    generatedAt: '',
    groups: [],
    conflicts: []
  },
  {
    defenseType: '正式答辩',
    generatedAt: '2025-05-11 09:00',
    groups: [{ id: 1 }, { id: 2 }],
    conflicts: [backendConflict]
  }
]

const scheduleOverview = summarizeScheduleOverview(generatedResults)
assert.equal(scheduleOverview.typeCount, 1)
assert.equal(scheduleOverview.totalGroups, 2)
assert.equal(scheduleOverview.latestGeneratedAt, new Date('2025-05-11 09:00').toLocaleString())

const conflictOverview = summarizeConflictOverview(generatedResults, [
  { checkedAt: '2025-05-01T08:00:00.000Z', conflicts: [staleLocalConflict] }
])
assert.equal(conflictOverview.errorCount, 0)
assert.equal(conflictOverview.warningCount, 1)
assert.equal(conflictOverview.checkedAt, new Date('2025-05-11 09:00').toLocaleString())

const ignoredLocalOverview = summarizeConflictOverview([], [
  { checkedAt: '', conflicts: [staleLocalConflict] }
])
assert.equal(ignoredLocalOverview.errorCount, 0)
assert.equal(ignoredLocalOverview.warningCount, 0)
assert.equal(ignoredLocalOverview.checkedAt, '-')

console.log('DASHBOARD_OVERVIEW_TEST_OK')
