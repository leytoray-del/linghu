# Inventory Module: Design (revision 4, as built)

| Item | Value |
|---|---|
| System | PSBU OpsHub (see `platform-architecture.md`) |
| Module | Inventory: equipment of any kind, registered on arrival, withdrawn to new locations with approval |
| Status | Built and in use. This revision replaces the earlier proposals, which had more than the requirement asks for. |
| Date | 13 Nov 2026 |

Revision 4 keeps only what the requirement asks for. Deliveries, delivery numbers, suppliers, project history views, and the fault, repair and write-off actions were removed.

## 1. Data flow

```
Device arrives ──► Register device (In stock, at a store)
                        │
                        ▼
       Request withdrawal: items of one project + the new location + a reason
                        │
           PM of the project approves   (skipped when the requester is that PM)
                        │
           An operations manager approves
                        │
                        ▼
       Items move to the new location (Deployed); the deployment date is filled in
                        │
                        ▼  (when needed)
               Return to stock, at a store
```

| Item status | Meaning | How it gets there |
|---|---|---|
| In stock | Registered, at a store | Registered on arrival, or returned to stock |
| Requested | In a withdrawal request waiting for approval; cannot be requested again | The request is submitted |
| Deployed | At the new location | Final approval of the withdrawal |

If a request is rejected or withdrawn, its items go back to In stock. Rejecting sends the request back to the requester, who can revise and resubmit it, or withdraw it.

## 2. Pages

| Page | Purpose |
|---|---|
| Inventory | All items. Status counts, a quick "warranty ends within 60 days" filter, filters by project, kind of equipment and location, search, Scan, Export to Excel. Tick in-stock items of one project to request a withdrawal. Cards on phones. |
| Item | Details (including the kind's own fields) and history. Buttons by permission: Request withdrawal (in stock), Return to stock (deployed), Edit, Delete. |
| Register device | Project, then store, received date and warranty (one year from the received date by default), then the model, then scan. Saved together. |
| Request withdrawal | One project, its in-stock items (scan or choose), the new location (from the list, or a new site added on the spot), a reason. |
| Withdrawals | My requests, waiting for me, all I can see. Each request shows its items, the approval steps, history, and the actions allowed to the viewer. |
| Approvals | The shared inbox shows withdrawals waiting for the person next to resource requests. |
| Scan | Opens the camera and goes to the scanned item. |

Menu: Inventory section with Inventory and Withdrawals. + New offers Register device and Request withdrawal.

## 3. Permissions

| Permission | Allows | Default roles |
|---|---|---|
| `inventory.view` | Inventory, item details and history, export, withdrawals one may see | Everyone |
| `inventory.register` | Register devices; add a model while registering | Engineer, Inventory editor, Administrator |
| `inventory.edit` | Change a saved item's details | Inventory editor, Administrator |
| `inventory.delete` | Delete an item (hidden from lists; record and history kept) | Administrator |
| `inventory.return` | Return a deployed item to a store | Engineer, Inventory editor, Administrator |
| `inventory.withdraw` | Request withdrawals; add a new site while doing so | Engineer, Inventory editor, Administrator |
| `inventory.withdrawals.all` | See every withdrawal request | Operations manager, Director, Viewer, Administrator |
| `inventory.admin` | Kinds of equipment and their fields, models | Administrator |

Approving is decided by assignment: the PM named on the project gives the first approval, and anyone with the Operations manager role gives the final approval. Nobody approves their own request. The configurable Roles and permissions screen is described in `permissions-design.html`.

## 4. Data

- `inv_items`: serial number (unique), kind, model, project, location, status, warranty start and end, the kind's own fields (JSON), remarks, deletion date, who deleted it and why.
- `inv_movements`: the history of each item (registered, details changed, requested, back in stock, deployed, returned, deleted), linked to the withdrawal request where there is one. Only ever added to.
- `inv_withdrawals`, `inv_withdrawal_items`, `inv_withdrawal_tasks`, `inv_withdrawal_events`: requests, their items, the PM and OM approval steps of each round, and what happened.
- `inv_categories`, `inv_models`: kinds of equipment with their fields, and models with optional serial number formats.
- Projects (with their PM) and locations are shared platform records.

Migration 0004 added the withdrawal tables and the deletion columns in place, and moved items in states that are no longer used back to In stock.

## 5. Emails

The approver of each step is emailed with a link to the request; the requester is emailed when the request is rejected or approved, and the project's PM is copied on approval.
