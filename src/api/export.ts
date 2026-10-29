import { runtimeConfig } from '../config/runtime'
import request from './request'
import { createCsvBlob, downloadBlob } from '../utils/download'
import type { DefenseType } from '../types/schedule'
import { getScheduleResults, toBackendDefenseType } from './schedule'
import { readLocalConflicts } from './conflict'
import { checkConflictsMock } from '../utils/conflictMock'
import { exportScheduleToCsv } from '../utils/exportMock'
import { getRuleConfig } from './ruleConfig'
import { renderSchedulePrint } from '../domain/printSchedule'
import { createOperationLog } from './operationLog'
import type { ScheduleConflict } from '../types/conflict'

const USE_MOCK = runtimeConfig.useMock

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

export async function exportScheduleExcel(defenseType: DefenseType, versionId?: number, includeRemarks?: boolean) {
  if (USE_MOCK) {
    await sleep(600)

    const result = await getScheduleResults(defenseType, versionId)
    if (!result) {
      return createCsvBlob('暂无排期数据可导出')
    }

    const { conflicts } = readLocalConflicts(defenseType)
    const freshConflicts = checkConflictsMock(result)
    assertNoHardConflicts(freshConflicts.length ? freshConflicts : conflicts)
    exportScheduleToCsv(result, freshConflicts.length ? freshConflicts : conflicts, includeRemarks)
    await createOperationLog({
      type: '导出结果',
      module: '排期管理',
      description: `导出${defenseType}排期（Excel）`,
      details: { format: 'Excel', defenseType, versionId: result.versionId, versionNumber: result.version }
    })

    return createCsvBlob('')
  }

  const blob = await request.get('/schedule/export/', {
    params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId, ...(includeRemarks === undefined ? {} : { include_remarks: includeRemarks }) },
    responseType: 'blob'
  }) as Blob
  downloadBlob(blob, `defense_schedule_${toBackendDefenseType(defenseType)}.xlsx`)
  return blob
}

export async function exportScheduleWord(defenseType: DefenseType, versionId?: number, includeRemarks?: boolean) {
  if (USE_MOCK) {
    await sleep(600)
    return createCsvBlob('Mock 模式不支持 Word 导出')
  }

  const blob = await request.get('/schedule/export_word/', {
    params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId, ...(includeRemarks === undefined ? {} : { include_remarks: includeRemarks }) },
    responseType: 'blob'
  }) as Blob
  downloadBlob(blob, `${defenseType}时间安排.docx`)
  return blob
}

/** 学院归档的第二种 Word：《评审小组结论》（每组一页，供专家现场勾选等级并签名）。 */
export async function exportScheduleConclusion(defenseType: DefenseType, versionId?: number, includeRemarks?: boolean) {
  if (USE_MOCK) {
    await sleep(600)
    return createCsvBlob('Mock 模式不支持 Word 导出')
  }

  const blob = await request.get('/schedule/export_conclusion/', {
    params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId, ...(includeRemarks === undefined ? {} : { include_remarks: includeRemarks }) },
    responseType: 'blob'
  }) as Blob
  downloadBlob(blob, `${defenseType}评审小组结论.docx`)
  return blob
}

export async function exportSchedulePdf(defenseType: DefenseType, versionId?: number, includeRemarks?: boolean) {
  const preview = window.open('', '_blank')
  if (!preview) throw new Error('打印窗口未打开，请允许此站点弹出窗口后重试')
  preview.opener = null
  preview.document.write('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>正在准备打印</title><p>正在读取本次安排，请稍候…</p></html>')
  try {
    const [result, config] = await Promise.all([getScheduleResults(defenseType, versionId), getRuleConfig(defenseType)])
    if (!result?.groups.length) throw new Error('暂无排期数据可打印')
    const local = USE_MOCK ? readLocalConflicts(defenseType).conflicts : []
    // [TASK-P12 修改] PDF优先采用所选历史版本的备注开关。
    const includeRemarksForExport = includeRemarks ?? result.rules?.include_remarks ?? result.rules?.includeRemarks ?? config.includeRemarks
    const currentConflicts = USE_MOCK ? checkConflictsMock(result) : result.conflicts || []
    assertNoHardConflicts(currentConflicts.length ? currentConflicts : local)
    preview.document.open()
    preview.document.write(renderSchedulePrint(result, { includeRemarks: includeRemarksForExport, conflicts: currentConflicts.length ? currentConflicts : local }))
    preview.document.close()
    if (USE_MOCK) {
      await createOperationLog({
        type: '导出结果',
        module: '排期管理',
        description: `导出${defenseType}排期（PDF）`,
        details: { format: 'PDF', defenseType, versionId: result.versionId, versionNumber: result.version }
      })
    } else {
      await request.post('/schedule/record-pdf-export/', {
        defense_type: toBackendDefenseType(defenseType),
        version_id: result.versionId
      })
    }
    preview.focus()
  } catch (error) {
    preview.close()
    throw error
  }
}

function assertNoHardConflicts(conflicts: ScheduleConflict[]) {
  const errorCount = conflicts.filter(conflict => conflict.level === 'error').length
  if (errorCount) {
    throw new Error(`当前排期有 ${errorCount} 项硬冲突，处理并重新复核后才能导出`)
  }
}
