import request from './request'
import type { Teacher } from '../types/teacher'
import { mockTeachers } from '../utils/mockData'

// Mock Data Storage
let teachersData = [...mockTeachers]
let nextId = 11

export const listTeachers = async () => {
  // return request.get('/teachers')
  return new Promise<Teacher[]>(resolve => {
    setTimeout(() => resolve([...teachersData]), 300)
  })
}

export const createTeacher = async (data: Omit<Teacher, 'id'>) => {
  // return request.post('/teachers', data)
  return new Promise<Teacher>(resolve => {
    setTimeout(() => {
      const newTeacher = { ...data, id: nextId++ }
      teachersData.push(newTeacher)
      resolve(newTeacher)
    }, 300)
  })
}

export const updateTeacher = async (id: number, data: Partial<Teacher>) => {
  // return request.put(`/teachers/${id}`, data)
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
  // return request.delete(`/teachers/${id}`)
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
