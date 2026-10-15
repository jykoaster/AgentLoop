import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../App.vue'
import * as api from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getSettings: vi.fn(),
    putSettings: vi.fn(),
    getChanges: vi.fn(),
    getRun: vi.fn(),
    getArchive: vi.fn(),
    getSpecs: vi.fn(),
    getFs: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getSettings.mockResolvedValue({
    target_project: 'my-project',
    oauth_token: { set: false, last4: '' },
    api_key: { set: false, last4: '' },
    workspace_root: '/workspace',
    run_active: false,
  })
  mockedApi.getChanges.mockResolvedValue([])
  mockedApi.getRun.mockResolvedValue({ active: false })
  mockedApi.getArchive.mockResolvedValue([])
  mockedApi.getSpecs.mockResolvedValue([])
})

describe('App 分頁', () => {
  test('開啟網頁後顯示四個主分頁且預設選中執行中任務', async () => {
    const wrapper = mount(App)
    await flushPromises()

    const tabs = wrapper.findAll('.tab-button')
    expect(tabs.map((t) => t.text())).toEqual(['執行中任務', '已封存任務', '既有 Spec', '設定'])
    expect(tabs[0].attributes('data-active')).toBe('true')

    await tabs[3].trigger('click')
    expect(wrapper.findAll('.tab-button')[3].attributes('data-active')).toBe('true')
    expect(wrapper.findAll('.tab-button')[0].attributes('data-active')).toBe('false')
    expect(wrapper.find('.settings-panel').exists()).toBe(true)
  })

  test('尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案', async () => {
    mockedApi.getSettings.mockResolvedValueOnce({
      target_project: '',
      oauth_token: { set: false, last4: '' },
      api_key: { set: false, last4: '' },
      workspace_root: '/workspace',
      run_active: false,
    })
    mockedApi.getFs.mockResolvedValue(['AgentLoop', 'my-project'])

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.find('.folder-picker').exists()).toBe(true)
    expect(wrapper.text()).toContain('請先在設定選擇目標專案')

    const entries = wrapper.findAll('.folder-picker li button')
    expect(entries.map((e) => e.text())).toEqual(['AgentLoop', 'my-project'])

    mockedApi.putSettings.mockResolvedValue({
      target_project: 'my-project',
      oauth_token: { set: false, last4: '' },
      api_key: { set: false, last4: '' },
      workspace_root: '/workspace',
      run_active: false,
    })
    mockedApi.getSettings.mockResolvedValue({
      target_project: 'my-project',
      oauth_token: { set: false, last4: '' },
      api_key: { set: false, last4: '' },
      workspace_root: '/workspace',
      run_active: false,
    })
    mockedApi.getChanges.mockResolvedValue([])
    mockedApi.getRun.mockResolvedValue({ active: false })

    await entries[1].trigger('click') // 進入 my-project（此處直接按確定即可，不需真的進入子資料夾）
    await wrapper.find('.folder-picker .confirm-button').trigger('click')
    await flushPromises()

    expect(mockedApi.putSettings).toHaveBeenCalledWith({ target_project: 'my-project' })
    expect(wrapper.find('.folder-picker').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('請先在設定選擇目標專案')
  })

  test('純圖示按鈕以滑鼠停留提示與無障礙名稱呈現原本文字', async () => {
    mockedApi.getSettings.mockResolvedValueOnce({
      target_project: '',
      oauth_token: { set: false, last4: '' },
      api_key: { set: false, last4: '' },
      workspace_root: '/workspace',
      run_active: false,
    })
    mockedApi.getFs.mockResolvedValue(['AgentLoop'])

    const wrapper = mount(App)
    await flushPromises()

    const upButton = wrapper.find('[aria-label="上一層"]')
    expect(upButton.exists()).toBe(true)
    expect(upButton.text()).toBe('')
    expect(upButton.attributes('title')).toBe('上一層')
    expect((upButton.element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.find('.folder-picker li button').trigger('click')
    await flushPromises()

    const upButtonAfterEnter = wrapper.find('[aria-label="上一層"]')
    expect((upButtonAfterEnter.element as HTMLButtonElement).disabled).toBe(false)
    expect(upButtonAfterEnter.text()).toBe('')
  })

  test('主要操作與階段狀態徽章在文字旁顯示對應圖示', async () => {
    const wrapper = mount(App)
    await flushPromises()

    const tabs = wrapper.findAll('.tab-button')
    expect(tabs.map((t) => t.find('svg[data-icon]').exists())).toEqual([true, true, true, true])
    expect(tabs.map((t) => t.text())).toEqual(['執行中任務', '已封存任務', '既有 Spec', '設定'])
  })
})
