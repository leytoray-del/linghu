import type { RouteRecordRaw } from 'vue-router'

/** Inventory pages. Mounted under the main layout; each checks the user's permissions. */
export const inventoryRoutes: RouteRecordRaw[] = [
  {
    path: 'inventory',
    name: 'inventory',
    component: () => import('./views/InventoryView.vue'),
    meta: { title: 'Inventory', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/items/:id(\\d+)',
    name: 'inventory-item',
    component: () => import('./views/ItemDetailView.vue'),
    meta: { title: 'Item', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/register',
    name: 'inventory-register',
    component: () => import('./views/RegisterDeliveryView.vue'),
    meta: { title: 'Register device', focus: true, allow: (a) => a.can('inventory.register') },
  },
  {
    path: 'inventory/scan',
    name: 'inventory-scan',
    component: () => import('./views/ScanView.vue'),
    meta: { title: 'Scan', focus: true, allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/withdrawals',
    name: 'inventory-withdrawals',
    component: () => import('./views/WithdrawalsView.vue'),
    meta: { title: 'Withdrawals', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/withdrawals/new',
    name: 'inventory-withdrawal-new',
    component: () => import('./views/WithdrawalFormView.vue'),
    meta: { title: 'Request withdrawal', focus: true, allow: (a) => a.can('inventory.withdraw') },
  },
  {
    path: 'inventory/withdrawals/:id(\\d+)',
    name: 'inventory-withdrawal',
    component: () => import('./views/WithdrawalDetailView.vue'),
    meta: { title: 'Withdrawal', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/withdrawals/:id(\\d+)/edit',
    name: 'inventory-withdrawal-edit',
    component: () => import('./views/WithdrawalFormView.vue'),
    meta: { title: 'Revise withdrawal', focus: true, allow: (a) => a.can('inventory.withdraw') },
  },
  // Addresses of earlier versions keep working.
  { path: 'inventory/deliveries/new', redirect: '/inventory/register' },
  { path: 'inventory/items', redirect: '/inventory' },
  { path: 'inventory/warranty', redirect: { path: '/inventory', query: { warranty: '1' } } },
  { path: 'inventory/projects/:id(\\d+)', redirect: (to) => ({ path: '/inventory', query: { project: String(to.params.id) } }) },
]
