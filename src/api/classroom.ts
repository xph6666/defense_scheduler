import request from './request'
import type { Classroom } from '../types/classroom'
import { mockClassrooms } from '../utils/mockData'

// Mock Data Storage
let classroomsData = [...mockClassrooms]
let nextId = 6

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

export const listClassrooms = async () => {
  if (!USE_MOCK) {
    return request.get('/rooms/') as Promise<Classroom[]>
  }
  return new Promise<Classroom[]>(resolve => {
    setTimeout(() => resolve([...classroomsData]), 300)
  })
}

export const createClassroom = async (data: Omit<Classroom, 'id'>) => {
  if (!USE_MOCK) {
    return request.post('/rooms/', data) as Promise<Classroom>
  }
  return new Promise<Classroom>(resolve => {
    setTimeout(() => {
      const newClassroom = { ...data, id: nextId++ }
      classroomsData.push(newClassroom)
      resolve(newClassroom)
    }, 300)
  })
}

export const updateClassroom = async (id: number, data: Partial<Classroom>) => {
  if (!USE_MOCK) {
    return request.put(`/rooms/${id}/`, data) as Promise<Classroom>
  }
  return new Promise<Classroom>((resolve, reject) => {
    setTimeout(() => {
      const index = classroomsData.findIndex(t => t.id === id)
      if (index !== -1) {
        classroomsData[index] = { ...classroomsData[index], ...data }
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
  return new Promise<void>((resolve, reject) => {
    setTimeout(() => {
      const index = classroomsData.findIndex(t => t.id === id)
      if (index !== -1) {
        classroomsData.splice(index, 1)
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
  return new Promise<{ message: string }>(resolve => {
    setTimeout(() => {
      classroomsData = classroomsData.filter(t => !ids.includes(t.id))
      resolve({ message: `Mock: 成功删除 ${ids.length} 条数据` })
    }, 300)
  })
}
