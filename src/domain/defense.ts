import sharedPolicy from '../../shared/defense-policy.json'

export const defenseTypes = ['预答辩', '正式答辩', '中期答辩'] as const
export type DefenseType = typeof defenseTypes[number]
export type BackendDefenseType = 'pre' | 'formal' | 'mid'
// [TASK-P04 修改] 前端职称类型纳入研究员序列。
export type TeacherTitle = '教授' | '研究员' | '副教授' | '副研究员' | '讲师' | '助教' | '其他' | '外院导师（职称待确认）' | '职称待确认'

const backendTypes: Record<DefenseType, BackendDefenseType> = {
  '预答辩': 'pre', '正式答辩': 'formal', '中期答辩': 'mid'
}
export const toBackendDefenseType = (type: DefenseType): BackendDefenseType => backendTypes[type]
export const isDefenseType = (value: unknown): value is DefenseType => defenseTypes.includes(value as DefenseType)
export const policyVersion = sharedPolicy.policyVersion as 3
export const getDefensePolicy = (type: DefenseType) => sharedPolicy.scenarios[toBackendDefenseType(type)]
