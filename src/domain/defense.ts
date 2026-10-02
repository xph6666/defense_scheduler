import sharedPolicy from '../../shared/defense-policy.json'

export const defenseTypes = ['预答辩', '正式答辩', '中期答辩'] as const
export type DefenseType = typeof defenseTypes[number]
export type BackendDefenseType = 'pre' | 'formal' | 'mid'
export type TeacherTitle = '教授' | '副教授' | '讲师' | '其他'

const backendTypes: Record<DefenseType, BackendDefenseType> = {
  '预答辩': 'pre', '正式答辩': 'formal', '中期答辩': 'mid'
}
export const toBackendDefenseType = (type: DefenseType): BackendDefenseType => backendTypes[type]
export const isDefenseType = (value: unknown): value is DefenseType => defenseTypes.includes(value as DefenseType)
export const policyVersion = sharedPolicy.policyVersion as 2
export const getDefensePolicy = (type: DefenseType) => sharedPolicy.scenarios[toBackendDefenseType(type)]
