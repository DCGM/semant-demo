import { Notify } from 'quasar'

function actionNotification (message: string) {
  return Notify.create({
    message,
    type: 'info',
    spinner: true,
    position: 'bottom-right',
    timeout: 60000
  })
}

function successNotification (message: string) {
  return Notify.create({
    message,
    type: 'positive',
    position: 'bottom-right',
    timeout: 4000
  })
}

function warningNotification (message: string) {
  return Notify.create({
    message,
    type: 'warning',
    position: 'bottom-right',
    timeout: 3000
  })
}

function errorNotification (message: string) {
  return Notify.create({
    message,
    type: 'negative',
    position: 'bottom-right',
    timeout: 6000
  })
}

function ongoingNotification (message: string) {
  const notif = Notify.create({
    message,
    type: 'ongoing',
    spinner: true,
    position: 'bottom-right',
    timeout: 0
  })
  return {
    success (message: string, timeout = 4000) {
      notif({ type: 'positive', message, timeout, spinner: false })
    },
    error (message: string, timeout = 6000) {
      notif({ type: 'negative', message, timeout, spinner: false })
    },
    dismiss () {
      notif()
    }
  }
}

export { actionNotification, successNotification, warningNotification, errorNotification, ongoingNotification }
