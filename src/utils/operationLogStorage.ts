import type { OperationLog, OperationType } from '../types/operationLog'

const STORAGE_KEY = 'operation_logs'
const MAX_LOGS = 200

export function addOperationLog(params: {
  type: OperationType
  module: string
  description: string
  result?: '成功' | '失败'
  operator?: string
}): void {
  const logs = getOperationLogs()
  const newLog: OperationLog = {
    id: Date.now(),
    type: params.type,
    module: params.module,
    description: params.description,
    operator: params.operator || '管理员',
    result: params.result || '成功',
    createdAt: new Date().toLocaleString()
  }

  logs.unshift(newLog)
  
  // 只保留最近 200 条
  const trimmedLogs = logs.slice(0, MAX_LOGS)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmedLogs))
}

export function getOperationLogs(): OperationLog[] {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved) {
    try {
      return JSON.parse(saved)
    } catch (e) {
      console.error('Failed to parse operation logs', e)
    }
  }
  return []
}

export function clearOperationLogs(): void {
  localStorage.removeItem(STORAGE_KEY)
}
