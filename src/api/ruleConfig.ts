import request from './request'
import type { RuleConfig, DefenseType } from '../types/ruleConfig'
import { getRuleConfigFromStorage, saveRuleConfigToStorage } from '../utils/ruleConfigStorage'
import { toBackendDefenseType } from './schedule'
import { isNotFoundError } from './request'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export async function getRuleConfig(defenseType: DefenseType) {
  if (USE_MOCK) {
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
  if (USE_MOCK) {
    saveRuleConfigToStorage(data)
    return data
  }

  return request.post('/rule-config/', {
    ...data,
    defense_type: toBackendDefenseType(data.defenseType)
  }) as Promise<RuleConfig>
}
