import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const MainLayout = () => import('../layout/MainLayout.vue')
const Login = () => import('../views/Login.vue')
const Dashboard = () => import('../views/Dashboard.vue')
const TeacherList = () => import('../views/teacher/TeacherList.vue')
const StudentList = () => import('../views/student/StudentList.vue')
const ClassroomList = () => import('../views/classroom/ClassroomList.vue')
const ScheduleResult = () => import('../views/schedule/ScheduleResult.vue')
const RuleConfig = () => import('../views/RuleConfig.vue')
const OperationLog = () => import('../views/OperationLog.vue')
const DemoGuide = () => import('../views/DemoGuide.vue')
const AcceptanceTest = () => import('../views/AcceptanceTest.vue')

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
