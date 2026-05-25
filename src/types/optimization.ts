export interface SoftConstraintScore {
  key: string
  label: string
  score: number
  maxScore: number
  description: string
}

export interface OptimizationSuggestion {
  id: number
  level: 'info' | 'warning'
  title: string
  description: string
  relatedGroupIds?: number[]
}

export interface OptimizationSummary {
  defenseType: '预答辩' | '正式答辩' | '中期答辩'
  totalScore: number
  maxScore: number
  scores: SoftConstraintScore[]
  suggestions: OptimizationSuggestion[]
  generatedAt: string
}
