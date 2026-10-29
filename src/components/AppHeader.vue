<template>
  <div class="w-full h-full px-6 flex items-center justify-between">
    <div class="text-gray-600 font-medium">
      {{ pageTitle }}
    </div>
    <div class="flex items-center gap-3">
      <GettingStarted />
      <el-avatar :size="32" class="bg-blue-500">{{ userStore.username?.charAt(0)?.toUpperCase() || 'A' }}</el-avatar>
      <span class="text-sm text-gray-700">{{ userStore.username || '管理员' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import GettingStarted from './GettingStarted.vue'
import { isDefenseType } from '../utils/useDefenseType'

const route = useRoute()
const userStore = useUserStore()

const currentTitle = computed(() => route.meta.title || '答辩排组排期系统')
const pageTitle = computed(() => {
  const type = isDefenseType(route.query.type) ? route.query.type : null
  if (route.path === '/dashboard') return type ? `${type}概览` : '工作台'
  if (route.path === '/rule-config') return `${type || '答辩'} · 安排要求`
  if (route.path === '/schedule-results') return `${type || '答辩'} · 排期方案`
  return currentTitle.value
})
</script>
