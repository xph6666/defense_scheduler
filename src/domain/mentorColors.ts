import colorSource from '../../shared/mentor-colors.json'
import type { CSSProperties } from 'vue'
import type { ScheduleGroup } from '../types/schedule'
import { getScheduleExperts } from './scheduleExperts'

export interface MentorColor extends CSSProperties { backgroundColor: string; borderColor: string; color: string }
export type MentorColorMap = Record<string, MentorColor>
const palette = colorSource.distinctPalette

function lab(hex: string): number[] {
  const rgb = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
  const [r, g, b] = rgb
  const f = (v: number) => v > .008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116
  const x = f((.4124564 * r + .3575761 * g + .1804375 * b) / .95047)
  const y = f(.2126729 * r + .7151522 * g + .072175 * b)
  const z = f((.0193339 * r + .119192 * g + .9503041 * b) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}
const labs = palette.map(p => lab(p.light))
const distance = (a: number, b: number) => Math.sqrt(labs[a].reduce((sum, v, i) => sum + (v - labs[b][i]) ** 2, 0))
export function mentorColorSeparation(a: MentorColor, b: MentorColor) {
  const x = lab(a.backgroundColor.replace('#', '')), y = lab(b.backgroundColor.replace('#', ''))
  return Math.sqrt(x.reduce((sum, v, i) => sum + (v - y[i]) ** 2, 0))
}
const style = (i: number): MentorColor => ({ backgroundColor: `#${palette[i].light}`, borderColor: `#${palette[i].dark}`, color: `#${palette[i].dark}` })
export const neutralMentorColor: MentorColor = { backgroundColor: '#edf0f3', borderColor: '#64748b', color: '#334155' }

/** Whole-version DSATUR coloring; co-occurring teachers are adjacent. */
export function buildMentorColors(groups: ScheduleGroup[]): MentorColorMap {
  const graph = new Map<string, Set<string>>()
  for (const group of groups) {
    const names = [...new Set([...getScheduleExperts(group).map(t => t.name), ...group.students.map(s => s.mentorName)]
      .map(name => (name || '').trim()).filter(Boolean))].sort()
    for (const name of names) {
      if (!graph.has(name)) graph.set(name, new Set())
      for (const other of names) if (other !== name) graph.get(name)!.add(other)
    }
  }
  const assigned = new Map<string, number>()
  while (assigned.size < graph.size) {
    const pending = [...graph.keys()].filter(name => !assigned.has(name)).sort()
    pending.sort((a, b) => {
      const saturation = (name: string) => new Set([...graph.get(name)!].filter(n => assigned.has(n)).map(n => assigned.get(n))).size
      return saturation(b) - saturation(a) || graph.get(b)!.size - graph.get(a)!.size
    })
    const name = pending[0]
    const neighbors = [...graph.get(name)!].filter(n => assigned.has(n)).map(n => assigned.get(n)!)
    const candidates = palette.map((_, i) => i).filter(i => !neighbors.includes(i))
    const available = candidates.length ? candidates : palette.map((_, i) => i)
    available.sort((a, b) => {
      const gap = (i: number) => neighbors.length ? Math.min(...neighbors.map(j => distance(i, j))) : 0
      return gap(b) - gap(a) || a - b
    })
    assigned.set(name, available[0])
  }
  return Object.fromEntries([...assigned].map(([name, i]) => [name, style(i)]))
}

/** Prefer global consistency; repair local collisions only if unavoidable. */
export function groupMentorColors(group: ScheduleGroup, global: MentorColorMap): MentorColorMap {
  const names = [...new Set([...getScheduleExperts(group).map(t => t.name), ...group.students.map(s => s.mentorName)])]
    .map(name => (name || '').trim()).filter(Boolean).sort()
  const result: MentorColorMap = {}
  const used: number[] = []
  for (const name of names) {
    let index = palette.findIndex(p => `#${p.light}` === global[name]?.backgroundColor)
    if (index < 0 || used.some(i => distance(i, index) < 20)) {
      const candidates = palette.map((_, i) => i).filter(i => !used.includes(i))
      index = candidates.sort((a, b) => Math.min(...used.map(j => distance(b, j)), 1e6) - Math.min(...used.map(j => distance(a, j)), 1e6) || a - b)[0] ?? 0
    }
    used.push(index)
    result[name] = style(index)
  }
  return result
}
