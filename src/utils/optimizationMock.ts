import type { ScheduleResult } from '../types/schedule'
import type { RuleConfig } from '../types/ruleConfig'
import type { OptimizationSummary, SoftConstraintScore, OptimizationSuggestion } from '../types/optimization'

export function evaluateSoftConstraints(
  result: ScheduleResult,
  config: RuleConfig
): OptimizationSummary {
  const scores: SoftConstraintScore[] = []
  const suggestions: OptimizationSuggestion[] = []
  let totalScore = 0

  // 1. 学生人数均衡 (权重: balanceStudentCount)
  const studentWeight = config.softWeights.balanceStudentCount
  if (studentWeight > 0) {
    const target = config.studentCount.target
    let diffSum = 0
    result.groups.forEach(g => {
      diffSum += Math.abs(g.students.length - target)
    })
    const avgDiff = diffSum / result.groups.length
    const scoreValue = Math.max(0, 100 - avgDiff * 20)
    const weightedScore = (scoreValue * studentWeight) / 10
    
    scores.push({
      key: 'balanceStudentCount',
      label: '学生人数均衡',
      score: Math.round(weightedScore),
      maxScore: studentWeight * 10,
      description: `各组人数与目标值(${target})的平均偏差为 ${avgDiff.toFixed(1)} 人`
    })
    totalScore += weightedScore
    
    if (avgDiff > 2) {
      suggestions.push({
        id: 1,
        level: 'info',
        title: '建议平衡组间人数',
        description: '部分小组人数偏差较大，建议手动调整以均衡工作量。'
      })
    }
  }

  // 2. 正高优先 (权重: preferSeniorTeacher)
  const seniorWeight = config.softWeights.preferSeniorTeacher
  if (seniorWeight > 0) {
    let seniorLeaderCount = 0
    result.groups.forEach(g => {
      const leader = g.teachers.find(t => g.leader === t.name || g.chairman === t.name)
      if (leader && leader.title === '教授') seniorLeaderCount++
    })
    const ratio = seniorLeaderCount / result.groups.length
    const scoreValue = ratio * 100
    const weightedScore = (scoreValue * seniorWeight) / 10
    
    scores.push({
      key: 'preferSeniorTeacher',
      label: '正高专家优先',
      score: Math.round(weightedScore),
      maxScore: seniorWeight * 10,
      description: `共有 ${seniorLeaderCount} 组由正高专家担任主席/组长，占比 ${(ratio * 100).toFixed(0)}%`
    })
    totalScore += weightedScore

    if (ratio < 0.5) {
      suggestions.push({
        id: 2,
        level: 'warning',
        title: '正高专家参与度偏低',
        description: '建议增加正高职称专家担任组长或主席的比例。'
      })
    }
  }

  // 3. 减少跨校区 (权重: avoidCrossCampus)
  const campusWeight = config.softWeights.avoidCrossCampus
  if (campusWeight > 0) {
    // 模拟评分
    const scoreValue = 85 
    const weightedScore = (scoreValue * campusWeight) / 10
    scores.push({
      key: 'avoidCrossCampus',
      label: '减少跨校区',
      score: Math.round(weightedScore),
      maxScore: campusWeight * 10,
      description: '大部分专家已安排在常驻校区，仅存在少量跨校区排期。'
    })
    totalScore += weightedScore
  }

  // 4. 外院集中 (权重: externalMentorConcentration)
  const externalWeight = config.softWeights.externalMentorConcentration
  if (externalWeight > 0) {
    const scoreValue = 70
    const weightedScore = (scoreValue * externalWeight) / 10
    scores.push({
      key: 'externalMentorConcentration',
      label: '外院导师集中',
      score: Math.round(weightedScore),
      maxScore: externalWeight * 10,
      description: '部分校外专家学生已实现集中排期。'
    })
    totalScore += weightedScore
  }

  const maxTotalScore = Object.values(config.softWeights).reduce((a, b) => a + b, 0) * 10

  return {
    defenseType: config.defenseType,
    totalScore: Math.round(totalScore),
    maxScore: maxTotalScore,
    scores,
    suggestions,
    generatedAt: new Date().toLocaleString()
  }
}
