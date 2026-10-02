import { createMockRepository } from '../utils/mockRepository'
import { STORAGE_KEYS } from '../utils/storageKeys'
import { runtimeConfig } from '../config/runtime'
import request from './request'
import { extractList } from './response'
import type { Student } from '../types/student'
import { mockStudents } from '../utils/mockData'

// Mock Data Storage
const repository = createMockRepository(STORAGE_KEYS.students, mockStudents)
let studentsData = [...mockStudents]


const USE_MOCK = runtimeConfig.useMock

export const listStudents = async () => {
  if (!USE_MOCK) {
    const result = await request.get('/students/')
    return extractList<Student>(result)
  }
  studentsData = repository.read()
  return new Promise<Student[]>(resolve => {
    setTimeout(() => resolve([...studentsData]), 300)
  })
}

export const createStudent = async (data: Omit<Student, 'id'>) => {
  if (!USE_MOCK) {
    return request.post('/students/', data) as Promise<Student>
  }
  studentsData = repository.read()
  return new Promise<Student>(resolve => {
    setTimeout(() => {
      const newStudent = { ...data, id: Math.max(0, ...studentsData.map(item => item.id)) + 1 }
      studentsData.push(newStudent)
      repository.write(studentsData)
      resolve(newStudent)
    }, 300)
  })
}

export const updateStudent = async (id: number, data: Partial<Student>) => {
  if (!USE_MOCK) {
    return request.put(`/students/${id}/`, data) as Promise<Student>
  }
  studentsData = repository.read()
  return new Promise<Student>((resolve, reject) => {
    setTimeout(() => {
      const index = studentsData.findIndex(t => t.id === id)
      if (index !== -1) {
        studentsData[index] = { ...studentsData[index], ...data }
        repository.write(studentsData)
        resolve(studentsData[index])
      } else {
        reject(new Error('Student not found'))
      }
    }, 300)
  })
}

export const deleteStudent = async (id: number) => {
  if (!USE_MOCK) {
    return request.delete(`/students/${id}/`)
  }
  studentsData = repository.read()
  return new Promise<void>((resolve, reject) => {
    setTimeout(() => {
      const index = studentsData.findIndex(t => t.id === id)
      if (index !== -1) {
        studentsData.splice(index, 1)
        repository.write(studentsData)
        resolve()
      } else {
        reject(new Error('Student not found'))
      }
    }, 300)
  })
}

export const importStudents = async (file: File) => {
  if (!USE_MOCK) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/students/import_data/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  }
  studentsData = repository.read()
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      resolve({ message: 'Mock: 导入成功（Mock 模式下仅模拟）' })
    }, 500)
  })
}

export const batchDeleteStudents = async (ids: number[]) => {
  if (!USE_MOCK) {
    return request.post('/students/batch_delete/', { ids })
  }
  studentsData = repository.read()
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      studentsData = studentsData.filter(t => !ids.includes(t.id))
      repository.write(studentsData)
      resolve({ message: `Mock: 成功删除 ${ids.length} 条数据` })
    }, 300)
  })
}
