<template>
  <el-dialog
    v-model="visible"
    title="导入课表（生成教师不可用时间）"
    width="min(820px, 94vw)"
    destroy-on-close
    :close-on-click-modal="!loading"
    :show-close="!loading"
  >
    <el-alert type="info" :closable="false" class="mb-4">
      <p>支持 Excel（.xlsx / .xls）及 UTF-8 CSV：矩阵式课表或含“主讲教师／时间地点”的行式课表。</p>
      <p>上课时间将追加为教师的"不可用时间"，仅更新系统中已有的教师，重复导入自动去重。</p>
      <p>模板可填写系统教师编号，优先校验编号；旧课表按系统唯一姓名匹配。周次支持连续周、单周、双周。</p>
      <el-button link type="primary" @click="downloadTimetableTemplate">下载模板与教师编号目录</el-button>
    </el-alert>

    <el-form label-width="130px">
      <el-form-item label="学期第一周周一" required>
        <el-date-picker
          v-model="firstMonday"
          type="date"
          placeholder="选择第一教学周的周一"
          value-format="YYYY-MM-DD"
          :disabled-date="disableNonMonday"
          :disabled="loading"
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
          :on-remove="handleFileRemove"
          :disabled="loading"
          :limit="1"
          style="width: 100%"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">拖拽课表文件到此处或 <em>点击上传</em></div>
        </el-upload>
      </el-form-item>
    </el-form>

    <div v-if="result" class="mt-2 text-sm">
      <el-alert :type="result.preview ? 'info' : 'success'" :closable="false">
        {{ result.message }}（共解析 {{ result.entryCount }} 条上课时间）
      </el-alert>
      <p v-if="result.preview" class="my-3">匹配 {{ result.matchedTeachers }} 位教师，已有 {{ result.duplicateCount || 0 }} 条时段将去重。确认后仅导入下列已匹配的有效记录。</p>
      <el-table v-if="result.rows?.length" :data="result.rows" max-height="300" class="mt-3">
        <el-table-column prop="teacherId" label="教师编号" width="90" />
        <el-table-column prop="teacherName" label="教师" width="110" />
        <el-table-column label="匹配" width="95"><template #default="{ row }"><el-tag :type="row.matched ? 'success' : 'danger'">{{ row.matched ? '已匹配' : '未匹配' }}</el-tag></template></el-table-column>
        <el-table-column label="课程占用时段" min-width="250"><template #default="{ row }"><div v-for="entry in row.entries" :key="entry">{{ entry }}</div></template></el-table-column>
        <el-table-column prop="duplicateCount" label="已存在" width="85" />
      </el-table>
      <el-alert v-if="result.unknownTeacherNames.length" type="warning" :closable="false" class="mt-2">
        以下教师不在系统中，不会导入：{{ result.unknownTeacherNames.join('、') }}
      </el-alert>
      <el-alert v-if="result.warnings.length" type="warning" :closable="false" class="mt-2">
        <p v-for="(warning, index) in result.warnings" :key="index">{{ warning }}</p>
      </el-alert>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button :disabled="loading" @click="visible = false">关闭</el-button>
        <el-button v-if="result?.preview" @click="result = null" :disabled="loading">重新选择</el-button>
        <el-button type="primary" @click="handleConfirm" :loading="loading" :disabled="result?.preview === true && !result.canImport">
          {{ result?.preview ? '确认导入有效记录' : '解析并预览' }}
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
import { importTimetable, downloadTimetableTemplate } from '../api/teacher'
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
    selectedFile.value = null
  }
})

watch(visible, val => {
  emit('update:modelValue', val)
})

// 学期第一周必须从周一起算，其他日期禁选
const disableNonMonday = (date: Date) => date.getDay() !== 1

const handleFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
  result.value = null
}
const handleFileRemove = () => { selectedFile.value = null; result.value = null }
watch(firstMonday, () => { result.value = null })

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
    const confirming = result.value?.preview === true
    result.value = await importTimetable(selectedFile.value, firstMonday.value, {
      preview: !confirming, previewToken: confirming ? result.value?.previewToken : undefined
    })
    if (confirming) {
      ElMessage.success(result.value.message || '课表导入成功')
      emit('success')
    }
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '课表导入失败，请检查文件格式')
  } finally {
    loading.value = false
  }
}
</script>
