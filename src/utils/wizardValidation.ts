import type { RuleConfig } from '../types/ruleConfig'

// Keep errors actionable when a constraint lives inside the collapsed advanced section.
export function validateWizardRules(config: RuleConfig): string[] {
  const errors: string[] = []
  if (!config.enabled) errors.push('请在“更多要求”中启用本次答辩类型。')
  if (!config.startDate || !config.endDate) errors.push('请填写答辩开始和结束日期。')
  else if (config.endDate < config.startDate) errors.push('结束日期不能早于开始日期。')
  const { target, min, max } = config.studentCount
  if (![target, min, max].every(value => Number.isInteger(value) && value >= 1)) {
    errors.push('每组学生人数及人数范围必须是大于 0 的整数。')
  } else if (min > target || target > max) {
    errors.push(`每组学生人数需在 ${min}–${max} 人之间；如需改变范围，请展开“更多要求”。`)
  }
  if (![config.expertCount.target, config.expertCount.min].every(value => Number.isInteger(value) && value >= 1)
      || config.expertCount.target < config.expertCount.min) {
    errors.push('专家人数不能低于 1 或已设置的最少人数，请核对“更多要求”。')
  }
  if (config.defenseType === '中期答辩' && (min < 10 || max > 12)) errors.push('中期答辩每组学生人数必须在 10–12 人之间。')
  const current = config.defenseType !== '中期答辩'
  if (current && (min < 5 || max > 7)) errors.push('预答辩及正式答辩每组必须为 5～7 人，建议 6 人。')
  if (current && (![3, 5].includes(config.expertCount.target) || config.expertCount.min !== config.expertCount.target)) errors.push('专家人数请选择 3 或 5 人，含组长。')
  const expertMinimum = current ? 3 : 5
  if (config.expertCount.min < expertMinimum || config.expertCount.target < expertMinimum) errors.push(`${config.defenseType}至少需要 ${expertMinimum} 位专家（含主席/组长）。`)
  if (config.defenseType === '中期答辩') for (const [campus, date] of Object.entries(config.campusStartDates || {})) {
    if (date && (!['创新港', '兴庆'].includes(campus) || date < config.startDate || date > config.endDate)) errors.push(`${campus}的独立开始日期需在全局排期日期范围内。`)
  }
  return errors
}
