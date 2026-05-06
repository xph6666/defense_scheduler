export interface Teacher {
  id: number
  name: string
  college: string
  isExternal: boolean
  title: '教授' | '副教授' | '讲师' | '其他'
  roles: string[]
  availableTypes: string[]
  campusPreference: '创新港' | '兴庆' | '不限'
  unavailableTimes: string
  avoidTeacherNames: string
  remark?: string
}
