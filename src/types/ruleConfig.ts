import type { DefenseType, TeacherTitle } from '../domain/defense'
export type { DefenseType, TeacherTitle } from '../domain/defense'

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
  policyVersion?: 2
  expertCountIncludesChair?: boolean
  courseHalfDayBlocking?: boolean
  formalSoftwareMin?: number
  includeRemarks?: boolean
  preservePreDefenseGroups?: boolean
  campusStartDates?: Record<string, string>
  defenseType: DefenseType
  enabled: boolean
  startDate: string
  endDate: string
  avoidWeekend: boolean
  avoidHoliday: boolean
  // 需要排除的具体日期（法定节假日等），格式 YYYY-MM-DD
  excludeDates?: string[]
  mentorAvoidance: boolean
  studentCount: StudentCountConfig
  expertCount: ExpertCountConfig
  secretaryCount: number
  roleQualification: RoleQualificationConfig
  softWeights: SoftConstraintWeightConfig
  updatedAt?: string
}
