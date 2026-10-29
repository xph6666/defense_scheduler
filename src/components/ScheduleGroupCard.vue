<template>
  <el-card shadow="hover" class="h-full" :class="cardClass" :data-group-name="group.groupName">
    <template #header>
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <div class="font-bold text-gray-800">{{ group.groupName }}</div>
          <el-tag v-if="shareSummary?.kind === 'explained' && status === 'normal'" size="small" effect="plain">已解释例外</el-tag>
          <ConflictTag v-else :status="status" />
          <el-tag v-if="conflictCount > 0" type="info" size="small">冲突 {{ conflictCount }}</el-tag>
        </div>
        <el-button v-if="canManage" size="small" @click="emit('adjust', group)">调整</el-button>
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
        <div class="text-gray-500 mb-2">专家（含主席/组长，共 {{ getScheduleExperts(group).length }} 人）</div>
        <div class="flex flex-wrap gap-2">
          <el-tag v-for="t in getScheduleExperts(group)" :key="t.id" size="small" :style="getStudentTagStyle(t.name)" :data-mentor="t.name.trim()">
            {{ t.name }}（{{ t.title }}） · {{ shareSummary?.counts[t.name.trim()] ?? group.students.filter(s => s.mentorName === t.name).length }} 名学生
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
            :data-mentor="s.mentorName.trim()"
          >
            {{ s.name }}（{{ s.studentType }}，{{ s.mentorName }}）
          </el-tag>
        </div>
      </div>

      <div v-if="shareSummary" class="mentor-share-summary" :data-share-kind="shareSummary.kind">
        <strong>导师学生数：{{ shareSummary.pattern }}</strong>
        <span v-if="shareSummary.kind === 'explained'"> · 已解释例外</span>
        <span v-else-if="shareSummary.kind === 'unbalanced'"> · 待均衡</span>
        <p v-if="shareSummary.reason">{{ shareSummary.reason }}</p>
      </div>

      <div v-if="group.remark" class="text-gray-600">
        <span class="text-gray-500">备注：</span>{{ group.remark }}
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getScheduleExperts } from '../domain/scheduleExperts'
import type { ScheduleGroup } from '../types/schedule'
import { buildMentorColors, groupMentorColors, neutralMentorColor, type MentorColorMap } from '../domain/mentorColors'
import type { MentorShares } from '../domain/mentorShares'
import ConflictTag from './ConflictTag.vue'

const props = defineProps<{
  group: ScheduleGroup
  status: 'normal' | 'warning' | 'error'
  conflictCount: number
  canManage?: boolean
  highlighted?: boolean
  mentorColors?: MentorColorMap
  shareSummary?: MentorShares
}>()

const emit = defineEmits<{
  (e: 'adjust', group: ScheduleGroup): void
}>()

const cardClass = computed(() => {
  const classes: string[] = []
  if (props.status === 'error') classes.push('border border-red-300')
  else if (props.status === 'warning') classes.push('border border-yellow-300')
  if (props.highlighted) classes.push('group-highlighted')
  return classes
})

const colors = computed(() => groupMentorColors(props.group, props.mentorColors ?? buildMentorColors([props.group])))
const getStudentTagStyle = (mentorName: string) => colors.value[mentorName.trim()] ?? neutralMentorColor
</script>

<style scoped>
.mentor-share-summary { padding: 10px 12px; background: #f5f7fa; border-left: 3px solid #94a3b8; border-radius: 4px; font-size: 12px; line-height: 1.65; }
.mentor-share-summary p { margin: 4px 0 0; }
.mentor-share-summary[data-share-kind="explained"] { background: #eef6fb; border-left-color: #347ca5; }
.mentor-share-summary[data-share-kind="unbalanced"] { background: #fff7ed; border-left-color: #c77b24; }
.group-highlighted {
  animation: highlightPulse 2s ease-out;
  border: 2px solid #00467f !important;
  box-shadow: 0 0 0 3px rgba(0, 70, 127, 0.15);
}

@keyframes highlightPulse {
  0% {
    box-shadow: 0 0 0 3px rgba(0, 70, 127, 0.3);
    background-color: #edf3f9;
  }
  50% {
    box-shadow: 0 0 0 6px rgba(0, 70, 127, 0.15);
  }
  100% {
    box-shadow: 0 0 0 3px rgba(0, 70, 127, 0.15);
    background-color: transparent;
  }
}
</style>
