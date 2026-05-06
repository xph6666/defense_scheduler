import { mockTeachers, mockStudents, mockClassrooms } from './mockData'
import type { DefenseType, ScheduleResult, ScheduleGroup, ScheduleTeacher, ScheduleStudent } from '../types/schedule'

const mapTeacher = (id: number): ScheduleTeacher => {
  const t = mockTeachers.find(x => x.id === id)!
  return {
    id: t.id,
    name: t.name,
    title: t.title,
    roles: t.roles,
    college: t.college,
    isExternal: t.isExternal
  }
}

const mapStudent = (id: number): ScheduleStudent => {
  const s = mockStudents.find(x => x.id === id)!
  return {
    id: s.id,
    name: s.name,
    studentType: s.studentType,
    mentorName: s.mentorName,
    secretaryName: s.secretaryName
  }
}

const pickClassroom = (idx: number) => mockClassrooms[idx % mockClassrooms.length]

const pickStudentsByDefenseType = (defenseType: DefenseType) => {
  return mockStudents.filter(s => s.defenseTypes.includes(defenseType))
}

const buildGroups = (defenseType: DefenseType): ScheduleGroup[] => {
  if (defenseType === '预答辩') {
    const baseStudents = pickStudentsByDefenseType(defenseType)
    const groupStudents = (start: number) => Array.from({ length: 6 }, (_, i) => mapStudent(baseStudents[(start + i) % baseStudents.length].id))

    return [
      {
        id: 101,
        defenseType,
        groupName: '预答辩第 1 组',
        campus: pickClassroom(0).campus,
        classroom: pickClassroom(0).name,
        date: '2026-05-06',
        timeRange: '09:00-10:30',
        leader: mapTeacher(2).name,
        secretary: mapTeacher(3).name,
        teachers: [mapTeacher(2), mapTeacher(8), mapTeacher(1)],
        students: groupStudents(0),
        status: 'normal',
        remark: '本周版本仅展示结果，后续支持人工调整。'
      },
      {
        id: 102,
        defenseType,
        groupName: '预答辩第 2 组',
        campus: pickClassroom(1).campus,
        classroom: pickClassroom(1).name,
        date: '2026-05-06',
        timeRange: '10:45-12:15',
        leader: mapTeacher(5).name,
        secretary: mapTeacher(10).name,
        teachers: [mapTeacher(5), mapTeacher(8), mapTeacher(1)],
        students: groupStudents(6),
        status: 'normal'
      },
      {
        id: 103,
        defenseType,
        groupName: '预答辩第 3 组',
        campus: pickClassroom(2).campus,
        classroom: pickClassroom(2).name,
        date: '2026-05-07',
        timeRange: '14:00-15:30',
        leader: mapTeacher(9).name,
        secretary: mapTeacher(3).name,
        teachers: [mapTeacher(9), mapTeacher(8), mapTeacher(2)],
        students: groupStudents(12),
        status: 'warning',
        remark: '预留：后续将提示时间冲突或专家冲突。'
      }
    ]
  }

  if (defenseType === '正式答辩') {
    const baseStudents = pickStudentsByDefenseType(defenseType)
    const groupStudents = (start: number) => Array.from({ length: 6 }, (_, i) => mapStudent(baseStudents[(start + i) % baseStudents.length].id))

    return [
      {
        id: 201,
        defenseType,
        groupName: '正式答辩第 1 组',
        campus: pickClassroom(0).campus,
        classroom: pickClassroom(0).name,
        date: '2026-05-10',
        timeRange: '09:00-11:00',
        chairman: mapTeacher(1).name,
        secretary: mapTeacher(3).name,
        teachers: [mapTeacher(1), mapTeacher(4), mapTeacher(6), mapTeacher(8), mapTeacher(2)],
        students: groupStudents(0),
        status: 'normal'
      },
      {
        id: 202,
        defenseType,
        groupName: '正式答辩第 2 组',
        campus: pickClassroom(1).campus,
        classroom: pickClassroom(1).name,
        date: '2026-05-10',
        timeRange: '13:30-15:30',
        chairman: mapTeacher(6).name,
        secretary: mapTeacher(10).name,
        teachers: [mapTeacher(6), mapTeacher(4), mapTeacher(8), mapTeacher(2), mapTeacher(9)],
        students: groupStudents(6),
        status: 'normal'
      },
      {
        id: 203,
        defenseType,
        groupName: '正式答辩第 3 组',
        campus: pickClassroom(2).campus,
        classroom: pickClassroom(2).name,
        date: '2026-05-11',
        timeRange: '09:00-11:00',
        chairman: mapTeacher(9).name,
        secretary: mapTeacher(3).name,
        teachers: [mapTeacher(9), mapTeacher(1), mapTeacher(4), mapTeacher(8), mapTeacher(2)],
        students: groupStudents(12),
        status: 'normal'
      }
    ]
  }

  const baseStudents = pickStudentsByDefenseType(defenseType)
  const groupStudentsA = Array.from({ length: 12 }, (_, i) => mapStudent(baseStudents[i % baseStudents.length].id))
  const groupStudentsB = Array.from({ length: 11 }, (_, i) => mapStudent(baseStudents[(i + 6) % baseStudents.length].id))

  return [
    {
      id: 301,
      defenseType,
      groupName: '中期答辩第 1 组',
      campus: pickClassroom(3).campus,
      classroom: pickClassroom(3).name,
      date: '2026-05-14',
      timeRange: '09:00-11:30',
      leader: mapTeacher(2).name,
      secretary: mapTeacher(7).name,
      teachers: [mapTeacher(2), mapTeacher(9), mapTeacher(5), mapTeacher(8), mapTeacher(4)],
      students: groupStudentsA,
      status: 'normal'
    },
    {
      id: 302,
      defenseType,
      groupName: '中期答辩第 2 组',
      campus: pickClassroom(4).campus,
      classroom: pickClassroom(4).name,
      date: '2026-05-14',
      timeRange: '14:00-16:30',
      leader: mapTeacher(9).name,
      secretary: mapTeacher(7).name,
      teachers: [mapTeacher(9), mapTeacher(2), mapTeacher(5), mapTeacher(8), mapTeacher(4)],
      students: groupStudentsB,
      status: 'normal'
    }
  ]
}

export const generateMockScheduleResult = (defenseType: DefenseType): ScheduleResult => {
  return {
    defenseType,
    generatedAt: new Date().toISOString(),
    groups: buildGroups(defenseType)
  }
}
