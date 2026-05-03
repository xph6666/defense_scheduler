<template>
  <el-dialog
    v-model="visible"
    title="导入数据"
    width="400px"
    destroy-on-close
  >
    <div class="py-4 text-center">
      <el-upload
        class="upload-demo"
        drag
        action="#"
        :auto-upload="false"
        accept=".xlsx, .csv"
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
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { importTeachers } from '../api/teacher'
import { importStudents } from '../api/student'
import { importClassrooms } from '../api/classroom'

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
    if (res.errors && res.errors.length > 0) {
      console.warn('部分数据导入失败:', res.errors)
      ElMessage.warning(`部分数据可能导入失败，详见控制台。`)
    }
    emit('success')
    visible.value = false
  } catch (e: any) {
    console.error(e)
    const errorMsg = e.response?.data?.message || e.response?.data?.error || '导入失败，请检查文件格式'
    const subErrors = e.response?.data?.errors
    
    if (subErrors && subErrors.length > 0) {
      ElMessage.error({
        message: `${errorMsg}: ${subErrors[0]}`,
        duration: 5000
      })
    } else {
      ElMessage.error(errorMsg)
    }
  } finally {
    loading.value = false
  }
}
</script>
