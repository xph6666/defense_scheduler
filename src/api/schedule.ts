import request from './request'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import { generateMockScheduleResult } from '../utils/scheduleMock'
import { getScheduleResult, saveScheduleResult } from '../utils/scheduleStorage'

const USE_MOCK = true

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

export const getScheduleResults = async (defenseType: DefenseType) => {
  if (!USE_MOCK) {
    return request.get('/schedule/results', { params: { defenseType } }) as Promise<ScheduleResult>
  }

  await sleep(300)
  return getScheduleResult(defenseType)
}

export const generateSchedule = async (defenseType: DefenseType) => {
  if (!USE_MOCK) {
    return request.post('/schedule/generate', { defenseType }) as Promise<ScheduleResult>
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
