export type DefenseType = '预答辩' | '正式答辩' | '中期答辩'

export interface ScheduleStudent {
  id: number
  name: string
  studentType: '学硕' | '专硕'
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
  leader?: string
  chairman?: string
  secretary: string
  teachers: ScheduleTeacher[]
  students: ScheduleStudent[]
  status?: 'normal' | 'warning' | 'error'
  remark?: string
}

export interface ScheduleResult {
  defenseType: DefenseType
  generatedAt: string
  groups: ScheduleGroup[]
}
