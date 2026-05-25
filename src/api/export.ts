import request from './request'
import { createCsvBlob } from '../utils/download'
import type { DefenseType } from '../types/schedule'
import { getScheduleResults } from './schedule'
import { readLocalConflicts } from './conflict'
import { exportScheduleToCsv } from '../utils/exportMock'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

export async function exportScheduleExcel(defenseType: DefenseType) {
  if (USE_MOCK) {
    await sleep(600)

    const result = await getScheduleResults(defenseType)
    if (!result) {
      return createCsvBlob('暂无排期数据可导出')
    }

    const { conflicts } = readLocalConflicts(defenseType)
    exportScheduleToCsv(result, conflicts)

    return createCsvBlob('')
  }

  return request.get('/schedule/export-excel/', {
    params: { defenseType },
    responseType: 'blob'
  }) as Promise<Blob>
}
