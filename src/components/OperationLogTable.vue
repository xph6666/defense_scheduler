<template>
  <div class="operation-log-table">
    <div class="mb-4 flex items-center justify-between">
      <div class="flex gap-4">
        <el-select v-model="filterType" placeholder="操作类型" clearable size="small" style="width: 140px" @change="handleFilter">
          <el-option v-for="t in types" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filterResult" placeholder="结果" clearable size="small" style="width: 100px" @change="handleFilter">
          <el-option label="成功" value="成功" />
          <el-option label="失败" value="失败" />
        </el-select>
      </div>
      <el-button type="danger" link size="small" @click="handleClear">清空日志</el-button>
    </div>

    <el-table :data="displayLogs" border stripe style="width: 100%" size="small">
      <el-table-column prop="createdAt" label="操作时间" width="180" />
      <el-table-column prop="type" label="操作类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="getTypeTag(row.type)">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="module" label="模块" width="120" />
      <el-table-column prop="description" label="操作说明" min-width="200" show-overflow-tooltip />
      <el-table-column prop="operator" label="操作人" width="100" />
      <el-table-column prop="result" label="结果" width="80" align="center">
        <template #default="{ row }">
          <span :class="row.result === '成功' ? 'text-green-500' : 'text-red-500'">
            {{ row.result }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4 flex justify-end">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredLogs.length"
        layout="total, prev, pager, next"
        small
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { OperationLog, OperationType } from '../types/operationLog'
import { getOperationLogs, clearOperationLogs } from '../utils/operationLogStorage'

const props = defineProps<{
  limit?: number
}>()

const allLogs = ref<OperationLog[]>(getOperationLogs())
const filterType = ref('')
const filterResult = ref('')
const currentPage = ref(1)
const pageSize = ref(15)

const types: OperationType[] = [
  '生成排期', '刷新排期', '人工调整', '冲突检测', '导出结果',
  '保存规则配置', '重置规则配置', '重置演示数据', '清空排期结果', '导入数据'
]

const filteredLogs = computed(() => {
  return allLogs.value.filter(log => {
    const matchType = !filterType.value || log.type === filterType.value
    const matchResult = !filterResult.value || log.result === filterResult.value
    return matchType && matchResult
  })
})

const displayLogs = computed(() => {
  if (props.limit) return filteredLogs.value.slice(0, props.limit)
  
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredLogs.value.slice(start, end)
})

const getTypeTag = (type: OperationType) => {
  switch (type) {
    case '生成排期': return 'success'
    case '人工调整': return 'warning'
    case '导出结果': return 'info'
    case '保存规则配置': return ''
    case '清空排期结果': return 'danger'
    default: return ''
  }
}

const handleFilter = () => {
  currentPage.value = 1
}

const handleClear = () => {
  ElMessageBox.confirm('确定要清空所有操作日志吗？', '确认清空').then(() => {
    clearOperationLogs()
    allLogs.value = []
    ElMessage.success('日志已清空')
  })
}

const refresh = () => {
  allLogs.value = getOperationLogs()
}

defineExpose({ refresh })
</script>
