import { route } from 'quasar/wrappers'
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory
} from 'vue-router'

import { Notify } from 'quasar'
import { useUserStore } from 'src/features/auth/userStore'
import routes from './routes'
import { installAuthGuard } from './authGuard'
import { keepScrollOfKeptPages } from './keptPages'

/*
 * If not building with SSR mode, you can
 * directly export the Router instantiation;
 *
 * The function below can be async too; either use
 * async/await or return a Promise which resolves
 * with the Router instance.
 */

export default route(function ({ store }) {
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : (process.env.VUE_ROUTER_MODE === 'history' ? createWebHistory : createWebHashHistory)

  let scrollBehavior: ReturnType<typeof keepScrollOfKeptPages> = () => ({ left: 0, top: 0 })
  const Router = createRouter({
    scrollBehavior: (...args) => scrollBehavior(...args),
    routes,

    // Leave this as is and make changes in quasar.conf.js instead!
    // quasar.conf.js -> build -> vueRouterMode
    // quasar.conf.js -> build -> publicPath
    history: createHistory(process.env.VUE_ROUTER_BASE)
  })

  scrollBehavior = keepScrollOfKeptPages(Router)

  installAuthGuard(Router, useUserStore(store), () => {
    Notify.create({ type: 'warning', position: 'top', message: 'Log in to open your collections.' })
  })

  return Router
})
