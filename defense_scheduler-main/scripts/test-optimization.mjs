import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const source = fs.readFileSync(new URL('../src/utils/optimization.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } })
const { evaluateSoftConstraints } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const config = { defenseType: '预答辩', studentCount: { target: 1 }, softWeights: {
  balanceStudentCount: 50, preferSeniorTeacher: 50, avoidCrossCampus: 50,
  externalMentorConcentration: 50, preferAcademicMasterFirst: 50
} }
const empty = evaluateSoftConstraints({ groups: [] }, config)
assert.equal(empty.totalScore, 0)
assert.equal(empty.maxScore, 0)
const result = evaluateSoftConstraints({ groups: [
  { students: [{}], teachers: [], chairTitle: '教授', chairId: 1, secretaryId: 2, campus: '创新港', date: '2026-09-16' },
  { students: [{}], teachers: [], chairTitle: '教授', chairId: 1, secretaryId: 2, campus: '兴庆', date: '2026-09-16' }
] }, config)
assert.equal(result.scores.find(s => s.key === 'avoidCrossCampus').score, 0)
assert.equal(result.maxScore, 1500)
assert.equal(result.scores.some(s => s.key === 'externalMentorConcentration'), false)
console.log('Optimization checks passed: empty input, actual campus conflicts, unassessed metrics.')
