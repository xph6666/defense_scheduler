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
              当前排期组数
            </div>
          </template>
          <div class="text-3xl font-bold text-gray-800">{{ scheduleOverview.totalGroups }}</div>
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
          <div class="flex items-center gap-3">
            <el-button v-if="enableDemoTools && canManage" type="warning" plain @click="handleResetDemoData">重置演示数据</el-button>
            <el-button type="primary" link @click="goSchedule">查看排期结果</el-button>
          </div>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTeachers } from '../api/teacher'
import { listStudents } from '../api/student'
import { listClassrooms } from '../api/classroom'
import { Avatar, User, OfficeBuilding, Timer, DataAnalysis, WarningFilled } from '@element-plus/icons-vue'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import { readLocalConflicts } from '../api/conflict'
import { resetDemoData } from '../utils/demoSeed'
import { addOperationLog } from '../utils/operationLogStorage'
import { enableDemoTools } from '../config/features'
import { useAdminGuard } from '../utils/adminGuard'
import { getScheduleResults } from '../api/schedule'
import { summarizeConflictOverview, summarizeScheduleOverview } from '../utils/dashboardOverview'

const stats = ref({
  teachers: 0,
  students: 0,
  classrooms: 0
})

const router = useRouter()
const { canManage, requireAdmin } = useAdminGuard()

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
const scheduleResults = ref<ScheduleResult[]>([])

const loadScheduleResults = async () => {
  const loaded = await Promise.all(defenseTypes.map(async defenseType => {
    try {
      return await getScheduleResults(defenseType)
    } catch {
      return null
    }
  }))
  return loaded.filter((result): result is ScheduleResult => !!result)
}

const refreshScheduleOverview = async () => {
  scheduleResults.value = await loadScheduleResults()
  scheduleOverview.value = summarizeScheduleOverview(scheduleResults.value)
  refreshConflictOverview()
}

const refreshConflictOverview = () => {
  const localRecords = defenseTypes.map(defenseType => readLocalConflicts(defenseType))
  conflictOverview.value = summarizeConflictOverview(scheduleResults.value, localRecords)
}

const goSchedule = () => {
  router.push('/schedule-results')
}

const handleResetDemoData = async () => {
  if (!requireAdmin()) return
  try {
    await ElMessageBox.confirm('确定要重置演示数据吗？当前排期结果与导出时间会被清空。', '确认重置', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    resetDemoData()
    addOperationLog({
      type: '重置演示数据',
      module: 'Dashboard',
      description: '重置教师、学生、教室演示数据并清空排期结果'
    })
    await fetchStats()
    await refreshScheduleOverview()
    ElMessage.success('演示数据已重置')
  } catch {
    return
  }
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
  refreshScheduleOverview().catch(error => {
    console.error('获取排期概览失败', error)
  })
})
</script>
