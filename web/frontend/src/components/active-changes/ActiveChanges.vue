<script setup lang="ts">
import { computed, ref } from 'vue'
import * as api from '../../api'
import type { ChangeRow as ChangeRowType, RunInfo } from '../../api'
import { usePolling } from '../../composables/usePolling'
import ChangeRow from './ChangeRow.vue'
import FileBrowser from '../utils/FileBrowser.vue'
import NewTaskDialog from './NewTaskDialog.vue'

const EMPTY_STAGES = {
  analyze_plan: 'pending',
  human_confirm: 'pending',
  execute: 'pending',
  review: 'pending',
  archive: 'pending',
} as const

const rows = ref<ChangeRowType[]>([])
const runs = ref<RunInfo[]>([])
const filesFor = ref('')
const showNewTaskDialog = ref(false)

async function load(): Promise<void> {
  const [changes, activeRuns] = await Promise.all([api.getChanges(), api.getRuns()])
  rows.value = changes
  runs.value = activeRuns
}

usePolling(load)

function runFor(changeName: string): RunInfo | null {
  return runs.value.find((r) => r.change_name === changeName) ?? null
}

// 每個沒有 change_name 的執行（分支名稱尚未決定）各顯示一列暫時列，以 run_id 為 key。
const tempRows = computed<{ run: RunInfo; row: ChangeRowType }[]>(() =>
  runs.value
    .filter((run) => !run.change_name)
    .map((run) => ({
      run,
      row: {
        change_name: '',
        branch_name: '',
        task: run.task,
        iteration: 0,
        stages: { ...EMPTY_STAGES, analyze_plan: 'running' },
        stage_notes: {},
      },
    })),
)

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
    <div v-if="rows.length === 0 && tempRows.length === 0" class="empty-state flex flex-col items-start gap-2">
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
        @click="showNewTaskDialog = true"
      >
        <font-awesome-icon icon="plus" class="mr-1" />新增任務
      </button>

      <ChangeRow
        v-for="item in tempRows"
        :key="item.run.run_id"
        :row="item.row"
        :run="item.run"
        :temporary="true"
        @rerun="onRerun"
      />
      <ChangeRow
        v-for="row in rows"
        :key="row.change_name"
        :row="row"
        :run="runFor(row.change_name)"
        @rerun="onRerun"
        @view-files="onViewFiles"
      />
    </template>

    <FileBrowser v-if="filesFor" mode="change" :target="filesFor" @close="filesFor = ''" />
    <NewTaskDialog
      v-if="showNewTaskDialog"
      @submit="onNewTask"
      @close="showNewTaskDialog = false"
    />
  </div>
</template>
