import request from './request'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import type { RuleConfig } from '../types/ruleConfig'
import { generateMockScheduleResult } from '../utils/scheduleMock'
import { getScheduleResult, saveScheduleResult } from '../utils/scheduleStorage'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

export const toBackendDefenseType = (defenseType: DefenseType) => {
  const typeMap: Record<DefenseType, string> = {
    '预答辩': 'pre',
    '正式答辩': 'formal',
    '中期答辩': 'mid'
  }
  return typeMap[defenseType]
}

export const getScheduleResults = async (defenseType: DefenseType) => {
  if (!USE_MOCK) {
    return request.get('/schedule/current/', {
      params: { defense_type: toBackendDefenseType(defenseType) }
    }) as Promise<ScheduleResult>
  }

  await sleep(300)
  return getScheduleResult(defenseType)
}

const addDays = (dateText: string, days: number) => {
  const date = new Date(dateText)
  if (Number.isNaN(date.getTime())) {
    return dateText
  }
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const buildScheduleRules = (defenseType: DefenseType, config?: RuleConfig) => {
  const startDate = config?.startDate || new Date().toISOString().split('T')[0]

  return {
    defense_type: toBackendDefenseType(defenseType),
    start_date: startDate,
    end_date: addDays(startDate, 10),
    group_size: config?.studentCount?.target || 6,
    expert_count: config?.expertCount?.target || 3,
    avoid_weekend: config?.avoidWeekend ?? true,
    avoid_holiday: config?.avoidHoliday ?? true,
    mentor_avoidance: config?.mentorAvoidance ?? false
  }
}

export const generateSchedule = async (defenseType: DefenseType, config?: RuleConfig) => {
  if (!USE_MOCK) {
    return request.post('/schedule/generate/', {
      rules: buildScheduleRules(defenseType, config)
    }) as Promise<ScheduleResult>
  }

  const delay = 800 + Math.floor(Math.random() * 400)
  await sleep(delay)

  if (Math.random() < 0.05) {
    throw new Error('generate_failed')
  }

  const result = generateMockScheduleResult(defenseType)
  saveScheduleResult(result)
  return result
}
