<template>
  <div class="preparation-guide">
    <div class="page-intro">
      <div><h1>{{ title }}</h1></div>
      <RouterLink :to="workflowLink('/dashboard')" class="text-link">返回工作台查看进度 →</RouterLink>
    </div>
    <div v-if="route.query.wizard === '1'" class="wizard-return">
      <div><strong>正在准备{{ workflowDefenseType }}资料</strong></div>
      <RouterLink :to="{ path: '/schedule-wizard', query: { type: workflowDefenseType, step: 2 } }" class="text-link">资料已补充，返回向导 →</RouterLink>
    </div>
    <div v-if="route.query.wizard !== '1'" class="compact-links">
      <RouterLink :to="workflowLink('/rule-config')" class="text-link">{{ canManage ? '资料齐了，下一步 →' : '查看安排要求 →' }}</RouterLink>
    </div>
  </div>
</template>
<script setup lang="ts">
import { workflowLink, useDefenseType } from '../utils/useDefenseType'
import { useRoute } from 'vue-router'
import { useAdminGuard } from '../utils/adminGuard'
defineProps<{ title: string; description: string }>()
const { canManage } = useAdminGuard()
const route = useRoute()
const workflowDefenseType = useDefenseType()
</script>
