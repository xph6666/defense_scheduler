import type { RuleConfig } from '../types/ruleConfig'
import { getDefensePolicy, policyVersion, toBackendDefenseType, type DefenseType } from './defense'

export function normalizeRuleConfig(config: RuleConfig): RuleConfig {
  const policy = getDefensePolicy(config.defenseType)
  const oldWeights = Object.values(config.softWeights || {})
  const legacyWeights = !config.policyVersion && oldWeights.length > 0 && oldWeights.every(weight => weight >= 0 && weight <= 10)
  const softWeights = { ...policy.softWeights, ...config.softWeights }
  if (legacyWeights) for (const key of Object.keys(config.softWeights) as (keyof typeof softWeights)[]) softWeights[key] *= 10
  const current = config.defenseType !== '中期答辩'
  const expertCount = current ? {
    target: config.policyVersion === 3 && config.expertCount?.target === 5 ? 5 : 3,
    min: config.policyVersion === 3 && config.expertCount?.target === 5 ? 5 : 3
  } : {
    target: Math.max(policy.expertCount.min, config.expertCount?.target || policy.expertCount.target),
    min: Math.max(policy.expertCount.min, config.expertCount?.min || policy.expertCount.min)
  }
  expertCount.target = Math.max(expertCount.target, expertCount.min)
  return {
    ...config,
    policyVersion: current ? policyVersion : 2,
    expertCountIncludesChair: true,
    expertCount,
    studentCount: current ? {
      target: config.studentCount?.target >= 5 && config.studentCount.target <= 7 ? config.studentCount.target : 6,
      min: 5, max: 7
    } : config.studentCount,
    secretaryCount: 1,
    courseHalfDayBlocking: config.courseHalfDayBlocking ?? true,
    formalSoftwareMin: 0,
    includeRemarks: config.includeRemarks ?? true,
    preservePreDefenseGroups: config.preservePreDefenseGroups ?? true,
    campusStartDates: { ...config.campusStartDates },
    roleQualification: { ...policy.roleQualification, ...config.roleQualification } as RuleConfig['roleQualification'],
    softWeights
  }
}

export function buildScheduleRules(defenseType: DefenseType, input: RuleConfig) {
  const config = normalizeRuleConfig({ ...input, defenseType })
  return {
    policy_version: config.policyVersion,
    defense_type: toBackendDefenseType(defenseType),
    start_date: config.startDate,
    end_date: config.endDate,
    campus_start_dates: defenseType === '中期答辩' ? Object.fromEntries(Object.entries(config.campusStartDates || {}).filter(([, date]) => !!date)) : {},
    group_size: config.studentCount.target,
    group_min: config.studentCount.min,
    group_max: config.studentCount.max,
    expert_count: config.expertCount.target,
    expert_min: config.expertCount.min,
    expert_count_includes_chair: true,
    secretary_count: config.secretaryCount,
    avoid_weekend: config.avoidWeekend,
    avoid_holiday: config.avoidHoliday,
    exclude_dates: config.avoidHoliday ? (config.excludeDates || []) : [],
    supervisor_policy: defenseType === '正式答辩' ? (config.mentorAvoidance ? 'avoid' : 'none') : 'same_group',
    grouping: defenseType === '正式答辩' && config.preservePreDefenseGroups ? 'secretary' : 'supervisor',
    avoid_supervisor: defenseType === '正式答辩' && config.mentorAvoidance,
    need_chair: true,
    chair_title: defenseType === '正式答辩' ? config.roleQualification.chairmanMinTitle || '教授' : config.roleQualification.leaderMinTitle || '副教授',
    secretary_title: config.roleQualification.secretaryMinTitle,
    prefer_senior: config.roleQualification.preferSeniorTitle,
    course_half_day_blocking: config.courseHalfDayBlocking,
    formal_software_min: config.formalSoftwareMin,
    include_remarks: config.includeRemarks,
    preserve_pre_defense_groups: config.preservePreDefenseGroups,
    formal_mentor_same_session: defenseType === '正式答辩',
    soft_weights: {
      balance_student_count: config.softWeights.balanceStudentCount,
      prefer_senior_teacher: config.softWeights.preferSeniorTeacher,
      avoid_cross_campus: config.softWeights.avoidCrossCampus,
      external_mentor_concentration: config.softWeights.externalMentorConcentration,
      prefer_academic_master_first: config.softWeights.preferAcademicMasterFirst
    }
  }
}
