import { getDefensePolicy } from '../domain/defense'
import { normalizeRuleConfig } from '../domain/scheduleRules'
import type { DefenseType, RuleConfig } from '../types/ruleConfig'

const STORAGE_KEY_PREFIX = 'rule_config_'

function addDays(dateText: string, days: number): string {
  const date = new Date(dateText)
  if (Number.isNaN(date.getTime())) {
    return dateText
  }
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

export function getDefaultRuleConfig(defenseType: DefenseType): RuleConfig {
  const startDate = new Date().toISOString().split('T')[0]
  const policy = getDefensePolicy(defenseType)
  return normalizeRuleConfig({
    ...policy,
    defenseType,
    startDate,
    endDate: addDays(startDate, 10),
    studentCount: { ...policy.studentCount },
    expertCount: { target: policy.expertCount.target, min: policy.expertCount.min },
    roleQualification: { ...policy.roleQualification },
    softWeights: { ...policy.softWeights }
  } as RuleConfig)
}

export function getRuleConfigFromStorage(defenseType: DefenseType): RuleConfig {
  const saved = localStorage.getItem(`${STORAGE_KEY_PREFIX}${defenseType}`)
  if (saved) {
    try {
      return normalizeRuleConfig({ ...getDefaultRuleConfig(defenseType), ...JSON.parse(saved), policyVersion: JSON.parse(saved).policyVersion, defenseType })
    } catch (e) {
      console.error('Failed to parse rule config', e)
    }
  }
  return getDefaultRuleConfig(defenseType)
}

export function saveRuleConfigToStorage(config: RuleConfig): void {
  config.updatedAt = new Date().toLocaleString()
  localStorage.setItem(`${STORAGE_KEY_PREFIX}${config.defenseType}`, JSON.stringify(normalizeRuleConfig(config)))
}

export function resetRuleConfig(defenseType: DefenseType): RuleConfig {
  const defaultConfig = getDefaultRuleConfig(defenseType)
  saveRuleConfigToStorage(defaultConfig)
  return defaultConfig
}

export function getAllRuleConfigs(): RuleConfig[] {
  const types: DefenseType[] = ['预答辩', '正式答辩', '中期答辩']
  return types.map(t => getRuleConfigFromStorage(t))
}
