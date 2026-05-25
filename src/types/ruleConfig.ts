export type DefenseType = '预答辩' | '正式答辩' | '中期答辩'

export type TeacherTitle = '教授' | '副教授' | '讲师' | '其他'

export interface RoleQualificationConfig {
  leaderMinTitle?: TeacherTitle
  chairmanMinTitle?: TeacherTitle
  secretaryMinTitle: TeacherTitle
  preferSeniorTitle: boolean
}

export interface StudentCountConfig {
  target: number
  min: number
  max: number
}

export interface ExpertCountConfig {
  target: number
  min: number
}

export interface SoftConstraintWeightConfig {
  balanceStudentCount: number
  preferSeniorTeacher: number
  avoidCrossCampus: number
  externalMentorConcentration: number
  preferAcademicMasterFirst: number
}

export interface RuleConfig {
  defenseType: DefenseType
  enabled: boolean
  startDate: string
  avoidWeekend: boolean
  avoidHoliday: boolean
  mentorAvoidance: boolean
  studentCount: StudentCountConfig
  expertCount: ExpertCountConfig
  secretaryCount: number
  roleQualification: RoleQualificationConfig
  softWeights: SoftConstraintWeightConfig
  updatedAt?: string
}
