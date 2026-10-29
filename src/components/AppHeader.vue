<template>
  <div class="w-full h-full px-6 flex items-center justify-between">
    <div class="text-gray-600 font-medium">
      {{ currentTitle }}
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

const route = useRoute()
const userStore = useUserStore()

const currentTitle = computed(() => route.meta.title || '答辩排组排期系统')
</script>
