<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Question } from '../../api'

const props = defineProps<{
  question: Question
  externalError?: string
}>()

const emit = defineEmits<{ submit: [answer: string] }>()

const requiredError = ref('')
const customText = ref('')
const textValue = ref('')
const selectedOptions = ref<Set<string>>(new Set())

watch(
  () => props.question.id,
  () => {
    requiredError.value = ''
    customText.value = ''
    textValue.value = ''
    selectedOptions.value = new Set()
  },
)

function parseOptionAnswer(option: string): string {
  const match = option.match(/^(\d+)\.\s*/)
  return match ? match[1] : option
}

const allSelected = computed(
  () => props.question.options.length > 0
    && props.question.options.every((opt) => selectedOptions.value.has(opt)),
)

function toggleOption(option: string): void {
  const next = new Set(selectedOptions.value)
  if (next.has(option)) next.delete(option)
  else next.add(option)
  selectedOptions.value = next
}

function toggleSelectAll(): void {
  selectedOptions.value = allSelected.value
    ? new Set()
    : new Set(props.question.options)
}

function submitMultiChoice(): void {
  const numbers = Array.from(selectedOptions.value)
    .map((opt) => Number(parseOptionAnswer(opt)))
    .sort((a, b) => a - b)
  emit('submit', numbers.join(','))
}

function submitOption(option: string): void {
  emit('submit', parseOptionAnswer(option))
}

function submitCustom(): void {
  emit('submit', customText.value.trim())
}

function submitConfirm(value: 'y' | 'n'): void {
  emit('submit', value)
}

function submitText(): void {
  const value = textValue.value.trim()
  if (props.question.required && !value) {
    requiredError.value = '此欄位為必填'
    return
  }
  requiredError.value = ''
  emit('submit', value)
}

function submitPause(value: '' | 'q'): void {
  emit('submit', value)
}
</script>

<template>
  <div class="question-form flex min-w-0 max-w-full flex-col items-start gap-2 rounded-xl border border-line bg-surface p-4 shadow-lg">
    <p class="question-prompt output-text font-medium text-fg">{{ question.prompt }}</p>

    <template v-if="question.kind === 'choice'">
      <button
        v-for="opt in question.options"
        :key="opt"
        type="button"
        class="btn-secondary output-text max-w-full text-left text-sm px-3 py-1.5"
        @click="submitOption(opt)"
      >
        {{ opt }}
      </button>
      <div class="flex gap-2">
        <input
          v-model="customText"
          type="text"
          placeholder="自訂答案"
          class="rounded-md border border-line bg-bg px-2 py-1 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
        <button
          type="button"
          class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-on-accent shadow-sm transition-colors hover:bg-primary-hover"
          @click="submitCustom"
        >
          <font-awesome-icon icon="paper-plane" class="mr-1" />送出
        </button>
      </div>
    </template>

    <template v-else-if="question.kind === 'multi_choice'">
      <label
        v-for="opt in question.options"
        :key="opt"
        class="output-text flex max-w-full items-start gap-2 text-sm text-fg"
      >
        <input
          type="checkbox"
          class="suggestion-checkbox mt-1"
          :checked="selectedOptions.has(opt)"
          @change="toggleOption(opt)"
        />
        <span>{{ opt }}</span>
      </label>
      <label class="flex items-center gap-2 text-sm font-medium text-fg">
        <input
          type="checkbox"
          class="select-all-checkbox"
          :checked="allSelected"
          @change="toggleSelectAll"
        />
        全選
      </label>
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-on-accent shadow-sm transition-colors hover:bg-primary-hover"
        @click="submitMultiChoice"
      >
        <font-awesome-icon icon="paper-plane" class="mr-1" />送出
      </button>
    </template>

    <template v-else-if="question.kind === 'confirm'">
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-on-accent shadow-sm transition-colors hover:bg-primary-hover"
        @click="submitConfirm('y')"
      >
        <font-awesome-icon icon="check" class="mr-1" />是
      </button>
      <button
        type="button"
        class="btn-secondary px-3 py-1.5"
        @click="submitConfirm('n')"
      >
        <font-awesome-icon icon="xmark" class="mr-1" />否
      </button>
    </template>

    <template v-else-if="question.kind === 'text'">
      <textarea
        v-if="question.multiline"
        v-model="textValue"
        class="w-full rounded-md border border-line bg-bg p-2 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      ></textarea>
      <input
        v-else
        v-model="textValue"
        type="text"
        class="rounded-md border border-line bg-bg px-2 py-1 text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      />
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-on-accent shadow-sm transition-colors hover:bg-primary-hover"
        @click="submitText"
      >
        <font-awesome-icon icon="paper-plane" class="mr-1" />送出
      </button>
      <p v-if="requiredError" class="error text-danger">{{ requiredError }}</p>
    </template>

    <template v-else-if="question.kind === 'pause'">
      <button
        type="button"
        class="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-on-accent shadow-sm transition-colors hover:bg-primary-hover"
        @click="submitPause('')"
      >
        <font-awesome-icon icon="play" class="mr-1" />繼續
      </button>
      <button
        type="button"
        class="btn-secondary px-3 py-1.5"
        @click="submitPause('q')"
      >
        <font-awesome-icon icon="stop" class="mr-1" />中止
      </button>
    </template>

    <p v-if="externalError" class="error text-danger">{{ externalError }}</p>
  </div>
</template>
