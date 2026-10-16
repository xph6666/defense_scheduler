import type { ScheduleResult } from '../types/schedule'
import type { RuleConfig } from '../types/ruleConfig'
import type { OptimizationSummary, SoftConstraintScore } from '../types/optimization'

/** Scores use observed data only; unavailable metrics do not enter the denominator. */
export function evaluateSoftConstraints(result: ScheduleResult, config: RuleConfig): OptimizationSummary {
  const scores: SoftConstraintScore[] = []
  const groups = result.groups
  const add = (key: keyof RuleConfig['softWeights'], label: string, value: number, description: string) => {
    const weight = config.softWeights[key]
    if (weight > 0) scores.push({ key, label, score: Math.round(Math.max(0, Math.min(100, value)) * weight / 10), maxScore: weight * 10, description })
  }
  if (groups.length) {
    const deviation = groups.reduce((sum, g) => sum + Math.abs(g.students.length - config.studentCount.target), 0) / groups.length
    add('balanceStudentCount', '学生人数均衡', 100 - deviation * 20, `每组人数与目标平均相差 ${deviation.toFixed(1)} 人`)
    const titles = groups.map(g => g.chairTitle || g.teachers.find(t => t.name === (g.chairman || g.leader))?.title)
    if (titles.every(Boolean)) {
      const count = titles.filter(t => t === '教授').length
      add('preferSeniorTeacher', '正高专家优先', count / groups.length * 100, `${count} / ${groups.length} 组由教授担任主席或组长`)
    }
    if (groups.every(g => g.chairId !== undefined && g.secretaryId !== undefined)) {
      const locations = new Map<string, Set<string>>()
      for (const g of groups) {
        const ids = new Set([g.chairId, g.secretaryId, ...g.teachers.map(t => t.id)].filter((id): id is number => !!id))
        for (const id of ids) {
          const key = `${id}:${g.date}`
          if (!locations.has(key)) locations.set(key, new Set())
          locations.get(key)!.add(g.campus)
        }
      }
      if (locations.size) {
        const crossDays = [...locations.values()].filter(campuses => campuses.size > 1).length
        add('avoidCrossCampus', '减少跨校区', (1 - crossDays / locations.size) * 100,
          `${locations.size} 个教师出席日中，${crossDays} 个涉及同日跨校区`)
      }
    }
  }
  return {
    defenseType: config.defenseType,
    totalScore: scores.reduce((sum, s) => sum + s.score, 0),
    maxScore: scores.reduce((sum, s) => sum + s.maxScore, 0),
    scores,
    suggestions: [{ id: 1, level: 'info', title: '评分范围', description: '仅对具备数据的指标评分。外院导师集中、学硕优先暂未评估；评分不替代发布前的冲突校验。' }],
    generatedAt: new Date().toLocaleString()
  }
}
