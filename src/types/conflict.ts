import type { DefenseType } from './schedule'

export type ConflictType =
  | '时间冲突'
  | '教室冲突'
  | '人员冲突'
  | '导师回避冲突'
  | '秘书学生冲突'
  | '不宜同组冲突'
  | '人数规则提示'
  | '校区切换提示'
  | '外院导师集中提示'

export type ConflictLevel = 'error' | 'warning' | 'info'

export interface ScheduleConflict {
  id: number
  defenseType: DefenseType
  groupId?: number
  groupName?: string
  type: ConflictType
  level: ConflictLevel
  target: string
  reason: string
  suggestion?: string
  relatedGroupIds?: number[]
  createdAt: string
}

