<template>
  <div class="h-screen w-screen flex items-center justify-center bg-gray-100">
    <el-card class="w-96 p-6 shadow-lg rounded-xl">
      <div class="text-center mb-8">
        <h2 class="text-2xl font-bold text-blue-600">答辩排组排期系统</h2>
        <p class="text-gray-500 mt-2">管理员登录</p>
      </div>
      
      <el-form :model="form" @keyup.enter="handleLogin">
        <el-form-item>
          <el-input 
            v-model="form.username" 
            placeholder="请输入账号 (admin)" 
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
            placeholder="请输入密码 (任意)" 
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
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const form = reactive({
  username: '',
  password: ''
})

const handleLogin = () => {
  if (form.username === 'admin') {
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } else {
    ElMessage.error('请输入正确账号 admin')
  }
}
</script>
