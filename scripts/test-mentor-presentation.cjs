const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const root = path.resolve(__dirname, '..'), cache = new Map()
function load(relative) {
  const filename = path.resolve(root, relative)
  if (cache.has(filename)) return cache.get(filename)
  const module = { exports: {} }
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
  const localRequire = name => {
    if (!name.startsWith('.')) return require(name)
    const resolved = path.resolve(path.dirname(filename), name)
    return resolved.endsWith('.json') ? JSON.parse(fs.readFileSync(resolved, 'utf8')) : load(path.relative(root, resolved + '.ts'))
  }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, { filename })(localRequire, module, module.exports)
  cache.set(filename, module.exports)
  return module.exports
}
const { buildMentorColors, groupMentorColors, mentorColorSeparation } = load('src/domain/mentorColors.ts')
const { buildMentorShares } = load('src/domain/mentorShares.ts')
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'shared/mentor-color-fixtures.json'), 'utf8'))
const palette = JSON.parse(fs.readFileSync(path.join(root, 'shared/mentor-colors.json'), 'utf8')).distinctPalette
const group = (id, names, shares) => ({ id, groupName: `G${id}`, defenseType: '预答辩', campus: '创新港',
  teachers: names.map((name, i) => ({ id: i + 1, name, title: '副教授', roles: ['普通专家'] })),
  students: names.flatMap((name, i) => Array.from({ length: shares[i] }, (_, n) => ({ id: id * 100 + i * 10 + n, name: `学生${n}`, mentorName: name, studentType: '软件工程' }))) })
const groups = fixture.groups.map((names, i) => group(i + 1, names, i === 2 ? [2, 2, 2] : [3, 2, 1]))
const colors = buildMentorColors(groups)
assert.deepEqual(colors, buildMentorColors([...groups].reverse()))
assert.deepEqual(Object.fromEntries(Object.entries(colors).map(([name, s]) => [name, palette.findIndex(p => `#${p.light}` === s.backgroundColor)])), fixture.indexes)
for (const g of groups) {
  const local = groupMentorColors(g, colors), names = g.teachers.map(t => t.name)
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) assert(mentorColorSeparation(local[names[i]], local[names[j]]) >= 20)
}
assert.deepEqual(groupMentorColors(groups[0], colors)['刘帅'], groupMentorColors(groups[2], colors)['刘帅'])
const shares = buildMentorShares(groups, true)
assert.equal(shares[1].kind, 'explained')
assert.equal(shares[2].kind, 'explained')
assert(shares[2].reason.includes('王文杰'))
assert.equal(shares[3].kind, 'balanced')
assert.equal(buildMentorShares(groups, false)[1].kind, 'unbalanced')
const uneven = group(9, ['甲', '乙', '丙'], [4, 2, 0])
assert.equal(buildMentorShares([uneven], true)[9].kind, 'unbalanced')
const { renderSchedulePrint } = load('src/domain/printSchedule.ts')
const html = renderSchedulePrint({ defenseType: '预答辩', groups, conflicts: [] })
for (const g of groups) for (const color of Object.values(groupMentorColors(g, colors))) assert(html.includes(`background:${color.backgroundColor}`))
const luminance = hex => {
  const v = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4)
  return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]
}
for (const p of palette) assert((luminance(p.light) + .05) / (luminance(p.dark) + .05) >= 4.5)
console.log('Mentor presentation passed: group separation, teacher consistency, filter stability, shared vectors, PDF, readable contrast and explicit exceptions')
