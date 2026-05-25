import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'
import MainLayout from '../layout/MainLayout.vue'
import Login from '../views/Login.vue'
import Dashboard from '../views/Dashboard.vue'
import TeacherList from '../views/teacher/TeacherList.vue'
import StudentList from '../views/student/StudentList.vue'
import ClassroomList from '../views/classroom/ClassroomList.vue'
import ScheduleResult from '../views/schedule/ScheduleResult.vue'
import RuleConfig from '../views/RuleConfig.vue'
import OperationLog from '../views/OperationLog.vue'
import DemoGuide from '../views/DemoGuide.vue'
import AcceptanceTest from '../views/AcceptanceTest.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: Login
    },
    {
      path: '/',
      component: MainLayout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: Dashboard,
          meta: { title: '首页' }
        },
        {
          path: 'teachers',
          name: 'TeacherList',
          component: TeacherList,
          meta: { title: '教师/专家管理' }
        },
        {
          path: 'students',
          name: 'StudentList',
          component: StudentList,
          meta: { title: '学生管理' }
        },
        {
          path: 'classrooms',
          name: 'ClassroomList',
          component: ClassroomList,
          meta: { title: '教室管理' }
        },
        {
          path: 'schedule-results',
          name: 'ScheduleResult',
          component: ScheduleResult,
          meta: { title: '排期结果' }
        },
        {
          path: 'rule-config',
          name: 'RuleConfig',
          component: RuleConfig,
          meta: { title: '规则配置中心' }
        },
        {
          path: 'operation-log',
          name: 'OperationLog',
          component: OperationLog,
          meta: { title: '操作日志' }
        },
        {
          path: 'demo-guide',
          name: 'DemoGuide',
          component: DemoGuide,
          meta: { title: '演示指南' }
        },
        {
          path: 'acceptance-test',
          name: 'AcceptanceTest',
          component: AcceptanceTest,
          meta: { title: '验收测试' }
        }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  if (to.path !== '/login' && !userStore.isLoggedIn) {
    return { path: '/login' }
  }
  if (to.path === '/login' && userStore.isLoggedIn) {
    return { path: '/dashboard' }
  }
})

export default router
