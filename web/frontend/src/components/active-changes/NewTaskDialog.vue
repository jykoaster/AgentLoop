<script setup lang="ts">
import { ref, computed } from 'vue'

const emit = defineEmits<{ submit: [task: string]; close: [] }>()

const task = ref('')
const canSubmit = computed(() => task.value.trim().length > 0)

function submit(): void {
  if (!canSubmit.value) return
  emit('submit', task.value.trim())
}
</script>

<template>
  <div class="modal new-task-dialog fixed inset-0 z-10 flex items-center justify-center bg-overlay backdrop-blur-sm">
    <div class="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5 shadow-2xl max-w-md w-full">
      <h3 class="font-semibold text-xl mb-3">新增任務</h3>
      <textarea
        v-model="task"
        placeholder="任務描述"
        rows="5"
        class="w-full rounded-md border border-line bg-bg p-2 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      ></textarea>
      <div class="flex gap-2 justify-end">
        <button
          type="button"
          class="cursor-pointer rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!canSubmit"
          @click="submit"
        >
          <font-awesome-icon icon="paper-plane" class="mr-1" />送出
        </button>
        <button
          type="button"
          class="btn-secondary px-3 py-2"
          @click="emit('close')"
        >
          <font-awesome-icon icon="xmark" class="mr-1" />取消
        </button>
      </div>
    </div>
  </div>
</template>
