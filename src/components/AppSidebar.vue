<template>
  <div class="sidebar-inner">
    <RouterLink class="brand" to="/dashboard" aria-label="答辩安排助手工作台">
      <span class="brand-mark">答</span>
      <span><strong>答辩安排助手</strong><small>DEFENSE PLANNER</small></span>
    </RouterLink>

    <el-menu
      :key="selectedDefenseIndex"
      :default-active="activeMenu"
      :default-openeds="openMenus"
      class="sidebar-menu"
      @select="handleSelect"
    >
      <div class="nav-section">总览</div>
      <el-menu-item index="workbench">
        <el-icon><DataBoard /></el-icon>
        <span>工作台</span>
      </el-menu-item>

      <div class="nav-section">答辩安排</div>
      <template v-for="item in defenseMenus" :key="item.type">
        <el-sub-menu v-if="canManage" :index="item.index">
          <template #title>
            <el-icon><Calendar /></el-icon>
            <span>{{ item.type }}</span>
          </template>
          <el-menu-item :index="`${item.index}:overview`">概览</el-menu-item>
          <el-menu-item :index="`${item.index}:rules`">安排要求</el-menu-item>
          <el-menu-item :index="`${item.index}:schedule`">排期方案</el-menu-item>
        </el-sub-menu>
        <el-menu-item v-else :index="`${item.index}:schedule`">
          <el-icon><Calendar /></el-icon>
          <span>{{ item.type }}</span>
        </el-menu-item>
      </template>

      <template v-if="canManage">
        <div class="nav-section">公共资料</div>
        <el-menu-item index="shared:students">
          <el-icon><User /></el-icon>
          <span>学生管理</span>
        </el-menu-item>
        <el-menu-item index="shared:teachers">
          <el-icon><Avatar /></el-icon>
          <span>教师 / 专家管理</span>
        </el-menu-item>
        <el-menu-item index="shared:classrooms">
          <el-icon><OfficeBuilding /></el-icon>
          <span>教室管理</span>
        </el-menu-item>

        <div class="nav-section">系统</div>
        <el-menu-item index="system:logs">
          <el-icon><Document /></el-icon>
          <span>操作日志</span>
        </el-menu-item>
      </template>
    </el-menu>

    <div class="sidebar-footer">
      <span class="sidebar-footer-dot" />
      <span>{{ canManage ? '管理员工作区' : '只读查看' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Avatar, Calendar, DataBoard, Document, OfficeBuilding, User } from '@element-plus/icons-vue'
import { defenseLink, defenseTypes, isDefenseType, workflowDefenseType } from '../utils/useDefenseType'
import type { DefenseType } from '../types/schedule'
import { useAdminGuard } from '../utils/adminGuard'

const route = useRoute()
const router = useRouter()
const { canManage } = useAdminGuard()

const defenseMenus = defenseTypes.map((type, index) => ({
  type,
  index: `defense:${index}`
}))

const selectedType = computed<DefenseType>(() =>
  isDefenseType(route.query.type) ? route.query.type : workflowDefenseType.value
)

const selectedDefenseIndex = computed(() =>
  defenseMenus.find(item => item.type === selectedType.value)?.index ?? defenseMenus[0].index
)

const openMenus = computed(() => canManage.value ? [selectedDefenseIndex.value] : [])

const activeMenu = computed(() => {
  if (route.path === '/dashboard' && !isDefenseType(route.query.type)) return 'workbench'
  if (route.path === '/dashboard') return `${selectedDefenseIndex.value}:overview`
  if (route.path === '/rule-config') return `${selectedDefenseIndex.value}:rules`
  if (route.path === '/schedule-results') return `${selectedDefenseIndex.value}:schedule`
  if (route.path === '/students') return 'shared:students'
  if (route.path === '/teachers') return 'shared:teachers'
  if (route.path === '/classrooms') return 'shared:classrooms'
  if (route.path === '/operation-log') return 'system:logs'
  return ''
})

const handleSelect = (index: string) => {
  if (index === 'workbench') {
    void router.push('/dashboard')
    return
  }

  const defenseMenu = defenseMenus.find(item => index.startsWith(`${item.index}:`))
  if (defenseMenu) {
    const section = index.slice(`${defenseMenu.index}:`.length)
    const path = section === 'overview' ? '/dashboard' : section === 'rules' ? '/rule-config' : '/schedule-results'
    void router.push(defenseLink(path, defenseMenu.type))
    return
  }

  const sharedRoutes: Record<string, string> = {
    'shared:students': '/students',
    'shared:teachers': '/teachers',
    'shared:classrooms': '/classrooms',
    'system:logs': '/operation-log'
  }
  const path = sharedRoutes[index]
  if (path) void router.push(defenseLink(path, selectedType.value))
}
</script>
