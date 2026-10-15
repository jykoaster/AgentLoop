<script setup lang="ts">
import { ref, watch } from 'vue'
import * as api from '../../api'

const props = defineProps<{
  mode: 'change' | 'archive'
  target: string
}>()

const emit = defineEmits<{ close: [] }>()

const files = ref<string[]>([])
const selected = ref('')
const content = ref('')

async function loadFiles(): Promise<void> {
  files.value = props.mode === 'change'
    ? await api.getChangeFiles(props.target)
    : await api.getArchiveFiles(props.target)
  selected.value = ''
  content.value = ''
}

async function openFile(path: string): Promise<void> {
  selected.value = path
  const result = props.mode === 'change'
    ? await api.getChangeFile(props.target, path)
    : await api.getArchiveFile(props.target, path)
  content.value = result.content
}

watch(() => [props.mode, props.target], loadFiles, { immediate: true })
</script>

<template>
  <div class="modal file-browser fixed inset-0 z-10 flex items-center justify-center bg-overlay backdrop-blur-sm">
    <div class="flex max-h-[80vh] w-[80vw] flex-col gap-3 overflow-auto rounded-xl border border-line bg-surface p-5 shadow-2xl">
      <button
        type="button"
        class="self-end rounded-md p-1.5 text-danger transition-colors cursor-pointer hover:bg-danger/15"
        title="關閉"
        aria-label="關閉"
        @click="emit('close')"
      >
        <font-awesome-icon icon="xmark" />
      </button>
      <ul class="flex flex-col gap-1">
        <li v-for="f in files" :key="f">
          <button
            type="button"
            class="w-full rounded-md px-2 py-1 text-left text-sm text-fg transition-colors cursor-pointer hover:bg-surface-muted"
            @click="openFile(f)"
          >
            <font-awesome-icon icon="file-lines" class="mr-1 text-fg-muted" />{{ f }}
          </button>
        </li>
      </ul>
      <pre v-if="selected" class="file-content whitespace-pre-wrap rounded-md bg-surface-muted p-3 font-mono text-sm">{{ content }}</pre>
    </div>
  </div>
</template>
