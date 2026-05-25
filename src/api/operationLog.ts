import request from './request'
import type { OperationLog, OperationType } from '../types/operationLog'
import { addOperationLog, clearOperationLogs, getOperationLogs } from '../utils/operationLogStorage'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

interface CreateOperationLogPayload {
  type: OperationType
  module: string
  description: string
  result?: '成功' | '失败'
  operator?: string
}

export async function listOperationLogs() {
  if (USE_MOCK) {
    return getOperationLogs()
  }

  return request.get('/operation-logs/') as Promise<OperationLog[]>
}

export async function createOperationLog(payload: CreateOperationLogPayload) {
  if (USE_MOCK) {
    addOperationLog(payload)
    return
  }

  return request.post('/operation-logs/', payload) as Promise<OperationLog>
}

export async function clearRemoteOperationLogs() {
  if (USE_MOCK) {
    clearOperationLogs()
    return { message: '日志已清空' }
  }

  return request.delete('/operation-logs/') as Promise<{ message: string }>
}

export const isOperationLogMockMode = () => USE_MOCK
