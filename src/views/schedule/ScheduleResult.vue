<template>
  <div class="space-y-4">
    <div class="bg-white p-6 rounded-lg shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-bold text-gray-800">排期结果</div>
          <div class="text-sm text-gray-500 mt-1">用于查看系统自动生成的分组、时间、教室与成员安排。</div>
        </div>
        <LegendTag />
      </div>

      <div class="mt-5">
        <ScheduleToolbar
          v-model:defenseType="defenseType"
          v-model:viewMode="viewMode"
          :loading="loading"
          :has-result="!!result"
          @generate="handleGenerate"
          @refresh="handleRefresh"
          @check-conflicts="handleCheckConflicts"
          @export="handleExportClick"
        />
      </div>
    </div>

    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      :title="errorMsg"
    />

    <div class="bg-white p-6 rounded-lg shadow-sm">
      <div class="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm text-gray-700">
        <div><span class="text-gray-500">当前答辩类型：</span>{{ defenseType }}</div>
        <div><span class="text-gray-500">生成时间：</span>{{ meta.generatedAt || '-' }}</div>
        <div><span class="text-gray-500">总组数：</span>{{ meta.groupCount }}</div>
        <div><span class="text-gray-500">总学生数：</span>{{ meta.studentCount }}</div>
        <div><span class="text-gray-500">总专家数：</span>{{ meta.teacherCount }}</div>
        <div><span class="text-gray-500">冲突数量：</span>{{ meta.conflictCount }}</div>
      </div>
    </div>

    <div v-if="loading" class="bg-white p-6 rounded-lg shadow-sm">
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else-if="!result" class="bg-white p-10 rounded-lg shadow-sm">
      <el-empty description="当前暂无排期结果，请先点击“一键生成排期”。" />
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2 space-y-4">
        <div v-if="viewMode === 'card'" class="space-y-4">
          <el-row :gutter="16">
            <el-col
              v-for="g in result.groups"
              :key="g.id"
              :span="12"
            >
              <ScheduleGroupCard
                :group="g"
                :status="groupStatusMap[g.id] || 'normal'"
                :conflict-count="groupConflictCountMap[g.id] || 0"
                @adjust="openAdjust"
              />
            </el-col>
          </el-row>
        </div>

        <div v-else class="bg-white p-6 rounded-lg shadow-sm">
          <ScheduleTable :groups="result.groups" :group-status="groupStatusMap" @adjust="openAdjust" />
        </div>
      </div>

      <div class="lg:col-span-1 space-y-4">
        <ConflictPanel
          :conflicts="conflicts"
          :loading="conflictLoading"
          @check="handleCheckConflicts"
          @view-detail="openConflictDetail"
        />
        <SoftConstraintPanel :summary="optimizationSummary" />
      </div>
    </div>
  </div>

  <ScheduleAdjustDrawer
    v-model="adjustVisible"
    :defense-type="defenseType"
    :group="currentGroup"
    :teachers="teacherOptions"
    :students="studentOptions"
    :classrooms="classroomOptions"
    :saving="adjustSaving"
    @save="handleSaveAdjust"
  />

  <ConflictDetailDialog v-model="conflictDetailVisible" :conflict="currentConflict" />

  <ExportDialog
    v-model="exportDialogVisible"
    :options="{ defenseType: defenseType }"
    :stats="exportStats"
    @confirm="handleExportConfirm"
  />

  <ExportProgress
    :status="exportStatus"
    @close="exportStatus = 'idle'"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ScheduleToolbar from '../../components/ScheduleToolbar.vue'
import ScheduleGroupCard from '../../components/ScheduleGroupCard.vue'
import ScheduleTable from '../../components/ScheduleTable.vue'
import LegendTag from '../../components/LegendTag.vue'
import ScheduleAdjustDrawer from '../../components/ScheduleAdjustDrawer.vue'
import ConflictPanel from '../../components/ConflictPanel.vue'
import ConflictDetailDialog from '../../components/ConflictDetailDialog.vue'
import ExportDialog from '../../components/ExportDialog.vue'
import ExportProgress from '../../components/ExportProgress.vue'
import SoftConstraintPanel from '../../components/SoftConstraintPanel.vue'
import type { DefenseType, ScheduleGroup, ScheduleResult, ScheduleStudent, ScheduleTeacher } from '../../types/schedule'
import { generateSchedule, getScheduleResults } from '../../api/schedule'
import { checkScheduleConflicts, readLocalConflicts } from '../../api/conflict'
import { updateScheduleGroup } from '../../api/adjustment'
import type { ScheduleConflict } from '../../types/conflict'
import { getGroupConflictCount, getGroupStatus } from '../../utils/conflictMock'
import { exportScheduleExcel } from '../../api/export'
import type { ExportStatus } from '../../types/export'
import type { OptimizationSummary } from '../../types/optimization'
import { evaluateSoftConstraints } from '../../utils/optimizationMock'
import { getRuleConfig } from '../../api/ruleConfig'
import { listTeachers } from '../../api/teacher'
import { listStudents } from '../../api/student'
import { listClassrooms } from '../../api/classroom'
import type { Classroom } from '../../types/classroom'

const defenseType = ref<DefenseType>('预答辩')
const viewMode = ref<'card' | 'table'>('card')
const loading = ref(false)
const errorMsg = ref('')
const result = ref<ScheduleResult | null>(null)

const conflicts = ref<ScheduleConflict[]>([])
const conflictLoading = ref(false)

const adjustVisible = ref(false)
const adjustSaving = ref(false)
const currentGroup = ref<ScheduleGroup | null>(null)

const currentConflict = ref<ScheduleConflict | null>(null)
const conflictDetailVisible = ref(false)

const exportDialogVisible = ref(false)
const exportStatus = ref<ExportStatus>('idle')

const optimizationSummary = ref<OptimizationSummary | null>(null)

const teacherOptions = ref<ScheduleTeacher[]>([])
const studentOptions = ref<ScheduleStudent[]>([])
const classroomOptions = ref<{ campus: '创新港' | '兴庆'; name: string }[]>([])

const updateOptimizationScore = async () => {
  if (!result.value) {
    optimizationSummary.value = null
    return
  }
  try {
    const config = await getRuleConfig(defenseType.value)
    optimizationSummary.value = evaluateSoftConstraints(result.value, config)
  } catch {
    optimizationSummary.value = null
  }
}

const openAdjust = (group: ScheduleGroup) => {
  currentGroup.value = group
  adjustVisible.value = true
}

const openConflictDetail = (c: ScheduleConflict) => {
  currentConflict.value = c
  conflictDetailVisible.value = true
}

const handleExportClick = () => {
  if (!result.value) return
  exportDialogVisible.value = true
}

const handleExportConfirm = async () => {
  exportStatus.value = 'exporting'
  try {
    await exportScheduleExcel(defenseType.value)
    exportStatus.value = 'success'
  } catch {
    exportStatus.value = 'error'
    ElMessage.error('导出失败，请稍后重试')
  }
}

const loadOptions = async () => {
  const [teachers, students, classrooms] = await Promise.all([
    listTeachers(),
    listStudents(),
    listClassrooms()
  ])

  teacherOptions.value = teachers.map(t => ({
    id: t.id,
    name: t.name,
    title: t.title,
    roles: t.roles,
    college: t.college,
    isExternal: t.isExternal
  }))

  studentOptions.value = students.map(s => ({
    id: s.id,
    name: s.name,
    studentType: s.studentType,
    mentorName: s.mentorName,
    secretaryName: s.secretaryName
  }))

  classroomOptions.value = (classrooms as Classroom[]).map(c => ({ campus: c.campus, name: c.name }))
}

const fetchResult = async () => {
  const currentDefenseType = defenseType.value
  loading.value = true
  errorMsg.value = ''
  try {
    const scheduleResult = await getScheduleResults(currentDefenseType)
    if (currentDefenseType !== defenseType.value) return
    result.value = scheduleResult
    await handleCheckConflicts(currentDefenseType)
    await updateOptimizationScore()
  } catch (e) {
    if (currentDefenseType !== defenseType.value) return
    errorMsg.value = e instanceof Error ? e.message : '排期结果加载失败'
    result.value = null
    conflicts.value = []
    currentConflict.value = null
    optimizationSummary.value = null
  } finally {
    if (currentDefenseType === defenseType.value) {
      loading.value = false
    }
  }
}

const handleGenerate = async () => {
  const currentDefenseType = defenseType.value
  loading.value = true
  errorMsg.value = ''
  conflicts.value = []
  currentConflict.value = null
  try {
    await generateSchedule(currentDefenseType)
    if (currentDefenseType !== defenseType.value) return
    const scheduleResult = await getScheduleResults(currentDefenseType)
    if (currentDefenseType !== defenseType.value) return
    result.value = scheduleResult
    ElMessage.success('排期生成成功')
    await handleCheckConflicts(currentDefenseType)
    await updateOptimizationScore()
  } catch (e) {
    if (currentDefenseType !== defenseType.value) return
    errorMsg.value = '生成失败'
    conflicts.value = []
    currentConflict.value = null
    ElMessage.error('排期生成失败，请稍后重试。')
  } finally {
    if (currentDefenseType === defenseType.value) {
      loading.value = false
    }
  }
}

const handleRefresh = async () => {
  await fetchResult()
}

const handleCheckConflicts = async (targetDefenseType: DefenseType = defenseType.value) => {
  if (!result.value) {
    conflicts.value = []
    currentConflict.value = null
    return
  }

  conflictLoading.value = true
  try {
    const nextConflicts = await checkScheduleConflicts(targetDefenseType)
    if (targetDefenseType !== defenseType.value) return
    conflicts.value = nextConflicts
  } catch (e) {
    if (targetDefenseType !== defenseType.value) return
    conflicts.value = []
    currentConflict.value = null
    const message = e instanceof Error ? e.message : '冲突检测失败'
    ElMessage.error(message)
  } finally {
    if (targetDefenseType === defenseType.value) {
      conflictLoading.value = false
    }
  }
}

const handleSaveAdjust = async (groupData: ScheduleGroup) => {
  if (!result.value) return
  adjustSaving.value = true
  try {
    await updateScheduleGroup({
      defenseType: defenseType.value,
      groupId: groupData.id,
      groupData
    })
    adjustVisible.value = false
    ElMessage.success('调整保存成功')
    await fetchResult()
  } catch (e) {
    const message = e instanceof Error ? e.message : '保存失败，请稍后重试'
    ElMessage.error(message)
  } finally {
    adjustSaving.value = false
  }
}

watch(defenseType, async () => {
  result.value = null
  conflicts.value = []
  currentConflict.value = null
  optimizationSummary.value = null
  await fetchResult()
})

onMounted(() => {
  loadOptions().catch(e => {
    const message = e instanceof Error ? e.message : '调整选项加载失败'
    ElMessage.error(message)
  })
  const local = readLocalConflicts(defenseType.value)
  conflicts.value = local.conflicts
  fetchResult()
})

const groupStatusMap = computed(() => {
  const map: Record<number, 'normal' | 'warning' | 'error'> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupStatus(g.id, conflicts.value)
  }
  return map
})

const groupConflictCountMap = computed(() => {
  const map: Record<number, number> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupConflictCount(g.id, conflicts.value)
  }
  return map
})

const exportStats = computed(() => ({
  groupCount: meta.value.groupCount,
  studentCount: meta.value.studentCount,
  conflictCount: meta.value.conflictCount,
  errorCount: conflicts.value.filter(c => c.level === 'error').length,
  warningCount: conflicts.value.filter(c => c.level === 'warning').length
}))

const meta = computed(() => {
  if (!result.value) {
    return {
      generatedAt: '',
      groupCount: 0,
      studentCount: 0,
      teacherCount: 0,
      conflictCount: 0
    }
  }

  const teacherSet = new Set<number>()
  let studentCount = 0
  for (const g of result.value.groups) {
    for (const t of g.teachers) teacherSet.add(t.id)
    studentCount += g.students.length
  }

  return {
    generatedAt: result.value.generatedAt ? new Date(result.value.generatedAt).toLocaleString() : '',
    groupCount: result.value.groups.length,
    studentCount,
    teacherCount: teacherSet.size,
    conflictCount: conflicts.value.length
  }
})
</script>
