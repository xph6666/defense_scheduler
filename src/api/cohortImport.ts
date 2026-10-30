import request from './request'
import type { DefenseType } from '../domain/defense'

// Parsing up to ten workbooks and validating thousands of rows can exceed the
// 10s default. Allow the server's 180s import window before giving up.
const IMPORT_TIMEOUT_MS = 3 * 60 * 1000

export interface CohortSource { file: string; sheet: string; row?: number }
export interface CohortFile { kind: 'teacher' | 'student'; index: number; name: string; sheets: string[]; sheetName: string }
export interface CohortStudent {
  key: string; sources: CohortSource[]; name: string; studentNo: string; mentorName: string
  campus: string; action: 'create' | 'update' | 'keep'; externalMentor: boolean
  remark?: string
}
export interface CohortTeacher {
  key: string; sources: CohortSource[]; name: string; title: string; college: string; roles: string[]
  expertOnly: boolean; isExternal: boolean; studentCount: number; action: 'create' | 'update' | 'keep'
}
export interface CohortPreview {
  preview: true; canImport: boolean
  stats: { students: number; totalStudents: number; excludedStudents: number; teachers: number; softwareTeachers: number; externalMentors: number; newTeachers: number; newStudents: number; duplicateStudentRows: number }
  teachers: CohortTeacher[]; students: CohortStudent[]; excludedStudents: CohortStudent[]; files: CohortFile[]
  errors: { key: string; sources: CohortSource[]; errors: Record<string, unknown> }[]; warnings: string[]
}
export interface CohortOptions {
  defenseTypes: DefenseType[]; campus: string; teacherSheet: string
  studentSheets: Record<string, string>; corrections: Record<string, { campus: string }>
}

export async function uploadCohort(teacher: File, students: File[], options: CohortOptions, preview: true): Promise<CohortPreview>
export async function uploadCohort(teacher: File, students: File[], options: CohortOptions, preview: false): Promise<{ message: string; stats: CohortPreview['stats'] }>
export async function uploadCohort(teacher: File, students: File[], options: CohortOptions, preview: boolean) {
  const form = new FormData()
  form.append('teacherFile', teacher)
  students.forEach(file => form.append('studentFiles', file))
  form.append('preview', String(preview))
  Object.entries(options).forEach(([key, value]) => form.append(key, typeof value === 'string' ? value : JSON.stringify(value)))
  return await request.post('/students/import-cohort/', form, { timeout: IMPORT_TIMEOUT_MS }) as unknown as CohortPreview | { message: string; stats: CohortPreview['stats'] }
}
