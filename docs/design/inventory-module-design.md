# Inventory Module: System Design

| Item | Value |
|---|---|
| System | PSBU OpsHub (see `platform-architecture.md`) |
| Module | Inventory: project-based recording, tracking and withdrawal of equipment of any category |
| Status | Draft for review, revision 3. Nothing in this document has been built yet. |
| Date | 12 Nov 2026 |

This document specifies the Inventory module of PSBU OpsHub. The platform as a whole is described in `platform-architecture.md`. That covers the system name, the combined menu, shared records such as projects and locations, permissions and the approval engine. This document covers only what is specific to inventory.

**Changes in revision 3.** The module is no longer limited to FR readers:

- An inventory **item** can belong to any **category**, such as FR readers, cameras, gateways, servers or tablets. Each category has its own fields, which the administrator defines without any code change.
- Inventory is **maintained under projects**. Registration starts by choosing the project, and each project has its own inventory page. That page is the main place where the project's items are viewed and managed.

---

## 1. Background and goals

### 1.1 Background

Suppliers deliver equipment to NEC for each project, and support engineers deploy it to the project's sites. FR readers are the first and most common category, but projects also receive other equipment, such as cameras, gateways, servers and tablets. Today nobody records this equipment in one shared place. As a result, it is hard to say what a project has received, where each item is now, or which warranties are about to end.

### 1.2 Goals

1. **Record every item under its project, at delivery.** A support engineer chooses the project, then registers the items that arrived for it.
2. **Support any category of equipment.** Each category has its own fields. For example, FR readers have FR ID, OS version, firmware version, APK version and mounting type. Adding a new category needs no development.
3. **Make registration fast on a phone.** Serial numbers are read by scanning the barcode label with the phone camera.
4. **Control withdrawals.** An engineer requests items from a project's stock. The project's PM approves first, then the operations manager (OM).
5. **Keep a complete history** of every item, which cannot be edited afterwards.

### 1.3 Design principles

- **The project is the home of inventory.** Every item belongs to exactly one project. People mostly work inside one project's inventory, and a cross-project view is available for management and the clerks.
- **Categories are configuration, not code.** The common fields are fixed. Each category adds its own fields through a field definition that the administrator maintains.
- **One record per physical item, for serialised equipment.** Items with serial numbers are tracked individually. Low-value items counted by quantity, such as cables and brackets, are a later extension (Section 4.7).
- **The history is a ledger.** The current state of an item is stored for fast lookup, and every change is also written to an append-only movement log.
- **Reuse the platform core** for projects, locations, users, permissions, approvals, email, numbering, import and export, and search.

### 1.4 Out of scope for the first release

- Purchasing, invoices and costs.
- Items counted by quantity (consumables). The design leaves room for them (Section 4.7).
- Offline use without a network connection.
- Integration with SAP or other corporate systems.

---

## 2. Industry practices this design follows

| Practice | How the design applies it |
|---|---|
| Asset classes with configurable attributes (as in ITAM tools and CMDBs, for example the ServiceNow CMDB class model or Snipe-IT custom fieldsets) | Each category defines its own fields. The common fields are the same for every category. |
| Serialised asset register (ISO/IEC 19770-1) | Each item has a unique serial number, model, category, project and location. |
| Project or cost-centre ownership | Every item belongs to one project. A move to another project is an explicit, approved transfer. |
| Goods receipt (GRN) | Items that arrive together are registered under one delivery record. |
| Lifecycle state machine | Items move through defined states. Only the allowed transitions are possible. |
| Immutable movement ledger | Every change records who did it, what changed, when, and from where to where. |
| Segregation of duties | Nobody approves their own request. Approval and physical handover are separate steps. |
| Reservation and confirmed handover | Approved items are held for the request, and the engineer confirms the handover by scanning. |
| Periodic stocktake | A later phase lets engineers scan a store or a project and see missing or unexpected items. |

---

## 3. Roles and permissions

Roles are shared across OpsHub (`platform-architecture.md`, Section 6). For inventory:

| Role | What they can do |
|---|---|
| Inventory clerk | Register deliveries and items for any project, edit item details, hand over approved items, record returns, transfers and repairs, run stocktakes. |
| Engineer | View project inventory, raise withdrawal requests, confirm handover, deploy, return and report faults. |
| Project manager | See the full inventory of their own projects. Approve withdrawals for their projects (first level). Optionally register items for their own projects (decision D6). |
| Operations manager | Approve withdrawals and transfers between projects. See all inventory and reports. |
| Viewer | Read-only access to inventory and reports. |
| Administrator | Maintain categories and their fields, models and suppliers. Correct records, always with a recorded reason. |

---

## 4. Data model

### 4.1 Entity overview

```
platform core:   projects (with PM) ── locations ── users
                     │
inventory:           ├──< inv_deliveries ──< inv_items >── inv_models >── inv_categories
                     │                          │                              │
                     │                          │                     field definitions
                     └──< inv_withdrawals ──< inv_withdrawal_lines
                                                │
                     inv_movements (append-only ledger, one row per change to an item)
approvals:       shared approval tasks of the platform engine (PM step, OM step)
```

Projects and locations belong to the platform core, because both modules use them. Every inventory table carries the `inv_` prefix.

### 4.2 Categories and their fields

**inv_categories**

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| code | text, unique | For example FR_READER, CAMERA, GATEWAY, SERVER, TABLET |
| name | text | For example "FR reader" |
| tracking | SERIAL (QUANTITY later) | How the category is counted |
| fields | JSON | The category's own fields, described below |
| warranty_required | boolean | Whether the warranty dates are mandatory for this category |
| is_active | boolean | |

Each entry in `fields` defines one field:

| Property | Example |
|---|---|
| key | `apk_version` |
| label | "APK version" |
| type | text, number, date, choice, yes/no |
| choices | For choice fields, for example Wall, Pedestal, Turnstile, Desk, Other |
| required | yes or no |
| show_in_list | whether the field is a column in the project's item list |
| order | the position on the form |

The FR reader category is created with the fields from the requirement:

| Field | Type | Required |
|---|---|---|
| FR ID | text | No |
| Deployment date | date | No |
| OS version | text | No |
| Firmware version | text | No |
| APK version | text | No |
| Mounting type | choice: Wall, Pedestal, Turnstile, Desk, Other | No |

A field can be added to a category at any time. A field can be retired, which hides it from forms, but it is never deleted, so values that were recorded earlier stay readable. Changing a field's type is not allowed. A new field is created instead.

**inv_models**: model_no (unique), name, manufacturer, category, serial_pattern (optional) and is_active. The serial number pattern catches scans of the wrong barcode on a label.

**inv_suppliers**: name and is_active.

### 4.3 Items

**inv_items**: one row per physical item.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | integer | | |
| serial_no | text, unique | Yes | Stored in capitals without spaces |
| category_id | category | Yes | Taken from the model |
| model_id | model | Yes | |
| project_id | project | Yes | The project the item belongs to |
| location_id | location | Yes | Where the item is now |
| warranty_start, warranty_end | date | Per category | |
| status | Section 5.1 | Yes | Changed only by actions |
| holder_user_id | user | No | The engineer holding the item while it is issued |
| delivery_id | delivery | No | The delivery it arrived in |
| attributes | JSON | Per category | Values of the category's own fields, checked against the field definitions on every save |
| remarks | text | No | |
| version | integer | | Optimistic locking |
| created_by, created_at, updated_at | | | |

Category fields are kept in one JSON column, `attributes`, rather than in a separate table per category. This is the common approach for configurable attributes. It keeps queries simple, works well with SQLite, and needs no database change when a field is added. Fields used for filtering, such as FR ID, can be given an index on their JSON value.

### 4.4 Deliveries

**inv_deliveries**: one row per delivery to a project.

| Column | Notes |
|---|---|
| delivery_no | Generated, for example GRN-2026-0042 |
| project_id | Chosen first. Every item in the delivery belongs to this project. |
| supplier_id, delivery_order_no, received_on, received_by | |
| location_id | The store where the items are kept |
| default model and warranty dates | Applied to each item scanned under the delivery, and can be changed per item |
| remarks | |

One delivery can contain items of several models and categories. The clerk switches the current model while scanning.

### 4.5 Movement ledger

**inv_movements** is append-only. It records: item, kind (RECEIVE, RESERVE, RELEASE, ISSUE, DEPLOY, RETURN, TRANSFER_LOCATION, TRANSFER_PROJECT, REPORT_FAULT, SEND_FOR_REPAIR, REPAIRED, DISPOSE, UPDATE, CORRECTION), the state, location, holder and project before and after, the withdrawal or delivery, any changed fields with their old and new values, a reason (required for CORRECTION, DISPOSE and TRANSFER_PROJECT), who did it, when, and from which device. The item and its movement are written in the same transaction.

### 4.6 Withdrawals

**inv_withdrawals**: request_no (WDR-2026-0001), requester, project, purpose, destination, needed_by, status, round, version and timestamps. The project decides which PM approves, and only that project's items can be requested.

**inv_withdrawal_lines**: one line per requested item. A line names either a **specific item**, which the engineer chooses by scanning or from the list, or a **model and a quantity**, in which case the clerk picks the items at handover. The issued items are recorded on the line at handover.

The PM and OM approval steps are tasks of the shared approval engine in the platform core, not an inventory table.

### 4.7 Room for quantity-tracked items

A later category can use `tracking = QUANTITY` for consumables such as cables or brackets. These would be held as a stock balance per project, model and location, with receipts and issues recorded in the same movement ledger. Delivery, withdrawal and approval use the same pages. Only the line asks for a quantity instead of serial numbers. Nothing in the first release blocks this.

### 4.8 Rules enforced by the database

- Serial numbers are unique across all projects and categories.
- An item can be in at most one open withdrawal. A partial unique index enforces this.
- Foreign keys are enforced. Records are deactivated, never deleted.
- Migrations are additive, so existing data is never replaced.

---

## 5. Workflows

### 5.1 Item lifecycle

The same lifecycle applies to every serialised category.

| State | Meaning |
|---|---|
| IN_STOCK | In a store, available to the project |
| RESERVED | Held for an approved withdrawal |
| ISSUED | Handed over to an engineer |
| DEPLOYED | Installed at a site |
| RETURNED | Back at a store, waiting to be checked |
| FAULTY | Reported faulty |
| IN_REPAIR | With the supplier or a repair centre |
| DISPOSED | Written off, with a reason. This state is final |

Allowed transitions:

- IN_STOCK → RESERVED → ISSUED → DEPLOYED
- RESERVED → IN_STOCK, when the request is rejected, cancelled or not collected
- ISSUED or DEPLOYED → RETURNED → IN_STOCK, or RETURNED → FAULTY
- Any state → FAULTY → IN_REPAIR → IN_STOCK
- FAULTY → DISPOSED

### 5.2 Registering a delivery under a project

1. **Choose the project.** Every item in the delivery will belong to it.
2. Enter the supplier, the delivery order number, the store location and the warranty dates once.
3. Choose the model. This sets the category, and so the fields shown.
4. Scan the items. Each scan adds one item. Duplicates in the delivery, and serial numbers already in the system, are flagged immediately.
5. Switch the model if the delivery contains other equipment, and keep scanning.
6. Optionally fill in the category fields for each item, now or later.
7. Save. All items are saved together, and each gets a RECEIVE entry in its history.

### 5.3 Withdrawal

1. The engineer opens the project's inventory and chooses **Request items**. The engineer adds specific items, or a model and quantity, and gives the purpose, destination and date needed.
2. The **project's PM** approves. If the requester is the PM, this step is skipped and the reason is recorded.
3. Any **operations manager** approves.
4. Specific items are reserved immediately. Model-and-quantity lines are checked against the available stock.
5. At **handover**, the clerk picks the items for any quantity lines, and the engineer scans every item. Items not in the request are refused.
6. The engineer marks each item as deployed, with the site and date, or returns it. The request closes when every item is accounted for.

A rejection sends the request back to the engineer, who can revise and resubmit it or withdraw it, the same as for resource requests.

### 5.4 Transfer between projects

An item sometimes moves to another project, for example when spare readers from one project are reused on another. A transfer is a separate request. It goes to the PM of the receiving project and then to the operations manager. On approval, the item's project changes, and the history records both projects and the reason. Decision D4 asks whether this approval is needed.

---

## 6. Barcode scanning on mobile

The scanning approach is the same as in the previous revision. It applies to every category.

- **Camera in the browser.** The phone's rear camera reads Code 128, Code 39, EAN/UPC, QR and Data Matrix. The page uses the browser's built-in reader where available, and the ZXing library elsewhere, for example Safari on iPhone. HTTPS is already in place.
- **Labels with several barcodes.** Codes that do not match the model's serial number pattern are ignored. If more than one code matches, the engineer taps the right one.
- **Other ways to enter.** Typing, or a Bluetooth or USB handheld scanner, which works like a keyboard.
- **Continuous scanning** during a delivery, with a beep, a vibration and a running count.

---

## 7. Pages

### 7.1 Navigation

Inventory pages sit in the combined OpsHub menu (`platform-architecture.md`, Section 3):

```
INVENTORY
  Project inventory     list of projects with item counts; open one to manage its inventory
  All items             search and filter across every project (clerks, OM, management)
  Deliveries            clerks
  Withdrawals
  Warranty
```

Withdrawal approvals appear in the shared Approvals inbox, and the person's withdrawals and items appear in My work. "Register delivery" and "Request items" appear under + New, and both ask for the project first. The shared Projects page has an Inventory tab that opens the same project inventory page.

### 7.2 Project inventory page

This is the main inventory page. It opens for one project and contains:

- **The header:** project name, WBS code, client and PM, and the buttons Register delivery and Request items.
- **A summary by category:** for each category, the counts in stock, reserved, issued, deployed and faulty. For example, "FR reader: 38 in stock, 4 issued, 120 deployed".
- **Tabs:**
  - **Items:** filter by category, model, status and location. The columns are the common fields plus the category's fields that are marked "show in list".
  - **Deliveries:** the project's deliveries.
  - **Withdrawals:** open and past requests for this project.
  - **History:** every movement on the project's items.
  - **Warranty:** items whose warranty ends soon.
- **Export to Excel,** which includes the category fields.

### 7.3 Other pages

| Page | Purpose |
|---|---|
| Item details | All fields, including the category's own fields, the history, and the actions allowed in the current state |
| Register delivery (phone) | The flow in Section 5.2 |
| Request items (phone and desktop) | The flow in Section 5.3 |
| Handover (phone) | For the clerk and the engineer, with scanning |
| Find an item | Scan or type a serial number. Also available from the top-bar Scan button |
| Warranty | All projects, within 30, 60 or 90 days |
| Administration: Categories | Create a category and define its fields, with a preview of the resulting form |
| Administration: Models and suppliers | |
| Import | Existing items from Excel, per project. The template's columns include the chosen category's fields |

### 7.4 Notifications

Approval emails go to the PM and the OM, with Approve and Reject buttons. The requester gets decision emails and a "ready for collection" email. Clerks are reminded about uncollected items, and the OM and clerks get a weekly warranty summary. The project PM can also opt in to a weekly summary of their project's inventory.

---

## 8. Architecture

### 8.1 A module of the platform

Inventory follows the module contract in `platform-architecture.md`, Section 4.2.

```
backend/src/opshub/modules/inventory/
  domain/      lifecycle, withdrawal and transfer rules; field definition validation
  models.py    inv_ tables
  services/    categories, deliveries, items, withdrawals, handover, transfers, stocktake, reports
  api.py       /api/v1/inventory/...
  templates/   email templates
  module.py    permissions, menu, approval routes, home, search and project-tab providers
frontend/src/modules/inventory/
  pages, the dynamic category form, the camera scanner, routes, module.ts
```

The **dynamic category form** is one component. It draws the fields of any category from its definition, and the same definition drives server-side validation, the item list columns, the Excel template and the export.

### 8.2 Approval routes

| Document type | Route |
|---|---|
| Item withdrawal | PM of the project (skipped if the requester is the PM), then any operations manager |
| Transfer between projects | PM of the receiving project, then any operations manager |

### 8.3 API examples

| Method and path | Purpose |
|---|---|
| `GET /inventory/projects/{id}/summary` | Counts by category and status for the project page |
| `GET /inventory/items?project=&category=&status=&model=&q=` | Search items |
| `GET /inventory/items/lookup?serial=` | Fast lookup after a scan |
| `GET /inventory/categories/{id}` | A category with its field definitions, for the dynamic form |
| `POST /inventory/deliveries` | Register a delivery and its items under a project |
| `POST /inventory/items/{id}/actions/{action}` | Deploy, return, report fault and other lifecycle actions |
| `POST /inventory/withdrawals`, `.../submit`, `.../handover` | Withdrawal flow |
| `POST /inventory/transfers` | Transfer between projects |

### 8.4 Capacity

Tens of thousands of items with their history need only tens of megabytes, which SQLite and the current server handle easily. Scanning runs on the phone and adds no server load.

---

## 9. Security and data quality

- Access is checked by permission, and PMs see only their own projects' requests.
- Every change is in the ledger. Corrections need a reason.
- Values are checked against the category's field definitions, the serial number pattern, duplicate checks and date rules.
- Forms carry the same "no sensitive information" reminder as the request form.
- The daily database backup covers the new tables.

---

## 10. Phased delivery

| Phase | Content |
|---|---|
| 1. Register and find | Categories with configurable fields (FR reader set up first), models, suppliers, the project inventory page, delivery registration with scanning, item details and history, Find an item, Excel import and export per project |
| 2. Withdraw and issue | Withdrawals with PM and OM approval, reservation, handover by scanning, deploy, return, report fault, transfer between projects |
| 3. Monitor | Warranty reminders, stocktake by scanning, reports by project and category; quantity-tracked categories if needed |

Phase 0 (the platform foundation) comes first, as described in `platform-architecture.md`.

---

## 11. Acceptance criteria for Phase 1

- An administrator can add a new category, such as Camera, with its own fields, and register a camera straight away without any software change.
- A clerk can choose a project and register a delivery of 20 items on a phone in under five minutes, using the camera.
- The project inventory page shows counts by category and status, and lists the items with their category fields.
- A serial number that already exists in any project is refused with a message that names the project and item.
- Existing items can be imported per project from Excel, with a preview.

---

## 12. Decisions needed from the business

| No. | Question | Recommendation |
|---|---|---|
| D1 | Which categories are needed at the start, and which fields do they have? | FR reader with the fields above, plus any others you name. More can be added at any time. |
| D2 | Do engineers request specific items, or a model and a quantity? | Allow both |
| D3 | When the requester is the project's PM, skip the PM step? | Yes, record why, and keep the OM approval |
| D4 | Do transfers between projects need approval? | Yes: the receiving project's PM, then the OM |
| D5 | Is a store location shared by all projects, or does each project have its own? | Shared stores. Items in a store still belong to their project. |
| D6 | May PMs register items for their own projects, or only clerks? | Clerks only at first, to keep the data consistent |
| D7 | Are there existing spreadsheets of equipment to import? | Import them per project in Phase 1 |
| D8 | Should consumables counted by quantity be included? | Later (Phase 3), if needed |
