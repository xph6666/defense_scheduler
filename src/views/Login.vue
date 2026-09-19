<template>
  <div class="h-screen w-screen flex items-center justify-center bg-gray-100">
    <el-card class="w-96 p-6 shadow-lg rounded-xl">
      <div class="text-center mb-8">
        <h2 class="text-2xl font-bold text-[var(--campus-blue)]">答辩排组排期系统</h2>
        <p class="text-gray-500 mt-2">管理员登录</p>
      </div>
      
      <el-form :model="form" @keyup.enter="handleLogin">
        <el-form-item>
          <el-input 
            v-model="form.username" 
            placeholder="请输入账号" 
            size="large"
          >
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input 
            v-model="form.password" 
            type="password" 
            placeholder="请输入密码" 
            size="large"
            show-password
          >
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-button 
          type="primary" 
          class="w-full mt-4" 
          size="large" 
          :loading="loading"
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const form = reactive({
  username: '',
  password: ''
})
const loading = ref(false)

const handleLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage.error('请输入账号和密码')
    return
  }

  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.push(redirect)
  } catch (error) {
    const message = error instanceof Error ? error.message : '账号或密码错误'
    ElMessage.error(message)
  } finally {
    loading.value = false
  }
}
</script>
