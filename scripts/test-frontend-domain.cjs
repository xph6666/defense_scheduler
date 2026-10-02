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

for (const [type, minimum] of [['预答辩', 4], ['正式答辩', 5], ['中期答辩', 5]]) {
  const config = getDefaultRuleConfig(type)
  const rules = buildScheduleRules(type, config)
  assert.equal(rules.policy_version, 2)
  assert.equal(rules.expert_count_includes_chair, true)
  assert.equal(rules.expert_min, minimum)
  assert.equal(rules.secretary_count, 1)
  assert.equal(rules.course_half_day_blocking, true)
}
const formal = normalizeRuleConfig({ ...getDefaultRuleConfig('正式答辩'), expertCount: { target: 9, min: 2 } })
assert.equal(formal.expertCount.target, 5)
assert.equal(formal.expertCount.min, 5)
const legacyPre = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), policyVersion: undefined, expertCount: { target: 3, min: 3 } })
assert.equal(legacyPre.expertCount.target, 4)
assert.equal(legacyPre.expertCount.min, 4)
assert.equal(buildScheduleRules('正式答辩', formal).formal_software_min, 3)
const migratedWeights = normalizeRuleConfig({ ...getDefaultRuleConfig('预答辩'), policyVersion: undefined, softWeights: { balanceStudentCount: 5, preferSeniorTeacher: 8, avoidCrossCampus: 3, externalMentorConcentration: 2, preferAcademicMasterFirst: 0 } })
assert.equal(migratedWeights.softWeights.preferSeniorTeacher, 80)
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
assert.ok(html.includes(`background:${getMentorColor('导师甲')}`), 'PDF follows the shared mentor color contract')
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
