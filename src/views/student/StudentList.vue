<template>
  <div class="bg-white p-6 rounded-lg shadow-sm">
    <!-- Search Bar -->
    <el-form :inline="true" :model="searchForm" class="mb-4">
      <el-form-item label="姓名">
        <el-input v-model="searchForm.name" placeholder="请输入姓名" clearable @keyup.enter="handleSearch" style="width: 180px" />
      </el-form-item>
      <el-form-item label="导师">
        <el-input v-model="searchForm.mentorName" placeholder="请输入导师" clearable @keyup.enter="handleSearch" style="width: 180px" />
      </el-form-item>
      <el-form-item label="所属校区">
        <el-select v-model="searchForm.campus" placeholder="选择校区" clearable style="width: 180px">
          <el-option label="创新港" value="创新港" />
          <el-option label="兴庆" value="兴庆" />
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
      <el-table-column prop="name" label="姓名" width="120" />
      <el-table-column prop="studentType" label="学生类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.studentType === '学硕' ? 'primary' : 'success'">{{ row.studentType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="mentorName" label="导师" width="120" />
      <el-table-column prop="campus" label="所属校区" width="100" />
      <el-table-column prop="defenseTypes" label="参与环节" min-width="150">
        <template #default="{ row }">
          <el-tag v-for="type in row.defenseTypes" :key="type" size="small" class="mr-1 mb-1">{{ type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="secretaryName" label="对应秘书" width="120" />
      <el-table-column prop="currentGroup" label="当前分组" width="120">
        <template #default="{ row }">
          <span v-if="row.currentGroup" class="text-blue-500 font-medium">{{ row.currentGroup }}</span>
          <span v-else class="text-gray-400">未分组</span>
        </template>
      </el-table-column>
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
      :title="isEdit ? '编辑学生' : '新增学生'"
      width="500px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入学生姓名" />
        </el-form-item>
        <el-form-item label="学生类型" prop="studentType">
          <el-select v-model="form.studentType" placeholder="请选择学生类型" style="width: 100%">
            <el-option label="学硕" value="学硕" />
            <el-option label="专硕" value="专硕" />
          </el-select>
        </el-form-item>
        <el-form-item label="导师" prop="mentorName">
          <el-input v-model="form.mentorName" placeholder="请输入导师姓名" />
        </el-form-item>
        <el-form-item label="所属校区" prop="campus">
          <el-select v-model="form.campus" placeholder="请选择校区" style="width: 100%">
            <el-option label="创新港" value="创新港" />
            <el-option label="兴庆" value="兴庆" />
          </el-select>
        </el-form-item>
        <el-form-item label="参与环节" prop="defenseTypes">
          <el-select v-model="form.defenseTypes" multiple placeholder="请选择参与环节" style="width: 100%">
            <el-option label="预答辩" value="预答辩" />
            <el-option label="正式答辩" value="正式答辩" />
            <el-option label="中期答辩" value="中期答辩" />
          </el-select>
        </el-form-item>
        <el-form-item label="对应秘书" prop="secretaryName">
          <el-input v-model="form.secretaryName" placeholder="请输入对应秘书姓名" />
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
import { listStudents, createStudent, updateStudent, deleteStudent } from '../../api/student'
import type { Student } from '../../types/student'

const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const importVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const tableData = ref<Student[]>([])
const allData = ref<Student[]>([])

const searchForm = reactive({
  name: '',
  mentorName: '',
  campus: ''
})

const defaultForm: Omit<Student, 'id'> = {
  name: '',
  studentType: '学硕',
  mentorName: '',
  campus: '创新港',
  defenseTypes: [],
  secretaryName: '',
  currentGroup: undefined,
  remark: ''
}

const form = reactive<Student>({ id: 0, ...defaultForm })

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入学生姓名', trigger: 'blur' }],
  studentType: [{ required: true, message: '请选择学生类型', trigger: 'change' }],
  mentorName: [{ required: true, message: '请输入导师姓名', trigger: 'blur' }],
  campus: [{ required: true, message: '请选择所属校区', trigger: 'change' }],
  defenseTypes: [{ required: true, type: 'array', message: '请选择参与环节', trigger: 'change' }]
})

const fetchData = async () => {
  loading.value = true
  try {
    const data = await listStudents()
    allData.value = data
    handleSearch()
  } catch (error) {
    ElMessage.error('获取学生数据失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  tableData.value = allData.value.filter(item => {
    const matchName = !searchForm.name || item.name.includes(searchForm.name)
    const matchMentor = !searchForm.mentorName || item.mentorName.includes(searchForm.mentorName)
    const matchCampus = !searchForm.campus || item.campus === searchForm.campus
    return matchName && matchMentor && matchCampus
  })
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.mentorName = ''
  searchForm.campus = ''
  handleSearch()
}

const handleAdd = () => {
  isEdit.value = false
  Object.assign(form, { id: 0, ...defaultForm })
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleEdit = (row: Student) => {
  isEdit.value = true
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleDelete = (row: Student) => {
  ElMessageBox.confirm(`确定要删除学生 "${row.name}" 吗？`, '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteStudent(row.id)
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
          await updateStudent(form.id, form)
          ElMessage.success('修改成功')
        } else {
          const { id, ...data } = form
          await createStudent(data)
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
