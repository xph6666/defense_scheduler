export const STORAGE_KEYS = {
  teachers: 'demo_teachers',
  students: 'demo_students',
  classrooms: 'demo_classrooms',

  scheduleResult: (defenseType: string) => `schedule_result_${defenseType}`,
  scheduleConflicts: (defenseType: string) => `schedule_conflicts_${defenseType}`,

  lastExportTime: 'last_export_time',
  acceptanceChecklist: 'p0_acceptance_checklist'
}
