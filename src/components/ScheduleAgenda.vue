<template>
  <div class="schedule-agenda">
    <section v-for="day in days" :key="day.date" class="agenda-day" :id="`agenda-day-${day.date || 'unscheduled'}`">
      <header class="agenda-date"><div><strong>{{ day.date || '日期待安排' }}</strong><span>{{ weekday(day.date) }}</span></div><span>{{ day.groups.length }} 个分组</span></header>
      <article
        v-for="group in day.groups"
        :key="group.id"
        :id="`agenda-group-${group.id}`"
        class="agenda-group"
        :class="{
          'has-problem': problemCount(group.id) > 0,
          'is-highlighted': highlightedGroupIds.includes(group.id)
        }"
      >
        <div class="agenda-time"><strong>{{ group.timeRange || '时间待安排' }}</strong><span>{{ group.campus }} · {{ group.classroom || '教室待安排' }}</span></div>
        <div class="agenda-body">
          <div class="material-top"><h3>{{ group.groupName }}</h3><el-tag v-if="problemCount(group.id)" type="warning">{{ problemCount(group.id) }} 项待核对</el-tag><el-tag v-else type="success">无分组冲突</el-tag></div>
          <p>学生 {{ group.students.length }} 人 · {{ group.defenseType === '正式答辩' ? '主席' : '组长' }}：{{ group.chairman || group.leader || '待安排' }} · 秘书：{{ group.secretary || '待安排' }}</p>
          <details class="agenda-members"><summary>查看教师与学生名单</summary><p>专家：{{ getScheduleExperts(group).map(teacher => teacher.name).join('、') || '待安排' }}</p><p>学生：{{ group.students.map(student => `${student.name}（导师：${student.mentorName || '未填写'}）`).join('、') || '暂无学生' }}</p></details>
          <div class="agenda-actions"><el-button v-if="canManage" size="small" @click="$emit('adjust', group)">调整本组</el-button><el-button v-if="problemCount(group.id)" size="small" type="warning" plain @click="$emit('problem', group.id)">查看问题</el-button></div>
        </div>
      </article>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, watch, nextTick } from 'vue'
import { getScheduleExperts } from '../domain/scheduleExperts'
import type { ScheduleGroup } from '../types/schedule'
import type { ScheduleConflict } from '../types/conflict'
const props = defineProps<{
  groups: ScheduleGroup[]
  conflicts: ScheduleConflict[]
  canManage: boolean
  highlightedGroupIds?: number[]
}>()
defineEmits<{ (event: 'adjust', group: ScheduleGroup): void; (event: 'problem', groupId: number): void }>()

const highlightedGroupIds = computed(() => props.highlightedGroupIds || [])

const days = computed(() => {
  const sorted = props.groups
  const dates = [...new Set(sorted.map(group => group.date))]
  return dates.map(date => ({ date, groups: sorted.filter(group => group.date === date) }))
})
const problemCount = (id: number) => props.conflicts.filter(conflict => conflict.groupId === id || conflict.relatedGroupIds?.includes(id)).length
function weekday(date: string) {
  const parsed = new Date(`${date}T12:00:00`)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleDateString('zh-CN', { weekday: 'long' })
}

// 高亮时自动滚动到第一个高亮分组
watch(highlightedGroupIds, async (ids) => {
  if (!ids.length) return
  await nextTick()
  const firstId = ids[0]
  const el = document.getElementById(`agenda-group-${firstId}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}, { flush: 'post' })
</script>

<style scoped>
.agenda-group.is-highlighted {
  animation: agendaHighlightPulse 2s ease-out;
  border-left: 4px solid #00467f !important;
  background-color: #f0f6fb;
}

@keyframes agendaHighlightPulse {
  0% {
    background-color: #d6e6f2;
    box-shadow: inset 4px 0 0 #00467f, 0 0 0 2px rgba(0, 70, 127, 0.2);
  }
  50% {
    background-color: #e8f0f7;
  }
  100% {
    background-color: #f0f6fb;
    box-shadow: none;
  }
}
</style>
