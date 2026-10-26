import type { ScheduleResult } from '../types/schedule'
import type { RuleConfig } from '../types/ruleConfig'
import type { OptimizationSummary, SoftConstraintScore } from '../types/optimization'

// [TASK-P09 修改] 五项质量评分只使用排期观测数据，缺失项不进入总分分母。
/** Scores use observed data only; unavailable metrics do not enter the denominator. */
export function evaluateSoftConstraints(result: ScheduleResult, config: RuleConfig): OptimizationSummary {
  const scores: SoftConstraintScore[] = []
  const unassessed: OptimizationSummary['unassessed'] = []
  const groups = result.groups
  const add = (key: keyof RuleConfig['softWeights'], label: string, value: number | null,
    description: string, unavailableReason: string) => {
    const weight = config.softWeights[key]
    if (weight <= 0) return
    if (value === null || !Number.isFinite(value)) {
      unassessed.push({ key, label, reason: unavailableReason })
      return
    }
    scores.push({ key, label, score: Math.round(Math.max(0, Math.min(100, value)) * weight / 10),
      maxScore: weight * 10, weight, description })
  }
  const deviation = groups.length
    ? groups.reduce((sum, group) => sum + Math.abs(group.students.length - config.studentCount.target), 0) / groups.length
    : null
  add('balanceStudentCount', '学生人数均衡', deviation === null ? null : 100 - deviation * 20,
    deviation === null ? '' : `每组人数与目标平均相差 ${deviation.toFixed(1)} 人`, '排期中没有分组数据')

  const titles = groups.map(group => group.chairTitle
    || group.teachers.find(teacher => teacher.name === (group.chairman || group.leader))?.title)
  const titledGroups = titles.filter((title): title is string => Boolean(title))
  const seniorCount = titledGroups.filter(title =>
    ['教授', '研究员', '正高', '正高级', 'professor'].includes(title.toLowerCase())).length
  add('preferSeniorTeacher', '正高专家优先', groups.length && titledGroups.length === groups.length
    ? seniorCount / groups.length * 100 : null,
  `${seniorCount} / ${groups.length} 组由正高职称担任主席或组长`, '缺少主席/组长职称数据')

  const locations = new Map<string, Set<string>>()
  const locationsComplete = groups.length > 0 && groups.every(group =>
    typeof group.chairId === 'number' && typeof group.secretaryId === 'number' && Boolean(group.date && group.campus))
  if (locationsComplete) {
    for (const group of groups) {
      const ids = new Set([group.chairId, group.secretaryId, ...group.teachers.map(teacher => teacher.id)]
        .filter((id): id is number => typeof id === 'number'))
      for (const id of ids) {
        const key = `${id}:${group.date}`
        if (!locations.has(key)) locations.set(key, new Set())
        locations.get(key)!.add(group.campus)
      }
    }
  }
  const crossDays = [...locations.values()].filter(campuses => campuses.size > 1).length
  add('avoidCrossCampus', '减少跨校区', locationsComplete && locations.size
    ? (1 - crossDays / locations.size) * 100 : null,
  `${locations.size} 个教师出席日中，${crossDays} 个涉及同日跨校区`, '缺少完整的教师、日期或校区数据')

  const students = groups.flatMap(group => group.students.map(student => ({ group, student })))
  const externalDataComplete = students.length > 0
    && students.every(({ student }) => typeof student.mentorIsExternal === 'boolean')
  const externalStudents = students.filter(({ student }) => student.mentorIsExternal === true)
  const externalMentorGroups = new Map<string, { studentCount: number; groups: Set<number> }>()
  let externalIdentityComplete = true
  for (const { group, student } of externalStudents) {
    const mentorKey = student.mentorId !== undefined && student.mentorId !== null
      ? `id:${student.mentorId}` : student.mentorName ? `name:${student.mentorName}` : ''
    if (!mentorKey || !group.campus) {
      externalIdentityComplete = false
      continue
    }
    const cohortKey = JSON.stringify([mentorKey, group.campus])
    const mentor = externalMentorGroups.get(cohortKey) || { studentCount: 0, groups: new Set<number>() }
    mentor.studentCount += 1
    mentor.groups.add(group.id)
    externalMentorGroups.set(cohortKey, mentor)
  }
  const compliantMentors = [...externalMentorGroups.values()].filter(mentor =>
    mentor.groups.size === (mentor.studentCount < 3 ? 1 : 2)).length
  const externalMetricAvailable = externalDataComplete && externalIdentityComplete && externalMentorGroups.size > 0
  add('externalMentorConcentration', '外院导师集中', externalMetricAvailable
    ? compliantMentors / externalMentorGroups.size * 100 : null,
  `${compliantMentors} / ${externalMentorGroups.size} 个外院导师校区组合符合按学生数安排的组数要求`,
  !externalDataComplete ? '缺少导师是否外院的数据' : !externalIdentityComplete
    ? '缺少外院导师身份或校区数据' : '排期中没有可评估的外院导师')

  const studentKind = (value: string) => {
    const normalized = value.replace(/\s/g, '')
    if (['学硕', '学术硕士', '学术型硕士'].includes(normalized)) return 'academic'
    if (['专硕', '专业硕士', '专业型硕士'].includes(normalized)) return 'professional'
    return null
  }
  const academicTimes: number[] = []
  const professionalTimes: number[] = []
  let academicTypesComplete = students.length > 0
  for (const { group, student } of students) {
    const kind = studentKind(student.studentType)
    if (!kind) {
      academicTypesComplete = false
      continue
    }
    const timestamp = Date.parse(`${group.date}T${group.timeRange.split('-')[0]}`)
    if (!Number.isFinite(timestamp)) {
      academicTypesComplete = false
      continue
    }
    if (kind === 'academic') academicTimes.push(timestamp)
    else professionalTimes.push(timestamp)
  }
  let academicFirstScore: number | null = null
  let academicProfessionalPairs = 0
  if (academicTypesComplete && academicTimes.length && professionalTimes.length) {
    let favorablePairs = 0
    for (const academicTime of academicTimes) {
      for (const professionalTime of professionalTimes) {
        academicProfessionalPairs += 1
        favorablePairs += academicTime < professionalTime ? 1 : academicTime === professionalTime ? 0.5 : 0
      }
    }
    academicFirstScore = favorablePairs / academicProfessionalPairs * 100
  }
  add('preferAcademicMasterFirst', '学硕优先安排', academicFirstScore,
    `${academicProfessionalPairs} 对学硕/专硕排期按先后顺序比较`, '缺少可识别的学硕、专硕或有效时段数据')
  return {
    defenseType: config.defenseType,
    totalScore: scores.reduce((sum, s) => sum + s.score, 0),
    maxScore: scores.reduce((sum, s) => sum + s.maxScore, 0),
    scores,
    unassessed,
    suggestions: [{ id: 1, level: 'info', title: '评分范围', description: '软件学院评审次数均等单独提示，不计入总分；评分不替代发布前的冲突校验。' }],
    generatedAt: new Date().toLocaleString()
  }
}
