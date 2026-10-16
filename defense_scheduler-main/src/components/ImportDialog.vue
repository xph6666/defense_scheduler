<template>
  <el-dialog
    v-model="visible"
    :title="{ teacher: '导入教师与专家名单', student: '导入学生名单', classroom: '导入教室资料' }[type]"
    width="min(480px, 94vw)"
    destroy-on-close
  >
    <div class="py-4 text-center">
      <el-upload
        class="upload-demo"
        drag
        action="#"
        :auto-upload="false"
        accept=".xlsx, .xls, .csv"
        :on-change="handleFileChange"
        :limit="1"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip text-gray-500 mt-2">
            请选择 Excel 或 CSV 文件。
          </div>
        </template>
      </el-upload>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm" :loading="loading">
          确定导入
        </el-button>
      </span>
    </template>
  </el-dialog>

  <ImportPreviewDialog
    v-model="previewVisible"
    :module="type"
    @success="handlePreviewSuccess"
  />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { importTeachers } from '../api/teacher'
import { importStudents } from '../api/student'
import { importClassrooms } from '../api/classroom'
import { ApiRequestError } from '../api/request'
import ImportPreviewDialog from './ImportPreviewDialog.vue'

const USE_MOCK = (import.meta as any).env?.VITE_USE_MOCK === 'true'

const props = defineProps<{
  modelValue: boolean
  type: 'teacher' | 'student' | 'classroom'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'success'): void
}>()

const visible = ref(props.modelValue)
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const previewVisible = ref(false)

type ImportRowError = {
  row?: number
  errors?: Record<string, unknown> | string
}

const stringifyImportMessages = (value: unknown): string => {
  if (Array.isArray(value)) {
    return value.map(item => String(item)).join('、')
  }
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(stringifyImportMessages).join('、')
  }
  return String(value)
}

const formatImportError = (entry: unknown): string => {
  if (typeof entry === 'string') {
    return entry
  }
  if (entry && typeof entry === 'object') {
    const rowError = entry as ImportRowError
    const prefix = rowError.row ? `第 ${rowError.row} 行` : '数据行'
    if (typeof rowError.errors === 'string') {
      return `${prefix}: ${rowError.errors}`
    }
    if (rowError.errors && typeof rowError.errors === 'object') {
      const details = Object.entries(rowError.errors)
        .map(([field, messages]) => `${field}: ${stringifyImportMessages(messages)}`)
      if (details.length > 0) {
        return `${prefix}: ${details.join('；')}`
      }
    }
    return prefix
  }
  return String(entry)
}

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const handleFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
}

const handleConfirm = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }

  if (USE_MOCK) {
    previewVisible.value = true
    return
  }

  loading.value = true
  try {
    let res: any
    if (props.type === 'teacher') {
      res = await importTeachers(selectedFile.value)
    } else if (props.type === 'student') {
      res = await importStudents(selectedFile.value)
    } else {
      res = await importClassrooms(selectedFile.value)
    }

    ElMessage.success(res.message || '导入成功')
    if (res.warnings && res.warnings.length > 0) {
      const extra = res.warningCount > res.warnings.length
        ? `（共 ${res.warningCount} 条提醒，仅显示前 ${res.warnings.length} 条）`
        : ''
      ElMessage.warning({
        message: `${res.warnings.join('\n')}${extra}`,
        duration: 8000,
        showClose: true
      })
    }
    if (res.errors && res.errors.length > 0) {
      ElMessage.warning(`部分数据可能导入失败：${formatImportError(res.errors[0])}`)
    }
    emit('success')
    visible.value = false
  } catch (e: unknown) {
    console.error(e)
    const apiError = e instanceof ApiRequestError ? e : null
    const rawPayload =
      apiError?.data && typeof apiError.data === 'object'
        ? (apiError.data as Record<string, unknown>)
        : e && typeof e === 'object' && 'response' in e
          ? ((e as { response?: { data?: Record<string, unknown> } }).response?.data || {})
          : {}

    const errorMsg =
      apiError?.message ||
      (typeof rawPayload.message === 'string' && rawPayload.message) ||
      (typeof rawPayload.error === 'string' && rawPayload.error) ||
      (e instanceof Error ? e.message : '') ||
      '导入失败，请检查文件格式'

    const subErrors = Array.isArray(rawPayload.errors) ? rawPayload.errors : []

    if (subErrors.length > 0) {
      const shown = subErrors.slice(0, 3).map(formatImportError).join('；')
      const more =
        typeof rawPayload.errorCount === 'number' && rawPayload.errorCount > subErrors.length
          ? `（共 ${rawPayload.errorCount} 处错误）`
          : subErrors.length > 3
            ? `（另有 ${subErrors.length - 3} 处）`
            : ''
      ElMessage.error({
        message: `${errorMsg}：${shown}${more}`,
        duration: 8000,
        showClose: true
      })
    } else {
      ElMessage.error(errorMsg)
    }
  } finally {
    loading.value = false
  }
}

const handlePreviewSuccess = () => {
  emit('success')
  visible.value = false
}
</script>
