import { runtimeConfig } from '../config/runtime'
import request from './request'
import type { ScheduleAdjustmentPayload, AdjustmentResult } from '../types/adjustment'
import { checkConflictsMock } from '../utils/conflictMock'
import { getScheduleResult, saveScheduleResult, updateScheduleGroupInStorage } from '../utils/scheduleStorage'
import { toBackendDefenseType } from '../domain/defense'

const USE_MOCK = runtimeConfig.useMock

export const updateScheduleGroup = async (data: ScheduleAdjustmentPayload) => {
  if (USE_MOCK) {
    const current = getScheduleResult(data.defenseType)
    if (current?.status === 'published') throw new Error('已发布排期不能修改，请生成新草稿')
    if (data.expectedRevision !== undefined && current?.revision !== data.expectedRevision) throw new Error('排期已更新，请刷新后重试')
    const updated = updateScheduleGroupInStorage(data.defenseType, data.groupId, data.groupData)
    if (!updated) {
      throw new Error('保存失败：未找到对应排期数据')
    }
    updated.revision = (updated.revision || 1) + 1
    updated.conflicts = checkConflictsMock(updated)
    saveScheduleResult(updated)
    return {
      success: true,
      message: '调整保存成功',
      updatedGroup: data.groupData
    } satisfies AdjustmentResult
  }

  return request.post('/schedule/adjust-group/', {
    defense_type: toBackendDefenseType(data.defenseType),
    group_id: data.groupId,
    expected_revision: data.expectedRevision,
    group_data: data.groupData
  }) as Promise<AdjustmentResult>
}
