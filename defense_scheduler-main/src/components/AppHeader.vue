<template>
  <div class="w-full h-full px-6 flex items-center justify-between">
    <div class="text-gray-600 font-medium">
      {{ currentTitle }}
    </div>
    <div class="flex items-center gap-3">
      <GettingStarted />
      <el-avatar :size="32" class="bg-blue-500">{{ userStore.username?.charAt(0)?.toUpperCase() || 'A' }}</el-avatar>
      <span class="text-sm text-gray-700">{{ userStore.username || '管理员' }}</span>
      <el-button type="primary" link @click="passwordDialogVisible = true">修改密码</el-button>
      <el-button type="primary" link @click="handleLogout">退出登录</el-button>
    </div>
    <ChangePasswordDialog v-model:visible="passwordDialogVisible" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import ChangePasswordDialog from './ChangePasswordDialog.vue'
import GettingStarted from './GettingStarted.vue'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const currentTitle = computed(() => route.meta.title || '答辩排组排期系统')
const passwordDialogVisible = ref(false)

const handleLogout = async () => {
  try {
    await userStore.logout()
    router.push('/login')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '退出失败，请检查网络后重试')
  }
}
</script>
