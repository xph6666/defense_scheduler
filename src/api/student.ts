import request from './request'
import type { Student } from '../types/student'
import { mockStudents } from '../utils/mockData'

// Mock Data Storage
let studentsData = [...mockStudents]
let nextId = 31

export const listStudents = async () => {
  // return request.get('/students')
  return new Promise<Student[]>(resolve => {
    setTimeout(() => resolve([...studentsData]), 300)
  })
}

export const createStudent = async (data: Omit<Student, 'id'>) => {
  // return request.post('/students', data)
  return new Promise<Student>(resolve => {
    setTimeout(() => {
      const newStudent = { ...data, id: nextId++ }
      studentsData.push(newStudent)
      resolve(newStudent)
    }, 300)
  })
}

export const updateStudent = async (id: number, data: Partial<Student>) => {
  // return request.put(`/students/${id}`, data)
  return new Promise<Student>((resolve, reject) => {
    setTimeout(() => {
      const index = studentsData.findIndex(t => t.id === id)
      if (index !== -1) {
        studentsData[index] = { ...studentsData[index], ...data }
        resolve(studentsData[index])
      } else {
        reject(new Error('Student not found'))
      }
    }, 300)
  })
}

export const deleteStudent = async (id: number) => {
  // return request.delete(`/students/${id}`)
  return new Promise<void>((resolve, reject) => {
    setTimeout(() => {
      const index = studentsData.findIndex(t => t.id === id)
      if (index !== -1) {
        studentsData.splice(index, 1)
        resolve()
      } else {
        reject(new Error('Student not found'))
      }
    }, 300)
  })
}
