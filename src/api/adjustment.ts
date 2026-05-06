import request from './request'
import type { ScheduleAdjustmentPayload, AdjustmentResult } from '../types/adjustment'

export const updateScheduleGroup = (data: ScheduleAdjustmentPayload) => {
  return request.post('/schedule/adjust-group/', data) as Promise<AdjustmentResult>
}

