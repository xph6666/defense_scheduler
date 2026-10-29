<template>
  <el-dialog
    v-model="visible"
    title="导出确认"
    width="500px"
    destroy-on-close
  >
    <div class="space-y-4">
      <!-- 版本信息展示 -->
      <div v-if="versionInfo" class="version-info p-3 rounded-md" :class="versionInfo.isCurrent ? 'bg-blue-50 border border-blue-200' : 'bg-orange-50 border border-orange-200'">
        <div class="flex items-center gap-2">
          <el-icon :class="versionInfo.isCurrent ? 'text-blue-600' : 'text-orange-600'"><Document /></el-icon>
          <div class="text-sm">
            <span class="font-bold" :class="versionInfo.isCurrent ? 'text-blue-700' : 'text-orange-700'">
              导出版本：v{{ versionInfo.versionNumber }}（{{ versionInfo.status === 'published' ? '已发布' : '草稿' }}）
            </span>
            <span v-if="versionInfo.isCurrent" class="text-blue-600 ml-2">· 当前版本</span>
          </div>
        </div>
        <p v-if="!versionInfo.isCurrent" class="text-xs text-orange-600 mt-2">
          正在导出历史版本，非当前草稿。如需导出最新内容，请切换到当前版本。
        </p>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">答辩类型</div>
          <div class="font-bold">{{ options.defenseType }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">总组数</div>
          <div class="font-bold">{{ stats.groupCount }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">总学生数</div>
          <div class="font-bold">{{ stats.studentCount }}</div>
        </div>
        <div class="p-3 bg-gray-50 rounded">
          <div class="text-xs text-gray-500">冲突数量</div>
          <div class="font-bold" :class="stats.conflictCount > 0 ? 'text-orange-500' : ''">
            {{ stats.conflictCount }}
          </div>
        </div>
      </div>

      <div v-if="stats.errorCount > 0" class="p-4 bg-red-50 border border-red-200 rounded flex items-start gap-3">
        <el-icon class="text-red-500 mt-1"><WarningFilled /></el-icon>
        <div>
          <div class="text-red-700 font-bold text-sm">当前排期存在硬冲突，禁止导出</div>
          <div class="text-red-600 text-xs mt-1">检测到 {{ stats.errorCount }} 处硬冲突，请先处理并重新复核。</div>
        </div>
      </div>

      <div v-else-if="stats.warningCount > 0" class="p-4 bg-orange-50 border border-orange-200 rounded flex items-start gap-3">
        <el-icon class="text-orange-500 mt-1"><InfoFilled /></el-icon>
        <div>
          <div class="text-orange-700 font-bold text-sm">当前排期存在提示项</div>
          <div class="text-orange-600 text-xs mt-1">系统检测到 {{ stats.warningCount }} 处警告，导出后请人工复核。</div>
        </div>
      </div>

      <div class="p-2">
        <div class="text-xs text-gray-500 mb-2">导出格式</div>
        <el-radio-group v-model="format" class="export-format-group">
          <el-radio value="word">Word 时间安排表（学院归档版式，含导师-学生同色标注）</el-radio>
          <el-radio value="conclusion">Word 评审小组结论（学院归档版式，每组一页，用于专家勾选与签名）</el-radio>
          <el-radio value="excel">Excel 分组明细（每组一个工作表，同色标注）</el-radio>
          <el-radio value="pdf">PDF · 打印或保存为 PDF（师生同色，冲突标红）</el-radio>
        </el-radio-group>
      </div>

      <div class="export-option-row">
        <div><strong>包含备注</strong><p>控制本次导出文件是否包含学生备注。</p></div>
        <el-switch v-model="includeRemarks" />
      </div>

      <div class="text-xs text-gray-400 p-2">
        <el-icon class="mr-1"><InfoFilled /></el-icon>
        提示：导师与其学生使用同一颜色标注；PDF 在打印窗口中保存，存在冲突的分组标红。
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :disabled="stats.errorCount > 0" @click="handleConfirm">继续导出</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { WarningFilled, InfoFilled, Document } from '@element-plus/icons-vue'
import type { ExportOptions } from '../types/export'

const props = defineProps<{
  modelValue: boolean
  options: ExportOptions
  stats: {
    groupCount: number
    studentCount: number
    conflictCount: number
    errorCount: number
    warningCount: number
  }
  versionInfo?: {
    versionNumber: number
    status: 'draft' | 'published'
    isCurrent: boolean
  }
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm', format: 'excel' | 'word' | 'conclusion' | 'pdf', includeRemarks: boolean): void
}>()

const format = ref<'excel' | 'word' | 'conclusion' | 'pdf'>('word')
const includeRemarks = ref(props.options.includeRemarks ?? true)

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

watch(() => props.modelValue, open => {
  if (open) includeRemarks.value = props.options.includeRemarks ?? true
})

const handleConfirm = () => {
  if (props.stats.errorCount > 0) return
  visible.value = false
  emit('confirm', format.value, includeRemarks.value)
}
</script>

<style scoped>
/* 四种导出的说明都比较长，竖排才不会在对话框里换行错位 */
.export-format-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
</style>
