import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

export const ADMIN_REQUIRED_MESSAGE = '需要管理员权限'

export function useAdminGuard() {
  const userStore = useUserStore()
  const canManage = computed(() => userStore.isAdmin)

  const requireAdmin = () => {
    if (canManage.value) return true
    ElMessage.warning(ADMIN_REQUIRED_MESSAGE)
    return false
  }

  return {
    canManage,
    requireAdmin
  }
}
