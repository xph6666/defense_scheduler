import { onBeforeUnmount, watch, type Ref } from 'vue'
import type { DefenseType } from '../domain/defense'
import { createScheduleRequestScope, type ScheduleRequestContext } from '../domain/scheduleContext'
import type { ScheduleResult } from '../types/schedule'

export interface ScheduleContext extends ScheduleRequestContext { resultVersionId?: number; revision?: number; campusScope?: string }

export function useScheduleContext(defenseType: Ref<DefenseType>, versionId: Ref<number | undefined>, result: Ref<ScheduleResult | null>, campusScope?: Ref<string>) {
  const scope = createScheduleRequestScope()
  let active = scope.begin(defenseType.value, versionId.value)
  const capture = (): ScheduleContext => ({ ...active, resultVersionId: result.value?.versionId, revision: result.value?.revision, campusScope: campusScope?.value })
  const begin = () => { active = scope.begin(defenseType.value, versionId.value); return capture() }
  const isCurrent = (context: ScheduleContext, requireRevision = false) => scope.isCurrent(context, defenseType.value, versionId.value)
    && context.campusScope === campusScope?.value
    && (!requireRevision || (context.resultVersionId === result.value?.versionId && context.revision === result.value?.revision))
  watch([defenseType, versionId], () => scope.invalidate(), { flush: 'sync' })
  if (campusScope) watch(campusScope, () => scope.invalidate(), { flush: 'sync' })
  onBeforeUnmount(() => scope.invalidate())
  return { begin, capture, isCurrent }
}
