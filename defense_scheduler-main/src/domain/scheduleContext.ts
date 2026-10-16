import type { DefenseType } from './defense'

export interface ScheduleRequestContext {
  sequence: number
  defenseType: DefenseType
  versionId?: number
}

/** One request owns the selected schedule until a newer request or navigation replaces it. */
export function createScheduleRequestScope() {
  let sequence = 0
  return {
    begin(defenseType: DefenseType, versionId?: number): ScheduleRequestContext {
      return { sequence: ++sequence, defenseType, versionId }
    },
    invalidate() { sequence += 1 },
    isCurrent(context: ScheduleRequestContext, defenseType: DefenseType, versionId?: number) {
      return context.sequence === sequence && context.defenseType === defenseType && context.versionId === versionId
    }
  }
}
