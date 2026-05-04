import request from './request'

export function listOperationLogs() {
  return request.get('/operation-logs/')
}
