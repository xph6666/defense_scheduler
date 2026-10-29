<template>
  <div class="preparation-guide">
    <div class="page-intro">
      <div>
        <span class="eyebrow">公共资料 · 三类答辩共用</span>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <RouterLink :to="defenseLink('/dashboard', workflowDefenseType)" class="text-link">返回{{ workflowDefenseType }}概览 →</RouterLink>
    </div>
    <div class="preparation-next-link">
      <span>{{ canManage ? '资料修改会供各答辩类型共用。' : '公共资料仅供查看。' }}</span>
      <RouterLink :to="defenseLink(canManage ? '/rule-config' : '/schedule-results', workflowDefenseType)" class="text-link">
        {{ canManage ? `继续设置${workflowDefenseType}要求` : `查看${workflowDefenseType}排期` }} →
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { defenseLink, useDefenseType } from '../utils/useDefenseType'
import { useAdminGuard } from '../utils/adminGuard'

defineProps<{ title: string; description: string }>()
const { canManage } = useAdminGuard()
const workflowDefenseType = useDefenseType()
</script>
