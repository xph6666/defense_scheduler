<template>
  <div class="bg-white p-6 rounded-lg shadow-sm">
    <PreparationGuide title="教室与时间" description="确认校区、容量和可用时段。教室可用日期应覆盖本次答辩日期。" />
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
    <div v-if="canManage" class="mb-4 flex justify-between items-center">
      <div class="flex flex-wrap gap-2">
        <el-button @click="handleAdd">
          <el-icon class="mr-1"><Plus /></el-icon>新增
        </el-button>
        <el-button type="primary" @click="openImport">
          <el-icon class="mr-1"><Upload /></el-icon>导入 Excel
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
      <el-table-column v-if="canManage" type="selection" width="55" />
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
      <el-table-column v-if="canManage" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4 flex justify-end">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="filteredData.length"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>

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

    <ImportDialog v-if="canManage" v-model="importVisible" type="classroom" @success="fetchData" />
  </div>
</template>

<script setup lang="ts">
import PreparationGuide from '../../components/PreparationGuide.vue'
import { computed, ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Search, Plus, Upload, Delete } from '@element-plus/icons-vue'
import ImportDialog from '../../components/ImportDialog.vue'
import { listClassrooms, createClassroom, updateClassroom, deleteClassroom, batchDeleteClassrooms } from '../../api/classroom'
import type { Classroom } from '../../types/classroom'
import { useAdminGuard } from '../../utils/adminGuard'

const loading = ref(false)
const submitLoading = ref(false)
const batchDeleteLoading = ref(false)
const dialogVisible = ref(false)
const importVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const allData = ref<Classroom[]>([])
const filteredData = ref<Classroom[]>([])
const selectedIds = ref<number[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const { canManage, requireAdmin } = useAdminGuard()

const tableData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

const handleSelectionChange = (selection: Classroom[]) => {
  selectedIds.value = selection.map(item => item.id)
}

const handleBatchDelete = () => {
  if (!requireAdmin()) return
  if (!selectedIds.value.length) return
  
  ElMessageBox.confirm(
    `确定要批量删除已选中的 ${selectedIds.value.length} 个教室吗？`,
    '批量删除警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    batchDeleteLoading.value = true
    try {
      await batchDeleteClassrooms(selectedIds.value)
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
  filteredData.value = allData.value.filter(item => {
    const matchCampus = !searchForm.campus || item.campus === searchForm.campus
    const matchName = !searchForm.name || item.name.includes(searchForm.name)
    return matchCampus && matchName
  })
  currentPage.value = 1
  selectedIds.value = []
}

const handlePageChange = () => {
  selectedIds.value = []
}

const handlePageSizeChange = () => {
  currentPage.value = 1
  selectedIds.value = []
}

const resetSearch = () => {
  searchForm.campus = ''
  searchForm.name = ''
  handleSearch()
}

const handleAdd = () => {
  if (!requireAdmin()) return
  isEdit.value = false
  Object.assign(form, { id: 0, ...defaultForm })
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleEdit = (row: Classroom) => {
  if (!requireAdmin()) return
  isEdit.value = true
  Object.assign(form, JSON.parse(JSON.stringify(row)))
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleDelete = (row: Classroom) => {
  if (!requireAdmin()) return
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
  if (!requireAdmin()) return
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitLoading.value = true
      try {
        if (isEdit.value) {
          await updateClassroom(form.id, form)
          ElMessage.success('修改成功')
        } else {
          const { id: _id, ...data } = form
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

const openImport = () => {
  if (!requireAdmin()) return
  importVisible.value = true
}

onMounted(() => {
  fetchData()
})
</script>
