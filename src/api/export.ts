import request from './request'

export function exportScheduleExcel(defenseType: string) {
  return request.get('/schedule/export-excel/', {
    params: { defenseType },
    responseType: 'blob'
  })
}
