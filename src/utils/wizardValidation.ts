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
  return errors
}
