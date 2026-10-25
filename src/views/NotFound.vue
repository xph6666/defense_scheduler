<template>
  <div class="workbench-panel not-found">
    <h1>页面不存在</h1>
    <p>{{ route.fullPath }} 没有对应的页面，可能是地址有误，或该功能已调整到其他位置。</p>
    <div class="not-found-actions">
      <el-button type="primary" @click="router.push(workflowLink('/dashboard'))">返回工作台</el-button>
      <el-button link type="primary" @click="router.back()">回到上一页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { workflowLink } from '../utils/useDefenseType'

const route = useRoute()
const router = useRouter()
</script>

<style scoped>
.not-found {
  max-width: 640px;
}

.not-found h1 {
  font-size: 22px;
  font-weight: 700;
  color: #25364a;
}

.not-found p {
  margin: 12px 0 20px;
  color: #516780;
  line-height: 1.7;
  word-break: break-all;
}

.not-found-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
