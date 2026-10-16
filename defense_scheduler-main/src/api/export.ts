import { runtimeConfig } from '../config/runtime'
import request from './request'
import { createCsvBlob, downloadBlob } from '../utils/download'
import type { DefenseType } from '../types/schedule'
import { getScheduleResults, toBackendDefenseType } from './schedule'
import { readLocalConflicts } from './conflict'
import { exportScheduleToCsv } from '../utils/exportMock'
import { getRuleConfig } from './ruleConfig'
import { renderSchedulePrint } from '../domain/printSchedule'

const USE_MOCK = runtimeConfig.useMock

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

export async function exportScheduleExcel(defenseType: DefenseType, versionId?: number) {
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

  const blob = await request.get('/schedule/export/', {
    params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId },
    responseType: 'blob'
  }) as Blob
  downloadBlob(blob, `defense_schedule_${toBackendDefenseType(defenseType)}.xlsx`)
  return blob
}

export async function exportScheduleWord(defenseType: DefenseType, versionId?: number) {
  if (USE_MOCK) {
    await sleep(600)
    return createCsvBlob('Mock 模式不支持 Word 导出')
  }

  const blob = await request.get('/schedule/export_word/', {
    params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId },
    responseType: 'blob'
  }) as Blob
  downloadBlob(blob, `${defenseType}时间安排.docx`)
  return blob
}

export async function exportSchedulePdf(defenseType: DefenseType, versionId?: number) {
  const preview = window.open('', '_blank')
  if (!preview) throw new Error('打印窗口未打开，请允许此站点弹出窗口后重试')
  preview.opener = null
  preview.document.write('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>正在准备打印</title><p>正在读取本次安排，请稍候…</p></html>')
  try {
    const [result, config] = await Promise.all([getScheduleResults(defenseType, versionId), getRuleConfig(defenseType)])
    if (!result?.groups.length) throw new Error('暂无排期数据可打印')
    const local = USE_MOCK ? readLocalConflicts(defenseType).conflicts : []
    preview.document.open()
    preview.document.write(renderSchedulePrint(result, { includeRemarks: config.includeRemarks, conflicts: result.conflicts || local }))
    preview.document.close()
    preview.focus()
  } catch (error) {
    preview.close()
    throw error
  }
}
