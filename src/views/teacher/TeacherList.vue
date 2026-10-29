<template>
  <div class="data-list-page bg-white rounded-lg shadow-sm">
    <PreparationGuide title="教师与专家" description="确认姓名、职称、担任角色及不可用时间；有课表时也可以直接导入。" />
    <DataListSearch v-model="searchQuery" placeholder="姓名 / 学院 / 职称 / 角色" :count="filteredData.length" @search="handleSearch">
    </DataListSearch>

    <!-- Toolbar -->
    <div v-if="canManage" class="data-list-toolbar">
      <div class="data-list-actions">
        <el-button @click="handleAdd">
          <el-icon class="mr-1"><Plus /></el-icon>新增
        </el-button>
        <el-button type="primary" @click="openImport">
          <el-icon class="mr-1"><Upload /></el-icon>导入 Excel
        </el-button>
        <el-button type="primary" plain @click="cohortImportVisible = true">批量导入学生与导师</el-button>
        <el-button type="warning" @click="openTimetableImport">
          <el-icon class="mr-1"><Calendar /></el-icon>导入课表
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
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="college" label="所属学院" width="150" />
      <el-table-column prop="isExternal" label="是否外院" width="100">
        <template #default="{ row }">
          <el-tag :type="row.isExternal ? 'warning' : 'info'">{{ row.isExternal ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态与资格" min-width="185">
        <template #default="{ row }">
          <el-tag :type="row.isActive === false ? 'info' : 'success'" size="small">{{ row.isActive === false ? '已停用' : '在用' }}</el-tag>
          <el-tag v-if="row.memberEligible === false" size="small" type="warning" class="ml-1">仅主席/组长</el-tag>
          <el-tag v-if="row.expertOnly" size="small" type="warning" class="ml-1">仅普通专家</el-tag>
          <el-tag v-if="row.isSoftwareTeacher" size="small" class="ml-1">软件学院</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="职称 / 待确认身份" min-width="180" />
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
      <el-table-column prop="availableTimes" label="可用时间" min-width="120" show-overflow-tooltip />
      <el-table-column label="时间确认" width="110"><template #default="{ row }"><el-tag :type="row.availabilityConfirmed || row.availableTimes || row.unavailableTimes ? 'success' : 'warning'">{{ row.availabilityConfirmed || row.availableTimes || row.unavailableTimes ? '已维护' : '待确认' }}</el-tag></template></el-table-column>
      <el-table-column label="同组多名学生" width="120"><template #default="{ row }">{{ row.allowMultipleStudents ? '已明确允许' : '按组人数均衡安排' }}</template></el-table-column>
      <el-table-column prop="avoidTeacherNames" label="不宜同组" min-width="120" show-overflow-tooltip />
      <el-table-column v-if="canManage" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="data-list-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="filteredData.length"
        layout="total, sizes, prev, pager, next, jumper"
        background
        :pager-count="5"
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>

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
        <el-form-item label="参与排期"><el-switch v-model="form.isActive" active-text="在用" inactive-text="停用" /></el-form-item>
        <el-form-item label="适合担任组员"><el-switch v-model="form.memberEligible" :disabled="form.expertOnly" /><span class="text-xs text-gray-500 ml-2">关闭后仅可担任主席或组长。</span></el-form-item>
        <el-form-item label="仅普通专家"><el-switch v-model="form.expertOnly" /><span class="text-xs text-gray-500 ml-2">启用后不允许担任主席、组长或秘书，职称不代表角色授权。</span></el-form-item>
        <el-form-item label="计为软件学院导师"><el-switch v-model="form.isSoftwareTeacher" /><span class="text-xs text-gray-500 ml-2">补充认定；非外院且学院含“软件”时自动计入。</span></el-form-item>
        <el-form-item label="职称" prop="title">
          <el-select v-model="form.title" placeholder="请选择职称" style="width: 100%">
            <!-- [TASK-P04 修改] 支持录入教授/研究员序列职称。 -->
            <el-option label="教授" value="教授" />
            <el-option label="研究员" value="研究员" />
            <el-option label="副教授" value="副教授" />
            <el-option label="副研究员" value="副研究员" />
            <el-option label="讲师" value="讲师" />
            <el-option label="其他" value="其他" />
            <el-option label="外院导师（职称待确认）" value="外院导师（职称待确认）" />
            <el-option label="职称待确认" value="职称待确认" />
          </el-select>
        </el-form-item>
        <el-form-item label="可担任角色" prop="roles">
          <el-select v-model="form.roles" multiple placeholder="请选择可担任角色" style="width: 100%">
            <el-option label="主席" value="主席" :disabled="form.expertOnly" />
            <el-option label="组长" value="组长" :disabled="form.expertOnly" />
            <el-option label="秘书" value="秘书" :disabled="form.expertOnly" />
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
        <el-form-item label="可用时间">
          <el-input v-model="form.availableTimes" placeholder="如：周一至周五全天；与不可用时间共同生效" />
        </el-form-item>
        <el-form-item label="可用时间已确认">
          <el-switch v-model="form.availabilityConfirmed" />
          <span class="text-xs text-gray-500 ml-2">未填写限制时可按无额外限制生成草稿，并保留待核对提醒；确认后表示无额外时间限制。已有课表仍生效。</span>
        </el-form-item>
        <el-form-item label="同组多名指导学生">
          <el-switch v-model="form.allowMultipleStudents" />
          <span class="text-xs text-gray-500 ml-2">预答辩已允许多名同导师学生同组，按组人数均衡安排；此项保留明确备注。</span>
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

    <ImportDialog v-if="canManage" v-model="importVisible" type="teacher" @success="fetchData" />
    <CohortImportDialog v-if="canManage" v-model="cohortImportVisible" @success="fetchData" />
    <TimetableImportDialog v-if="canManage" v-model="timetableImportVisible" @success="fetchData" />
  </div>
</template>

<script setup lang="ts">
import PreparationGuide from '../../components/PreparationGuide.vue'
import DataListSearch from '../../components/DataListSearch.vue'
import { matchesListSearch } from '../../utils/listSearch'
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Upload, Delete, Calendar } from '@element-plus/icons-vue'
import ImportDialog from '../../components/ImportDialog.vue'
import CohortImportDialog from '../../components/CohortImportDialog.vue'
import TimetableImportDialog from '../../components/TimetableImportDialog.vue'
import { listTeachers, createTeacher, updateTeacher, deleteTeacher, batchDeleteTeachers } from '../../api/teacher'
import type { Teacher } from '../../types/teacher'
import { useAdminGuard } from '../../utils/adminGuard'

const loading = ref(false)
const submitLoading = ref(false)
const batchDeleteLoading = ref(false)
const dialogVisible = ref(false)
const importVisible = ref(false)
const cohortImportVisible = ref(false)
const timetableImportVisible = ref(false)
const isEdit = ref(false)
const formRef = ref<FormInstance>()
const allData = ref<Teacher[]>([])
const filteredData = ref<Teacher[]>([])
const selectedIds = ref<number[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const { canManage, requireAdmin } = useAdminGuard()

const tableData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

const handleSelectionChange = (selection: Teacher[]) => {
  selectedIds.value = selection.map(item => item.id)
}

const handleBatchDelete = () => {
  if (!requireAdmin()) return
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

const searchQuery = ref('')

const defaultForm: Omit<Teacher, 'id'> = {
  name: '',
  college: '',
  isExternal: false,
  isActive: true,
  memberEligible: true,
  expertOnly: false,
  isSoftwareTeacher: false,
  title: '讲师',
  roles: [],
  availableTypes: [],
  campusPreference: '不限',
  unavailableTimes: '',
  availableTimes: '',
  availabilityConfirmed: false,
  allowMultipleStudents: false,
  avoidTeacherNames: '',
  remark: ''
}

const form = reactive<Teacher>({ id: 0, ...defaultForm })
watch(() => form.expertOnly, value => { if (value) { form.roles = ['普通专家']; form.memberEligible = true } })

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
  filteredData.value = allData.value.filter(item => matchesListSearch(searchQuery.value, [item.name, item.college, item.title, item.roles, item.isExternal ? "外院" : "校内"]))
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


const handleAdd = () => {
  if (!requireAdmin()) return
  isEdit.value = false
  Object.assign(form, { id: 0, ...defaultForm })
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleEdit = (row: Teacher) => {
  if (!requireAdmin()) return
  isEdit.value = true
  Object.assign(form, defaultForm, JSON.parse(JSON.stringify(row)))
  dialogVisible.value = true
  if (formRef.value) formRef.value.clearValidate()
}

const handleDelete = (row: Teacher) => {
  if (!requireAdmin()) return
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
  if (!requireAdmin()) return
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitLoading.value = true
      try {
        if (isEdit.value) {
          await updateTeacher(form.id, form)
          ElMessage.success('修改成功')
        } else {
          const { id: _id, ...data } = form
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

const openImport = () => {
  if (!requireAdmin()) return
  importVisible.value = true
}

const openTimetableImport = () => {
  if (!requireAdmin()) return
  timetableImportVisible.value = true
}

onMounted(() => {
  fetchData()
})
</script>
