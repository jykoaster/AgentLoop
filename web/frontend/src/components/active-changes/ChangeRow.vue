<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ChangeRow as ChangeRowType, RunStatus } from '../../api'
import StageCard from './StageCard.vue'
import StageDetail from './StageDetail.vue'

const STAGES = ['analyze_plan', 'human_confirm', 'execute', 'review', 'archive'] as const
const RERUNNABLE = new Set<string>(['analyze_plan', 'execute', 'review', 'archive'])

const props = defineProps<{
  row: ChangeRowType
  runStatus: RunStatus
  temporary?: boolean
}>()

const emit = defineEmits<{
  rerun: [payload: { changeName: string; stage: string }]
  'view-files': [changeName: string]
}>()

const selectedStage = ref<string | null>(null)
const collapsed = ref(true)

const truncatedTask = computed(() => {
  const task = props.row.task
  return task.length > 80 ? `${task.slice(0, 80)}…` : task
})

const disabledReason = computed(() =>
  props.runStatus.active ? `目前已有 ${props.runStatus.label ?? ''} 執行中` : '',
)

const hasPendingQuestion = computed(() =>
  !!props.runStatus.active &&
  !!props.runStatus.question &&
  (props.runStatus.change_name || '') === (props.row.change_name || ''),
)

function hasQuestion(stage: string): boolean {
  return hasPendingQuestion.value && props.runStatus.question?.stage === stage
}

const question = computed(() =>
  selectedStage.value && hasQuestion(selectedStage.value) ? (props.runStatus.question ?? null) : null,
)

function openStage(stage: string): void {
  selectedStage.value = stage
}

const selectedStageStatus = computed<string | undefined>(() =>
  selectedStage.value ? props.row.stages[selectedStage.value as keyof ChangeRowType['stages']] : undefined,
)

function rerun(stage: string): void {
  emit('rerun', { changeName: props.row.change_name, stage })
}
</script>

<template>
  <div
    class="change-row flex flex-col gap-3 rounded-xl border border-line bg-surface p-5 shadow-lg"
    :class="{ 'animate-breathe-warning motion-reduce:animate-none': hasPendingQuestion }"
    :data-change-name="row.change_name || '(temp)'"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="flex flex-wrap items-baseline gap-2">
        <template v-if="!temporary">
          <span class="change-name font-semibold">{{ row.change_name }}</span>
          <span class="text-fg-muted">{{ row.branch_name }}</span>
        </template>
        <span class="task">{{ truncatedTask }}</span>
        <span v-if="!temporary" class="iteration text-fg-muted">第 {{ row.iteration }} 次迭代</span>
      </div>
      <button
        v-if="!temporary"
        type="button"
        class="view-files-button btn-secondary self-start px-2 py-1.5 text-sm"
        title="檢視規格文件"
        aria-label="檢視規格文件"
        @click="emit('view-files', row.change_name)"
      >
        <font-awesome-icon icon="file-lines" />
      </button>
      <button
        type="button"
        class="collapse-toggle btn-secondary px-2 py-1.5 text-sm"
        :title="collapsed ? '展開' : '收合'"
        :aria-label="collapsed ? '展開' : '收合'"
        :aria-expanded="!collapsed"
        @click="collapsed = !collapsed"
      >
        <font-awesome-icon :icon="collapsed ? 'chevron-down' : 'chevron-up'" />
      </button>
    </div>

    <template v-if="!collapsed">
      <div class="grid grid-cols-5 gap-2">
        <StageCard
          v-for="stage in STAGES"
          :key="stage"
          :stage="stage"
          :status="row.stages[stage]"
          :has-question="hasQuestion(stage)"
          :rerunnable="RERUNNABLE.has(stage)"
          :disabled-reason="disabledReason"
          @click="openStage(stage)"
          @rerun="rerun(stage)"
        />
      </div>

      <div v-if="selectedStage" class="stage-detail-panel rounded-lg border border-line p-4">
        <div class="flex justify-between items-center mb-5">
          <p class="text-2xl font-bold">{{ selectedStage }}</p>
          <button
            type="button"
            class="rounded-md p-1.5 text-danger transition-colors cursor-pointer hover:bg-danger/15"
            title="關閉"
            aria-label="關閉"
            @click="selectedStage = null"
            >
            <font-awesome-icon icon="xmark" />
          </button>
        </div>
        <StageDetail
          :change-name="row.change_name"
          :stage="selectedStage"
          :question="question"
          :temporary="temporary"
          :stage-status="selectedStageStatus"
        />
      </div>
    </template>
  </div>
</template>
