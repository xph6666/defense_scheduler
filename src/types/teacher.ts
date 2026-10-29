import type { TeacherTitle } from '../domain/defense'

export interface Teacher {
  id: number
  name: string
  college: string
  isExternal: boolean
  isActive?: boolean
  memberEligible?: boolean
  expertOnly?: boolean
  isSoftwareTeacher?: boolean
  // [TASK-P04 修改] 使用共享职称枚举，包括研究员职称。
  title: TeacherTitle
  roles: string[]
  availableTypes: string[]
  campusPreference: '创新港' | '兴庆' | '不限'
  unavailableTimes: string
  availableTimes?: string
  availabilityConfirmed?: boolean
  allowMultipleStudents?: boolean
  avoidTeacherNames: string
  remark?: string
}
