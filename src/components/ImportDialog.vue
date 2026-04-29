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
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip text-gray-500 mt-2">
            请选择 Excel 或 CSV 文件。本周版本仅完成导入入口，后续将对接批量导入接口。
          </div>
        </template>
      </el-upload>
    </div>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm">
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

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const handleConfirm = () => {
  ElMessage.success('导入功能后续对接后端接口')
  visible.value = false
}
</script>
