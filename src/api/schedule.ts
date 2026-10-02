import { runtimeConfig } from '../config/runtime'
import request, { isNotFoundError } from './request'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import type { RuleConfig } from '../types/ruleConfig'
import { buildScheduleRules } from '../domain/scheduleRules'
import { defenseTypes } from '../domain/defense'
import { generateMockScheduleResult } from '../utils/scheduleMock'
import { getScheduleResult, saveScheduleResult } from '../utils/scheduleStorage'
import { getDefaultRuleConfig } from '../utils/ruleConfigStorage'
import { checkConflictsMock } from '../utils/conflictMock'
export { toBackendDefenseType } from '../domain/defense'
import { toBackendDefenseType } from '../domain/defense'

const USE_MOCK = runtimeConfig.useMock

export async function getScheduleResults(defenseType: DefenseType, versionId?: number): Promise<ScheduleResult | null> {
  if (USE_MOCK) return getScheduleResult(defenseType)
  try {
    return await request.get('/schedule/current/', {
      params: { defense_type: toBackendDefenseType(defenseType), version_id: versionId }
    }) as ScheduleResult
  } catch (error) {
    if (isNotFoundError(error) && versionId === undefined) return null
    throw error
  }
}

/** A timeout can be retried with the same key; a different rule payload starts a new request. */
function generationKey(storageKey: string, payload: unknown) {
  let pending: { rules: string; key: string } | null = null
  try { pending = JSON.parse(sessionStorage.getItem(storageKey) || 'null') } catch { /* malformed optional state */ }
  const fingerprint = JSON.stringify(payload)
  if (!pending || pending.rules !== fingerprint) {
    pending = { rules: fingerprint, key: crypto.randomUUID() }
    sessionStorage.setItem(storageKey, JSON.stringify(pending))
  }
  return pending.key
}

function mockDraft(defenseType: DefenseType) {
  const previous = getScheduleResult(defenseType)
  const result = generateMockScheduleResult(defenseType)
  result.versionId = Date.now() + defenseTypes.indexOf(defenseType)
  result.version = (previous?.version || 0) + 1
  result.revision = 1
  result.status = 'draft'
  result.isCurrent = true
  result.conflicts = checkConflictsMock(result)
  saveScheduleResult(result)
  return result
}

export async function generateSchedule(defenseType: DefenseType, config = getDefaultRuleConfig(defenseType)) {
  if (USE_MOCK) return mockDraft(defenseType)
  const rules = buildScheduleRules(defenseType, config)
  const storageKey = `pending-generation-${defenseType}`
  const result = await request.post('/schedule/generate/', {
    rules, request_key: generationKey(storageKey, rules)
  }, { timeout: 120000 }) as ScheduleResult
  sessionStorage.removeItem(storageKey)
  return result
}

export interface LinkedScheduleResult { pre: ScheduleResult; formal: ScheduleResult }

export async function generateLinkedSchedule(preConfig: RuleConfig, formalConfig: RuleConfig): Promise<LinkedScheduleResult> {
  if (USE_MOCK) {
    const pre = mockDraft('预答辩')
    const formal = mockDraft('正式答辩')
    formal.groups = formal.groups.map((group, index) => ({
      ...group,
      students: pre.groups[index]?.students.map(student => ({ ...student })) || group.students,
      secretary: pre.groups[index]?.secretary || group.secretary,
      secretaryId: pre.groups[index]?.secretaryId || group.secretaryId
    }))
    formal.conflicts = checkConflictsMock(formal)
    saveScheduleResult(formal)
    return { pre, formal }
  }
  const payload = {
    pre_rules: buildScheduleRules('预答辩', preConfig),
    formal_rules: buildScheduleRules('正式答辩', formalConfig)
  }
  const storageKey = 'pending-generation-linked'
  const result = await request.post('/schedule/generate-linked/', {
    ...payload, request_key: generationKey(storageKey, payload)
  }, { timeout: 120000 }) as LinkedScheduleResult
  sessionStorage.removeItem(storageKey)
  return result
}

export interface ScheduleVersionOption {
  id: number
  version: number
  status: 'draft' | 'published'
  is_current: boolean
  created_at: string
  revision: number
}

export async function listScheduleVersions(defenseType: DefenseType): Promise<ScheduleVersionOption[]> {
  if (USE_MOCK) {
    const result = getScheduleResult(defenseType)
    return result?.versionId ? [{ id: result.versionId, version: result.version || 1, status: result.status || 'draft', is_current: true, created_at: result.generatedAt, revision: result.revision || 1 }] : []
  }
  return request.get('/schedule/versions/', { params: { defense_type: toBackendDefenseType(defenseType) } }) as Promise<ScheduleVersionOption[]>
}

function editableMock(versionId?: number, groupId?: number, revision?: number) {
  const result = defenseTypes.map(getScheduleResult).find(result => result && (versionId !== undefined ? result.versionId === versionId : result.groups.some(group => group.id === groupId)))
  if (!result) throw new Error('未找到对应排期')
  if (result.status === 'published') throw new Error('已发布的排期不能修改，请生成新草稿')
  if (revision !== undefined && result.revision !== revision) throw new Error('排期已更新，请刷新后重试')
  return result
}

export async function publishSchedule(versionId: number, revision: number): Promise<ScheduleResult> {
  if (USE_MOCK) {
    const result = editableMock(versionId, undefined, revision)
    result.conflicts = checkConflictsMock(result)
    if (result.conflicts.some(conflict => conflict.level === 'error')) throw new Error('请先处理硬冲突后再发布')
    const published = { ...result, status: 'published' as const, revision: revision + 1 }
    saveScheduleResult(published)
    return published
  }
  return request.post('/schedule/publish/', { version_id: versionId, expected_revision: revision }) as Promise<ScheduleResult>
}

export interface StudentMoveOptions { preserveSecretary?: boolean; moveMentor?: boolean; secretaryId?: number | null }

export async function moveScheduleStudent(studentId: number, fromGroupId: number, toGroupId: number, revision?: number, options: StudentMoveOptions = {}) {
  const preserveSecretary = options.preserveSecretary ?? true
  const moveMentor = options.moveMentor ?? true
  if (USE_MOCK) {
    const result = editableMock(undefined, fromGroupId, revision)
    const source = result.groups.find(group => group.id === fromGroupId)
    const target = result.groups.find(group => group.id === toGroupId)
    const student = source?.students.find(student => student.id === studentId)
    if (!source || !target || !student || source === target) throw new Error('请选择不同的有效目标组')
    if (!preserveSecretary) {
      student.secretaryId = options.secretaryId ?? null
      student.secretaryName = options.secretaryId ? result.groups.flatMap(group => group.teachers).find(teacher => teacher.id === options.secretaryId)?.name || '' : ''
    }
    source.students = source.students.filter(item => item.id !== studentId)
    target.students.push(student)
    if (moveMentor && result.defenseType !== '正式答辩') {
      const mentor = source.teachers.find(teacher => student.mentorId ? teacher.id === student.mentorId : teacher.name === student.mentorName)
      if (mentor && !target.teachers.some(teacher => teacher.id === mentor.id)) target.teachers.push({ ...mentor })
    }
    result.revision = (result.revision || 1) + 1
    result.conflicts = checkConflictsMock(result)
    saveScheduleResult(result)
    return result
  }
  return request.post('/schedule/adjust/', {
    action: 'move_student', student_id: studentId, from_group_id: fromGroupId,
    to_group_id: toGroupId, expected_revision: revision,
    preserve_secretary: preserveSecretary, move_mentor: moveMentor,
    ...(!preserveSecretary ? { secretary_id: options.secretaryId ?? null } : {})
  })
}
