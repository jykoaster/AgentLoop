import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from '../components/settings/SettingsPanel.vue'
import * as api from '../api'
import type { SettingsView } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getSettings: vi.fn(),
    putSettings: vi.fn(),
  }
})

const mockedApi = vi.mocked(api)

function baseSettings(overrides: Partial<SettingsView> = {}): SettingsView {
  return {
    target_project: 'my-project',
    oauth_token: { set: true, last4: '9xYz' },
    api_key: { set: false, last4: '' },
    workspace_root: '/workspace',
    run_active: false,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SettingsPanel', () => {
  test('設定分頁顯示目前設定並可儲存', async () => {
    mockedApi.getSettings.mockResolvedValue(baseSettings())
    mockedApi.putSettings.mockResolvedValue(
      baseSettings({ api_key: { set: true, last4: 'abcd' } }),
    )

    const wrapper = mount(SettingsPanel)
    await flushPromises()

    const labels = wrapper.findAll('.field label')
    expect(labels.map((l) => l.text())).toEqual([
      '目標專案', 'Claude OAuth token', 'Anthropic API key',
    ])

    expect(wrapper.text()).toContain('my-project')
    expect(wrapper.text()).toContain('已設定（末四碼 9xYz）')
    expect(wrapper.text()).toContain('未設定')

    await wrapper.find('.api-key input').setValue('sk-ant-api03-…abcd')
    await wrapper.find('.save-button').trigger('click')
    await flushPromises()

    expect(mockedApi.putSettings).toHaveBeenCalledWith(
      expect.objectContaining({ api_key: 'sk-ant-api03-…abcd' }),
    )
    expect(wrapper.text()).toContain('已儲存')
    expect(wrapper.text()).toContain('已設定（末四碼 abcd）')
  })

  test('有執行進行中時無法變更目標專案', async () => {
    mockedApi.getSettings.mockResolvedValue(baseSettings({ run_active: true }))

    const wrapper = mount(SettingsPanel)
    await flushPromises()

    const pickButton = wrapper.find('.target-project button')
    expect((pickButton.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('執行進行中，無法變更目標專案')

    const oauthInput = wrapper.find('.oauth-token input')
    const apiKeyInput = wrapper.find('.api-key input')
    expect((oauthInput.element as HTMLInputElement).disabled).toBe(false)
    expect((apiKeyInput.element as HTMLInputElement).disabled).toBe(false)
  })
})
