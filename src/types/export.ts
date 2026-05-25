export type ExportStatus = 'idle' | 'exporting' | 'success' | 'error'

export interface ExportOptions {
  defenseType: '预答辩' | '正式答辩' | '中期答辩'
  includeConflicts?: boolean
  includeRemark?: boolean
  mockMode?: boolean
}

export interface ExportResult {
  success: boolean
  fileName?: string
  message: string
}
