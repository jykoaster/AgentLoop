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

describe('StageDetail', () => {
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
