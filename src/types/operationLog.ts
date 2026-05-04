export type OperationType =
  | '生成排期'
  | '刷新排期'
  | '人工调整'
  | '冲突检测'
  | '导出结果'
  | '保存规则配置'
  | '重置规则配置'
  | '重置演示数据'
  | '清空排期结果'
  | '导入数据'

export interface OperationLog {
  id: number
  type: OperationType
  module: string
  description: string
  operator: string
  result: '成功' | '失败'
  createdAt: string
}
