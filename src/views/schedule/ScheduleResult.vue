<template>
  <div class="space-y-4">
    <WorkflowSteps v-if="!guided" :current="result?.status === 'published' ? 4 : 3" />

    <!-- 流程引导状态条 -->
    <WorkflowStatusBar
      v-if="!guided"
      :has-result="!!result?.groups.length"
      :status="result?.status === 'published' ? 'published' : 'draft'"
      :error-count="conflicts.filter(c => c.level === 'error').length"
      :is-historical="result?.isCurrent === false"
    />

    <div class="page-header bg-white p-6 rounded-lg shadow-sm">
      <div v-if="!guided" class="flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-bold text-gray-800">答辩安排与导出</div>
        </div>
        <LegendTag />
      </div>

      <div :class="{ 'mt-5': !guided }">
        <ScheduleToolbar
          v-model:defenseType="defenseType"
          v-model:viewMode="viewMode"
          :loading="loading || publishing || moving || adjustSaving"
          :has-result="!!result?.groups.length"
          :can-manage="canManage"
          :guided="guided"
          @generate="prepareGeneration()"
          @generate-linked="prepareLinkedGeneration()"
          @refresh="handleRefresh"
          @export="handleExportClick"
        />
      </div>
    </div>

    <div v-if="!loading && !errorMsg" class="workflow-note compact-status" aria-live="polite">
      <strong>{{ nextStepTitle }}</strong>
      <div class="compact-links">
        <el-button v-if="guided" link type="primary" @click="emit('requirements')">返回第 3 步修改要求 →</el-button>
        <RouterLink v-else :to="workflowLink('/rule-config')" class="text-link">查看或修改安排要求 →</RouterLink>
        <el-button v-if="guided" link type="primary" @click="emit('materials')">返回第 2 步检查资料 →</el-button>
        <RouterLink v-else :to="workflowLink('/dashboard')" class="text-link">返回工作台检查资料 →</RouterLink>
      </div>
    </div>

    <div v-if="versions.length" ref="publishBar" class="version-bar bg-white p-4 rounded-lg shadow-sm flex flex-wrap items-center gap-3">
      <span class="text-sm text-gray-600">排期版本</span>
      <el-select v-model="selectedVersion" placeholder="当前版本（下拉可查看历史）" clearable class="w-64" @change="fetchResult">
        <el-option
          v-for="v in versions" :key="v.id" :value="v.id"
          :label="`v${v.version} · ${v.status === 'published' ? '已发布' : '草稿'}${v.is_current ? ' · 当前' : ''}`"
        />
      </el-select>
      <el-tag :type="result?.status === 'published' ? 'success' : 'warning'">
        {{ result?.status === 'published' ? '已发布 · 内容已锁定' : '草稿 · 请核对后发布' }}
      </el-tag>
      <el-button v-if="canEdit && result?.versionId && (!guided || guidedStage === 'publish')" :loading="publishing" :disabled="loading" type="primary" @click="handlePublish">校验并发布</el-button>
      <el-button v-if="canEdit && result?.versionId" :disabled="loading" @click="editingRevision = result?.revision; moveVisible = true">移动学生</el-button>
      <el-button :disabled="loading" link type="primary" @click="openOperationLogDrawer">
        <el-icon><Document /></el-icon>
        <span>查看操作记录</span>
      </el-button>
    </div>

    <el-alert
      v-if="errorMsg"
      type="error"
      :closable="false"
      show-icon
      :title="errorMsg"
    />

    <div class="stats-panel bg-white p-6 rounded-lg shadow-sm">
      <div class="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm text-gray-700">
        <div><span class="text-gray-500">当前答辩类型：</span>{{ defenseType }}</div>
        <div><span class="text-gray-500">生成时间：</span>{{ meta.generatedAt || '-' }}</div>
        <div><span class="text-gray-500">总组数：</span>{{ meta.groupCount }}</div>
        <div><span class="text-gray-500">总学生数：</span>{{ meta.studentCount }}</div>
        <div><span class="text-gray-500">总专家数：</span>{{ meta.teacherCount }}</div>
        <div><span class="text-gray-500">错误：</span>{{ exportStats.errorCount }}</div>
        <div><span class="text-gray-500">提醒：</span>{{ meta.conflictCount - exportStats.errorCount }}</div>
        <div v-if="result?.rules?.expert_count">本次专家：{{ result.rules.expert_count }} 人（含组长）</div>
        <div v-if="result?.rules?.start_date">排班范围：{{ result.rules.start_date }} 至 {{ result.rules.end_date }}</div>
        <div v-if="result?.allocationStatus">分配状态：{{ result.allocationStatus === 'partial' ? '部分安排，待处理剩余学生' : '全部学生已安排' }}</div>
        <div v-if="showRandomSeed" class="random-seed-row">
          <span class="text-gray-400 text-xs">种子：{{ result?.randomSeed }}</span>
        </div>
      </div>
      <section v-if="!loading && result?.groups.length" class="student-count-summary" aria-label="学生人数分布">
        <div class="student-count-heading">
          <strong>学生人数分布</strong>
          <span v-if="studentCountSummary.target !== null">本版本目标 {{ studentCountSummary.target }} 人/组</span>
          <span v-else>该版本未记录目标人数</span>
          <span v-if="studentCountSummary.preferredGroupCount !== null" class="student-count-match">{{ studentCountSummary.preferredMinimum === studentCountSummary.target ? '达到目标' : `${studentCountSummary.preferredMinimum}～${studentCountSummary.preferredMaximum} 人均衡区间` }} {{ studentCountSummary.preferredGroupCount }} / {{ studentCountSummary.groupCount }} 组</span>
        </div>
        <div class="student-count-buckets">
          <span v-for="bucket in studentCountSummary.buckets" :key="bucket.size" class="student-count-bucket" :class="{ 'is-target': bucket.isTarget }">
            {{ bucket.size }} 人组 <strong>× {{ bucket.count }}</strong><span v-if="bucket.isTarget"> · 目标</span>
          </span>
        </div>
        <p class="section-tip mt-2">统计本版本全部分组，不随日期、校区筛选改变。</p>
      </section>
    </div>

    <div v-if="result?.groups.length" class="schedule-filters">
      <el-select v-model="dateFilter" aria-label="按日期筛选" placeholder="全部日期" clearable style="width: 160px"><el-option v-for="date in availableDates" :key="date" :value="date" :label="date || '日期待安排'" /></el-select>
      <el-select v-model="campusFilter" aria-label="按校区筛选" placeholder="全部校区" clearable style="width: 130px"><el-option label="创新港" value="创新港" /><el-option label="兴庆" value="兴庆" /></el-select>
      <el-checkbox v-model="onlyProblems">只看有问题的分组</el-checkbox>
      <span>显示 {{ filteredGroups.length }} / {{ result.groups.length }} 组</span>
      <el-button v-if="dateFilter || campusFilter || onlyProblems" link type="primary" @click="resetFilters">清除筛选</el-button>
      <p v-if="onlyProblems" class="section-tip w-full">全局问题（如未分组学生）仍显示在冲突检测中，不一定属于某个分组。</p>
    </div>

    <el-card v-if="result?.unassignedStudents?.length" shadow="never">
      <template #header><strong>未安排学生（{{ result.unassignedStudents.length }} 人，已尝试局部补排）</strong></template>
      <el-table :data="result.unassignedStudents" row-key="id"><el-table-column prop="name" label="学生" width="140" /><el-table-column prop="reason" label="未安排原因" /></el-table>
    </el-card>
    <details v-if="result?.teacherWorkloads?.length" class="bg-white p-4 rounded-lg shadow-sm">
      <summary>教师工作量与任务分布</summary>
      <el-table :data="result.teacherWorkloads" row-key="id"><el-table-column prop="name" label="教师" /><el-table-column prop="supervisedStudents" label="指导学生数" /><el-table-column prop="studentCount" label="参与学生数" /><el-table-column prop="groupCount" label="参与组数" /><el-table-column label="到场时段" min-width="240"><template #default="{ row }">{{ row.sessions.join('；') || '未安排' }}</template></el-table-column></el-table>
    </details>
    <div v-if="loading" class="bg-white p-6 rounded-lg shadow-sm">
      <p v-if="loadingMessage" class="mb-4 text-sm text-gray-600" role="status">{{ loadingMessage }}</p>
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else-if="!result?.groups.length" class="bg-white p-10 rounded-lg shadow-sm">
      <el-empty :description="emptyResultDescription" />
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2 space-y-4">
        <el-empty v-if="!filteredGroups.length" description="当前筛选下没有分组，可清除筛选查看全部安排。"><el-button @click="resetFilters">查看全部分组</el-button></el-empty>
        <ScheduleAgenda
          v-else-if="viewMode === 'agenda'"
          :groups="filteredGroups"
          :conflicts="conflicts"
          :can-manage="canEdit"
          :highlighted-group-ids="highlightedGroupIds"
          @adjust="openAdjust"
          @problem="openGroupProblem"
        />
        <div v-else-if="viewMode === 'card'" class="space-y-4">
          <el-row :gutter="16" class="schedule-card-grid">
            <el-col
              v-for="g in filteredGroups"
              :key="g.id"
              :xs="24" :md="12"
            >
              <ScheduleGroupCard
                :group="g"
                :status="groupStatusMap[g.id] || 'normal'"
                :conflict-count="groupConflictCountMap[g.id] || 0"
                :can-manage="canEdit"
                :highlighted="highlightedGroupIds.includes(g.id)"
                @adjust="openAdjust"
              />
            </el-col>
          </el-row>
        </div>

        <div v-else class="bg-white p-6 rounded-lg shadow-sm">
          <ScheduleTable
            :groups="filteredGroups"
            :group-status="groupStatusMap"
            :can-manage="canEdit"
            :highlighted-group-ids="highlightedGroupIds"
            @adjust="openAdjust"
          />
        </div>
      </div>

      <div class="lg:col-span-1 space-y-4 conflict-sidebar">
        <ConflictPanel
          :conflicts="conflicts"
          :loading="conflictLoading"
          @check="handleCheckConflicts"
          @view-detail="openConflictDetail"
          @locate="handleLocateConflict"
        />
        <details class="secondary-details"><summary>查看分组质量评分</summary><SoftConstraintPanel :summary="optimizationSummary" :conflicts="conflicts" /></details>
      </div>
    </div>
  </div>

  <el-dialog v-model="generationVisible" title="生成前，确认这次安排" width="min(560px, 94vw)" :close-on-click-modal="false">
    <template v-if="generationConfig">
      <p class="mb-4">{{ defenseType === '正式答辩' ? '沿用当前预答辩的固定组号、学生、组长、专家和秘书；按本阶段要求补充本院专家，重新核对共同可用时间。' : '确认后生成新草稿，历史版本保留。每组仅允许 5～7 人，以 6 人为主，尽量减少 5 或 7 人组。平衡教师次数与参与学生数，再集中同日上午下午。' }}</p>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="答辩类型">{{ defenseType }}</el-descriptions-item>
        <el-descriptions-item label="答辩日期">{{ generationConfig.startDate || '未设置' }} 至 {{ generationConfig.endDate || '未设置' }}</el-descriptions-item>
        <el-descriptions-item label="每组人数">学生 {{ generationConfig.studentCount.target }} 人 / 专家{{ defenseType === '预答辩' ? '至少' : '目标' }} {{ defenseType === '预答辩' ? generationConfig.expertCount.min : generationConfig.expertCount.target }} 人<span v-if="defenseType !== '预答辩'">（至少 {{ generationConfig.expertCount.min }} 人）</span> / 秘书 1 人</el-descriptions-item>
        <el-descriptions-item label="参与学生">{{ generationStudentCount }} 人</el-descriptions-item>
        <el-descriptions-item label="导师安排">{{ defenseType !== '正式答辩' ? '导师与学生同组' : generationConfig.mentorAvoidance ? '导师回避自己的学生' : '不要求导师回避' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="!generationConfig.enabled" title="此答辩类型尚未启用，请先修改安排要求。" type="warning" :closable="false" class="mt-4" />
      <el-alert v-else-if="!generationStudentCount" title="还没有参加本次答辩的学生，请先在学生名单中补充参与环节。" type="warning" :closable="false" class="mt-4" />

      <!-- 预检结果区域 -->
      <div v-else class="preflight-section mt-4">
        <!-- 未预检 -->
        <div v-if="preflightStatus === 'idle'" class="preflight-idle text-sm text-gray-500 flex items-center gap-2">
          <el-icon><InfoFilled /></el-icon>
          <span>点击生成后将自动检查资料和安排要求</span>
        </div>
        <!-- 预检中 -->
        <div v-else-if="preflightStatus === 'loading'" class="preflight-loading text-sm text-gray-600 flex items-center gap-2">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在检查资料和安排要求...</span>
        </div>
        <!-- 预检通过 -->
        <div v-else-if="preflightStatus === 'passed'" class="preflight-passed">
          <el-alert :type="preflightResult?.warnings.length ? 'warning' : 'success'" :closable="false" show-icon>
            <template #title>
              <span>{{ preflightResult?.warnings.length ? '存在预检提醒，可继续生成草稿' : '检查通过，可以生成' }}</span>
              <span class="text-xs text-green-600 ml-2">（学生 {{ preflightResult?.stats.studentCount }} 人 · 教师 {{ preflightResult?.stats.teacherCount }} 人 · 教室 {{ preflightResult?.stats.roomCount }} 间）</span>
            </template>
          </el-alert>
        </div>
        <!-- 预检不通过 -->
        <div v-else-if="preflightStatus === 'failed'" class="preflight-failed space-y-3">
          <div class="flex items-center gap-2 text-red-600 font-medium">
            <el-icon><CircleCloseFilled /></el-icon>
            <span>检测到 {{ preflightResult?.errors.length }} 项问题，暂不能生成</span>
          </div>
          <div class="preflight-error-list space-y-2 max-h-60 overflow-y-auto pr-1">
            <div
              v-for="(issue, idx) in preflightResult?.errors"
              :key="`err-${idx}`"
              class="preflight-error-item p-3 bg-red-50 border border-red-200 rounded"
            >
              <div class="flex items-start gap-2">
                <el-icon class="text-red-500 mt-0.5 flex-shrink-0"><Warning /></el-icon>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-red-800">{{ issue.description }}</div>
                  <div v-if="issue.studentNames?.length" class="text-xs text-red-600 mt-1">
                    涉及学生：{{ issue.studentNames.join('、') }}{{ issue.count > 5 ? ` 等${issue.count}人` : '' }}
                  </div>
                  <div v-if="issue.teacherNames?.length" class="text-xs text-red-600 mt-1">
                    涉及导师：{{ issue.teacherNames.join('、') }}
                  </div>
                  <div class="flex items-center justify-between mt-2">
                    <span class="text-xs text-red-500">建议：{{ issue.suggestion }}</span>
                    <el-button
                      size="small"
                      type="primary"
                      link
                      @click="goToFixData(issue.type)"
                    >
                      {{ ['external_mentor_capacity', 'inherited_group_size'].includes(issue.type) ? '修改要求' : '去补齐' }}
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- 警告提示 -->
        </div>
        <div v-if="preflightResult?.warnings.length" class="mt-3 space-y-2" role="status">
          <strong class="text-sm text-orange-700">预检提醒（{{ preflightResult.warnings.length }} 项）</strong>
          <div v-for="(issue, idx) in preflightResult.warnings" :key="idx" class="p-3 bg-orange-50 border border-orange-200 rounded text-sm">
            <div>{{ issue.description }}</div><div class="mt-1 text-gray-600">{{ issue.suggestion }}</div>
          </div>
          <p class="section-tip">可继续生成草稿核对人员；预检通过不代表全部安排可行，最终以生成后的冲突校验为准。</p>
        </div>
      </div>
    </template>
    <template #footer>
      <el-button @click="generationVisible = false">暂不生成</el-button>
      <el-button @click="generationVisible = false; guided ? emit('requirements') : router.push(workflowLink('/rule-config'))">修改要求</el-button>
      <el-button
        type="primary"
        :loading="preflightLoading"
        :disabled="!generationConfig?.enabled || !generationStudentCount || preflightStatus === 'failed'"
        @click="handleGenerate"
      >
        {{ preflightStatus === 'passed' && preflightResult?.warnings.length ? '继续生成草稿' : '确认生成草稿' }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="linkedVisible" title="联合生成预答辩与正式答辩" width="min(680px, 94vw)" :close-on-click-modal="false">
    <p class="mb-4">预答辩每组仅允许 5～7 人，以 6 人为主，余数用少量 5 或 7 人组消化；3 位专家含组长。平衡教师出场次数和学生数，尽量安排同日上午下午。先尝试每组最多 1 位外院专家，仅在无法满足人数底线时允许必要的第 2 位外院导师。正式阶段沿用固定组号、学生和原教师，补充本院专家至 5 人，并核对共同可用时间。教室可后续补充。</p>
    <el-form-item label="预答辩专家人数"><el-select v-model="linkedExpertCount" :disabled="linkedPreflightLoading" @change="updateLinkedExpertCount"><el-option :value="3" label="3 人（含组长）" /><el-option :value="5" label="5 人（含组长，增加 2 名本院专家）" /></el-select></el-form-item>
    <el-descriptions v-if="linkedConfigs" :column="1" border>
      <el-descriptions-item v-for="config in linkedConfigs" :key="config.defenseType" :label="config.defenseType">{{ config.startDate }} 至 {{ config.endDate }}；学生目标 {{ config.studentCount.target }} 人/组；专家 {{ config.expertCount.target }} 人（含组长）</el-descriptions-item>
    </el-descriptions>
    <el-alert v-if="linkedError" class="mt-4" :title="linkedError" type="warning" :closable="false" show-icon />
    <div v-if="linkedPreflightStatus === 'failed'" class="mt-4 space-y-3" role="alert">
      <div class="font-medium text-red-700">资料或安排要求检查未通过，暂不能联合生成</div>
      <template v-for="stage in [{ label: '预答辩', result: linkedPreflightPre }, { label: '正式答辩', result: linkedPreflightFormal }]" :key="stage.label">
        <div v-if="stage.result?.errors.length" class="space-y-2">
          <div class="font-medium">{{ stage.label }}</div>
          <div v-for="(issue, idx) in stage.result.errors" :key="idx" class="p-3 bg-red-50 border border-red-200 rounded text-sm">
            <div class="text-red-800">{{ issue.description }}</div>
            <div class="mt-2 text-red-700">建议：{{ issue.suggestion }}</div>
          </div>
        </div>
      </template>
    </div>
    <div v-if="linkedPreflightStatus !== 'idle' && linkedPreflightStatus !== 'loading'" class="mt-4 space-y-2" role="status">
      <template v-for="stage in [{ label: '预答辩', result: linkedPreflightPre }, { label: '正式答辩', result: linkedPreflightFormal }]" :key="stage.label">
        <div v-for="(issue, idx) in stage.result?.warnings || []" :key="`${stage.label}-${idx}`" class="p-3 bg-orange-50 border border-orange-200 rounded text-sm">
          <strong>{{ stage.label }} · 预检提醒</strong>
          <div class="mt-1">{{ issue.description }}</div><div class="mt-1 text-gray-600">{{ issue.suggestion }}</div>
        </div>
      </template>
      <p v-if="linkedHasWarnings" class="section-tip">可继续生成草稿；预检通过不代表全部安排可行，最终以生成后的冲突校验为准。</p>
    </div>
    <template #footer><el-button @click="linkedVisible = false">取消</el-button><el-button @click="linkedVisible = false; guided ? emit('requirements') : router.push(workflowLink('/rule-config'))">修改两阶段要求</el-button><el-button type="primary" :loading="linkedPreflightLoading" :disabled="!linkedConfigs || !!linkedError || linkedPreflightStatus === 'failed'" @click="handleGenerateLinked">{{ linkedPreflightStatus === 'passed' && linkedHasWarnings ? '继续联合生成' : '确认联合生成' }}</el-button></template>
  </el-dialog>

  <el-dialog v-model="moveVisible" title="移动学生" width="520px" :close-on-click-modal="false">
    <div class="space-y-4">
      <el-alert
        title="学生移动后将自动重新校验冲突"
        type="info"
        :closable="false"
        show-icon
        size="small"
      >
        <template #default>
          <div class="text-xs">
            <p>• 导师跟随：预答辩/中期答辩时，导师随学生一起移动到目标组</p>
            <p>• 秘书关系：可选择保留原秘书或改绑到目标组秘书</p>
            <p>• 冲突检测：移动完成后自动刷新冲突状态</p>
          </div>
        </template>
      </el-alert>

      <div class="move-select-row">
        <label class="move-label">选择学生</label>
        <el-select v-model="moveStudentId" filterable placeholder="请选择要移动的学生" class="w-full" @change="handleMoveStudentChange">
          <el-option v-for="s in moveChoices" :key="s.id" :value="s.id" :label="s.label" />
        </el-select>
      </div>

      <div v-if="selectedMoveStudent" class="move-student-info bg-gray-50 p-3 rounded-lg border border-gray-200">
        <div class="text-sm text-gray-600 mb-1">当前组信息</div>
        <div class="flex flex-wrap gap-4 text-sm">
          <div><span class="text-gray-500">所在组：</span><span class="font-medium">{{ selectedMoveStudent.groupName }}</span></div>
          <div><span class="text-gray-500">导师：</span><span>{{ selectedMoveStudent.mentorName || '未设置' }}</span></div>
          <div><span class="text-gray-500">秘书：</span><span>{{ selectedMoveStudent.secretaryName || '未绑定' }}</span></div>
        </div>
      </div>

      <div class="move-select-row">
        <label class="move-label">目标组</label>
        <el-select v-model="moveTargetId" placeholder="请选择目标组" class="w-full">
          <el-option
            v-for="g in result?.groups || []"
            :key="g.id"
            :value="g.id"
            :label="g.groupName"
            :disabled="g.id === moveChoices.find(choice => choice.id === moveStudentId)?.groupId"
          />
        </el-select>
      </div>

      <div class="move-select-row">
        <label class="move-label">秘书关系</label>
        <div class="w-full space-y-2">
          <el-checkbox v-model="preserveSecretary" class="w-full">
            保留该学生的秘书关系（跟随学生一起移动）
          </el-checkbox>

          <div v-if="!preserveSecretary" class="secretary-rebind-panel pl-6 py-2 border-l-2 border-orange-300 bg-orange-50 rounded-r">
            <div class="text-sm text-orange-700 font-medium mb-2">
              <el-icon class="mr-1"><Warning /></el-icon>
              改绑秘书确认
            </div>
            <p class="text-xs text-orange-600 mb-2">
              取消保留后，该学生的秘书将被重新绑定。请明确选择新的秘书：
            </p>
            <el-select v-model="replacementSecretaryId" filterable placeholder="选择改绑后的秘书" class="w-full">
              <el-option
                v-for="teacher in teacherOptions.filter(teacher => teacher.roles.includes('秘书'))"
                :key="teacher.id"
                :value="teacher.id"
                :label="`${teacher.name}（${teacher.college || ''}）`"
              />
            </el-select>
            <p class="text-xs text-orange-600 mt-2">
              移动后系统将重新检测「秘书与学生同组」等冲突规则。
            </p>
          </div>
        </div>
      </div>

      <div class="move-select-row">
        <label class="move-label">导师跟随</label>
        <div class="w-full">
          <el-tag v-if="defenseType === '正式答辩'" size="small" type="info">
            正式答辩不移动导师（导师回避）
          </el-tag>
          <el-tag v-else size="small" type="success">
            导师将随学生一起移动到目标组
          </el-tag>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="moveVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="moving"
        :disabled="!moveStudentId || !moveTargetId || (!preserveSecretary && !replacementSecretaryId)"
        @click="handleMoveStudent"
      >
        确认移动
      </el-button>
    </template>
  </el-dialog>

  <!-- 发布前硬冲突确认对话框 -->
  <el-dialog v-model="publishBlockVisible" title="存在硬冲突，无法发布" width="min(520px, 94vw)">
    <div class="space-y-4">
      <div class="flex items-start gap-3">
        <el-icon class="text-red-500 mt-1 text-xl"><CircleCloseFilled /></el-icon>
        <div>
          <div class="font-bold text-red-700">检测到 {{ hardConflictCount }} 项硬冲突</div>
          <div class="text-sm text-red-600 mt-1">请先处理以下硬冲突后再发布：</div>
        </div>
      </div>
      <div class="max-h-60 overflow-y-auto space-y-2 pr-2">
        <div
          v-for="c in hardConflicts.slice(0, 10)"
          :key="c.id"
          class="p-3 bg-red-50 border border-red-200 rounded text-sm"
        >
          <div class="font-medium text-red-800">{{ c.type }}<span v-if="c.groupName"> · {{ c.groupName }}</span></div>
          <div class="text-red-600 text-xs mt-1">{{ c.reason }}</div>
        </div>
        <div v-if="hardConflictCount > 10" class="text-xs text-gray-500 text-center pt-2">
          还有 {{ hardConflictCount - 10 }} 项冲突未显示，请在右侧冲突面板中查看全部。
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="publishBlockVisible = false">我知道了</el-button>
      <el-button type="primary" @click="scrollToConflictPanel">查看冲突</el-button>
    </template>
  </el-dialog>

  <ScheduleAdjustDrawer
    v-model="adjustVisible"
    :defense-type="defenseType"
    :group="currentGroup"
    :teachers="teacherOptions"
    :students="studentOptions"
    :classrooms="classroomOptions"
    :saving="adjustSaving"
    :readonly="!canEdit"
    :conflict-count="currentGroupConflictCount"
    :error-count="currentGroupErrorCount"
    @save="handleSaveAdjust"
  />

  <ConflictDetailDialog v-model="conflictDetailVisible" :conflict="currentConflict" @locate="handleLocateConflict" />

  <ExportDialog
    v-model="exportDialogVisible"
    :options="{ defenseType: defenseType }"
    :stats="exportStats"
    :version-info="exportVersionInfo"
    @confirm="handleExportConfirm"
  />

  <ExportProgress
    :status="exportStatus"
    @close="exportStatus = 'idle'"
  />

  <!-- 操作记录抽屉 -->
  <el-drawer v-model="operationLogDrawerVisible" title="排期操作记录" size="720px" destroy-on-close>
    <div class="px-2">
      <p class="text-sm text-gray-500 mb-4">
        查看当前答辩类型的排期相关操作记录，包括生成、调整、移动学生、发布等操作。
        <span v-if="canManage">服务端审计日志（标记「审计」）由系统自动记录。</span>
      </p>
      <OperationLogTable
        ref="scheduleLogTableRef"
        :can-manage="canManage"
        default-module="排期管理"
        :show-authoritative-toggle="canManage"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Warning, CircleCloseFilled, InfoFilled, Loading } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import WorkflowSteps from '../../components/WorkflowSteps.vue'
import WorkflowStatusBar from '../../components/WorkflowStatusBar.vue'
import { useDefenseType, workflowLink } from '../../utils/useDefenseType'
import type { RuleConfig } from '../../types/ruleConfig'
import ScheduleAgenda from '../../components/ScheduleAgenda.vue'
import ScheduleToolbar from '../../components/ScheduleToolbar.vue'
import ScheduleGroupCard from '../../components/ScheduleGroupCard.vue'
import ScheduleTable from '../../components/ScheduleTable.vue'
import LegendTag from '../../components/LegendTag.vue'
import ScheduleAdjustDrawer from '../../components/ScheduleAdjustDrawer.vue'
import ConflictPanel from '../../components/ConflictPanel.vue'
import ConflictDetailDialog from '../../components/ConflictDetailDialog.vue'
import ExportDialog from '../../components/ExportDialog.vue'
import ExportProgress from '../../components/ExportProgress.vue'
import SoftConstraintPanel from '../../components/SoftConstraintPanel.vue'
import OperationLogTable from '../../components/OperationLogTable.vue'
import type { ScheduleGroup, ScheduleResult, ScheduleStudent, ScheduleTeacher, ScheduleWorkflowState } from '../../types/schedule'
import { generateSchedule, generateLinkedSchedule, getScheduleResults, listScheduleVersions, publishSchedule, moveScheduleStudent, preflightSchedule, type ScheduleVersionOption, type PreflightResult } from '../../api/schedule'
import { checkScheduleConflicts } from '../../api/conflict'
import { updateScheduleGroup } from '../../api/adjustment'
import type { ScheduleConflict } from '../../types/conflict'
import { getGroupConflictCount, getGroupStatus } from '../../utils/conflictMock'
import { exportScheduleExcel, exportScheduleWord, exportSchedulePdf } from '../../api/export'
import type { ExportStatus } from '../../types/export'
import type { OptimizationSummary } from '../../types/optimization'
import { evaluateSoftConstraints } from '../../utils/optimization'
import { getRuleConfig } from '../../api/ruleConfig'
import { listTeachers } from '../../api/teacher'
import { listStudents } from '../../api/student'
import { listClassrooms } from '../../api/classroom'
import type { Classroom } from '../../types/classroom'
import { useScheduleContext, type ScheduleContext } from '../../composables/useScheduleContext'
import { getScheduleExperts } from '../../domain/scheduleExperts'
import { buildScheduleRules } from '../../domain/scheduleRules'
import { orderScheduleGroups } from '../../domain/scheduleOrder'
import { summarizeStudentCounts } from '../../domain/studentCountSummary'
import { validateWizardRules } from '../../utils/wizardValidation'
import { useAdminGuard } from '../../utils/adminGuard'

const props = defineProps<{ guided?: boolean; guidedStage?: 'review' | 'publish' }>()
const emit = defineEmits<{
  (event: 'state', state: ScheduleWorkflowState): void
  (event: 'requirements'): void
  (event: 'materials'): void
}>()
const defenseType = useDefenseType()
const router = useRouter()
const route = useRoute()
const publishBar = ref<HTMLElement>()
const generationVisible = ref(false)
const linkedVisible = ref(false)
const linkedConfigs = ref<[RuleConfig, RuleConfig] | null>(null)
const linkedExpertCount = ref(3)
const updateLinkedExpertCount = () => {
  if (linkedConfigs.value) linkedConfigs.value = linkedConfigs.value.map((config, index) => ({ ...config, mentorAvoidance: false, expertCount: { target: index === 0 ? linkedExpertCount.value : 5, min: index === 0 ? linkedExpertCount.value : 5 } })) as [RuleConfig, RuleConfig]
  linkedPreflightStatus.value = 'idle'
  linkedPreflightPre.value = null
  linkedPreflightFormal.value = null
}
const linkedError = ref('')
const generationConfig = ref<RuleConfig | null>(null)
const generationStudentCount = ref(0)
// 预检相关状态
const preflightLoading = ref(false)
const preflightResult = ref<PreflightResult | null>(null)
const preflightStatus = ref<'idle' | 'loading' | 'passed' | 'failed'>('idle')
// 联合生成预检状态
const linkedPreflightLoading = ref(false)
const linkedPreflightPre = ref<PreflightResult | null>(null)
const linkedPreflightFormal = ref<PreflightResult | null>(null)
const linkedPreflightStatus = ref<'idle' | 'loading' | 'passed' | 'failed'>('idle')
const viewMode = ref<'agenda' | 'card' | 'table'>(props.guided ? 'agenda' : 'card')
const loading = ref(false)
const loadingMessage = ref('')
const errorMsg = ref('')
const result = ref<ScheduleResult | null>(null)
const studentCountSummary = computed(() => summarizeStudentCounts(result.value?.groups ?? [], result.value?.rules))
const linkedHasWarnings = computed(() => !!(linkedPreflightPre.value?.warnings.length || linkedPreflightFormal.value?.warnings.length))
const { canManage, requireAdmin } = useAdminGuard()

const selectedVersion = ref<number | undefined>()
const versions = ref<ScheduleVersionOption[]>([])
const workspace = useScheduleContext(defenseType, selectedVersion, result)
const editingRevision = ref<number | undefined>()
const canEdit = computed(() => canManage.value && result.value?.status !== 'published' && result.value?.isCurrent !== false && !loading.value && !publishing.value && !moving.value)

// 随机种子展示：仅正式答辩且种子存在时显示
const showRandomSeed = computed(() => {
  return defenseType.value === '正式答辩' && result.value?.randomSeed !== undefined && result.value?.randomSeed !== null && result.value.randomSeed !== ''
})

const publishing = ref(false)
const moving = ref(false)
const moveVisible = ref(false)
const moveStudentId = ref<number>()
const moveTargetId = ref<number>()
const preserveSecretary = ref(true)
const replacementSecretaryId = ref<number>()
const moveChoices = computed(() => result.value?.groups.flatMap(g => g.students.map(student => ({
  id: student.id, groupId: g.id, label: `${student.name}（${g.groupName}）`
}))) || [])

// 当前选中的待移动学生详情
const selectedMoveStudent = computed(() => {
  if (!moveStudentId.value || !result.value) return null
  for (const g of result.value.groups) {
    const s = g.students.find(student => student.id === moveStudentId.value)
    if (s) {
      return {
        ...s,
        groupId: g.id,
        groupName: g.groupName
      }
    }
  }
  return null
})

// 操作记录抽屉
const operationLogDrawerVisible = ref(false)
const scheduleLogTableRef = ref<InstanceType<typeof OperationLogTable> | null>(null)

const openOperationLogDrawer = () => {
  operationLogDrawerVisible.value = true
  // 打开后刷新日志列表
  setTimeout(() => {
    scheduleLogTableRef.value?.loadLogs()
  }, 100)
}

const handleMoveStudentChange = () => {
  // 学生变化时重置目标组选择
  moveTargetId.value = undefined
}

// 高亮分组 ID 列表（冲突定位用）
const highlightedGroupIds = ref<number[]>([])
let highlightTimer: ReturnType<typeof setTimeout> | null = null

const handleLocateConflict = (groupIds: number[]) => {
  if (!groupIds.length) return
  // 清除之前的定时器
  if (highlightTimer) {
    clearTimeout(highlightTimer)
    highlightTimer = null
  }
  // 设置新的高亮
  highlightedGroupIds.value = [...groupIds]
  // 2 秒后自动取消高亮
  highlightTimer = setTimeout(() => {
    highlightedGroupIds.value = []
    highlightTimer = null
  }, 2000)
}

// 发布前硬冲突阻断
const publishBlockVisible = ref(false)
const hardConflicts = computed(() => conflicts.value.filter(c => c.level === 'error'))
const hardConflictCount = computed(() => hardConflicts.value.length)

const scrollToConflictPanel = () => {
  publishBlockVisible.value = false
  // 滚动到右侧冲突面板
  const panel = document.querySelector('.conflict-panel-scroll-target')
  if (panel) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const handlePublish = async () => {
  if (!requireAdmin() || !canEdit.value || !result.value?.versionId || result.value.revision === undefined) return

  // 前端预检查：有硬冲突时提前拦截
  if (hardConflictCount.value > 0) {
    publishBlockVisible.value = true
    return
  }

  const context = workspace.capture()
  const current = result.value
  publishing.value = true
  try {
    const published = await publishSchedule(current.versionId!, current.revision!)
    if (!workspace.isCurrent(context, true)) return
    result.value = published
    applyConflictsFromResult(published)
    const options = await listScheduleVersions(context.defenseType)
    if (!workspace.isCurrent(context)) return
    versions.value = options
    ElMessage.success('已发布并锁定该版本，后续修改请生成新草稿')
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '发布失败')
  } finally { if (workspace.isCurrent(context)) publishing.value = false }
}

const handleMoveStudent = async () => {
  const choice = moveChoices.value.find(student => student.id === moveStudentId.value)
  const sourceGroup = result.value?.groups.find(g => g.id === choice?.groupId)
  const targetGroup = result.value?.groups.find(g => g.id === moveTargetId.value)
  if (!requireAdmin() || !choice || !moveTargetId.value || !result.value || !canEdit.value || (!preserveSecretary.value && !replacementSecretaryId.value)) return
  const context = workspace.capture()
  const beforeErrorCount = conflicts.value.filter(c => c.level === 'error').length
  const studentName = selectedMoveStudent.value?.name || '该学生'
  const sourceGroupName = sourceGroup?.groupName || '原组'
  const targetGroupName = targetGroup?.groupName || '目标组'
  const secretaryText = preserveSecretary.value ? '保留原秘书' : `改绑秘书`
  const mentorText = defenseType.value === '正式答辩' ? '导师回避（不移动）' : '导师跟随移动'

  moving.value = true
  try {
    await moveScheduleStudent(choice.id, choice.groupId, moveTargetId.value, editingRevision.value, { preserveSecretary: preserveSecretary.value, moveMentor: true, secretaryId: replacementSecretaryId.value })
    if (!workspace.isCurrent(context, true)) return
    moveVisible.value = false
    moving.value = false

    // 移动后刷新结果，自动获取最新冲突（自动复核）
    await fetchResult()
    if (!workspace.isCurrent(context)) return

    const afterErrorCount = conflicts.value.filter(c => c.level === 'error').length
    const newErrors = afterErrorCount - beforeErrorCount

    // 构建详细成功提示
    const detailLines = [
      `学生：${studentName}`,
      `从【${sourceGroupName}】 → 【${targetGroupName}】`,
      `秘书：${secretaryText}${preserveSecretary.value ? '' : replacementSecretaryId.value ? '（已选择新秘书）' : ''}`,
      `导师：${mentorText}`,
      `冲突已自动复核${newErrors > 0 ? `，新增 ${newErrors} 项硬冲突` : '，无新增硬冲突'}`
    ]

    if (newErrors > 0) {
      ElMessage.warning({
        message: detailLines.join(' | '),
        duration: 5000,
        showClose: true
      })
    } else {
      ElMessage.success({
        message: `${detailLines.join(' | ')} | 操作已记录日志`,
        duration: 4000,
        showClose: true
      })
    }
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '移动失败')
  } finally { if (workspace.isCurrent(context)) moving.value = false }
}

const conflicts = ref<ScheduleConflict[]>([])
const conflictLoading = ref(false)

const adjustVisible = ref(false)
const adjustSaving = ref(false)
const currentGroup = ref<ScheduleGroup | null>(null)

const currentConflict = ref<ScheduleConflict | null>(null)
const conflictDetailVisible = ref(false)

const exportDialogVisible = ref(false)
const exportCheckLoading = ref(false)
const exportStatus = ref<ExportStatus>('idle')

const optimizationSummary = ref<OptimizationSummary | null>(null)

const teacherOptions = ref<ScheduleTeacher[]>([])
const studentOptions = ref<ScheduleStudent[]>([])
const classroomOptions = ref<{ campus: '创新港' | '兴庆'; name: string }[]>([])

const updateOptimizationScore = async (scheduleResult: ScheduleResult, context: ScheduleContext) => {
  try {
    const config = await getRuleConfig(context.defenseType)
    if (!workspace.isCurrent(context) || result.value?.versionId !== scheduleResult.versionId || result.value?.revision !== scheduleResult.revision) return
    optimizationSummary.value = evaluateSoftConstraints(scheduleResult, config)
  } catch {
    if (workspace.isCurrent(context)) optimizationSummary.value = null
  }
}

const openAdjust = (group: ScheduleGroup) => {
  if (!requireAdmin()) return
  if (!canEdit.value) return
  editingRevision.value = result.value?.revision
  currentGroup.value = group
  adjustVisible.value = true
}

const openConflictDetail = (c: ScheduleConflict) => {
  currentConflict.value = c
  conflictDetailVisible.value = true
}

const handleExportClick = async () => {
  const current = result.value
  if (!current || loading.value || exportCheckLoading.value) return
  const context = workspace.capture()
  exportCheckLoading.value = true
  try {
    const checked = await checkScheduleConflicts(context.defenseType, current)
    if (!workspace.isCurrent(context, true)) return
    conflicts.value = checked
    const errors = checked.filter(conflict => conflict.level === 'error')
    if (errors.length) {
      ElMessage.error(`当前排期有 ${errors.length} 项硬冲突，处理并重新复核后才能导出`)
      return
    }
    exportDialogVisible.value = true
  } catch (error) {
    if (workspace.isCurrent(context)) {
      ElMessage.error(error instanceof Error ? error.message : '导出前冲突复核失败，暂不能导出')
    }
  } finally {
    if (workspace.isCurrent(context)) exportCheckLoading.value = false
  }
}

// 导出版本信息
const exportVersionInfo = computed(() => {
  if (!result.value || result.value.version === undefined) return undefined
  return {
    versionNumber: result.value.version,
    status: (result.value.status || 'draft') as 'draft' | 'published',
    isCurrent: result.value.isCurrent !== false
  }
})

const handleExportConfirm = async (format: 'excel' | 'word' | 'pdf' = 'excel') => {
  if (conflicts.value.some(conflict => conflict.level === 'error')) {
    ElMessage.error('当前排期存在硬冲突，处理并重新复核后才能导出')
    return
  }
  const type = defenseType.value
  const versionId = result.value?.versionId
  exportStatus.value = 'exporting'
  try {
    if (format === 'pdf') {
      await exportSchedulePdf(type, versionId)
    } else if (format === 'word') {
      await exportScheduleWord(type, versionId)
    } else {
      await exportScheduleExcel(type, versionId)
    }
    exportStatus.value = 'success'
  } catch (error) {
    exportStatus.value = 'error'
    ElMessage.error(error instanceof Error ? error.message : '导出失败，请稍后重试')
  }
}

const loadOptions = async (context: ScheduleContext) => {
  const [teachers, students, classrooms] = await Promise.all([
    listTeachers(),
    listStudents(context.defenseType, context.versionId),
    listClassrooms()
  ])

  if (!workspace.isCurrent(context)) return
  teacherOptions.value = teachers.filter(t => t.isActive !== false).map(t => ({
    id: t.id,
    name: t.name,
    title: t.title,
    roles: t.roles,
    college: t.college,
    isExternal: t.isExternal,
    isActive: t.isActive, memberEligible: t.memberEligible, isSoftwareTeacher: t.isSoftwareTeacher
  }))

  studentOptions.value = students.map(s => ({
    id: s.id,
    name: s.name,
    studentType: s.studentType,
    mentorName: s.mentorName,
    mentorId: s.mentorId, secretaryId: s.secretaryId, studentNo: s.studentNo, remark: s.remark,
    secretaryName: s.secretaryName
  }))

  classroomOptions.value = (classrooms as Classroom[]).map(c => ({ campus: c.campus, name: c.name }))
}

// 后端排期响应自带生成时的冲突快照；带了就直接用，否则回退到本地/远程检测
const applyConflictsFromResult = (scheduleResult: ScheduleResult): boolean => {
  if (Array.isArray(scheduleResult.conflicts)) {
    conflicts.value = scheduleResult.conflicts
    currentConflict.value = null
    return true
  }
  return false
}

const fetchResult = async () => {
  const context = workspace.begin()
  loading.value = true
  loadingMessage.value = ''
  errorMsg.value = ''
  conflictLoading.value = false
  publishing.value = false
  moving.value = false
  highlightedGroupIds.value = []
  try {
    const [scheduleResult, versionOptions] = await Promise.all([
      getScheduleResults(context.defenseType, context.versionId), listScheduleVersions(context.defenseType)
    ])
    if (!workspace.isCurrent(context)) return
    result.value = scheduleResult
    versions.value = versionOptions
    conflicts.value = []
    currentConflict.value = null
    optimizationSummary.value = null
    await loadOptions(context)
    if (!workspace.isCurrent(context) || !scheduleResult) return
    if (!applyConflictsFromResult(scheduleResult)) {
      const checked = await checkScheduleConflicts(context.defenseType, scheduleResult)
      if (!workspace.isCurrent(context)) return
      conflicts.value = checked
    }
    await updateOptimizationScore(scheduleResult, context)
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '排期结果加载失败'
    result.value = null
    conflicts.value = []
    currentConflict.value = null
    optimizationSummary.value = null
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

const prepareGeneration = async () => {
  if (!requireAdmin() || loading.value || publishing.value || moving.value) return
  const context = workspace.capture()
  loading.value = true
  try {
    const [config, students] = await Promise.all([
      getRuleConfig(context.defenseType), listStudents(context.defenseType)
    ])
    if (!workspace.isCurrent(context)) return
    generationConfig.value = context.defenseType === '预答辩'
      ? { ...config, expertCount: { target: 3, min: 3 } }
      : context.defenseType === '正式答辩'
        ? { ...config, preservePreDefenseGroups: true, mentorAvoidance: false } : config
    generationStudentCount.value = students.filter(student => student.defenseTypes.includes(context.defenseType)).length
    // 重置预检状态
    preflightStatus.value = 'idle'
    preflightResult.value = null
    preflightLoading.value = false
    generationVisible.value = true
  } catch (error) { if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '无法读取安排要求，请重试') }
  finally { if (workspace.isCurrent(context)) loading.value = false }
}

const prepareLinkedGeneration = async () => {
  if (!requireAdmin() || loading.value || publishing.value || moving.value) return
  const context = workspace.capture()
  loading.value = true
  try {
    const [pre, formal, students] = await Promise.all([
      getRuleConfig('预答辩'), getRuleConfig('正式答辩'), listStudents('预答辩')
    ])
    if (!workspace.isCurrent(context)) return
    linkedConfigs.value = [pre, { ...formal, preservePreDefenseGroups: true }]
    linkedExpertCount.value = pre.expertCount.target
    updateLinkedExpertCount()
    const errors = [...validateWizardRules(pre), ...validateWizardRules(formal)]
    if (formal.startDate <= pre.endDate) errors.push('正式答辩开始日期必须晚于预答辩结束日期，请修改两阶段日期。')
    if (!students.some(student => student.defenseTypes.includes('预答辩') && student.defenseTypes.includes('正式答辩'))) errors.push('请先为联合安排的学生勾选预答辩与正式答辩两个参与环节。')
    linkedError.value = errors.join(' ')
    // 重置联合预检状态
    linkedPreflightStatus.value = 'idle'
    linkedPreflightPre.value = null
    linkedPreflightFormal.value = null
    linkedPreflightLoading.value = false
    linkedVisible.value = true
  } catch (error) { if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '两阶段要求读取失败') }
  finally { if (workspace.isCurrent(context)) loading.value = false }
}

const handleGenerateLinked = async () => {
  if (!requireAdmin() || !linkedConfigs.value || linkedError.value || loading.value || linkedPreflightLoading.value) return
  const configs = linkedConfigs.value

  // 第一步：预检（两阶段分别预检）
  if (linkedPreflightStatus.value !== 'passed') {
    linkedPreflightLoading.value = true
    linkedPreflightStatus.value = 'loading'
    try {
      const preRules = buildScheduleRules('预答辩', configs[0])
      const formalRules = buildScheduleRules('正式答辩', configs[1])
      const [preResult, formalResult] = await Promise.all([
        preflightSchedule(preRules as unknown as Record<string, unknown>, { linkedGeneration: true }),
        preflightSchedule(formalRules as unknown as Record<string, unknown>, { linkedGeneration: true })
      ])
      linkedPreflightPre.value = preResult
      linkedPreflightFormal.value = formalResult

      if (preResult.canGenerate && formalResult.canGenerate) {
        linkedPreflightStatus.value = 'passed'
        // 预检通过后，继续生成
        if (!linkedHasWarnings.value) await doGenerateLinked(configs)
      } else {
        linkedPreflightStatus.value = 'failed'
        ElMessage.warning('资料或安排要求检查未通过，请查看具体原因后再联合生成')
      }
    } catch (error) {
      linkedPreflightStatus.value = 'idle'
      ElMessage.error(error instanceof Error ? error.message : '预检失败，请重试')
    } finally {
      linkedPreflightLoading.value = false
    }
    return
  }

  // 预检已通过，直接生成
  await doGenerateLinked(configs)
}

const doGenerateLinked = async (configs: [RuleConfig, RuleConfig]) => {
  linkedVisible.value = false
  selectedVersion.value = undefined
  const context = workspace.begin()
  loading.value = true
  try {
    await generateLinkedSchedule(configs[0], configs[1])
    if (!workspace.isCurrent(context)) return
    ElMessage.success('两阶段草稿已生成，请分别核对冲突后发布')
    await fetchResult()
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '联合生成失败'
    ElMessage.error(`${errorMsg.value}。若请求超时，可重试获取同一联合生成结果。`)
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

const handleGenerate = async () => {
  if (!requireAdmin() || !generationConfig.value || loading.value || preflightLoading.value) return
  const config = generationConfig.value
  const ruleErrors = validateWizardRules(config)
  if (ruleErrors.length) { ElMessage.error(ruleErrors.join(' ')); return }

  // 第一步：预检
  if (preflightStatus.value !== 'passed') {
    preflightLoading.value = true
    preflightStatus.value = 'loading'
    try {
      const rules = buildScheduleRules(defenseType.value, config)
      const result = await preflightSchedule(rules as unknown as Record<string, unknown>)
      preflightResult.value = result
      if (result.canGenerate) {
        preflightStatus.value = 'passed'
        // 预检通过后，继续生成
        if (!result.warnings.length) await doGenerate(config)
      } else {
        preflightStatus.value = 'failed'
        ElMessage.warning('资料或安排要求检查未通过，请查看具体原因后再生成')
      }
    } catch (error) {
      preflightStatus.value = 'idle'
      ElMessage.error(error instanceof Error ? error.message : '预检失败，请重试')
    } finally {
      preflightLoading.value = false
    }
    return
  }

  // 预检已通过，直接生成
  await doGenerate(config)
}

const doGenerate = async (config: RuleConfig) => {
  generationVisible.value = false
  selectedVersion.value = undefined
  const context = workspace.begin()
  loading.value = true
  errorMsg.value = ''
  conflicts.value = []
  currentConflict.value = null
  try {
    const scheduleResult = await generateSchedule(context.defenseType, config)
    if (!workspace.isCurrent(context)) return
    result.value = scheduleResult
    const options = await listScheduleVersions(context.defenseType)
    if (!workspace.isCurrent(context)) return
    versions.value = options
    ElMessage.success('草稿已生成，请核对冲突后发布')
    if (!applyConflictsFromResult(scheduleResult)) {
      const checked = await checkScheduleConflicts(context.defenseType, scheduleResult)
      if (!workspace.isCurrent(context)) return
      conflicts.value = checked
    }
    await loadOptions(context)
    if (!workspace.isCurrent(context)) return
    await updateOptimizationScore(scheduleResult, context)
  } catch (error) {
    if (!workspace.isCurrent(context)) return
    errorMsg.value = error instanceof Error ? error.message : '生成失败'
    conflicts.value = []
    currentConflict.value = null
    ElMessage.error(`${errorMsg.value}。若请求超时，可重试获取同一生成结果。`)
  } finally { if (workspace.isCurrent(context)) loading.value = false }
}

// 根据错误类型跳转到对应的数据补齐页面
const goToFixData = (issueType: string) => {
  // 与学生相关的问题 → 学生名单
  const studentTypes = ['mentor_missing', 'student_defense_type_missing', 'no_students']
  // 与教师相关的问题 → 教师名单
  const teacherTypes = ['mentor_not_found', 'mentor_unavailable_for_defense', 'secretary_not_found', 'secretary_unavailable_for_defense', 'no_teachers']

  generationVisible.value = false
  linkedVisible.value = false

  if (['external_mentor_capacity', 'inherited_group_size'].includes(issueType)) {
    if (props.guided) emit('requirements')
    else router.push(workflowLink('/rule-config'))
  } else if (studentTypes.includes(issueType)) {
    router.push(preparationLink('/students'))
  } else if (teacherTypes.includes(issueType)) {
    router.push(preparationLink('/teachers'))
  } else {
    router.push(workflowLink('/dashboard'))
  }
}

// 补齐资料的跳转保留当前答辩类型；向导中添加 wizard 标记，管理页可直接返回向导
const preparationLink = (path: string) => ({
  path,
  query: props.guided ? { type: defenseType.value, wizard: '1' } : { type: defenseType.value }
})

// 从步骤条进入“发布与导出”时定位到版本与发布区域，避免与“生成与检查”看起来是同一个位置
const scrollToPublishArea = async () => {
  await nextTick()
  publishBar.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
watch(() => [route.query.stage, versions.value.length], () => {
  if (!props.guided && route.query.stage === 'export') void scrollToPublishArea()
}, { immediate: true })

const handleRefresh = async () => {
  await fetchResult()
}

let conflictRequest = 0
const handleCheckConflicts = async () => {
  const current = result.value
  if (!current || loading.value) return
  const context = workspace.capture()
  const requestId = ++conflictRequest
  conflictLoading.value = true
  try {
    const checked = await checkScheduleConflicts(context.defenseType, current)
    if (!workspace.isCurrent(context, true) || requestId !== conflictRequest) return
    conflicts.value = checked
    ElMessage.success('手动复核完成')
  } catch (error) {
    if (workspace.isCurrent(context, true) && requestId === conflictRequest) ElMessage.error(error instanceof Error ? error.message : '冲突检测失败')
  } finally { if (workspace.isCurrent(context) && requestId === conflictRequest) conflictLoading.value = false }
}

const handleSaveAdjust = async (groupData: ScheduleGroup) => {
  if (!requireAdmin() || !result.value || !canEdit.value) return
  const context = workspace.capture()
  const beforeErrorCount = conflicts.value.filter(c => c.level === 'error').length
  adjustSaving.value = true
  try {
    await updateScheduleGroup({ defenseType: context.defenseType, groupId: groupData.id, expectedRevision: editingRevision.value, groupData })
    if (!workspace.isCurrent(context, true)) return
    adjustVisible.value = false
    adjustSaving.value = false

    // 调整后刷新结果，自动获取最新冲突（自动复核）
    await fetchResult()
    if (!workspace.isCurrent(context)) return

    const afterErrorCount = conflicts.value.filter(c => c.level === 'error').length
    if (afterErrorCount > beforeErrorCount) {
      ElMessage.warning(`调整保存成功，但产生了 ${afterErrorCount - beforeErrorCount} 项新的硬冲突，请及时处理`)
    } else if (afterErrorCount < beforeErrorCount) {
      ElMessage.success(`调整保存成功，已自动复核冲突，硬冲突减少 ${beforeErrorCount - afterErrorCount} 项`)
    } else {
      ElMessage.success('调整保存成功，已自动复核冲突')
    }
  } catch (error) {
    if (workspace.isCurrent(context)) ElMessage.error(error instanceof Error ? error.message : '保存失败，请稍后重试')
  } finally { if (workspace.isCurrent(context)) adjustSaving.value = false }
}

watch(selectedVersion, () => { adjustVisible.value = false; moveVisible.value = false; generationVisible.value = false; linkedVisible.value = false; publishing.value = false; moving.value = false; adjustSaving.value = false; highlightedGroupIds.value = [] })
watch(moveVisible, visible => { if (visible) { preserveSecretary.value = true; replacementSecretaryId.value = undefined; moveStudentId.value = undefined; moveTargetId.value = undefined } })

watch(defenseType, async () => {
  selectedVersion.value = undefined
  adjustVisible.value = false
  moveVisible.value = false
  generationVisible.value = false
  linkedVisible.value = false
  publishing.value = false
  moving.value = false
  adjustSaving.value = false
  result.value = null
  conflicts.value = []
  currentConflict.value = null
  optimizationSummary.value = null
  highlightedGroupIds.value = []
  await fetchResult()
})

watch(canManage, isAllowed => {
  if (!isAllowed) {
    adjustVisible.value = false
    currentGroup.value = null
  }
})

onMounted(() => { void fetchResult() })

const groupStatusMap = computed(() => {
  const map: Record<number, 'normal' | 'warning' | 'error'> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupStatus(g.id, conflicts.value)
  }
  return map
})

const groupConflictCountMap = computed(() => {
  const map: Record<number, number> = {}
  if (!result.value) return map
  for (const g of result.value.groups) {
    map[g.id] = getGroupConflictCount(g.id, conflicts.value)
  }
  return map
})

const currentGroupConflictCount = computed(() => {
  if (!currentGroup.value) return 0
  return groupConflictCountMap.value[currentGroup.value.id] || 0
})

const currentGroupErrorCount = computed(() => {
  if (!currentGroup.value) return 0
  return conflicts.value.filter(c =>
    c.level === 'error' &&
    (c.groupId === currentGroup.value?.id || c.relatedGroupIds?.includes(currentGroup.value!.id))
  ).length
})

const nextStepTitle = computed(() => {
  if (!result.value?.groups.length) return canManage.value ? '下一步：生成一份草稿' : '等待管理员发布安排'
  if (result.value.status === 'published') return '安排已发布，下一步可以导出文件'
  if (result.value.isCurrent === false) return '正在查看历史版本'
  const errors = conflicts.value.filter(c => c.level === 'error').length
  return errors ? `下一步：处理 ${errors} 项问题` : '下一步：核对分组，确认后发布'
})
const dateFilter = ref('')
const campusFilter = ref('')
const onlyProblems = ref(false)
const availableDates = computed(() => [...new Set(result.value?.groups.map(group => group.date) || [])].sort())
const filteredGroups = computed(() => orderScheduleGroups(result.value?.groups || []).filter(group =>
  (!dateFilter.value || group.date === dateFilter.value)
  && (!campusFilter.value || group.campus === campusFilter.value)
  && (!onlyProblems.value || groupConflictCountMap.value[group.id] > 0)))
const resetFilters = () => { dateFilter.value = ''; campusFilter.value = ''; onlyProblems.value = false }
const openGroupProblem = (groupId: number) => {
  const conflict = conflicts.value.find(item => item.groupId === groupId || item.relatedGroupIds?.includes(groupId))
  if (conflict) openConflictDetail(conflict)
}
watch([defenseType, selectedVersion], resetFilters)
watch(() => ({
  hasResult: !!result.value?.groups.length && !errorMsg.value,
  status: result.value?.status === 'published' ? 'published' as const : 'draft' as const,
  errorCount: conflicts.value.filter(conflict => conflict.level === 'error').length,
  busy: loading.value || publishing.value || moving.value || adjustSaving.value || conflictLoading.value || generationVisible.value || linkedVisible.value || adjustVisible.value || moveVisible.value || exportDialogVisible.value || exportStatus.value === 'exporting'
}), state => emit('state', state), { immediate: true })

const emptyResultDescription = computed(() => {
  return canManage.value
    ? `还没有分组。资料和要求确认后，点击上方“${defenseType.value === '中期答辩' ? '生成排期草稿' : defenseType.value === '预答辩' ? '生成预答辩草稿' : '沿用预答辩生成正式答辩'}”。`
    : '当前暂无排期结果，请联系管理员生成排期。'
})

const exportStats = computed(() => ({
  groupCount: meta.value.groupCount,
  studentCount: meta.value.studentCount,
  conflictCount: meta.value.conflictCount,
  errorCount: conflicts.value.filter(c => c.level === 'error').length,
  warningCount: conflicts.value.filter(c => c.level === 'warning').length
}))

const meta = computed(() => {
  if (!result.value) {
    return {
      generatedAt: '',
      groupCount: 0,
      studentCount: 0,
      teacherCount: 0,
      conflictCount: 0
    }
  }

  const teacherSet = new Set<number>()
  let studentCount = 0
  for (const g of result.value.groups) {
    for (const t of getScheduleExperts(g)) teacherSet.add(t.id)
    studentCount += g.students.length
  }

  return {
    generatedAt: result.value.generatedAt ? new Date(result.value.generatedAt).toLocaleString() : '',
    groupCount: result.value.groups.length,
    studentCount,
    teacherCount: teacherSet.size,
    conflictCount: conflicts.value.length
  }
})
</script>

<style scoped>
/* 移动学生对话框样式 */
.move-select-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.move-label {
  width: 80px;
  flex-shrink: 0;
  line-height: 32px;
  font-size: 14px;
  color: #606266;
  text-align: right;
}

.move-student-info {
  margin-left: 92px;
}

.secretary-rebind-panel {
  margin-top: 8px;
}

/* 工作流提示 */
.workflow-note.compact-status {
  padding: 10px 14px;
  background: #f0f9ff;
  border: 1px solid #d9ecff;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.compact-links {
  display: flex;
  gap: 16px;
  margin-top: 6px;
}

.text-link {
  color: #409eff;
  text-decoration: none;
  font-size: 12px;
}

.text-link:hover {
  text-decoration: underline;
}

/* 排期筛选栏 */
.schedule-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  font-size: 13px;
  color: #606266;
}

.section-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

/* 二级详情面板 */
.secondary-details summary {
  cursor: pointer;
  color: #606266;
  font-size: 13px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  list-style: none;
}

.secondary-details summary::-webkit-details-marker {
  display: none;
}

.secondary-details summary::before {
  content: '▸ ';
  transition: transform 0.2s;
  display: inline-block;
}

.secondary-details[open] summary::before {
  transform: rotate(90deg);
}

/* 预检结果区域样式 */
.student-count-summary {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}
.student-count-heading, .student-count-buckets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  font-size: 13px;
}
.student-count-heading { color: #606266; }
.student-count-heading strong { color: #303133; }
.student-count-match { margin-left: auto; }
.student-count-buckets { margin-top: 12px; gap: 8px; }
.student-count-bucket {
  padding: 7px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 5px;
  color: #606266;
  background: #fafafa;
}
.student-count-bucket.is-target {
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.preflight-section {
  min-height: 40px;
}

.preflight-idle {
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  border: 1px dashed #dcdfe6;
}

.preflight-loading {
  padding: 8px 12px;
  background: #ecf5ff;
  border-radius: 6px;
  border: 1px solid #d9ecff;
}

.preflight-error-item {
  transition: background-color 0.2s;
}

.preflight-error-item:hover {
  background-color: #fef0f0;
}

.linked-preflight-stage {
  padding-left: 8px;
  border-left: 3px solid #e4e7ed;
}

/* 随机种子展示行 - 低调显示 */
.random-seed-row {
  display: inline-flex;
  align-items: center;
  margin-left: auto;
}

.random-seed-row .regenerate-btn {
  margin-left: 2px;
}

.random-seed-row :deep(.el-button--small) {
  padding: 2px 4px;
  font-size: 12px;
}

/* ========== 移动端适配 ========== */
@media (max-width: 768px) {
  /* 版本选择区域 */
  .version-bar {
    padding: 12px !important;
    gap: 8px !important;
  }

  .version-bar .el-select {
    width: 100% !important;
  }

  .version-bar > span {
    width: 100%;
    font-weight: 500;
  }

  .version-bar .el-tag {
    margin-right: auto;
  }

  .version-bar .el-button {
    flex: 1;
    min-width: 0;
  }

  /* 排期筛选栏 - 移动端可横向滚动 */
  .schedule-filters {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding: 10px 12px;
    gap: 10px;
    -webkit-overflow-scrolling: touch;
  }

  .schedule-filters > * {
    flex-shrink: 0;
  }

  .schedule-filters .el-select {
    width: 120px;
  }

  .section-tip {
    flex-shrink: 1 !important;
    min-width: 100%;
  }

  /* 统计信息区域 */
  .stats-panel {
    padding: 14px !important;
  }

  .stats-panel > div {
    width: 50%;
    font-size: 13px;
  }

  /* 操作按钮区域 - 标题栏 */
  .page-header {
    padding: 16px !important;
  }

  .page-header > div:first-child {
    flex: 1;
    min-width: 0;
  }

  /* 卡片视图在移动端单列 */
  .schedule-card-grid :deep(.el-col) {
    margin-bottom: 12px;
  }

  /* 工作流提示紧凑化 */
  .workflow-note.compact-status {
    padding: 8px 12px;
    font-size: 12px;
  }

  .compact-links {
    flex-wrap: wrap;
    gap: 8px 16px;
  }

  /* 冲突面板在移动端与主内容同宽 */
  .conflict-sidebar {
    width: 100% !important;
  }
}

@media (max-width: 480px) {
  /* 更小屏幕下按钮堆叠 */
  .version-bar .el-button {
    flex: 1 1 100%;
    width: 100%;
  }

  .schedule-filters .el-select {
    width: 110px;
  }

  .stats-panel > div {
    width: 100%;
  }
}
</style>
