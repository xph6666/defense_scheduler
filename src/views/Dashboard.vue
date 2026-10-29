<template>
  <main class="workbench overview-page">
    <header class="workbench-heading overview-heading">
      <div>
        <span class="eyebrow">答辩安排总览</span>
        <h1>{{ scopedType ? `${scopedType}概览` : '工作台' }}</h1>
        <p>{{ scopedType ? '查看本类型的排期状态，并从系统推荐的下一步继续。' : '查看三类答辩进度，选择一项即可继续处理。' }}</p>
      </div>
      <el-button :loading="loading" plain @click="load">刷新状态</el-button>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="mb-5">
      <template #default><el-button link type="primary" @click="load">重新读取</el-button></template>
    </el-alert>

    <el-skeleton v-if="loading && !error" :rows="5" animated />

    <template v-else-if="!error">
      <section v-if="scopedType" class="overview-focus" :aria-labelledby="`focus-${scopedType}`">
        <div class="focus-topline">
          <div>
            <span class="status-kicker">{{ summaryFor(scopedType).statusLabel }}</span>
            <h2 :id="`focus-${scopedType}`">{{ scopedType }}</h2>
            <p>{{ summaryFor(scopedType).description }}</p>
          </div>
          <el-tag :type="summaryFor(scopedType).tagType" effect="light" size="large">
            {{ summaryFor(scopedType).statusLabel }}
          </el-tag>
        </div>

        <div class="overview-focus-grid">
          <div class="overview-metric"><span>参加本类型的学生</span><strong>{{ summaryFor(scopedType).studentCount }}</strong></div>
          <div class="overview-metric"><span>可用教师 / 专家</span><strong>{{ summaryFor(scopedType).teacherCount }}</strong></div>
          <div class="overview-metric"><span>{{ summaryFor(scopedType).result ? '当前分组' : '最近状态' }}</span><strong>{{ summaryFor(scopedType).result ? `${summaryFor(scopedType).groupCount} 组` : summaryFor(scopedType).statusShort }}</strong></div>
        </div>

        <div class="focus-action">
          <div>
            <strong>{{ summaryFor(scopedType).nextTitle }}</strong>
            <p>{{ summaryFor(scopedType).nextDescription }}</p>
          </div>
          <el-button type="primary" size="large" :disabled="summaryFor(scopedType).disabled" @click="go(summaryFor(scopedType).actionPath, scopedType)">
            {{ summaryFor(scopedType).actionLabel }}
          </el-button>
        </div>
      </section>

      <section v-else class="overview-grid" aria-label="三类答辩状态">
        <article
          v-for="type in defenseTypes"
          :key="type"
          class="defense-overview-card"
          :class="summaryFor(type).cardClass"
        >
          <div class="overview-card-head">
            <div>
              <span class="overview-label">答辩类型</span>
              <h2>{{ type }}</h2>
            </div>
            <el-tag :type="summaryFor(type).tagType" effect="light">{{ summaryFor(type).statusLabel }}</el-tag>
          </div>
          <div class="overview-count">
            <div><strong>{{ summaryFor(type).studentCount }}</strong><span>参排学生</span></div>
            <div><strong>{{ summaryFor(type).groupCount || '—' }}</strong><span>{{ summaryFor(type).result ? '当前分组' : '分组' }}</span></div>
          </div>
          <p class="overview-next">{{ summaryFor(type).nextDescription }}</p>
          <el-button type="primary" plain :disabled="summaryFor(type).disabled" @click="go(summaryFor(type).actionPath, type)">
            {{ summaryFor(type).actionLabel }}
          </el-button>
        </article>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listTeachers } from '../api/teacher'
import { listStudents } from '../api/student'
import { getScheduleResults } from '../api/schedule'
import type { DefenseType, ScheduleResult } from '../types/schedule'
import type { Student } from '../types/student'
import type { Teacher } from '../types/teacher'
import { defenseLink, defenseTypes, isDefenseType } from '../utils/useDefenseType'
import { useAdminGuard } from '../utils/adminGuard'

const route = useRoute()
const router = useRouter()
const { canManage } = useAdminGuard()
const scopedType = computed(() => isDefenseType(route.query.type) ? route.query.type : null)
const teachers = ref<Teacher[]>([])
const students = ref<Student[]>([])
const results = ref<Partial<Record<DefenseType, ScheduleResult>>>({})
const loading = ref(true)
const error = ref('')

function summaryFor(type: DefenseType) {
  const result = results.value[type]
  const scheduledCount = new Set(result?.groups.flatMap(group => group.students.map(student => student.id)) || []).size
  const studentCount = students.value.filter(student => !student.participationExcluded && student.defenseTypes.includes(type)).length
  const teacherCount = teachers.value.filter(teacher => teacher.isActive !== false && (!teacher.availableTypes?.length || teacher.availableTypes.includes(type))).length
  const errorCount = result?.conflicts?.filter(conflict => conflict.level === 'error').length || 0
  const warningCount = result?.conflicts?.filter(conflict => conflict.level === 'warning').length || 0
  const unassignedCount = result?.unassignedStudents?.length || 0
  const hasSchedule = !!result?.groups.length
  const isPublished = result?.status === 'published'

  let statusLabel = '尚未生成'
  let statusShort = '未生成'
  let tagType: 'success' | 'warning' | 'danger' | 'info' = 'info'
  let description = '准备好学生与教师资料后，即可设置要求并生成草稿。'
  let nextTitle = '从当前状态继续'
  let nextDescription = description
  let actionLabel = '查看本类型概览'
  let actionPath = '/rule-config'
  let disabled = false
  let cardClass = ''

  if (hasSchedule && isPublished) {
    statusLabel = '已发布'
    statusShort = `${scheduledCount} 人已安排`
    tagType = 'success'
    description = `已发布 ${result!.groups.length} 个分组，可查看和导出当前版本。`
    nextTitle = '查看已发布安排'
    nextDescription = description
    actionLabel = '查看排期方案'
    actionPath = '/schedule-results'
    cardClass = 'is-ready'
  } else if (hasSchedule) {
    statusLabel = errorCount || unassignedCount ? '草稿待处理' : '草稿待核对'
    statusShort = `${scheduledCount} 人已安排`
    tagType = errorCount || unassignedCount ? 'danger' : 'warning'
    description = `当前有 ${result!.groups.length} 个分组；${errorCount ? `${errorCount} 项硬冲突` : '暂无硬冲突'}，${unassignedCount ? `${unassignedCount} 名学生未安排` : '未安排学生为 0'}${warningCount ? `，另有 ${warningCount} 项提醒` : ''}。`
    nextTitle = errorCount || unassignedCount ? '处理草稿中的问题' : '核对草稿并发布'
    nextDescription = description
    actionLabel = errorCount || unassignedCount ? '查看待处理项' : '核对并发布'
    actionPath = '/schedule-results'
    cardClass = 'is-attention'
  } else if (!canManage.value) {
    statusLabel = '暂无已发布安排'
    statusShort = '等待发布'
    tagType = 'info'
    description = '管理员发布本类型安排后，可在这里查看和导出。'
    nextTitle = '等待管理员发布'
    nextDescription = description
    actionLabel = '查看排期方案'
    actionPath = '/schedule-results'
  } else {
    const missingStudents = studentCount === 0
    const missingTeachers = teacherCount === 0
    const missing = missingStudents ? '学生名单' : missingTeachers ? '教师 / 专家资料' : null
    statusLabel = missing ? '资料待准备' : '待设置要求'
    statusShort = missing ? '资料待准备' : '待设置'
    tagType = 'warning'
    description = missing
      ? `请先补充${missing}，之后即可设置规则并生成草稿。`
      : '资料已有记录，下一步是确认日期、人数和角色要求。'
    nextTitle = missing ? `先补充${missing}` : '确认日期和排期要求'
    nextDescription = description
    actionLabel = missing ? '前往公共资料' : '设置安排要求'
    actionPath = missingStudents ? '/students' : missingTeachers ? '/teachers' : '/rule-config'
    cardClass = 'is-attention'
  }

  return {
    result,
    studentCount,
    teacherCount,
    groupCount: result?.groups.length || 0,
    statusLabel,
    statusShort,
    tagType,
    description,
    nextTitle,
    nextDescription,
    actionLabel,
    actionPath,
    disabled,
    cardClass
  }
}

function go(path: string, type: DefenseType) {
  void router.push(defenseLink(path, type))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [teacherRows, studentRows, ...scheduleRows] = await Promise.all([
      listTeachers(),
      listStudents(),
      ...defenseTypes.map(type => getScheduleResults(type))
    ])
    teachers.value = teacherRows as Teacher[]
    students.value = studentRows as Student[]
    results.value = Object.fromEntries(defenseTypes.flatMap((type, index) => {
      const result = scheduleRows[index]
      if (!result || (!canManage.value && result.status !== 'published')) return []
      return [[type, result]]
    }))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '读取答辩进度失败，请重试。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
