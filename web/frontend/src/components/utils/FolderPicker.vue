<script setup lang="ts">
import { ref, computed } from 'vue'
import * as api from '../../api'

const emit = defineEmits<{ picked: [path: string]; close: [] }>()

const currentPath = ref('')
const entries = ref<string[]>([])

async function load(): Promise<void> {
  entries.value = await api.getFs(currentPath.value)
}
void load()

function enter(name: string): void {
  currentPath.value = currentPath.value ? `${currentPath.value}/${name}` : name
  void load()
}

function up(): void {
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  currentPath.value = parts.join('/')
  void load()
}

const canGoUp = computed(() => currentPath.value !== '')

function confirmPick(): void {
  emit('picked', currentPath.value)
}
</script>

<template>
  <div class="modal folder-picker fixed inset-0 z-10 flex items-center justify-center bg-overlay backdrop-blur-sm">
    <div class="flex w-96 flex-col gap-3 rounded-xl border border-line bg-surface p-5 shadow-2xl">
      <p class="text-sm text-fg-muted">目前路徑：{{ currentPath || '（根目錄）' }}</p>
      <button
        type="button"
        class="btn-secondary self-start px-2 py-1 text-sm"
        :disabled="!canGoUp"
        title="上一層"
        aria-label="上一層"
        @click="up"
      >
        <font-awesome-icon icon="arrow-up" />
      </button>
      <ul class="flex flex-col gap-1">
        <li v-for="name in entries" :key="name">
          <button
            type="button"
            class="w-full rounded-md px-2 py-1 text-left text-sm text-fg transition-colors cursor-pointer hover:bg-surface-muted"
            @click="enter(name)"
          >
            <font-awesome-icon icon="folder" class="mr-1 text-fg-muted" />{{ name }}
          </button>
        </li>
      </ul>
      <div class="flex gap-2">
        <button
          type="button"
          class="confirm-button rounded-md bg-primary px-3 py-2 text-on-accent shadow-sm transition-colors cursor-pointer hover:bg-primary-hover"
          @click="confirmPick"
        >
          <font-awesome-icon icon="check" class="mr-1" />確定
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
