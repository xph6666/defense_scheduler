import type { ScheduleResult } from '../types/schedule'
import type { ScheduleConflict } from '../types/conflict'
import { getDefensePolicy } from './defense'
import { getMentorColor } from '../utils/color'
import { getScheduleExperts } from './scheduleExperts'

export const escapeHtml = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!))

/** All imported names and remarks are escaped; the printable document has no external resources. */
export function renderSchedulePrint(result: ScheduleResult, options: { includeRemarks?: boolean; conflicts?: ScheduleConflict[] } = {}): string {
  const conflicts = options.conflicts || result.conflicts || []
  const includeRemarks = options.includeRemarks ?? true
  const policy = getDefensePolicy(result.defenseType)
  const groups = result.groups.map(group => {
    const related = conflicts.filter(conflict => conflict.groupId === group.id || conflict.relatedGroupIds?.includes(group.id) || (!conflict.groupId && !conflict.relatedGroupIds?.length))
    const hasError = related.some(conflict => conflict.level === 'error')
    const experts = getScheduleExperts(group)
    const teacherList = experts.map(teacher => {
      const linked = group.students.find(student => student.mentorId ? student.mentorId === teacher.id : student.mentorName === teacher.name)
      const color = linked ? getMentorColor(linked.mentorName) : '#f4f6f8'
      return `<span class="person" style="background:${color}">${escapeHtml(teacher.name)}（${escapeHtml(teacher.title)}）</span>`
    }).join(' ')
    const students = group.students.map((student, index) => {
      const background = getMentorColor(student.mentorName)
      return `<tr${hasError ? ' class="conflict-row"' : ''}><td>${index + 1}</td><td>${escapeHtml(student.studentNo || '')}</td><td style="background:${background}">${escapeHtml(student.name)}</td><td>${escapeHtml(student.studentType)}</td><td style="background:${background}">${escapeHtml(student.mentorName)}</td><td>${escapeHtml(student.secretaryName || '')}</td>${includeRemarks ? `<td>${escapeHtml(student.remark || '')}</td>` : ''}</tr>`
    }).join('')
    const issues = related.length ? `<div class="issues"><strong>校验结果</strong><ul>${related.map(conflict => `<li class="${conflict.level === 'error' ? 'error' : ''}">${escapeHtml(conflict.reason)}${conflict.suggestion ? `；${escapeHtml(conflict.suggestion)}` : ''}</li>`).join('')}</ul></div>` : ''
    return `<section class="group${hasError ? ' has-errors' : ''}"><h2>${escapeHtml(group.groupName)}</h2><p class="location">${escapeHtml(group.date)} ${escapeHtml(group.timeRange)} · ${escapeHtml(group.campus)} · ${escapeHtml(group.classroom)}</p><p>${result.defenseType === '正式答辩' ? '主席' : '组长'}：${escapeHtml(group.chairman || group.leader || '')} &nbsp; 秘书：${escapeHtml(group.secretary)}</p><div class="experts">专家（含主席/组长，共 ${experts.length} 人）：${teacherList}</div><table><thead><tr><th>序号</th><th>学号</th><th>学生</th><th>类型/学科</th><th>导师</th><th>对应秘书</th>${includeRemarks ? '<th>备注</th>' : ''}</tr></thead><tbody>${students}</tbody></table>${includeRemarks && group.remark ? `<p class="remark">备注：${escapeHtml(group.remark)}</p>` : ''}${issues}</section>`
  }).join('')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(result.defenseType)}安排</title><style>
  *{box-sizing:border-box}body{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#182433;margin:24px auto;max-width:1100px;padding:0 24px;line-height:1.6}.toolbar{display:flex;align-items:center;gap:18px;padding:16px;background:#edf4fc;margin-bottom:24px}.toolbar button{border:0;border-radius:6px;background:#245f9f;color:white;padding:10px 18px;font-size:15px;cursor:pointer}h1{font-size:26px;margin-bottom:8px}h2{font-size:19px;background:${policy.color};color:${result.defenseType === '中期答辩' ? '#fff' : '#182433'};padding:8px 12px;margin-top:0}.meta,.location{color:#4c5d70}.group{margin:28px 0 36px;break-before:page}.group:first-of-type{break-before:auto}.person{display:inline-block;padding:2px 7px;border-radius:3px;margin:3px}.experts{margin-bottom:12px}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px}th,td{border:1px solid #bfccd8;padding:8px;overflow-wrap:anywhere}th{background:#eef3f8}.conflict-row{color:#b91c1c}.has-errors h2{border-left:5px solid #dc2626}.issues{font-size:13px;background:#fff3ee;border-left:3px solid #d35c37;padding:8px 12px;margin-top:14px}.issues ul{margin:4px 0}.error{color:#b91c1c}.remark{white-space:pre-wrap;font-size:13px}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:14mm}@media print{body{margin:0;padding:0;max-width:none;font-size:12px}.toolbar{display:none}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}h1{font-size:22px}.group{margin-bottom:0}.issues{break-inside:avoid}}
  </style></head><body><div class="toolbar"><button type="button" onclick="window.print()">打印或保存为 PDF</button><span>在打印窗口中选择“另存为 PDF”，可保留关系颜色与冲突标记。</span></div><h1>${escapeHtml(result.defenseType)}安排</h1><p class="meta">版本 ${escapeHtml(result.version || '—')} · ${result.status === 'published' ? '已发布' : '草稿'} · 生成于 ${escapeHtml(result.generatedAt)} · 共 ${result.groups.length} 组</p>${groups}</body></html>`
}
