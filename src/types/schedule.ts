import type { ScheduleConflict } from './conflict'

export type DefenseType = '预答辩' | '正式答辩' | '中期答辩'

export interface ScheduleWorkflowState {
  hasResult: boolean
  status: 'draft' | 'published'
  errorCount: number
  busy: boolean
}

export interface ScheduleStudent {
  id: number
  name: string
  studentNo?: string
  // 真实名单中该列为学科（如"计算机科学与技术"），不再限定为 学硕/专硕
  studentType: string
  mentorName: string
  secretaryName?: string
}

export interface ScheduleTeacher {
  id: number
  name: string
  title: '教授' | '副教授' | '讲师' | '其他'
  roles: string[]
  college?: string
  isExternal?: boolean
}

export interface ScheduleGroup {
  id: number
  defenseType: DefenseType
  groupName: string
  campus: '创新港' | '兴庆'
  classroom: string
  date: string
  timeRange: string
  chairTitle?: string
  chairId?: number
  secretaryId?: number
  leader?: string
  chairman?: string
  secretary: string
  teachers: ScheduleTeacher[]
  students: ScheduleStudent[]
  status?: 'normal' | 'warning' | 'error'
  remark?: string
}

export interface ScheduleResult {
  versionId?: number
  version?: number
  revision?: number
  status?: 'draft' | 'published'
  isCurrent?: boolean
  defenseType: DefenseType
  generatedAt: string
  groups: ScheduleGroup[]
  /** 后端生成排期时的冲突快照；旧后端/Mock 模式下不存在 */
  conflicts?: ScheduleConflict[]
}
