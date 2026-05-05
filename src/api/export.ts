import request from './request'
import { createCsvBlob } from '../utils/download'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export async function exportScheduleExcel(defenseType: string) {
  if (USE_MOCK) {
    const csvContent = [
      '答辩类型,导出模式,生成时间',
      `"${defenseType}","Mock","${new Date().toLocaleString()}"`
    ].join('\n')

    return createCsvBlob(csvContent)
  }

  return request.get('/schedule/export-excel/', {
    params: { defenseType },
    responseType: 'blob'
  }) as Promise<Blob>
}
