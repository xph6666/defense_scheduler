<template>
  <el-dialog
    v-model="visible"
    title="导入预览"
    width="800px"
    destroy-on-close
  >
    <div v-if="!previewData" class="py-10 text-center">
      <el-upload
        drag
        action="#"
        :auto-upload="false"
        :on-change="handleFileChange"
        :show-file-list="false"
        accept=".xlsx,.csv"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip text-center mt-2">
            支持 .xlsx, .csv 格式文件
          </div>
        </template>
      </el-upload>
    </div>

    <div v-else class="space-y-4">
      <div class="flex items-center justify-between bg-blue-50 p-3 rounded">
        <div class="text-sm">
          <span class="text-gray-500">文件名：</span>{{ previewData.fileInfo.name }}
          <span class="text-gray-500 ml-4">大小：</span>{{ (previewData.fileInfo.size / 1024).toFixed(2) }} KB
        </div>
        <el-tag type="success">可导入 {{ previewData.validCount }} 条</el-tag>
      </div>

      <el-table :data="previewData.rows" border size="small" height="300px">
        <el-table-column
          v-for="col in previewData.columns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
        >
          <template #header>
            <div class="flex items-center gap-1">
              <span>{{ col.label }}</span>
              <el-icon v-if="col.matched" class="text-green-500"><CircleCheck /></el-icon>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="text-xs text-gray-400">
        提示：当前为模拟预览，系统已自动匹配字段并解析前 5 行数据。
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <el-button @click="visible = false">取消</el-button>
        <el-button 
          v-if="previewData" 
          type="primary" 
          :loading="importing"
          @click="handleConfirm"
        >
          确定导入
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { UploadFilled, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { ImportModule, ImportPreviewResult } from '../types/import'
import { mockParseImportFile } from '../utils/importMock'

const props = defineProps<{
  modelValue: boolean
  module: ImportModule
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success', data: any[]): void
}>()

const visible = ref(props.modelValue)
const previewData = ref<ImportPreviewResult | null>(null)
const importing = ref(false)

watch(() => props.modelValue, v => {
  visible.value = v
  if (!v) previewData.value = null
})
watch(visible, v => emit('update:modelValue', v))

const handleFileChange = async (file: any) => {
  try {
    previewData.value = await mockParseImportFile(props.module, file.raw)
  } catch (e) {
    ElMessage.error('文件解析失败')
  }
}

const handleConfirm = async () => {
  if (!previewData.value) return
  importing.value = true
  // 模拟导入过程
  await new Promise(resolve => setTimeout(resolve, 1000))
  emit('success', previewData.value.rows)
  ElMessage.success(`导入成功，共导入 ${previewData.value.rows.length} 条数据`)
  importing.value = false
  visible.value = false
}
</script>
