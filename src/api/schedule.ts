import request from './request'
import type { DefenseType, ScheduleResult } from '../types/schedule'
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

export const generateSchedule = async (defenseType: DefenseType) => {
  if (!USE_MOCK) {
    return request.post('/schedule/generate/', {
      rules: { defense_type: toBackendDefenseType(defenseType) }
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
