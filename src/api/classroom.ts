import { createMockRepository } from '../utils/mockRepository'
import { STORAGE_KEYS } from '../utils/storageKeys'
import { runtimeConfig } from '../config/runtime'
import request from './request'
import { extractList } from './response'
import type { Classroom } from '../types/classroom'
import { mockClassrooms } from '../utils/mockData'

// Mock Data Storage
const repository = createMockRepository(STORAGE_KEYS.classrooms, mockClassrooms)
let classroomsData = [...mockClassrooms]


const USE_MOCK = runtimeConfig.useMock

export const listClassrooms = async () => {
  if (!USE_MOCK) {
    const result = await request.get('/rooms/')
    return extractList<Classroom>(result)
  }
  classroomsData = repository.read()
  return new Promise<Classroom[]>(resolve => {
    setTimeout(() => resolve([...classroomsData]), 300)
  })
}

export const createClassroom = async (data: Omit<Classroom, 'id'>) => {
  if (!USE_MOCK) {
    return request.post('/rooms/', data) as Promise<Classroom>
  }
  classroomsData = repository.read()
  return new Promise<Classroom>(resolve => {
    setTimeout(() => {
      const newClassroom = { ...data, id: Math.max(0, ...classroomsData.map(item => item.id)) + 1 }
      classroomsData.push(newClassroom)
      repository.write(classroomsData)
      resolve(newClassroom)
    }, 300)
  })
}

export const updateClassroom = async (id: number, data: Partial<Classroom>) => {
  if (!USE_MOCK) {
    return request.put(`/rooms/${id}/`, data) as Promise<Classroom>
  }
  classroomsData = repository.read()
  return new Promise<Classroom>((resolve, reject) => {
    setTimeout(() => {
      const index = classroomsData.findIndex(t => t.id === id)
      if (index !== -1) {
        classroomsData[index] = { ...classroomsData[index], ...data }
        repository.write(classroomsData)
        resolve(classroomsData[index])
      } else {
        reject(new Error('Classroom not found'))
      }
    }, 300)
  })
}

export const deleteClassroom = async (id: number) => {
  if (!USE_MOCK) {
    return request.delete(`/rooms/${id}/`)
  }
  classroomsData = repository.read()
  return new Promise<void>((resolve, reject) => {
    setTimeout(() => {
      const index = classroomsData.findIndex(t => t.id === id)
      if (index !== -1) {
        classroomsData.splice(index, 1)
        repository.write(classroomsData)
        resolve()
      } else {
        reject(new Error('Classroom not found'))
      }
    }, 300)
  })
}

export const importClassrooms = async (file: File) => {
  if (!USE_MOCK) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/rooms/import_data/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  }
  classroomsData = repository.read()
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      resolve({ message: 'Mock: 导入成功（Mock 模式下仅模拟）' })
    }, 500)
  })
}

export const batchDeleteClassrooms = async (ids: number[]) => {
  if (!USE_MOCK) {
    return request.post('/rooms/batch_delete/', { ids })
  }
  classroomsData = repository.read()
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      classroomsData = classroomsData.filter(t => !ids.includes(t.id))
      repository.write(classroomsData)
      resolve({ message: `Mock: 成功删除 ${ids.length} 条数据` })
    }, 300)
  })
}
