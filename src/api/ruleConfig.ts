import request from './request'
import type { RuleConfig, DefenseType } from '../types/ruleConfig'
import { getRuleConfigFromStorage, saveRuleConfigToStorage } from '../utils/ruleConfigStorage'
import { toBackendDefenseType } from './schedule'
import { isNotFoundError } from './request'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'
const USE_REMOTE_RULE_CONFIG = (import.meta as any).env?.VITE_USE_REMOTE_RULE_CONFIG === 'true'

export async function getRuleConfig(defenseType: DefenseType) {
  if (USE_MOCK || !USE_REMOTE_RULE_CONFIG) {
    return getRuleConfigFromStorage(defenseType)
  }

  try {
    return await request.get('/rule-config/', {
      params: { defense_type: toBackendDefenseType(defenseType) }
    }) as RuleConfig
  } catch (error) {
    if (isNotFoundError(error)) {
      return getRuleConfigFromStorage(defenseType)
    }
    throw error
  }
}

export async function saveRuleConfig(data: RuleConfig) {
  if (USE_MOCK || !USE_REMOTE_RULE_CONFIG) {
    saveRuleConfigToStorage(data)
    return data
  }

  return request.post('/rule-config/', {
    ...data,
    defense_type: toBackendDefenseType(data.defenseType)
  }) as Promise<RuleConfig>
}
