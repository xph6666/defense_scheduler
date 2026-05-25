import request from './request'
import type { ScheduleAdjustmentPayload, AdjustmentResult } from '../types/adjustment'
import { updateScheduleGroupInStorage } from '../utils/scheduleStorage'
import { toBackendDefenseType } from './schedule'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export const updateScheduleGroup = async (data: ScheduleAdjustmentPayload) => {
  if (USE_MOCK) {
    const updated = updateScheduleGroupInStorage(data.defenseType, data.groupId, data.groupData)
    if (!updated) {
      throw new Error('保存失败：未找到对应排期数据')
    }
    return {
      success: true,
      message: '调整保存成功',
      updatedGroup: data.groupData
    } satisfies AdjustmentResult
  }

  return request.post('/schedule/adjust-group/', {
    defense_type: toBackendDefenseType(data.defenseType),
    group_id: data.groupId,
    group_data: data.groupData
  }) as Promise<AdjustmentResult>
}
