import type { ScheduleGroup, DefenseType } from './schedule'

export interface ScheduleAdjustmentPayload {
  defenseType: DefenseType
  groupId: number
  groupData: ScheduleGroup
}

export interface AdjustmentResult {
  success: boolean
  message: string
  updatedGroup: ScheduleGroup
}

