const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

const cache = new Map()
function load(relative) {
  const filename = path.resolve(__dirname, '..', relative)
  if (cache.has(filename)) return cache.get(filename)
  const exports = {}
  cache.set(filename, exports)
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true }
  }).outputText
  const module = { exports }
  vm.runInThisContext(`(function(require, module, exports) { ${code}\n})`, { filename })(specifier => {
    if (!specifier.startsWith('.')) return require(specifier)
    const resolved = path.resolve(path.dirname(filename), specifier)
    if (resolved.endsWith('.json')) return JSON.parse(fs.readFileSync(resolved, 'utf8'))
    return load(path.relative(path.resolve(__dirname, '..'), `${resolved}.ts`))
  }, module, exports)
  cache.set(filename, module.exports)
  return module.exports
}

const { buildScheduleRules, normalizeRuleConfig } = load('src/domain/scheduleRules.ts')
const { createScheduleRequestScope } = load('src/domain/scheduleContext.ts')
const { getDefaultRuleConfig } = load('src/utils/ruleConfigStorage.ts')
const { orderScheduleGroups } = load('src/domain/scheduleOrder.ts')
const unorderedGroups = [
  { id: 30, groupName: 'G10', date: '2026-11-02', timeRange: '14:00-17:00' },
  { id: 20, groupName: 'G2', date: '2026-11-02', timeRange: '09:00-12:00' },
  { id: 10, groupName: 'G1', date: '2026-11-02', timeRange: '09:00-12:00' }
]
const orderedGroups = orderScheduleGroups(unorderedGroups)
assert.deepEqual(orderedGroups.map(group => group.id), [10, 20, 30])
assert.deepEqual(orderedGroups.map(group => group.displayOrder), [1, 2, 3])
assert.deepEqual(unorderedGroups.map(group => group.id), [30, 20, 10])

for (const [type, minimum] of [['预答辩', 3], ['正式答辩', 5], ['中期答辩', 5]]) {
  const config = getDefaultRuleConfig(type)
  const rules = buildScheduleRules(type, config)
  assert.equal(rules.policy_version, type === '中期答辩' ? 2 : 3)
  assert.equal(rules.expert_count_includes_chair, true)
  assert.equal(rules.expert_min, minimum)
  assert.equal(rules.secretary_count, 1)
  assert.equal(rules.course_half_day_blocking, true)
}
const formal = normalizeRuleConfig({ ...getDefaultRuleConfig('正式答辩'), expertCount: { target: 9, min: 2 } })
assert.equal(formal.expertCount.target, 5)
assert.equal(formal.expertCount.min, 5)
assert.equal(formal.mentorAvoidance, true)
assert.equal(buildScheduleRules('正式答辩', { ...formal, mentorAvoidance: false }).avoid_supervisor, true)
const legacyPre = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), policyVersion: undefined, expertCount: { target: 3, min: 3 } })
assert.equal(legacyPre.expertCount.target, 3)
assert.equal(legacyPre.expertCount.min, 3)
const { validateWizardRules: validateCommitteeRules } = load('src/utils/wizardValidation.ts')
assert.deepEqual(validateCommitteeRules(getDefaultRuleConfig('预答辩')), [])
const adjustedFormal = normalizeRuleConfig({ ...getDefaultRuleConfig('正式答辩'), expertCount: { target: 5, min: 5 } })
assert.equal(adjustedFormal.expertCount.target, 5)
assert.equal(adjustedFormal.expertCount.min, 5)
assert.equal(adjustedFormal.formalSoftwareMin, 0)
assert.equal(buildScheduleRules('正式答辩', adjustedFormal).expert_count, 5)
assert.equal(buildScheduleRules('正式答辩', adjustedFormal).expert_min, 5)
assert.deepEqual(validateCommitteeRules(adjustedFormal), [])
const adjustedPre = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), expertCount: { target: 5, min: 5 } })
assert.equal(buildScheduleRules('预答辩', adjustedPre).expert_min, 5)
assert(validateCommitteeRules({ ...getDefaultRuleConfig('预答辩'), expertCount: { target: 4, min: 4 } }).some(message => message.includes('3 或 5')))
assert.deepEqual(validateCommitteeRules(getDefaultRuleConfig('中期答辩')), [])
assert(validateCommitteeRules({ ...getDefaultRuleConfig('中期答辩'), studentCount: { target: 12, min: 10, max: 13 } }).some(message => message.includes('10–12')))
assert.equal(buildScheduleRules('正式答辩', formal).formal_software_min, 0)
const migratedWeights = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), policyVersion: undefined, softWeights: { balanceStudentCount: 5, preferSeniorTeacher: 8, avoidCrossCampus: 3, externalMentorConcentration: 2, preferAcademicMasterFirst: 0 } })
assert.equal(migratedWeights.softWeights.preferSeniorTeacher, 80)
// [TASK-P09 新增] 覆盖五项评分、缺失指标和真实/演示口径一致性。
const { evaluateSoftConstraints } = load('src/utils/optimization.ts')
const { evaluateSoftConstraints: evaluateMockSoftConstraints } = load('src/utils/optimizationMock.ts')
const scoringConfig = getDefaultRuleConfig('正式答辩')
scoringConfig.studentCount.target = 2
const scoringResult = {
  defenseType: '正式答辩', generatedAt: '2026-10-12', groups: [
    { id: 1, date: '2026-10-12', timeRange: '09:00-12:00', campus: '创新港', chairId: 1,
      chairTitle: '研究员', chairman: '研究员甲', secretaryId: 2, teachers: [], students: [
        { id: 1, studentType: '学硕', mentorId: 10, mentorName: '外院导师', mentorIsExternal: true },
        { id: 2, studentType: '学硕', mentorId: 10, mentorName: '外院导师', mentorIsExternal: true }
      ] },
    { id: 2, date: '2026-10-12', timeRange: '14:00-17:00', campus: '创新港', chairId: 3,
      chairTitle: '教授', chairman: '教授乙', secretaryId: 4, teachers: [], students: [
        { id: 3, studentType: '专硕', mentorId: 11, mentorName: '校内导师', mentorIsExternal: false }
      ] }
  ]
}
const quality = evaluateSoftConstraints(scoringResult, scoringConfig)
assert.deepEqual(quality.scores.map(score => score.key), [
  'balanceStudentCount', 'preferSeniorTeacher', 'avoidCrossCampus',
  'externalMentorConcentration', 'preferAcademicMasterFirst'
])
assert.equal(quality.unassessed.length, 0)
assert.equal(quality.scores.find(score => score.key === 'preferSeniorTeacher').score,
  quality.scores.find(score => score.key === 'preferSeniorTeacher').maxScore)
assert.equal(quality.scores.find(score => score.key === 'externalMentorConcentration').score,
  quality.scores.find(score => score.key === 'externalMentorConcentration').maxScore)
assert.equal(quality.scores.find(score => score.key === 'preferAcademicMasterFirst').score,
  quality.scores.find(score => score.key === 'preferAcademicMasterFirst').maxScore)
assert.equal(quality.scores.find(score => score.key === 'preferAcademicMasterFirst').weight,
  scoringConfig.softWeights.preferAcademicMasterFirst)
assert.equal(quality.scores.some(score => score.key === 'balanceSoftwareParticipation'), false)
const demoQuality = evaluateMockSoftConstraints(scoringResult, scoringConfig)
assert.deepEqual(demoQuality.scores, quality.scores, 'demo and real scoring share the same calculations')
const unavailableQuality = evaluateSoftConstraints({ ...scoringResult, groups: scoringResult.groups.map(group => ({
  ...group, students: group.students.map(student => ({ ...student, studentType: '计算机科学与技术', mentorIsExternal: null }))
})) }, scoringConfig)
assert.ok(unavailableQuality.unassessed.some(item => item.key === 'externalMentorConcentration'))
assert.ok(unavailableQuality.unassessed.some(item => item.key === 'preferAcademicMasterFirst'))
const { validateWizardRules } = load('src/utils/wizardValidation.ts')
const midCampusConfig = { ...getDefaultRuleConfig('中期答辩'), startDate: '2026-10-12', endDate: '2026-10-20', campusStartDates: { '创新港': '2026-10-12', '兴庆': '2026-10-15' } }
assert.deepEqual(buildScheduleRules('中期答辩', midCampusConfig).campus_start_dates, midCampusConfig.campusStartDates)
assert.equal(validateWizardRules(midCampusConfig).length, 0)
assert.ok(validateWizardRules({ ...midCampusConfig, campusStartDates: { '兴庆': '2026-10-25' } }).some(error => error.includes('独立开始日期')))

const scope = createScheduleRequestScope()
const first = scope.begin('预答辩', 1)
const second = scope.begin('预答辩', 2)
assert.equal(scope.isCurrent(first, '预答辩', 1), false, 'a late response cannot replace the selected version')
assert.equal(scope.isCurrent(second, '预答辩', 2), true)
scope.invalidate()
assert.equal(scope.isCurrent(second, '预答辩', 2), false, 'invalidating the page also invalidates conflict/score work')
const { renderSchedulePrint } = load('src/domain/printSchedule.ts')
const unsafeName = '<img src=x onerror=alert(1)>'
const printResult = {
  defenseType: '预答辩', generatedAt: '2026-10-02', version: 1, groups: [{
    id: 7, groupName: '第一组', date: '2026-10-02', timeRange: '09:00-10:30', campus: '创新港', classroom: '<script>bad()</script>',
    leader: '导师甲', secretary: '秘书乙', teachers: [{ id: 1, name: '导师甲', title: '教授' }],
    students: [{ id: 2, name: unsafeName, studentType: '学硕', mentorId: 1, mentorName: '导师甲', remark: 'STUDENT PRIVATE <备注>' }], remark: 'PRIVATE REMARK'
  }], conflicts: [{ groupId: 7, level: 'error', reason: '<b>不安全内容</b>' }]
}
const html = renderSchedulePrint(printResult)
assert.ok(!html.includes(unsafeName), 'imported student names must never become HTML')
assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'))
assert.ok(html.includes('&lt;script&gt;bad()&lt;/script&gt;'))
assert.ok(html.includes('&lt;b&gt;不安全内容&lt;/b&gt;'))
assert.ok(html.includes('class="conflict-row"'))
assert.ok(html.includes('PRIVATE REMARK'))
assert.ok(!renderSchedulePrint(printResult, { includeRemarks: false }).includes('PRIVATE REMARK'))
assert.ok(html.includes('STUDENT PRIVATE &lt;备注&gt;'))
assert.ok(!renderSchedulePrint(printResult, { includeRemarks: false }).includes('STUDENT PRIVATE'))
const { getMentorColor } = load('src/utils/color.ts')
const { buildMentorColors, groupMentorColors } = load('src/domain/mentorColors.ts')
assert.ok(html.includes(`background:${groupMentorColors(printResult.groups[0], buildMentorColors(printResult.groups))['导师甲'].backgroundColor}`), 'PDF follows collision-free version colors')
const stressMentors = Array.from({ length: 17 }, (_, index) => `QA导师${String(index + 1).padStart(2, '0')}`)
assert.equal(new Set(stressMentors.map(getMentorColor)).size, stressMentors.length,
  'the expanded shared palette distinguishes 17 mentors')
const { getScheduleExperts } = load('src/domain/scheduleExperts.ts')
const backendGroup = { ...printResult.groups[0], chairId: 1, teachers: [{ id: 3, name: '组员甲', title: '副教授' }] }
assert.equal(getScheduleExperts(backendGroup).length, 2, 'API member-only lists also count the chair')
assert.equal(getScheduleExperts({ ...backendGroup, teachers: [{ id: 1, name: '导师甲', title: '教授' }] }).length, 1, 'legacy lists do not double count the chair')
const globalIssueHtml = renderSchedulePrint({ ...printResult, groups: [backendGroup, { ...backendGroup, id: 8 }], conflicts: [{ level: 'error', reason: '全局数据错误' }] })
assert.equal((globalIssueHtml.match(/class="group has-errors"/g) || []).length, 2, 'global errors mark every group')
const midPrintHtml = renderSchedulePrint({ ...printResult, defenseType: '中期答辩' })
assert.ok(midPrintHtml.includes('background:#2E75B6;color:#fff;'), 'mid-term headings retain the shared blue with readable white text')
if (process.argv.includes('--print-fixture')) {
  const outputDir = path.resolve(__dirname, '../.tmp/v2-ui')
  fs.mkdirSync(outputDir, { recursive: true })
  fs.writeFileSync(path.join(outputDir, 'mid-print.html'), midPrintHtml)
}
assert.ok(html.includes('break-before:page'))
const { createMockRepository } = load('src/utils/mockRepository.ts')
const storage = new Map()
global.localStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) }
const { saveRuleConfigToStorage, getRuleConfigFromStorage } = load('src/utils/ruleConfigStorage.ts')
saveRuleConfigToStorage(adjustedFormal)
assert.equal(getRuleConfigFromStorage('正式答辩').expertCount.target, 5)
assert.equal(getRuleConfigFromStorage('正式答辩').expertCount.min, 5)
const repo = createMockRepository('demo_resources', [{ id: 1, name: '初始资料' }])
repo.write([{ id: 2, name: '编辑后的资料' }])
assert.equal(createMockRepository('demo_resources', []).read()[0].name, '编辑后的资料')
localStorage.setItem('demo_resources', JSON.stringify([{ id: 1, name: '重置资料' }]))
assert.equal(repo.read()[0].name, '重置资料', 'demo reset and CRUD read the same source')
const { summarizeConflictOverview } = load('src/utils/dashboardOverview.ts')
const overview = summarizeConflictOverview([
  { defenseType: '预答辩', generatedAt: '2026-10-12', conflicts: [{ level: 'error' }] },
  { defenseType: '正式答辩', generatedAt: '2026-10-13', conflicts: [{ level: 'warning' }] }
])
assert.equal(overview.errorCount, 1)
assert.equal(overview.warningCount, 1, 'the dashboard counts conflicts from all current defense types')
console.log('Frontend domain checks passed: V2 policy, legacy migration, request isolation, safe PDF HTML, shared demo storage')

const { summarizeParticipation } = load('src/utils/studentParticipation.ts')
const importedFormal = [{ defenseTypes: ['正式答辩'] }, { defenseTypes: [] }]
const preParticipation = summarizeParticipation(importedFormal, '预答辩')
assert.equal(preParticipation.total, 2)
assert.equal(preParticipation.current, 0)
assert.equal(preParticipation.unassigned, 1)
assert.deepEqual([...preParticipation.availableTypes], ['正式答辩'])
assert.equal(summarizeParticipation(importedFormal, '正式答辩').current, 1)
const withExcluded = summarizeParticipation([...importedFormal, { defenseTypes: [], participationExcluded: true }], '正式答辩')
assert.equal(withExcluded.total, 3)
assert.equal(withExcluded.current, 1)
assert.equal(withExcluded.unassigned, 1)
assert.equal(withExcluded.excluded, 1)
assert.ok(withExcluded.hint.includes('1 位明确不参加本次答辩'))
const { matchesListSearch } = load('src/utils/listSearch.ts')
assert.equal(matchesListSearch('  xQ001 兴庆 ', ['学生甲', 'XQ001', '兴庆']), true)
assert.equal(matchesListSearch('外院 待确认', ['外院导师（职称待确认）', ['普通专家']]), true)
assert.equal(matchesListSearch('兴庆 002', ['XQ001', '创新港']), false)
assert.equal(matchesListSearch('   ', [null]), true)
console.log('Participation counts and unified multi-field search passed')

const { summarizeStudentCounts } = load('src/domain/studentCountSummary.ts')
const summaryGroups = [5, 6, 6, 7].map(size => ({ students: Array(size).fill({}) }))
const summary = summarizeStudentCounts(summaryGroups, { group_size: 6 })
assert.equal(summary.target, 6)
assert.equal(summary.targetGroupCount, 2)
assert.deepEqual(summary.buckets, [
  { size: 5, count: 1, isTarget: false }, { size: 6, count: 2, isTarget: true }, { size: 7, count: 1, isTarget: false }
])
assert.equal(summarizeStudentCounts(summaryGroups, { studentCount: { target: 5 } }).targetGroupCount, 1)
assert.equal(summarizeStudentCounts(summaryGroups).target, null)
assert.equal(summarizeStudentCounts(summaryGroups, { policy_version: 3, group_size: 6 }).preferredMinimum, 5)
assert.equal(summarizeStudentCounts(summaryGroups, { policy_version: 3, group_size: 6 }).preferredGroupCount, 4)
assert.deepEqual(summarizeStudentCounts([], { group_size: 6 }).buckets, [])
console.log('Version-specific student headcount distribution passed')

const migratedCounts = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), studentCount: { target: 4, min: 4, max: 7 } })
assert.deepEqual(migratedCounts.studentCount, { target: 6, min: 5, max: 7 })
assert(validateCommitteeRules({ ...getDefaultRuleConfig('预答辩'), studentCount: { target: 6, min: 4, max: 7 } }).some(message => message.includes('5～7')))
console.log('Strict 5–7 student range and legacy configuration migration passed')

const { isPreDefenseChairEligible } = load('src/domain/scheduleExperts.ts')
for (const title of ['副教授', '教授', '副研究员', '研究员']) assert.equal(isPreDefenseChairEligible(title), true)
for (const title of ['讲师', '其他', '外院导师（职称待确认）']) assert.equal(isPreDefenseChairEligible(title), false)
console.log('Pre-defense chair title eligibility passed')

const { buildMentorShares } = load('src/domain/mentorShares.ts')
const { mentorColorSeparation } = load('src/domain/mentorColors.ts')
const colorGroup = (id, names, shares) => ({ id, groupName: `G${id}`, defenseType: '预答辩', campus: '创新港',
  teachers: names.map((name, i) => ({ id: i + 1, name, title: '副教授', roles: ['普通专家'] })),
  students: names.flatMap((name, i) => Array.from({ length: shares[i] }, (_, n) => ({ id: id * 100 + i * 10 + n, mentorName: name }))) })
const colorGroups = [colorGroup(1, ['刘帅', '刘杨', '张萌'], [3, 2, 1]),
  colorGroup(2, ['赵加坤', '赵国帅', '王文杰'], [3, 2, 1]), colorGroup(3, ['刘帅', '赵加坤', '赵国帅'], [2, 2, 2])]
const versionColors = buildMentorColors(colorGroups)
assert.deepEqual(versionColors, buildMentorColors([...colorGroups].reverse()), 'ordering must not change teacher colors')
for (const group of colorGroups) {
  const local = groupMentorColors(group, versionColors)
  const names = group.teachers.map(t => t.name)
  assert.equal(new Set(names.map(n => local[n].backgroundColor)).size, names.length)
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
    assert(mentorColorSeparation(local[names[i]], local[names[j]]) >= 20, 'same-group colors must be perceptually distinct')
  }
}
assert.deepEqual(groupMentorColors(colorGroups[0], versionColors)['刘帅'], groupMentorColors(colorGroups[2], versionColors)['刘帅'])
const summaries = buildMentorShares(colorGroups, true)
assert.equal(summaries[1].kind, 'explained')
assert.equal(summaries[2].kind, 'explained')
assert(summaries[2].reason.includes('王文杰'))
assert.equal(buildMentorShares(colorGroups, false)[1].kind, 'unbalanced', 'partial assignment cannot prove a mentor has only one student')
assert.equal(summaries[3].kind, 'balanced')
console.log('Co-occurrence teacher colors and explained 3+2+1 exceptions passed')
const colorFixture = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../shared/mentor-color-fixtures.json'), 'utf8'))
const distinctPalette = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../shared/mentor-colors.json'), 'utf8')).distinctPalette
assert.deepEqual(Object.fromEntries(Object.entries(versionColors).map(([name, s]) => [name, distinctPalette.findIndex(p => `#${p.light}` === s.backgroundColor)])), colorFixture.indexes)
