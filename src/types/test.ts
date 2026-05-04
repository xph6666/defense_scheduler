export type TestStatus = 'pending' | 'passed' | 'failed'

export interface TestChecklistItem {
  id: number
  module: string
  title: string
  description: string
  expectedResult: string
  status: TestStatus
}
