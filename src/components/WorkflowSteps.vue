<template>
  <nav class="workflow-steps" aria-label="答辩安排步骤">
    <RouterLink
      v-for="(step, index) in steps" :key="step.title" :to="{ ...workflowLink(step.path), query: { ...workflowLink(step.path).query, stage: index === 3 ? 'export' : undefined } }"
      class="workflow-step" :class="{ 'is-current': current === index + 1 }"
      :aria-current="current === index + 1 ? 'step' : undefined"
    >
      <span class="step-number">{{ index + 1 }}</span>
      <span><strong>{{ step.title }}</strong></span>
      <span v-if="index < steps.length - 1" class="step-arrow" aria-hidden="true">›</span>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { workflowLink } from '../utils/useDefenseType'
defineProps<{ current: number }>()
const steps = [
  { path: '/dashboard', title: '准备资料', description: '学生、教师与教室' },
  { path: '/rule-config', title: '确认要求', description: '答辩日期与每组人数' },
  { path: '/schedule-results', title: '生成与检查', description: '检查问题，按需调整' },
  { path: '/schedule-results', title: '发布与导出', description: '确认后下载安排表' }
]
</script>
