import type { RouteRecordRaw } from 'vue-router'

/** Inventory pages. Mounted under the main layout; each checks the user's permissions. */
export const inventoryRoutes: RouteRecordRaw[] = [
  {
    path: 'inventory',
    name: 'inventory-projects',
    component: () => import('./views/ProjectsView.vue'),
    meta: { title: 'Project inventory', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/projects/:id(\\d+)',
    name: 'inventory-project',
    component: () => import('./views/ProjectInventoryView.vue'),
    meta: { title: 'Project inventory', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/items',
    name: 'inventory-items',
    component: () => import('./views/ItemsView.vue'),
    meta: { title: 'All items', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/warranty',
    name: 'inventory-warranty',
    component: () => import('./views/ItemsView.vue'),
    props: { warranty: true },
    meta: { title: 'Warranty', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/items/:id(\\d+)',
    name: 'inventory-item',
    component: () => import('./views/ItemDetailView.vue'),
    meta: { title: 'Item', allow: (a) => a.can('inventory.view') },
  },
  {
    path: 'inventory/deliveries/new',
    name: 'inventory-delivery-new',
    component: () => import('./views/RegisterDeliveryView.vue'),
    meta: { title: 'Register delivery', focus: true, allow: (a) => a.can('inventory.register') },
  },
  {
    path: 'inventory/scan',
    name: 'inventory-scan',
    component: () => import('./views/ScanView.vue'),
    meta: { title: 'Scan', focus: true, allow: (a) => a.can('inventory.view') },
  },
]
