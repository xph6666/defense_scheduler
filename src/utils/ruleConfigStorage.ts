import type { DefenseType, RuleConfig } from '../types/ruleConfig'

const STORAGE_KEY_PREFIX = 'rule_config_'

export function getDefaultRuleConfig(defenseType: DefenseType): RuleConfig {
  const base = {
    defenseType,
    enabled: true,
    startDate: new Date().toISOString().split('T')[0],
    avoidWeekend: true,
    avoidHoliday: true,
    mentorAvoidance: false,
    studentCount: { target: 6, min: 4, max: 8 },
    expertCount: { target: 3, min: 3 },
    secretaryCount: 1,
    roleQualification: {
      leaderMinTitle: '副教授',
      secretaryMinTitle: '讲师',
      preferSeniorTitle: true
    },
    softWeights: {
      balanceStudentCount: 5,
      preferSeniorTeacher: 8,
      avoidCrossCampus: 3,
      externalMentorConcentration: 2,
      preferAcademicMasterFirst: 0
    }
  }

  if (defenseType === '正式答辩') {
    return {
      ...base,
      mentorAvoidance: true,
      expertCount: { target: 5, min: 5 },
      roleQualification: {
        chairmanMinTitle: '教授',
        secretaryMinTitle: '讲师',
        preferSeniorTitle: true
      },
      softWeights: {
        balanceStudentCount: 5,
        preferSeniorTeacher: 9,
        avoidCrossCampus: 5,
        externalMentorConcentration: 4,
        preferAcademicMasterFirst: 7
      }
    }
  }

  if (defenseType === '中期答辩') {
    return {
      ...base,
      studentCount: { target: 12, min: 10, max: 13 },
      expertCount: { target: 5, min: 5 },
      softWeights: {
        balanceStudentCount: 8,
        preferSeniorTeacher: 5,
        avoidCrossCampus: 7,
        externalMentorConcentration: 3,
        preferAcademicMasterFirst: 0
      }
    }
  }

  return base as RuleConfig
}

export function getRuleConfigFromStorage(defenseType: DefenseType): RuleConfig {
  const saved = localStorage.getItem(`${STORAGE_KEY_PREFIX}${defenseType}`)
  if (saved) {
    try {
      return JSON.parse(saved)
    } catch (e) {
      console.error('Failed to parse rule config', e)
    }
  }
  return getDefaultRuleConfig(defenseType)
}

export function saveRuleConfigToStorage(config: RuleConfig): void {
  config.updatedAt = new Date().toLocaleString()
  localStorage.setItem(`${STORAGE_KEY_PREFIX}${config.defenseType}`, JSON.stringify(config))
}

export function resetRuleConfig(defenseType: DefenseType): RuleConfig {
  const defaultConfig = getDefaultRuleConfig(defenseType)
  saveRuleConfigToStorage(defaultConfig)
  return defaultConfig
}

export function getAllRuleConfigs(): RuleConfig[] {
  const types: DefenseType[] = ['预答辩', '正式答辩', '中期答辩']
  return types.map(t => getRuleConfigFromStorage(t))
}
