import { normalizeRuleConfig } from '../domain/scheduleRules'
import { runtimeConfig } from '../config/runtime'
import request from './request'
import type { RuleConfig, DefenseType } from '../types/ruleConfig'
import { getRuleConfigFromStorage, saveRuleConfigToStorage } from '../utils/ruleConfigStorage'
import { toBackendDefenseType } from '../domain/defense'

const USE_MOCK = runtimeConfig.useMock

export async function getRuleConfig(defenseType: DefenseType) {
  if (USE_MOCK) {
    return getRuleConfigFromStorage(defenseType)
  }

  const result = await request.get('/rule-config/', {
    params: { defense_type: toBackendDefenseType(defenseType) }
  }) as RuleConfig
  return normalizeRuleConfig(result)
}

export async function saveRuleConfig(data: RuleConfig) {
  data = normalizeRuleConfig(data)
  if (USE_MOCK) {
    saveRuleConfigToStorage(data)
    return data
  }

  const result = await request.post('/rule-config/', {
    ...data,
    defense_type: toBackendDefenseType(data.defenseType)
  }) as RuleConfig
  return normalizeRuleConfig(result)
}
