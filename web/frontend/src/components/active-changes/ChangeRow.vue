<script setup lang="ts">
import { computed } from 'vue'
import type { ChangeRow as ChangeRowType, RunStatus } from '../../api'
import StageCard from './StageCard.vue'

const STAGES = ['analyze_plan', 'human_confirm', 'execute', 'review', 'archive'] as const
const RERUNNABLE = new Set<string>(['analyze_plan', 'execute', 'review', 'archive'])

const props = defineProps<{
  row: ChangeRowType
  runStatus: RunStatus
  temporary?: boolean
}>()

const emit = defineEmits<{
  'open-stage': [payload: { changeName: string; stage: string }]
  rerun: [payload: { changeName: string; stage: string }]
  'view-files': [changeName: string]
}>()

const truncatedTask = computed(() => {
  const task = props.row.task
  return task.length > 80 ? `${task.slice(0, 80)}…` : task
})

const disabledReason = computed(() =>
  props.runStatus.active ? `目前已有 ${props.runStatus.label ?? ''} 執行中` : '',
)

function hasQuestion(stage: string): boolean {
  if (!props.runStatus.active || !props.runStatus.question) return false
  if (props.runStatus.question.stage !== stage) return false
  return (props.runStatus.change_name || '') === (props.row.change_name || '')
}

function openStage(stage: string): void {
  emit('open-stage', { changeName: props.row.change_name, stage })
}

function rerun(stage: string): void {
  emit('rerun', { changeName: props.row.change_name, stage })
}
</script>

<template>
  <div
    class="change-row flex flex-col gap-3 rounded-xl border border-line bg-surface p-5 shadow-lg"
    :data-change-name="row.change_name || '(temp)'"
  >
    <div class="flex flex-wrap items-baseline gap-2">
      <template v-if="!temporary">
        <span class="change-name font-semibold">{{ row.change_name }}</span>
        <span class="text-fg-muted">{{ row.branch_name }}</span>
      </template>
      <span class="task">{{ truncatedTask }}</span>
      <span v-if="!temporary" class="iteration text-fg-muted">第 {{ row.iteration }} 次迭代</span>
    </div>

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
  </div>
</template>
