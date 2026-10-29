import type { ScheduleConflict } from './conflict'

import type { DefenseType, TeacherTitle } from '../domain/defense'
export type { DefenseType } from '../domain/defense'

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
  mentorId?: number | null
  // [TASK-P09 新增] 评分按导师外院属性统计；null表示数据缺失。
  mentorIsExternal?: boolean | null
  secretaryId?: number | null
  secretaryName?: string
  remark?: string
}

export interface ScheduleTeacher {
  id: number
  name: string
  title: TeacherTitle
  roles: string[]
  college?: string
  isExternal?: boolean
  isActive?: boolean
  memberEligible?: boolean
  isSoftwareTeacher?: boolean
}

export interface ScheduleGroup {
  id: number
  defenseType: DefenseType
  groupName: string
  displayOrder?: number
  campus: '创新港' | '兴庆'
  classroom: string
  date: string
  timeRange: string
  chairTitle?: string
  chairIsExternal?: boolean
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
  unassignedStudents?: { id: number; name: string; reason: string }[]
  teacherWorkloads?: { id: number; name: string; supervisedStudents: number; groupCount: number; studentCount: number; sessions: string[] }[]
  allocationStatus?: 'partial' | 'scheduled'
  totalStudents?: number
  // [TASK-P12 新增] 历史版本导出按该版本规则快照处理备注。
  rules?: {
    policy_version?: number
    expert_count?: number
    start_date?: string
    end_date?: string
    include_remarks?: boolean
    includeRemarks?: boolean
    group_size?: number
    group_min?: number
    group_max?: number
    studentCount?: { target?: number; min?: number; max?: number }
  }
  /** 后端生成排期时的冲突快照；旧后端/Mock 模式下不存在 */
  conflicts?: ScheduleConflict[]
  /** 随机种子（正式答辩专家随机补充时使用） */
  randomSeed?: number | string
}
