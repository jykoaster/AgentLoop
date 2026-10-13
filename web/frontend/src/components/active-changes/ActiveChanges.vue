<script setup lang="ts">
import { computed, ref } from 'vue'
import * as api from '../../api'
import type { ChangeRow as ChangeRowType, RunStatus } from '../../api'
import { usePolling } from '../../composables/usePolling'
import ChangeRow from './ChangeRow.vue'
import FileBrowser from '../utils/FileBrowser.vue'
import NewTaskDialog from './NewTaskDialog.vue'
import StageDetail from './StageDetail.vue'

const EMPTY_STAGES = {
  analyze_plan: 'pending',
  human_confirm: 'pending',
  execute: 'pending',
  review: 'pending',
  archive: 'pending',
} as const

const rows = ref<ChangeRowType[]>([])
const runStatus = ref<RunStatus>({ active: false })
const selected = ref<{ changeName: string; stage: string } | null>(null)
const filesFor = ref('')
const showNewTaskDialog = ref(false)

async function load(): Promise<void> {
  const [changes, run] = await Promise.all([api.getChanges(), api.getRun()])
  rows.value = changes
  runStatus.value = run
}

usePolling(load)

const tempRow = computed<ChangeRowType | null>(() => {
  if (!runStatus.value.active || runStatus.value.change_name) return null
  return {
    change_name: '',
    branch_name: '',
    task: runStatus.value.task ?? '',
    iteration: 0,
    stages: { ...EMPTY_STAGES, analyze_plan: 'running' },
    stage_notes: {},
  }
})

const disabledReason = computed(() =>
  runStatus.value.active ? `目前已有 ${runStatus.value.label ?? ''} 執行中` : '',
)

function questionFor(target: { changeName: string; stage: string }) {
  if (!runStatus.value.active || !runStatus.value.question) return null
  if (runStatus.value.question.stage !== target.stage) return null
  return (runStatus.value.change_name || '') === target.changeName ? runStatus.value.question : null
}

function onOpenStage(payload: { changeName: string; stage: string }): void {
  selected.value = payload
}

async function onRerun(payload: { changeName: string; stage: string }): Promise<void> {
  await api.postRerun(payload.changeName, payload.stage)
  await load()
}

function onViewFiles(changeName: string): void {
  filesFor.value = changeName
}

async function onNewTask(task: string): Promise<void> {
  await api.postNewTask(task)
  showNewTaskDialog.value = false
  await load()
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="rows.length === 0 && !tempRow" class="empty-state flex flex-col items-start gap-2">
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        @click="showNewTaskDialog = true"
      >
        <font-awesome-icon icon="plus" class="mr-1" />新增任務
      </button>
      <p class="text-fg-muted">目前沒有執行中的任務</p>
    </div>

    <template v-else>
      <button
        type="button"
        class="new-task-button self-start rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors cursor-pointer hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="runStatus.active"
        :title="disabledReason"
        @click="showNewTaskDialog = true"
      >
        <font-awesome-icon icon="plus" class="mr-1" />新增任務
      </button>

      <ChangeRow
        v-if="tempRow"
        :row="tempRow"
        :run-status="runStatus"
        :temporary="true"
        @open-stage="onOpenStage"
        @rerun="onRerun"
      />
      <ChangeRow
        v-for="row in rows"
        :key="row.change_name"
        :row="row"
        :run-status="runStatus"
        @open-stage="onOpenStage"
        @rerun="onRerun"
        @view-files="onViewFiles"
      />
    </template>

    <div v-if="selected" class="stage-detail-panel rounded-xl border border-line bg-surface p-5 shadow-lg">
      <button
        type="button"
        class="mb-5 rounded-md p-1.5 text-danger transition-colors cursor-pointer hover:bg-danger/15"
        title="關閉"
        aria-label="關閉"
        @click="selected = null"
      >
        <font-awesome-icon icon="xmark" />
      </button>
      <StageDetail
        :change-name="selected.changeName"
        :stage="selected.stage"
        :question="questionFor(selected)"
      />
    </div>

    <FileBrowser v-if="filesFor" mode="change" :target="filesFor" @close="filesFor = ''" />
    <NewTaskDialog
      v-if="showNewTaskDialog"
      @submit="onNewTask"
      @close="showNewTaskDialog = false"
    />
  </div>
</template>
