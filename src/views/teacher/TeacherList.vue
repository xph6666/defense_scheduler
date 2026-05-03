<template>
  <div class="bg-white p-6 rounded-lg shadow-sm">
    <!-- Search Bar -->
    <el-form :inline="true" :model="searchForm" class="mb-4">
      <el-form-item label="姓名">
        <el-input v-model="searchForm.name" placeholder="请输入姓名" clearable @keyup.enter="handleSearch" style="width: 180px" />
      </el-form-item>
      <el-form-item label="学院">
        <el-input v-model="searchForm.college" placeholder="请输入学院" clearable @keyup.enter="handleSearch" style="width: 180px" />
      </el-form-item>
      <el-form-item label="职称">
        <el-select v-model="searchForm.title" placeholder="选择职称" clearable style="width: 180px">
          <el-option label="教授" value="教授" />
          <el-option label="副教授" value="副教授" />
          <el-option label="讲师" value="讲师" />
          <el-option label="其他" value="其他" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">
          <el-icon class="mr-1"><Search /></el-icon>搜索
        </el-button>
        <el-button @click="resetSearch">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- Toolbar -->
    <div class="mb-4 flex justify-between items-center">
      <div class="flex gap-2">
        <el-button type="primary" @click="handleAdd">
          <el-icon class="mr-1"><Plus /></el-icon>新增
        </el-button>
        <el-button type="success" @click="importVisible = true">
          <el-icon class="mr-1"><Upload /></el-icon>导入
        </el-button>
        <el-button 
          type="danger" 
          :disabled="!selectedIds.length" 
          @click="handleBatchDelete"
          :loading="batchDeleteLoading"
        >
          <el-icon class="mr-1"><Delete /></el-icon>批量删除
        </el-button>
      </div>
      <div v-if="selectedIds.length" class="text-sm text-gray-500">
        已选择 {{ selectedIds.length }} 项
      </div>
    </div>

    <!-- Table -->
    <el-table 
      :data="tableData" 
      v-loading="loading" 
      border 
      style="width: 100%"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="college" label="所属学院" width="150" />
      <el-table-column prop="isExternal" label="是否外院" width="100">
        <template #default="{ row }">
          <el-tag :type="row.isExternal ? 'warning' : 'info'">{{ row.isExternal ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="职称" width="100" />
      <el-table-column prop="roles" label="可担任角色" min-width="150">
        <template #default="{ row }">
          <el-tag v-for="role in row.roles" :key="role" size="small" class="mr-1 mb-1">{{ role }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="availableTypes" label="可参加答辩类型" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="type in row.availableTypes" :key="type" size="small" type="success" class="mr-1 mb-1">{{ type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="campusPreference" label="校区偏好" width="100" />
      <el-table-column prop="unavailableTimes" label="不可用时间" min-width="120" show-overflow-tooltip />
      <el-table-column prop="avoidTeacherNames" label="不宜同组" min-width="120" show-overflow-tooltip />
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
      :title="isEdit ? '编辑教师' : '新增教师'"
      width="600px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="所属学院" prop="college">
          <el-input v-model="form.college" placeholder="请输入所属学院" />
        </el-form-item>
        <el-form-item label="是否外院" prop="isExternal">
          <el-switch v-model="form.isExternal" />
        </el-form-item>
        <el-form-item label="职称" prop="title">
          <el-select v-model="form.title" placeholder="请选择职称" style="width: 100%">
            <el-option label="教授" value="教授" />
            <el-option label="副教授" value="副教授" />
            <el-option label="讲师" value="讲师" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="可担任角色" prop="roles">
          <el-select v-model="form.roles" multiple placeholder="请选择可担任角色" style="width: 100%">
            <el-option label="主席" value="主席" />
            <el-option label="组长" value="组长" />
            <el-option label="秘书" value="秘书" />
            <el-option label="普通专家" value="普通专家" />
          </el-select>
        </el-form-item>
        <el-form-item label="参加答辩类型" prop="availableTypes">
          <el-select v-model="form.availableTypes" multiple placeholder="请选择答辩类型" style="width: 100%">
            <el-option label="预答辩" value="预答辩" />
            <el-option label="正式答辩" value="正式答辩" />
            <el-option label="中期答辩" value="中期答辩" />
          </el-select>
        </el-form-item>
        <el-form-item label="校区偏好" prop="campusPreference">
          <el-select v-model="form.campusPreference" placeholder="请选择校区偏好" style="width: 100%">
            <el-option label="创新港" value="创新港" />
            <el-option label="兴庆" value="兴庆" />
            <el-option label="不限" value="不限" />
          </el-select>
        </el-form-item>
        <el-form-item label="不可用时间" prop="unavailableTimes">
          <el-input v-model="form.unavailableTimes" placeholder="请输入不可用时间，如: 周二上午" />
        </el-form-item>
        <el-form-item label="不宜同组专家" prop="avoidTeacherNames">
          <el-input v-model="form.avoidTeacherNames" placeholder="请输入不宜同组的专家姓名" />
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

    <ImportDialog v-model="importVisible" type="teacher" @success="fetchData" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Search, Plus, Upload, Delete } from '@element-plus/icons-vue'
import ImportDialog from '../../components/ImportDialog.vue'
import { listTeachers, createTeacher, updateTeacher, deleteTeacher, batchDeleteTeachers } from '../../api/teacher'
import type { Teacher } from '../../types/teacher'

const loading = ref(false)
const submitLoading = ref(false)
const batchDeleteLoading = ref(false)
const dialogVisible = ref(false)
const importVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const tableData = ref<Teacher[]>([])
const allData = ref<Teacher[]>([])
const selectedIds = ref<number[]>([])

const handleSelectionChange = (selection: Teacher[]) => {
  selectedIds.value = selection.map(item => item.id)
}

const handleBatchDelete = () => {
  if (!selectedIds.value.length) return
  
  ElMessageBox.confirm(
    `确定要批量删除已选中的 ${selectedIds.value.length} 名教师吗？`,
    '批量删除警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    batchDeleteLoading.value = true
    try {
      await batchDeleteTeachers(selectedIds.value)
      ElMessage.success('批量删除成功')
      selectedIds.value = []
      fetchData()
    } catch (error) {
      ElMessage.error('批量删除失败')
    } finally {
      batchDeleteLoading.value = false
    }
  }).catch(() => {})
}

const searchForm = reactive({
  name: '',
  college: '',
  title: ''
})

const defaultForm: Omit<Teacher, 'id'> = {
  name: '',
  college: '',
  isExternal: false,
  title: '讲师',
  roles: [],
  availableTypes: [],
  campusPreference: '不限',
  unavailableTimes: '无',
  avoidTeacherNames: '',
  remark: ''
}

const form = reactive<Teacher>({ id: 0, ...defaultForm })

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  college: [{ required: true, message: '请输入所属学院', trigger: 'blur' }],
  title: [{ required: true, message: '请选择职称', trigger: 'change' }],
  roles: [{ required: true, type: 'array', message: '请选择可担任角色', trigger: 'change' }],
  availableTypes: [{ required: true, type: 'array', message: '请选择参加答辩类型', trigger: 'change' }],
  campusPreference: [{ required: true, message: '请选择校区偏好', trigger: 'change' }]
})

const fetchData = async () => {
  loading.value = true
  try {
    const data = await listTeachers()
    allData.value = data
    handleSearch()
  } catch (error) {
    ElMessage.error('获取教师数据失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  tableData.value = allData.value.filter(item => {
    const matchName = !searchForm.name || item.name.includes(searchForm.name)
    const matchCollege = !searchForm.college || item.college.includes(searchForm.college)
    const matchTitle = !searchForm.title || item.title === searchForm.title
    return matchName && matchCollege && matchTitle
  })
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.college = ''
  searchForm.title = ''
  handleSearch()
}

const handleAdd = () => {
  isEdit.value = false
  Object.assign(form, { id: 0, ...defaultForm })
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleEdit = (row: Teacher) => {
  isEdit.value = true
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleDelete = (row: Teacher) => {
  ElMessageBox.confirm(`确定要删除教师 "${row.name}" 吗？`, '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteTeacher(row.id)
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
          await updateTeacher(form.id, form)
          ElMessage.success('修改成功')
        } else {
          const { id, ...data } = form
          await createTeacher(data)
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
