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
          @generate="handleGenerate"
          @refresh="handleRefresh"
          @check-conflicts="handleCheckConflicts"
        />
      </div>
    </div>

    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      title="排期生成失败，请稍后重试。"
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

      <div class="lg:col-span-1">
        <ConflictPanel
          :conflicts="conflicts"
          :loading="conflictLoading"
          @check="handleCheckConflicts"
          @view-detail="openConflictDetail"
        />
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
import type { DefenseType, ScheduleGroup, ScheduleResult, ScheduleStudent, ScheduleTeacher } from '../../types/schedule'
import { generateSchedule, getScheduleResults } from '../../api/schedule'
import { updateScheduleGroupInStorage } from '../../utils/scheduleStorage'
import { checkScheduleConflicts, readLocalConflicts } from '../../api/conflict'
import type { ScheduleConflict } from '../../types/conflict'
import { getGroupConflictCount, getGroupStatus } from '../../utils/conflictMock'
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

const teacherOptions = ref<ScheduleTeacher[]>([])
const studentOptions = ref<ScheduleStudent[]>([])
const classroomOptions = ref<{ campus: '创新港' | '兴庆'; name: string }[]>([])

const openAdjust = (group: ScheduleGroup) => {
  currentGroup.value = group
  adjustVisible.value = true
}

const openConflictDetail = (c: ScheduleConflict) => {
  currentConflict.value = c
  conflictDetailVisible.value = true
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
  loading.value = true
  errorMsg.value = ''
  try {
    result.value = await getScheduleResults(defenseType.value)
    await handleCheckConflicts()
  } finally {
    loading.value = false
  }
}

const handleGenerate = async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    await generateSchedule(defenseType.value)
    ElMessage.success('排期生成成功')
    result.value = await getScheduleResults(defenseType.value)
    await handleCheckConflicts()
  } catch (e) {
    errorMsg.value = '生成失败'
    ElMessage.error('排期生成失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

const handleRefresh = async () => {
  await fetchResult()
}

const handleCheckConflicts = async () => {
  conflictLoading.value = true
  try {
    conflicts.value = await checkScheduleConflicts(defenseType.value)
  } finally {
    conflictLoading.value = false
  }
}

const handleSaveAdjust = async (groupData: ScheduleGroup) => {
  if (!result.value) return
  adjustSaving.value = true
  try {
    const updated = updateScheduleGroupInStorage(defenseType.value, groupData.id, groupData)
    if (!updated) {
      ElMessage.error('保存失败：未找到对应排期数据')
      return
    }
    result.value = updated
    adjustVisible.value = false
    ElMessage.success('调整保存成功')
    await handleCheckConflicts()
  } finally {
    adjustSaving.value = false
  }
}

watch(defenseType, async () => {
  await fetchResult()
})

onMounted(() => {
  loadOptions()
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
