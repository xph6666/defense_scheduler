import request from './request'
import type { Classroom } from '../types/classroom'
import { mockClassrooms } from '../utils/mockData'

// Mock Data Storage
let classroomsData = [...mockClassrooms]
let nextId = 6

export const listClassrooms = async () => {
  // return request.get('/classrooms')
  return new Promise<Classroom[]>(resolve => {
    setTimeout(() => resolve([...classroomsData]), 300)
  })
}

export const createClassroom = async (data: Omit<Classroom, 'id'>) => {
  // return request.post('/classrooms', data)
  return new Promise<Classroom>(resolve => {
    setTimeout(() => {
      const newClassroom = { ...data, id: nextId++ }
      classroomsData.push(newClassroom)
      resolve(newClassroom)
    }, 300)
  })
}

export const updateClassroom = async (id: number, data: Partial<Classroom>) => {
  // return request.put(`/classrooms/${id}`, data)
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
  // return request.delete(`/classrooms/${id}`)
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
