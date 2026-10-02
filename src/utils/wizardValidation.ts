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
  const expertMinimum = config.defenseType === '预答辩' ? 4 : 5
  if (config.expertCount.min < expertMinimum || config.expertCount.target < expertMinimum) errors.push(`${config.defenseType}至少需要 ${expertMinimum} 位专家（含主席/组长）。`)
  if (config.defenseType === '正式答辩' && (config.expertCount.target !== 5 || config.expertCount.min !== 5)) errors.push('正式答辩必须固定 5 位专家（含主席）。')
  if (config.defenseType === '正式答辩' && (!Number.isInteger(config.formalSoftwareMin) || (config.formalSoftwareMin || 0) < 3 || (config.formalSoftwareMin || 0) > 5)) errors.push('正式答辩的软件学院专家至少人数需为 3–5 人。')
  if (config.defenseType === '中期答辩') for (const [campus, date] of Object.entries(config.campusStartDates || {})) {
    if (date && (!['创新港', '兴庆'].includes(campus) || date < config.startDate || date > config.endDate)) errors.push(`${campus}的独立开始日期需在全局排期日期范围内。`)
  }
  return errors
}
