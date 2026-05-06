<template>
  <div class="space-y-6">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover" class="border-l-4 border-l-blue-500">
          <template #header>
            <div class="flex items-center text-gray-500 text-sm">
              <el-icon class="mr-2"><Avatar /></el-icon>
              教师/专家数量
            </div>
          </template>
          <div class="text-3xl font-bold text-gray-800">{{ stats.teachers }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="border-l-4 border-l-green-500">
          <template #header>
            <div class="flex items-center text-gray-500 text-sm">
              <el-icon class="mr-2"><User /></el-icon>
              学生数量
            </div>
          </template>
          <div class="text-3xl font-bold text-gray-800">{{ stats.students }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="border-l-4 border-l-purple-500">
          <template #header>
            <div class="flex items-center text-gray-500 text-sm">
              <el-icon class="mr-2"><OfficeBuilding /></el-icon>
              教室数量
            </div>
          </template>
          <div class="text-3xl font-bold text-gray-800">{{ stats.classrooms }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="border-l-4 border-l-orange-500">
          <template #header>
            <div class="flex items-center text-gray-500 text-sm">
              <el-icon class="mr-2"><Timer /></el-icon>
              本周开发阶段
            </div>
          </template>
          <div class="text-sm font-medium text-gray-700 leading-tight">
            第 3 周：人工调整 + 冲突检测 + 冲突高亮
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center justify-between">
          <div class="flex items-center">
            <el-icon class="mr-2 text-blue-500"><DataAnalysis /></el-icon>
            排期结果概览
          </div>
          <el-button type="primary" link @click="goSchedule">查看排期结果</el-button>
        </div>
      </template>

      <div v-if="scheduleOverview.typeCount === 0" class="text-gray-500">
        暂无已生成排期结果
      </div>
      <div v-else class="flex flex-wrap gap-x-10 gap-y-2 text-sm text-gray-700">
        <div><span class="text-gray-500">当前已有排期类型数：</span>{{ scheduleOverview.typeCount }}</div>
        <div><span class="text-gray-500">已生成总组数：</span>{{ scheduleOverview.totalGroups }}</div>
        <div><span class="text-gray-500">最近一次生成时间：</span>{{ scheduleOverview.latestGeneratedAt }}</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center">
          <el-icon class="mr-2 text-blue-500"><WarningFilled /></el-icon>
          冲突统计概览
        </div>
      </template>

      <div v-if="conflictOverview.checkedAt === '-'" class="text-gray-500">
        暂无冲突检测记录
      </div>
      <div v-else class="flex flex-wrap gap-x-10 gap-y-2 text-sm text-gray-700">
        <div><span class="text-gray-500">当前错误冲突数量：</span>{{ conflictOverview.errorCount }}</div>
        <div><span class="text-gray-500">当前警告数量：</span>{{ conflictOverview.warningCount }}</div>
        <div><span class="text-gray-500">最近一次检测时间：</span>{{ conflictOverview.checkedAt }}</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="font-bold text-gray-800 flex items-center">
          <el-icon class="mr-2 text-blue-500"><InfoFilled /></el-icon>
          系统进度说明
        </div>
      </template>
      <div class="text-gray-600 space-y-2 leading-relaxed">
        <p><strong>当前已完成：</strong>前端工程搭建、基础布局、基础数据管理、排期结果展示、一键生成排期、人工调整入口、冲突检测展示。</p>
        <p><strong>下一步：</strong>对接后端排期与冲突接口，完善人工调整能力与导出功能。</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listTeachers } from '../api/teacher'
import { listStudents } from '../api/student'
import { listClassrooms } from '../api/classroom'
import { Avatar, User, OfficeBuilding, Timer, InfoFilled, DataAnalysis, WarningFilled } from '@element-plus/icons-vue'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import type { ScheduleConflict } from '../types/conflict'
import { getAllScheduleResults } from '../utils/scheduleStorage'
import { readLocalConflicts } from '../api/conflict'

const stats = ref({
  teachers: 0,
  students: 0,
  classrooms: 0
})

const router = useRouter()

const scheduleOverview = ref({
  typeCount: 0,
  totalGroups: 0,
  latestGeneratedAt: '-'
})

const conflictOverview = ref({
  errorCount: 0,
  warningCount: 0,
  checkedAt: '-'
})

const defenseTypes: DefenseType[] = ['预答辩', '正式答辩', '中期答辩']

const refreshScheduleOverview = () => {
  const all = getAllScheduleResults()
  const typeCount = all.length
  const totalGroups = all.reduce((sum, r) => sum + r.groups.length, 0)
  const latest = all.reduce((max, r) => {
    const t = Date.parse(r.generatedAt)
    if (Number.isNaN(t)) return max
    return Math.max(max, t)
  }, 0)

  scheduleOverview.value = {
    typeCount,
    totalGroups,
    latestGeneratedAt: latest ? new Date(latest).toLocaleString() : '-'
  }
}

const refreshConflictOverview = () => {
  let latest = 0
  let latestAt = ''
  let latestConflicts: ScheduleConflict[] = []

  for (const dt of defenseTypes) {
    const { conflicts, checkedAt } = readLocalConflicts(dt)
    if (!checkedAt) continue
    const t = Date.parse(checkedAt)
    if (Number.isNaN(t)) continue
    if (t >= latest) {
      latest = t
      latestAt = checkedAt
      latestConflicts = conflicts
    }
  }

  conflictOverview.value = {
    errorCount: latestConflicts.filter(c => c.level === 'error').length,
    warningCount: latestConflicts.filter(c => c.level === 'warning').length,
    checkedAt: latestAt ? new Date(latestAt).toLocaleString() : '-'
  }
}

const goSchedule = () => {
  router.push('/schedule-results')
}

const fetchStats = async () => {
  try {
    const [teachers, students, classrooms] = await Promise.all([
      listTeachers(),
      listStudents(),
      listClassrooms()
    ])
    stats.value = {
      teachers: teachers.length,
      students: students.length,
      classrooms: classrooms.length
    }
  } catch (error) {
    console.error('获取统计数据失败', error)
  }
}

onMounted(() => {
  fetchStats()
  refreshScheduleOverview()
  refreshConflictOverview()
})
</script>
