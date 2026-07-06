import request from './request'
import { extractList } from './response'
import type { Teacher } from '../types/teacher'
import { mockTeachers } from '../utils/mockData'

// Mock Data Storage
let teachersData = [...mockTeachers]
let nextId = 11

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export const listTeachers = async () => {
  if (!USE_MOCK) {
    const response = await request.get('/teachers/')
    return extractList<Teacher>(response)
  }
  return new Promise<Teacher[]>(resolve => {
    setTimeout(() => resolve([...teachersData]), 300)
  })
}

export const createTeacher = async (data: Omit<Teacher, 'id'>) => {
  if (!USE_MOCK) {
    return request.post('/teachers/', data) as Promise<Teacher>
  }
  return new Promise<Teacher>(resolve => {
    setTimeout(() => {
      const newTeacher = { ...data, id: nextId++ }
      teachersData.push(newTeacher)
      resolve(newTeacher)
    }, 300)
  })
}

export const updateTeacher = async (id: number, data: Partial<Teacher>) => {
  if (!USE_MOCK) {
    return request.put(`/teachers/${id}/`, data) as Promise<Teacher>
  }
  return new Promise<Teacher>((resolve, reject) => {
    setTimeout(() => {
      const index = teachersData.findIndex(t => t.id === id)
      if (index !== -1) {
        teachersData[index] = { ...teachersData[index], ...data }
        resolve(teachersData[index])
      } else {
        reject(new Error('Teacher not found'))
      }
    }, 300)
  })
}

export const deleteTeacher = async (id: number) => {
  if (!USE_MOCK) {
    return request.delete(`/teachers/${id}/`)
  }
  return new Promise<void>((resolve, reject) => {
    setTimeout(() => {
      const index = teachersData.findIndex(t => t.id === id)
      if (index !== -1) {
        teachersData.splice(index, 1)
        resolve()
      } else {
        reject(new Error('Teacher not found'))
      }
    }, 300)
  })
}

export const importTeachers = async (file: File) => {
  if (!USE_MOCK) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/teachers/import_data/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  }
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      resolve({ message: 'Mock: 导入成功（Mock 模式下仅模拟）' })
    }, 500)
  })
}

export interface TimetableImportResult {
  message: string
  updatedTeachers: number
  matchedTeachers: number
  unknownTeachers: number
  unknownTeacherNames: string[]
  warnings: string[]
  entryCount: number
}

export const importTimetable = async (file: File, semesterFirstMonday: string) => {
  if (!USE_MOCK) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('semesterFirstMonday', semesterFirstMonday)
    return request.post('/teachers/import_timetable/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }) as Promise<TimetableImportResult>
  }
  return new Promise<TimetableImportResult>(resolve => {
    setTimeout(() => {
      resolve({
        message: 'Mock: 课表导入成功（Mock 模式下仅模拟）',
        updatedTeachers: 0,
        matchedTeachers: 0,
        unknownTeachers: 0,
        unknownTeacherNames: [],
        warnings: [],
        entryCount: 0
      })
    }, 500)
  })
}

export const batchDeleteTeachers = async (ids: number[]) => {
  if (!USE_MOCK) {
    return request.post('/teachers/batch_delete/', { ids })
  }
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      teachersData = teachersData.filter(t => !ids.includes(t.id))
      resolve({ message: `Mock: 成功删除 ${ids.length} 条数据` })
    }, 300)
  })
}
