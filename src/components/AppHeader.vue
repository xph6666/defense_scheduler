<template>
  <div class="w-full h-full px-6 flex items-center justify-between">
    <div class="text-gray-600 font-medium">
      {{ currentTitle }}
    </div>
    <div class="flex items-center gap-3">
      <el-avatar :size="32" class="bg-blue-500">Admin</el-avatar>
      <span class="text-sm text-gray-700">管理员</span>
      <el-button type="primary" link @click="handleLogout">退出登录</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const currentTitle = computed(() => route.meta.title || '答辩排组排期系统')

const handleLogout = () => {
  router.push('/login')
}
</script>
