<script setup lang="ts">
const props = defineProps<{
  stage: string
  status: string
  hasQuestion: boolean
  rerunnable: boolean
  disabledReason: string
}>()

const emit = defineEmits<{ click: []; rerun: [] }>()

const STATUS_LABEL: Record<string, string> = {
  pending: '尚未開始',
  running: '執行中',
  done: '完成',
  error: '錯誤',
}

const STATUS_CLASS: Record<string, { bar: string; badge: string }> = {
  pending: { bar: 'border-l-stage-pending', badge: 'bg-stage-pending' },
  running: { bar: 'border-l-stage-running', badge: 'bg-stage-running' },
  done: { bar: 'border-l-stage-done', badge: 'bg-stage-done' },
  error: { bar: 'border-l-stage-error', badge: 'bg-stage-error' },
}

const STATUS_ICON: Record<string, string> = {
  pending: 'clock',
  running: 'spinner',
  done: 'circle-check',
  error: 'circle-xmark',
}

function statusIcon(status: string): string {
  return STATUS_ICON[status] ?? STATUS_ICON.pending
}

function statusClass(status: string): { bar: string; badge: string } {
  return STATUS_CLASS[status] ?? STATUS_CLASS.pending
}

function onRerunClick(event: Event): void {
  event.stopPropagation()
  if (props.disabledReason) return
  if (window.confirm(`確定要重跑 ${props.stage} 嗎？`)) {
    emit('rerun')
  }
}
</script>

<template>
  <div
    class="stage-card relative flex cursor-pointer flex-col gap-1 rounded-lg border border-line border-l-4 bg-surface p-3 shadow transition-colors hover:border-primary"
    :class="[statusClass(status).bar, { 'animate-breathe motion-reduce:animate-none': status === 'running' }]"
    :data-status="status"
    @click="emit('click')"
  >
    <div class="flex items-center justify-between gap-2 mb-1">
      <div class=" font-semibold" :class="{ 'break-all': hasQuestion }">{{ stage }}</div>
      <span
        v-if="hasQuestion"
        class="question-mark text-2xl font-black leading-none text-warning"
        aria-label="等待回覆"
      >!</span>
    </div>
    <div
      class="stage-status flex w-fit items-center gap-1 rounded-full px-2 text-xs font-medium text-on-accent"
      :class="statusClass(status).badge"
    >
      <font-awesome-icon :icon="statusIcon(status)" :spin="status === 'running'" class="motion-reduce:animate-none" />
      {{ STATUS_LABEL[status] ?? status }}
    </div>
  
    <button
      v-if="rerunnable"
      type="button"
      class="rerun-button mt-3 self-start rounded-md p-1.5 text-warning transition-colors cursor-pointer hover:bg-warning/15 disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="!!disabledReason"
      :title="disabledReason || '重跑'"
      aria-label="重跑"
      @click="onRerunClick"
    >
      <font-awesome-icon icon="rotate-right" />
    </button>
  </div>
</template>
