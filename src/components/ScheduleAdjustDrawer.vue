<template>
  <el-drawer v-model="visible" :title="drawerTitle" size="640px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" :disabled="readonly">
      <el-form-item label="组名" prop="groupName">
        <el-input v-model="form.groupName" />
      </el-form-item>

      <el-form-item label="日期" prop="date">
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>

      <el-form-item label="时间段" prop="timeRange">
        <el-select v-model="form.timeRange" style="width: 100%">
          <el-option v-for="t in timeOptions" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>

      <el-form-item label="校区" prop="campus">
        <el-select v-model="form.campus" style="width: 100%" @change="handleCampusChange">
          <el-option label="创新港" value="创新港" />
          <el-option label="兴庆" value="兴庆" />
        </el-select>
      </el-form-item>

      <el-form-item label="教室" prop="classroom">
        <el-select v-model="form.classroom" style="width: 100%">
          <el-option v-for="c in filteredClassrooms" :key="c" :label="c" :value="c" />
        </el-select>
      </el-form-item>

      <el-form-item :label="leaderLabel" :prop="leaderProp">
        <el-select v-model="leaderValue" filterable style="width: 100%">
          <el-option v-for="teacher in chairOptions" :key="teacher.id" :label="`${teacher.name}（${teacher.title}）· #${teacher.id}`" :value="teacher.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="秘书" prop="secretary">
        <el-select v-model="secretaryValue" filterable style="width: 100%">
          <el-option v-for="teacher in secretaryOptions" :key="teacher.id" :label="`${teacher.name} · #${teacher.id}`" :value="teacher.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="普通专家/组员" prop="teachers">
        <el-select v-model="teacherIds" multiple filterable style="width: 100%">
          <el-option
            v-for="t in memberOptions"
            :key="t.id"
            :label="`${t.name}（${t.title}）`"
            :value="t.id"
          />
        </el-select>
        <div class="text-xs text-gray-500 mt-1">主席/组长单独选择并计入专家总人数；这里选择其余组员。</div>
      </el-form-item>

      <el-form-item label="学生列表" prop="students">
        <el-select v-model="studentIds" multiple filterable disabled style="width: 100%">
          <el-option
            v-for="s in students"
            :key="s.id"
            :label="`${s.name}（${s.studentType}，${s.mentorName}）`"
            :value="s.id"
          />
        </el-select>
        <div class="text-xs text-gray-500 mt-1">调整学生归属请使用排期页的“移动学生”，确保学生始终属于一个组。</div>
      </el-form-item>

      <el-form-item label="备注" prop="remark">
        <el-input v-model="form.remark" type="textarea" />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <el-button @click="visible = false">取消</el-button>
        <el-button v-if="!readonly" type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { ScheduleGroup, ScheduleTeacher, ScheduleStudent, DefenseType } from '../types/schedule'

const props = defineProps<{
  modelValue: boolean
  defenseType: DefenseType
  group: ScheduleGroup | null
  teachers: ScheduleTeacher[]
  students: ScheduleStudent[]
  classrooms: { campus: '创新港' | '兴庆'; name: string }[]
  saving?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', groupData: ScheduleGroup): void
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => { visible.value = v })
watch(visible, v => { emit('update:modelValue', v) })

const timeOptions = ['08:30-10:30', '10:30-12:30', '14:00-16:00', '16:00-18:00', '19:00-21:00']

const emptyGroup: ScheduleGroup = {
  id: 0,
  defenseType: '预答辩',
  groupName: '',
  campus: '创新港',
  classroom: '',
  date: '',
  timeRange: timeOptions[0],
  secretary: '',
  teachers: [],
  students: [],
  remark: ''
}

const form = reactive<ScheduleGroup>({ ...emptyGroup })
const formRef = ref<FormInstance>()

watch(
  () => props.group,
  g => {
    if (!g) return
    Object.assign(form, emptyGroup, JSON.parse(JSON.stringify(g)))
    form.chairId = g.chairId ?? props.teachers.find(teacher => teacher.name === (g.chairman || g.leader))?.id
    form.secretaryId = g.secretaryId ?? props.teachers.find(teacher => teacher.name === g.secretary)?.id
    form.teachers = form.teachers.filter(teacher => teacher.id !== form.chairId)
  },
  { immediate: true }
)

const chairOptions = computed(() => props.teachers.filter(teacher => {
  const qualified = props.defenseType === '正式答辩' ? teacher.title === '教授' : ['教授', '副教授'].includes(teacher.title)
  return qualified && (teacher.roles.includes(props.defenseType === '正式答辩' ? '主席' : '组长') || teacher.id === form.chairId)
}))
const secretaryOptions = computed(() => props.teachers.filter(teacher => teacher.roles.includes('秘书') && teacher.title !== '其他'))
const memberOptions = computed(() => props.teachers.filter(teacher => teacher.memberEligible !== false && teacher.id !== form.chairId && teacher.id !== form.secretaryId))

const filteredClassrooms = computed(() => {
  return props.classrooms.filter(c => c.campus === form.campus).map(c => c.name)
})

const handleCampusChange = () => {
  if (!filteredClassrooms.value.includes(form.classroom)) {
    form.classroom = ''
  }
}

const leaderLabel = computed(() => (props.defenseType === '正式答辩' ? '主席' : '组长'))
const leaderProp = computed(() => (props.defenseType === '正式答辩' ? 'chairman' : 'leader'))

const leaderValue = computed({
  get: () => form.chairId,
  set(id: number | undefined) {
    const teacher = props.teachers.find(teacher => teacher.id === id)
    form.chairId = id
    form.chairTitle = teacher?.title
    if (props.defenseType === '正式答辩') { form.chairman = teacher?.name; form.leader = undefined }
    else { form.leader = teacher?.name; form.chairman = undefined }
    form.teachers = form.teachers.filter(member => member.id !== id)
  }
})
const secretaryValue = computed({
  get: () => form.secretaryId,
  set(id: number | undefined) {
    form.secretaryId = id
    form.secretary = props.teachers.find(teacher => teacher.id === id)?.name || ''
  }
})

const teacherIds = computed<number[]>({
  get() {
    return form.teachers.map(t => t.id)
  },
  set(ids) {
    form.teachers = ids.map(id => props.teachers.find(t => t.id === id)).filter(Boolean) as ScheduleTeacher[]
  }
})

const studentIds = computed<number[]>({
  get() {
    return form.students.map(s => s.id)
  },
  set(ids) {
    form.students = ids.map(id => props.students.find(s => s.id === id)).filter(Boolean) as ScheduleStudent[]
  }
})

const rules = reactive<FormRules>({
  chairman: [{ required: true, message: '请选择主席', trigger: 'change' }],
  leader: [{ required: true, message: '请选择组长', trigger: 'change' }],
  groupName: [{ required: true, message: '请输入组名', trigger: 'blur' }],
  date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  timeRange: [{ required: true, message: '请选择时间段', trigger: 'change' }],
  campus: [{ required: true, message: '请选择校区', trigger: 'change' }],
  classroom: [{ required: true, message: '请选择教室', trigger: 'change' }],
  secretary: [{ required: true, message: '请选择秘书', trigger: 'change' }],
  teachers: [{ required: true, type: 'array', message: '请选择专家列表', trigger: 'change' }],
  students: [{ required: true, type: 'array', message: '请选择学生列表', trigger: 'change' }]
})

const drawerTitle = computed(() => {
  if (!props.group) return '调整排期'
  return `调整排期 - ${props.group.groupName}`
})

const handleSave = async () => {
  if (props.readonly) return
  if (!formRef.value) return
  await formRef.value.validate(valid => {
    if (!valid) return
    emit('save', JSON.parse(JSON.stringify(form)))
  })
}
</script>

