<template>
  <div class="bg-white p-6 rounded-lg shadow-sm">
    <!-- Search Bar -->
    <el-form :inline="true" :model="searchForm" class="mb-4">
      <el-form-item label="校区">
        <el-select v-model="searchForm.campus" placeholder="选择校区" clearable style="width: 180px">
          <el-option label="创新港" value="创新港" />
          <el-option label="兴庆" value="兴庆" />
        </el-select>
      </el-form-item>
      <el-form-item label="教室名称">
        <el-input v-model="searchForm.name" placeholder="请输入教室名称/编号" clearable @keyup.enter="handleSearch" style="width: 180px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">
          <el-icon class="mr-1"><Search /></el-icon>搜索
        </el-button>
        <el-button @click="resetSearch">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- Toolbar -->
    <div class="mb-4 flex gap-2">
      <el-button type="primary" @click="handleAdd">
        <el-icon class="mr-1"><Plus /></el-icon>新增
      </el-button>
      <el-button type="success" @click="importVisible = true">
        <el-icon class="mr-1"><Upload /></el-icon>导入
      </el-button>
    </div>

    <!-- Table -->
    <el-table :data="tableData" v-loading="loading" border style="width: 100%">
      <el-table-column prop="campus" label="校区" width="120">
        <template #default="{ row }">
          <el-tag :type="row.campus === '创新港' ? 'primary' : 'success'">{{ row.campus }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="教室名称/编号" width="200" />
      <el-table-column prop="capacity" label="容量" width="120">
        <template #default="{ row }">
          <span class="font-medium text-gray-700">{{ row.capacity }} 人</span>
        </template>
      </el-table-column>
      <el-table-column prop="availableTimes" label="可用时间" min-width="200" />
      <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑教室' : '新增教室'"
      width="500px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="所属校区" prop="campus">
          <el-select v-model="form.campus" placeholder="请选择校区" style="width: 100%">
            <el-option label="创新港" value="创新港" />
            <el-option label="兴庆" value="兴庆" />
          </el-select>
        </el-form-item>
        <el-form-item label="教室名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入教室名称或编号" />
        </el-form-item>
        <el-form-item label="容量" prop="capacity">
          <el-input-number v-model="form.capacity" :min="1" :max="500" style="width: 100%" />
        </el-form-item>
        <el-form-item label="可用时间" prop="availableTimes">
          <el-input v-model="form.availableTimes" placeholder="请输入可用时间，如: 周一至周五全天" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitLoading">确定</el-button>
        </span>
      </template>
    </el-dialog>

    <ImportDialog v-model="importVisible" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Search, Plus, Upload } from '@element-plus/icons-vue'
import ImportDialog from '../../components/ImportDialog.vue'
import { listClassrooms, createClassroom, updateClassroom, deleteClassroom } from '../../api/classroom'
import type { Classroom } from '../../types/classroom'

const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const importVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const tableData = ref<Classroom[]>([])
const allData = ref<Classroom[]>([])

const searchForm = reactive({
  campus: '',
  name: ''
})

const defaultForm: Omit<Classroom, 'id'> = {
  campus: '创新港',
  name: '',
  capacity: 30,
  availableTimes: '',
  remark: ''
}

const form = reactive<Classroom>({ id: 0, ...defaultForm })

const rules = reactive<FormRules>({
  campus: [{ required: true, message: '请选择所属校区', trigger: 'change' }],
  name: [{ required: true, message: '请输入教室名称/编号', trigger: 'blur' }],
  capacity: [{ required: true, type: 'number', message: '请输入教室容量', trigger: 'blur' }],
  availableTimes: [{ required: true, message: '请输入可用时间', trigger: 'blur' }]
})

const fetchData = async () => {
  loading.value = true
  try {
    const data = await listClassrooms()
    allData.value = data
    handleSearch()
  } catch (error) {
    ElMessage.error('获取教室数据失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  tableData.value = allData.value.filter(item => {
    const matchCampus = !searchForm.campus || item.campus === searchForm.campus
    const matchName = !searchForm.name || item.name.includes(searchForm.name)
    return matchCampus && matchName
  })
}

const resetSearch = () => {
  searchForm.campus = ''
  searchForm.name = ''
  handleSearch()
}

const handleAdd = () => {
  isEdit.value = false
  Object.assign(form, { id: 0, ...defaultForm })
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleEdit = (row: Classroom) => {
  isEdit.value = true
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleDelete = (row: Classroom) => {
  ElMessageBox.confirm(`确定要删除教室 "${row.name}" 吗？`, '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteClassroom(row.id)
      ElMessage.success('删除成功')
      fetchData()
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitLoading.value = true
      try {
        if (isEdit.value) {
          await updateClassroom(form.id, form)
          ElMessage.success('修改成功')
        } else {
          const { id, ...data } = form
          await createClassroom(data)
          ElMessage.success('新增成功')
        }
        dialogVisible.value = false
        fetchData()
      } catch (error) {
        ElMessage.error(isEdit.value ? '修改失败' : '新增失败')
      } finally {
        submitLoading.value = false
      }
    }
  })
}

onMounted(() => {
  fetchData()
})
</script>
