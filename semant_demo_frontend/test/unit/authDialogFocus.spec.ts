import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { Platform, Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'

import LoginDialog from 'src/features/auth/LoginDialog.vue'
import RegisterDialog from 'src/features/auth/RegisterDialog.vue'

// The login and registration dialogs open with the cursor in their first field, so that
// Log In, typing and Enter is enough (#708). Touch devices are left alone: focusing there
// would pop up the on-screen keyboard over the dialog.

const mounted: VueWrapper[] = []
const desktop = Platform.is.desktop
afterEach(() => {
  mounted.splice(0).forEach(w => w.unmount())
  document.body.innerHTML = ''
  Platform.is.desktop = desktop
})

async function open (component: unknown) {
  setActivePinia(createPinia())
  const wrapper = mount(component as never, {
    props: { modelValue: true } as never,
    global: { plugins: [Quasar] },
    attachTo: document.body
  })
  mounted.push(wrapper)
  await flushPromises()
  // The dialog focuses after its enter transition.
  await new Promise(resolve => setTimeout(resolve, 400))
  return wrapper
}

const focusedLabel = () => document.activeElement?.closest('.q-field')?.querySelector('.q-field__label')?.textContent

describe('auth dialogs focus their first field', () => {
  it.each([
    ['login', 'Email or Username', LoginDialog],
    ['registration', 'Username', RegisterDialog]
  ])('%s dialog focuses %s on desktop', async (_name, label, component) => {
    Platform.is.desktop = true
    await open(component)
    expect(document.activeElement?.tagName).toBe('INPUT')
    expect(focusedLabel()).toBe(label)
  })

  it.each([
    ['login', LoginDialog],
    ['registration', RegisterDialog]
  ])('%s dialog leaves the fields unfocused on touch devices', async (_name, component) => {
    Platform.is.desktop = false
    await open(component)
    expect(document.activeElement?.tagName).not.toBe('INPUT')
  })
})
