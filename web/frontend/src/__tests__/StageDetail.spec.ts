import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import StageDetail from '../components/active-changes/StageDetail.vue'
import * as api from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getStageDetail: vi.fn(),
    postAnswer: vi.fn(),
    postAbort: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

const longPathReviewResult =
  '## Standards\n- `tests/unit/user/views/userManagement/userListContainer/UsersListContainer.spec.js`：新增 describe `分頁`\n\n## Spec\n無問題'

describe('StageDetail', () => {
  test.each([
    {
      stage: 'analyze_plan',
      fields: { analysis: '分析內容\n第二行', plan: ['1.1 撰寫測試', '1.2 實作功能'] },
    },
    {
      stage: 'human_confirm',
      fields: { status: '已通過', human_feedback: '修改意見\n第二行' },
    },
    {
      stage: 'execute',
      fields: { execution_result: '執行摘要\n第二行' },
    },
    {
      stage: 'review',
      fields: { review_level: '修補', review_result: longPathReviewResult },
    },
  ])('各階段結果欄位、執行計畫與執行日誌以使用者可讀輸出呈現：$stage', async ({ stage, fields }) => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'done',
      note: '',
      fields,
      log: 'log line1\nlog line2',
    })

    const wrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage, question: null },
    })
    await flushPromises()

    const pres = wrapper.findAll('pre')
    const logPre = wrapper.find('.log')
    expect(logPre.classes()).toContain('output-text')

    if (stage === 'analyze_plan') {
      expect(pres[0]!.classes()).toContain('output-text')
      const items = wrapper.findAll('li')
      expect(items).toHaveLength(2)
      expect(items.map((item) => item.text())).toEqual(['1.1 撰寫測試', '1.2 實作功能'])
      for (const item of items) {
        expect(item.classes()).toContain('output-text')
      }
      const list = wrapper.find('ul, ol')
      expect(list.element.tagName).not.toBe('OL')
      expect(list.classes()).not.toContain('list-decimal')
    } else if (stage === 'human_confirm') {
      const statusEl = wrapper.findAll('p').find((p) => p.text() === '已通過')!
      expect(statusEl.classes()).toContain('output-text')
      expect(pres[0]!.classes()).toContain('output-text')
    } else if (stage === 'execute') {
      expect(pres[0]!.classes()).toContain('output-text')
    } else if (stage === 'review') {
      const levelEl = wrapper.findAll('p').find((p) => p.text() === '修補')!
      expect(levelEl.classes()).toContain('output-text')
      expect(pres[0]!.classes()).toContain('output-text')
      expect(pres[0]!.element.textContent).toBe(longPathReviewResult)
    }
  })


  test('點擊卡片後顯示該階段的執行結果與執行日誌', async () => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'done',
      note: '',
      fields: { review_result: '## Standards\n無問題', review_level: '修補' },
      log: 'line1\nline2',
    })

    const wrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage: 'review', question: null },
    })
    await flushPromises()

    expect(mockedApi.getStageDetail).toHaveBeenCalledWith('feat-login', 'review')
    expect(wrapper.text()).toContain('修補')
    expect(wrapper.text()).toContain('## Standards')
    expect(wrapper.find('.log').text()).toContain('line1')
    expect(wrapper.find('.log').text()).toContain('line2')
  })

  test('被使用者中止的階段在詳情顯示使用者中止', async () => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'error',
      note: '使用者中止',
      fields: { execution_result: '' },
      log: '',
    })

    const wrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage: 'execute', question: null },
    })
    await flushPromises()

    expect(wrapper.find('.aborted-note').text()).toBe('使用者中止')
    expect(wrapper.text()).toContain('（尚無資料）')
  })

  test('必填文字題送出空白時不送出並提示必填', async () => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'running', note: '', fields: {}, log: '',
    })
    const question = {
      id: 'q1', stage: 'analyze_plan', kind: 'text' as const,
      prompt: '請輸入本次任務要使用的 git 分支名稱', options: [], required: true, multiline: false,
    }

    const wrapper = mount(StageDetail, {
      props: { changeName: '', stage: 'analyze_plan', question },
    })
    await flushPromises()

    const submitButton = wrapper
      .findAll('.question-form button')
      .find((b) => b.text() === '送出')!
    await submitButton.trigger('click')

    expect(mockedApi.postAnswer).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('此欄位為必填')
  })

  test('待回覆提問的提示文字照原文換行顯示且選項可在區塊內折行', async () => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'running', note: '', fields: {}, log: '',
    })
    const choicePrompt = 'QUESTION: 這次要做到哪個程度？\n1. 純文字排版（建議）\n2. 轉譯 Markdown'
    const choiceQuestion = {
      id: 'q1', stage: 'analyze_plan', kind: 'choice' as const,
      prompt: choicePrompt,
      options: ['1. 純文字排版（建議）', '2. 轉譯 Markdown'],
      required: false, multiline: false,
    }

    const choiceWrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage: 'analyze_plan', question: choiceQuestion },
    })
    await flushPromises()

    const choicePromptEl = choiceWrapper.find('.question-prompt')
    expect(choicePromptEl.element.textContent).toBe(choicePrompt)
    expect(choicePromptEl.classes()).toContain('output-text')
    const optionButtons = choiceWrapper
      .findAll('.question-form button')
      .filter((b) => choiceQuestion.options.includes(b.text()))
    expect(optionButtons).toHaveLength(2)
    for (const button of optionButtons) {
      expect(button.classes()).toContain('output-text')
    }

    const confirmPrompt = '## 執行計畫（共 3 個 TASK）\n\n1.1 a\n1.2 b\n2.1 c\n\n繼續執行？'
    const confirmQuestion = {
      id: 'q2', stage: 'human_confirm', kind: 'confirm' as const,
      prompt: confirmPrompt, options: [], required: false, multiline: false,
    }

    const confirmWrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage: 'human_confirm', question: confirmQuestion },
    })
    await flushPromises()

    const confirmPromptEl = confirmWrapper.find('.question-prompt')
    expect(confirmPromptEl.element.textContent).toBe(confirmPrompt)
    expect(confirmPromptEl.classes()).toContain('output-text')
  })

  test('提問已被回覆後再送出回覆時顯示提問已結束', async () => {
    mockedApi.getStageDetail.mockResolvedValue({
      status: 'running', note: '', fields: {}, log: '',
    })
    mockedApi.postAnswer.mockRejectedValue(new api.ApiError(410, '此提問已結束，請重新整理'))
    const question = {
      id: 'q1', stage: 'human_confirm', kind: 'confirm' as const,
      prompt: '繼續執行？', options: [], required: false, multiline: false,
    }

    const wrapper = mount(StageDetail, {
      props: { changeName: 'feat-login', stage: 'human_confirm', question },
    })
    await flushPromises()

    const yesButton = wrapper.findAll('.question-form button').find((b) => b.text() === '是')!
    await yesButton.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('此提問已結束，請重新整理')
  })
})
