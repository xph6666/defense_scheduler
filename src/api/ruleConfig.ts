import request from './request'
import type { RuleConfig, DefenseType } from '../types/ruleConfig'

export function getRuleConfig(defenseType: DefenseType) {
  return request.get('/rule-config/', { params: { defenseType } })
}

export function saveRuleConfig(data: RuleConfig) {
  return request.post('/rule-config/', data)
}
