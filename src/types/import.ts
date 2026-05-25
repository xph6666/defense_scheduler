export type ImportModule = 'teacher' | 'student' | 'classroom'

export interface ImportFileInfo {
  name: string
  size: number
  type: string
}

export interface ImportPreviewColumn {
  prop: string
  label: string
  matched: boolean
  required?: boolean
}

export interface ImportPreviewResult<T = any> {
  module: ImportModule
  fileInfo: ImportFileInfo
  columns: ImportPreviewColumn[]
  rows: T[]
  validCount: number
  invalidCount: number
  warnings: string[]
}
