import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { DefenseType } from '../types/schedule'

import { isDefenseType } from '../domain/defense'
export { defenseTypes } from '../domain/defense'
let saved: string | null = null
try { saved = sessionStorage.getItem('workflow-defense-type') } catch { /* optional preference */ }
export const workflowDefenseType = ref<DefenseType>(isDefenseType(saved) ? saved : '预答辩')
export const workflowLink = (path: string) => ({ path, query: { type: workflowDefenseType.value } })

export function useDefenseType() {
  const route = useRoute()
  const router = useRouter()
  watch(() => route.query.type, value => {
    if (isDefenseType(value)) workflowDefenseType.value = value
  }, { immediate: true })
  watch(workflowDefenseType, value => {
    try { sessionStorage.setItem('workflow-defense-type', value) } catch { /* optional preference */ }
    if (route.query.type !== value) void router.replace({ query: { ...route.query, type: value } })
  })
  return workflowDefenseType
}
