import type { Teacher } from '../types/teacher'
import type { Student } from '../types/student'
import type { Classroom } from '../types/classroom'

export const mockTeachers: Teacher[] = [
  { id: 1, name: '张教授', college: '计算机学院', isExternal: false, title: '教授', roles: ['主席', '组长'], availableTypes: ['预答辩', '正式答辩'], campusPreference: '创新港', unavailableTimes: '周二上午', avoidTeacherNames: '李教授' },
  { id: 2, name: '李副教授', college: '软件学院', isExternal: false, title: '副教授', roles: ['组长', '普通专家'], availableTypes: ['正式答辩', '中期答辩'], campusPreference: '不限', unavailableTimes: '无', avoidTeacherNames: '' },
  { id: 3, name: '王讲师', college: '网络安全学院', isExternal: false, title: '讲师', roles: ['秘书', '普通专家'], availableTypes: ['预答辩', '中期答辩'], campusPreference: '兴庆', unavailableTimes: '周五下午', avoidTeacherNames: '' },
  { id: 4, name: '赵专家', college: '信息学院', isExternal: true, title: '教授', roles: ['主席', '普通专家'], availableTypes: ['正式答辩'], campusPreference: '创新港', unavailableTimes: '周一全天', avoidTeacherNames: '' },
  { id: 5, name: '陈副教授', college: '计算机学院', isExternal: false, title: '副教授', roles: ['组长', '秘书'], availableTypes: ['预答辩', '中期答辩'], campusPreference: '不限', unavailableTimes: '无', avoidTeacherNames: '' },
  { id: 6, name: '刘教授', college: '软件学院', isExternal: false, title: '教授', roles: ['主席'], availableTypes: ['正式答辩'], campusPreference: '创新港', unavailableTimes: '无', avoidTeacherNames: '' },
  { id: 7, name: '周讲师', college: '外语学院', isExternal: true, title: '讲师', roles: ['秘书'], availableTypes: ['中期答辩'], campusPreference: '兴庆', unavailableTimes: '周三上午', avoidTeacherNames: '' },
  { id: 8, name: '吴副教授', college: '理学院', isExternal: true, title: '副教授', roles: ['普通专家'], availableTypes: ['预答辩', '正式答辩'], campusPreference: '不限', unavailableTimes: '无', avoidTeacherNames: '' },
  { id: 9, name: '郑教授', college: '计算机学院', isExternal: false, title: '教授', roles: ['主席', '组长'], availableTypes: ['正式答辩', '中期答辩'], campusPreference: '创新港', unavailableTimes: '周四下午', avoidTeacherNames: '' },
  { id: 10, name: '林讲师', college: '数学学院', isExternal: false, title: '讲师', roles: ['秘书', '普通专家'], availableTypes: ['预答辩'], campusPreference: '兴庆', unavailableTimes: '无', avoidTeacherNames: '' }
]

export const mockStudents: Student[] = Array.from({ length: 30 }, (_, i) => ({
  id: i + 1,
  name: `学生${i + 1}`,
  studentType: i % 3 === 0 ? '专硕' : '学硕',
  mentorName: `导师${(i % 5) + 1}`,
  campus: i % 2 === 0 ? '创新港' : '兴庆',
  defenseTypes: i % 2 === 0 ? ['预答辩', '正式答辩'] : ['中期答辩'],
  secretaryName: `秘书${(i % 3) + 1}`,
  currentGroup: i % 4 === 0 ? `第${(i % 4) + 1}组` : undefined,
  remark: '无'
}))

export const mockClassrooms: Classroom[] = [
  { id: 1, campus: '创新港', name: '1-101', capacity: 30, availableTimes: '周一至周五全天' },
  { id: 2, campus: '创新港', name: '2-202', capacity: 50, availableTimes: '周一至周三全天' },
  { id: 3, campus: '兴庆', name: '主楼A-101', capacity: 40, availableTimes: '周二至周四下午' },
  { id: 4, campus: '兴庆', name: '中二-1200', capacity: 60, availableTimes: '周一至周五全天' },
  { id: 5, campus: '创新港', name: '3-303', capacity: 20, availableTimes: '仅周末' }
]
