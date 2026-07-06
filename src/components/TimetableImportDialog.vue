<template>
  <el-dialog
    v-model="visible"
    title="导入课表（生成教师不可用时间）"
    width="480px"
    destroy-on-close
  >
    <el-alert type="info" :closable="false" class="mb-4">
      <p>支持两种课表：软件学院矩阵式课表（.xlsx）与学部行式课表（.xls）。</p>
      <p>上课时间将追加为教师的"不可用时间"，仅更新系统中已有的教师，重复导入自动去重。</p>
    </el-alert>

    <el-form label-width="130px">
      <el-form-item label="学期第一周周一" required>
        <el-date-picker
          v-model="firstMonday"
          type="date"
          placeholder="选择第一教学周的周一"
          value-format="YYYY-MM-DD"
          :disabled-date="disableNonMonday"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="课表文件" required>
        <el-upload
          drag
          action="#"
          :auto-upload="false"
          accept=".xlsx, .xls, .csv"
          :on-change="handleFileChange"
          :limit="1"
          style="width: 100%"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">拖拽课表文件到此处或 <em>点击上传</em></div>
        </el-upload>
      </el-form-item>
    </el-form>

    <div v-if="result" class="mt-2 text-sm">
      <el-alert type="success" :closable="false">
        {{ result.message }}（共解析 {{ result.entryCount }} 条上课时间）
      </el-alert>
      <el-alert v-if="result.unknownTeacherNames.length" type="warning" :closable="false" class="mt-2">
        以下教师不在系统中，已跳过：{{ result.unknownTeacherNames.join('、') }}
      </el-alert>
      <el-alert v-if="result.warnings.length" type="warning" :closable="false" class="mt-2">
        <p v-for="(warning, index) in result.warnings" :key="index">{{ warning }}</p>
      </el-alert>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">关闭</el-button>
        <el-button type="primary" @click="handleConfirm" :loading="loading">
          导入课表
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
import { importTimetable } from '../api/teacher'
import type { TimetableImportResult } from '../api/teacher'

const props = defineProps<{ modelValue: boolean }>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'success'): void
}>()

const visible = ref(props.modelValue)
const firstMonday = ref('')
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const result = ref<TimetableImportResult | null>(null)

watch(() => props.modelValue, val => {
  visible.value = val
  if (val) {
    result.value = null
  }
})

watch(visible, val => {
  emit('update:modelValue', val)
})

// 学期第一周必须从周一起算，其他日期禁选
const disableNonMonday = (date: Date) => date.getDay() !== 1

const handleFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
}

const handleConfirm = async () => {
  if (!firstMonday.value) {
    ElMessage.warning('请先选择学期第一周周一的日期')
    return
  }
  if (!selectedFile.value) {
    ElMessage.warning('请先选择课表文件')
    return
  }

  loading.value = true
  try {
    result.value = await importTimetable(selectedFile.value, firstMonday.value)
    ElMessage.success(result.value.message || '课表导入成功')
    emit('success')
  } catch (e: any) {
    console.error(e)
    const errorMsg = e.response?.data?.error || e.response?.data?.message || '课表导入失败，请检查文件格式'
    ElMessage.error(errorMsg)
  } finally {
    loading.value = false
  }
}
</script>
