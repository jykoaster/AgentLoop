<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import * as api from '../../api'
import type { Question, StageDetail as StageDetailType } from '../../api'
import { usePolling } from '../../composables/usePolling'
import QuestionForm from './QuestionForm.vue'

const props = defineProps<{
  changeName: string
  stage: string
  question: Question | null
  temporary?: boolean
  stageStatus?: string
}>()

const detail = ref<StageDetailType | null>(null)
const answerError = ref('')

async function load(): Promise<void> {
  if (props.temporary) return
  try {
    detail.value = await api.getStageDetail(props.changeName, props.stage)
  } catch {
    detail.value = null
  }
}

usePolling(load)
watch(() => [props.changeName, props.stage], load)

const isRunning = computed(() =>
  props.temporary ? props.stageStatus === 'running' : detail.value?.status === 'running',
)
const isAborted = computed(() => !props.temporary && detail.value?.note === '使用者中止')

function field(key: string): string {
  const value = detail.value?.fields?.[key]
  if (value === undefined || value === null || value === '') return '（尚無資料）'
  return String(value)
}

const plan = computed<string[]>(() => {
  const value = detail.value?.fields?.plan
  return Array.isArray(value) ? (value as string[]) : []
})

async function onSubmitAnswer(answer: string): Promise<void> {
  if (!props.question) return
  answerError.value = ''
  try {
    await api.postAnswer(props.question.id, answer)
    await load()
  } catch (e) {
    if (e instanceof api.ApiError && e.status === 410) {
      answerError.value = '此提問已結束，請重新整理'
    } else if (e instanceof api.ApiError && e.status === 422) {
      answerError.value = '此欄位為必填'
    } else {
      answerError.value = e instanceof Error ? e.message : String(e)
    }
  }
}

async function onAbort(): Promise<void> {
  if (!window.confirm('確定要中止這個階段嗎？')) return
  await api.postAbort()
  await load()
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-3">
    <p v-if="isAborted" class="aborted-note font-semibold text-danger">使用者中止</p>

    <QuestionForm
      v-if="question"
      :question="question"
      :external-error="answerError"
      @submit="onSubmitAnswer"
    />

    <template v-if="stage === 'analyze_plan'">
      <h4 class="font-semibold text-fg">分析摘要</h4>
      <pre class="output-text rounded-md bg-surface-muted p-3 font-mono text-sm">{{ field('analysis') }}</pre>
      <h4 class="font-semibold text-fg">執行計畫</h4>
      <ul v-if="plan.length" class="list-none pl-5">
        <li v-for="(t, i) in plan" :key="i" class="output-text">{{ t }}</li>
      </ul>
      <p v-else class="text-fg-muted">（尚無資料）</p>
    </template>

    <template v-else-if="stage === 'human_confirm'">
      <h4 class="font-semibold text-fg">確認結果</h4>
      <p class="output-text">{{ field('status') }}</p>
      <h4 class="font-semibold text-fg">修改意見</h4>
      <pre class="output-text rounded-md bg-surface-muted p-3 font-mono text-sm">{{ field('human_feedback') }}</pre>
    </template>

    <template v-else-if="stage === 'execute'">
      <h4 class="font-semibold text-fg">執行摘要</h4>
      <pre class="output-text rounded-md bg-surface-muted p-3 font-mono text-sm">{{ field('execution_result') }}</pre>
    </template>

    <template v-else-if="stage === 'review'">
      <h4 class="font-semibold text-fg">審查等級</h4>
      <p class="output-text">{{ field('review_level') }}</p>
      <h4 class="font-semibold text-fg">審查報告</h4>
      <pre class="output-text rounded-md bg-surface-muted p-3 font-mono text-sm">{{ field('review_result') }}</pre>
    </template>

    <h4 class="font-semibold text-fg">執行日誌</h4>
    <pre class="log output-text max-h-96 overflow-auto rounded-md bg-surface-muted p-3 font-mono text-sm">{{ detail?.log ?? '' }}</pre>

    <button
      v-if="isRunning"
      type="button"
      class="self-start rounded-md bg-danger px-3 py-2 text-on-accent shadow-sm transition-colors cursor-pointer hover:brightness-110"
      @click="onAbort"
    >
      <font-awesome-icon icon="stop" class="mr-1" />中止
    </button>
  </div>
</template>
