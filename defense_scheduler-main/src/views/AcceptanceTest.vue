<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-800">P0 前端自测清单</h2>
        <p class="text-sm text-gray-500 mt-1">用于在提交前检查基础数据管理、排期生成、人工调整、冲突检测和导出流程是否正常；状态仅保存在当前浏览器本地。</p>
      </div>
      <div class="flex items-center gap-4">
        <div class="text-right">
          <div class="text-sm text-gray-500">通过率</div>
          <div class="text-2xl font-bold" :class="passRate >= 100 ? 'text-green-500' : 'text-blue-500'">
            {{ passRate }}%
          </div>
        </div>
        <el-button type="warning" plain @click="resetChecklist">一键重置</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="mb-4 flex gap-4">
        <el-radio-group v-model="filterModule" size="small">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button v-for="m in modules" :key="m" :label="m">{{ m }}</el-radio-button>
        </el-radio-group>
      </div>

      <el-table :data="filteredList" border style="width: 100%">
        <el-table-column prop="module" label="模块" width="120" />
        <el-table-column prop="title" label="测试项" width="200" />
        <el-table-column prop="description" label="操作步骤" min-width="250" />
        <el-table-column prop="expectedResult" label="预期结果" min-width="200" />
        <el-table-column label="状态" width="180" align="center">
          <template #default="{ row }">
            <el-radio-group v-model="row.status" size="small" @change="saveToStorage">
              <el-radio-button label="passed">通过</el-radio-button>
              <el-radio-button label="failed">失败</el-radio-button>
              <el-radio-button label="pending">待测</el-radio-button>
            </el-radio-group>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { TestChecklistItem } from '../types/test'
import { getDefaultChecklist } from '../utils/testChecklist'
import { STORAGE_KEYS } from '../utils/storageKeys'

const checklist = ref<TestChecklistItem[]>([])
const filterModule = ref('')

const modules = computed(() => Array.from(new Set(checklist.value.map(i => i.module))))

const filteredList = computed(() => {
  if (!filterModule.value) return checklist.value
  return checklist.value.filter(i => i.module === filterModule.value)
})

const passRate = computed(() => {
  if (checklist.value.length === 0) return 0
  const passedCount = checklist.value.filter(i => i.status === 'passed').length
  return Math.round((passedCount / checklist.value.length) * 100)
})

const saveToStorage = () => {
  localStorage.setItem(STORAGE_KEYS.acceptanceChecklist, JSON.stringify(checklist.value))
}

const resetChecklist = () => {
  ElMessageBox.confirm('确定要重置所有测试项状态吗？', '确认重置').then(() => {
    checklist.value = getDefaultChecklist()
    saveToStorage()
    ElMessage.success('已重置')
  })
}

onMounted(() => {
  const saved = localStorage.getItem(STORAGE_KEYS.acceptanceChecklist)
  if (saved) {
    try {
      checklist.value = JSON.parse(saved)
    } catch (e) {
      checklist.value = getDefaultChecklist()
    }
  } else {
    checklist.value = getDefaultChecklist()
  }
})
</script>
