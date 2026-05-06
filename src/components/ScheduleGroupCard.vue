<template>
  <el-card shadow="hover" class="h-full" :class="borderClass">
    <template #header>
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <div class="font-bold text-gray-800">{{ group.groupName }}</div>
          <ConflictTag :status="status" />
          <el-tag v-if="conflictCount > 0" type="info" size="small">冲突 {{ conflictCount }}</el-tag>
        </div>
        <el-button size="small" @click="emit('adjust', group)">调整</el-button>
      </div>
    </template>

    <div class="space-y-3 text-sm text-gray-700">
      <div class="flex flex-wrap gap-x-6 gap-y-2">
        <div><span class="text-gray-500">答辩类型：</span>{{ group.defenseType }}</div>
        <div><span class="text-gray-500">日期：</span>{{ group.date }}</div>
        <div><span class="text-gray-500">时间：</span>{{ group.timeRange }}</div>
      </div>

      <div class="flex flex-wrap gap-x-6 gap-y-2">
        <div><span class="text-gray-500">校区：</span>{{ group.campus }}</div>
        <div><span class="text-gray-500">教室：</span>{{ group.classroom }}</div>
      </div>

      <div class="flex flex-wrap gap-x-6 gap-y-2">
        <div v-if="group.leader"><span class="text-gray-500">组长：</span>{{ group.leader }}</div>
        <div v-if="group.chairman"><span class="text-gray-500">主席：</span>{{ group.chairman }}</div>
        <div><span class="text-gray-500">秘书：</span>{{ group.secretary }}</div>
      </div>

      <div>
        <div class="text-gray-500 mb-2">专家</div>
        <div class="flex flex-wrap gap-2">
          <el-tag v-for="t in group.teachers" :key="t.id" size="small">
            {{ t.name }}（{{ t.title }}）
          </el-tag>
        </div>
      </div>

      <div>
        <div class="text-gray-500 mb-2">学生</div>
        <div class="flex flex-wrap gap-2">
          <el-tag
            v-for="s in group.students"
            :key="s.id"
            size="small"
            :style="getStudentTagStyle(s.mentorName)"
          >
            {{ s.name }}（{{ s.studentType }}，{{ s.mentorName }}）
          </el-tag>
        </div>
      </div>

      <div v-if="group.remark" class="text-gray-600">
        <span class="text-gray-500">备注：</span>{{ group.remark }}
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScheduleGroup } from '../types/schedule'
import { getMentorColor } from '../utils/color'
import ConflictTag from './ConflictTag.vue'

const props = defineProps<{
  group: ScheduleGroup
  status: 'normal' | 'warning' | 'error'
  conflictCount: number
}>()

const emit = defineEmits<{
  (e: 'adjust', group: ScheduleGroup): void
}>()

const borderClass = computed(() => {
  if (props.status === 'error') return 'border border-red-300'
  if (props.status === 'warning') return 'border border-yellow-300'
  return ''
})

const getStudentTagStyle = (mentorName: string) => {
  const color = getMentorColor(mentorName)
  return {
    backgroundColor: color,
    borderColor: color,
    color: '#374151'
  }
}
</script>
