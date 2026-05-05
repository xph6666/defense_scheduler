import request from './request'
import type { RuleConfig, DefenseType } from '../types/ruleConfig'
import { getRuleConfigFromStorage, saveRuleConfigToStorage } from '../utils/ruleConfigStorage'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export async function getRuleConfig(defenseType: DefenseType) {
  if (USE_MOCK) {
    return getRuleConfigFromStorage(defenseType)
  }

  return request.get('/rule-config/', { params: { defenseType } }) as Promise<RuleConfig>
}

export async function saveRuleConfig(data: RuleConfig) {
  if (USE_MOCK) {
    saveRuleConfigToStorage(data)
    return data
  }

  return request.post('/rule-config/', data) as Promise<RuleConfig>
}
