# Inventory Module: System Design

| Item | Value |
|---|---|
| System | PSBU OpsHub (see `platform-architecture.md`) |
| Module | Inventory recording, tracking and withdrawal of FR readers |
| Status | Draft for review. Nothing in this document has been built yet. |
| Date | 12 Nov 2026 |

This document specifies the Inventory module of PSBU OpsHub. The platform as a whole, including the system name, the combined menu, shared records, permissions and the approval engine, is described in `platform-architecture.md`; this document covers what is specific to inventory. It proposes how to add inventory management to the system. It covers the scope, roles, data model, workflows, the mobile pages with barcode scanning, the architecture and a phased delivery plan. Section 12 lists the decisions the business needs to confirm before development starts.

---

## 1. Background and goals

### 1.1 Background

Suppliers deliver FR readers to NEC, and support engineers deploy them to project sites. Today, nobody records the readers' details in one shared place. As a result, it is hard to answer simple questions such as "Where is reader SN-12345 now?", "Which readers belong to the HSA project?" or "Which warranties expire next quarter?". Withdrawals from stock are also not approved or traced consistently.

### 1.2 Goals

1. **Record every reader once, at delivery.** Support engineers register each reader with its key information when it arrives from the supplier.
2. **Make registration fast on a phone.** The registration page works on a mobile browser and reads the serial number by scanning the barcode label with the phone camera.
3. **Control withdrawals.** An engineer who needs readers raises a withdrawal request. The project manager (PM) and then the operations manager (OM) approve it before the readers are issued.
4. **Keep a complete history.** Every change to a reader, including receipt, issue, return, transfer, repair and disposal, is recorded and cannot be edited afterwards.
5. **Follow industry practice** for asset management, without adding steps that the team does not need.

### 1.3 Design principles

- **Practical and easy to use.** The common tasks, which are registering a delivery and requesting readers, take as few taps as possible on a phone.
- **One record per physical device.** Each reader is tracked individually by its serial number. This is "serialised inventory", the normal practice for valuable equipment with warranties.
- **The history is a ledger.** The current state of a reader is stored for fast lookup, but every change is also written to an append-only movement log. The log is the audit trail and is never updated or deleted.
- **Reuse what ERS already has.** The module uses the existing sign-in, users, roles, email notifications, email approval links, Excel import and export, and deployment pipeline.

### 1.4 Out of scope for the first release

- Purchasing, supplier invoices and costs. The module records what was received, not what it cost.
- Consumables counted by quantity, such as cables or brackets. These could be added later as "non-serialised items".
- Offline use without a network connection. Section 7.5 explains why, and how it could be added.
- Integration with SAP or other corporate systems.

---

## 2. Industry practices this design follows

| Practice | How the design applies it |
|---|---|
| Serialised asset register (ITAM / ISO/IEC 19770-1) | Each reader is one record with a unique serial number, model, owner project and location. |
| Goods receipt (GRN) | Readers that arrive together are registered under one receipt, which records the supplier, delivery order number and date. |
| Asset lifecycle state machine | A reader moves through defined states (Section 5.1). Only the allowed transitions are possible. |
| Immutable movement ledger | Every change writes a movement record with who, what, when, from where and to where. |
| Segregation of duties (maker-checker) | The person who requests a withdrawal cannot approve it. Approval and physical handover are separate steps. |
| Reservation on approval | Requested readers are held for the request, so two requests cannot take the same reader. |
| Handover confirmation | The engineer confirms receipt of the readers by scanning them, so the record matches what was physically handed over. |
| Periodic stocktake (cycle count) | A later phase lets engineers scan the readers in a store and see any that are missing or unexpected. |
| Role-based access control | Each role sees and does only what it needs (Section 3). |
| Master data | Models, projects, locations and suppliers are chosen from maintained lists instead of typed freely, which keeps reports accurate. |

---

## 3. Roles and permissions

The module reuses ERS user accounts. It adds two roles and uses project-level assignment for the PM.

| Role | Who | What they can do |
|---|---|---|
| Inventory clerk (new role) | Support engineers who receive deliveries | Register deliveries and readers, edit reader details, issue approved readers, record returns, transfers and repairs, run stocktakes. |
| Engineer (existing role) | Field and support engineers | View stock, raise withdrawal requests, confirm receipt of issued readers, report a faulty reader. |
| Project manager | The PM assigned to each project in the project list | Approve or reject withdrawal requests for their own projects (first level). |
| Operations manager (new role) | OM | Approve or reject withdrawal requests after the PM (second level). See all inventory and reports. |
| Viewer (existing role) | Management | Read-only access to inventory and reports. |
| Administrator (existing role) | System administrator | Maintain models, projects, locations, suppliers and settings. Correct records when needed, with a recorded reason. |

The PM is not a global role. Each project in the project list names its PM, and a withdrawal request for that project goes to that person. This means a person can be the PM of one project and an ordinary engineer on another.

---

## 4. Data model

### 4.1 Entity overview

```
device_models ─┐
suppliers ─────┼──< goods_receipts ──< assets >── locations
projects ──────┘                        │   ▲
   │ (pm_user_id)                       │   │
   │                                    ▼   │
   └──────< withdrawal_requests ──< withdrawal_items
                 │
                 └──< approval tasks (shared platform core: PM step, OM step)

assets ──< asset_movements  (append-only ledger)
```

### 4.2 Master data

Projects (with their PM) and locations belong to the platform core, because both modules use them (`platform-architecture.md`, Section 5). Device models and suppliers belong to the inventory module.

**device_models**: the reader models that can be registered.

| Column | Type | Notes |
|---|---|---|
| id | integer | Primary key |
| model_no | text, unique | For example, the supplier's model code |
| name | text | A readable name |
| manufacturer | text | |
| serial_pattern | text, optional | A pattern the serial number must match, such as 12 letters and digits. It catches scanning the wrong barcode on the label. |
| is_active | boolean | Inactive models cannot be chosen for new readers |

**projects**: projects that own readers. These are also the projects that withdrawal requests are raised for.

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| code | text, unique | WBS code |
| name | text | |
| client_name | text | |
| pm_user_id | user | The PM who approves withdrawals for this project |
| is_active | boolean | |

**locations**: where a reader physically is.

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| name | text, unique | For example, "NEC Store, Level 3" or "HSA Outram site" |
| kind | STORE, SITE, REPAIR, OTHER | Readers can only be issued from a STORE |
| project_id | project, optional | For sites that belong to one project |
| is_active | boolean | |

**suppliers**: id, name and is_active.

### 4.3 Readers (assets)

**assets**: one row per physical reader. This table holds the current state for fast lookup.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | integer | | |
| serial_no | text, unique | Yes | Stored in capitals with spaces removed, so the same reader cannot be registered twice |
| model_id | device model | Yes | |
| project_id | project | Yes | The project the reader belongs to |
| location_id | location | Yes | Where the reader is now |
| warranty_start | date | Yes | |
| warranty_end | date | Yes | Must be on or after the start date |
| status | see Section 5.1 | Yes | Set by the system, not edited directly |
| fr_id | text | No | |
| deployment_date | date | No | |
| os_version | text | No | |
| firmware_version | text | No | |
| apk_version | text | No | |
| mounting_type | WALL, PEDESTAL, TURNSTILE, DESK, OTHER | No | Chosen from a list |
| holder_user_id | user | No | The engineer who has the reader, while it is issued |
| receipt_id | goods receipt | No | The delivery it arrived in |
| remarks | text | No | |
| version | integer | | Optimistic locking, as in the request module |
| created_by, created_at, updated_at | | | |

**goods_receipts**: one row per delivery.

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| receipt_no | text, unique | Generated, for example GRN-2026-0001 |
| supplier_id | supplier | |
| delivery_order_no | text | The number on the supplier's delivery order |
| received_on | date | |
| received_by | user | |
| project_id, location_id, model_id | | Defaults applied to every reader scanned under this receipt |
| warranty_start, warranty_end | date | Defaults for every reader, which can be changed per reader |
| remarks | text | |

### 4.4 Movement ledger

**asset_movements**: append-only. The application never updates or deletes rows in this table.

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| asset_id | asset | |
| kind | RECEIVE, RESERVE, RELEASE, ISSUE, DEPLOY, RETURN, TRANSFER, SEND_FOR_REPAIR, REPAIRED, REPORT_FAULT, DISPOSE, UPDATE, CORRECTION | |
| from_status, to_status | status | |
| from_location_id, to_location_id | location | |
| from_holder_id, to_holder_id | user | |
| withdrawal_id | withdrawal request | When the movement belongs to a request |
| receipt_id | goods receipt | For RECEIVE |
| changes | JSON | For UPDATE and CORRECTION: each changed field with its old and new value |
| reason | text | Required for CORRECTION and DISPOSE |
| actor_id | user | |
| occurred_at | timestamp (UTC) | |
| client | JSON | The IP address and device, as recorded for email approvals |

The asset row and its movement row are always written in the same database transaction, so they cannot disagree.

### 4.5 Withdrawal requests

**withdrawal_requests**

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| request_no | text, unique | For example, WDR-2026-0001 |
| requester_id | user | The engineer |
| project_id | project | Decides which PM approves |
| purpose | text | Why the readers are needed |
| destination | text | The site or customer the readers are going to |
| needed_by | date | |
| status | see Section 5.2 | |
| round | integer | Increases each time the request is resubmitted after a rejection |
| version | integer | Optimistic locking |
| submitted_at, approved_at, issued_at, closed_at | timestamps | |

**withdrawal_items**: the readers in the request.

| Column | Type | Notes |
|---|---|---|
| id | integer | |
| withdrawal_id | withdrawal request | |
| asset_id | asset | A specific reader (see decision D2 in Section 12) |
| issued_at, returned_at | timestamps | Filled in at handover and on return |

**Approval tasks** are not an inventory table. The PM and OM steps are tasks of the shared approval engine in the platform core (`platform-architecture.md`, Section 4.4), the same engine that handles resource requests, including the email Approve and Reject links.

### 4.6 Rules enforced by the database

- `assets.serial_no` is unique, so a reader cannot be registered twice.
- A reader can be in at most one open withdrawal request. A partial unique index on open withdrawal items enforces this.
- Foreign keys are enforced, and records are deactivated rather than deleted.
- The migration is additive (0003), in line with the incremental update rule for the production database.

---

## 5. Workflows

### 5.1 Reader lifecycle

```
              register
                 │
                 ▼
   ┌───────► IN_STOCK ◄──────────────┐
   │             │ request approved   │ released (rejected,
   │             ▼                    │ cancelled or expired)
   │         RESERVED ────────────────┘
   │             │ handed over
   │             ▼
   │          ISSUED ──── installed at site ───► DEPLOYED
   │             │                                 │
   │  returned   │                                 │ removed / fault
   └─────────────┴──────────── RETURNED ◄──────────┘
                                  │
                                  ▼
   any state ──► FAULTY ──► IN_REPAIR ──► IN_STOCK
                    │
                    └──────────────► DISPOSED (final)
```

| State | Meaning |
|---|---|
| IN_STOCK | In a store and available |
| RESERVED | Held for an approved withdrawal request, waiting for handover |
| ISSUED | Handed over to an engineer, not yet installed |
| DEPLOYED | Installed at a site |
| RETURNED | Back in a store and waiting to be checked. A clerk then puts it back in stock or marks it faulty |
| FAULTY | Reported faulty |
| IN_REPAIR | With the supplier or a repair centre |
| DISPOSED | Written off. This is final, and needs a reason |

State changes happen only through actions such as Issue, Return or Report fault. Nobody edits the status field directly. The same transition-table approach is used in the request workflow (`domain/workflow.py`).

### 5.2 Withdrawal request

```
DRAFT ──submit──► PENDING_PM ──approve──► PENDING_OM ──approve──► APPROVED
                     │                       │                       │ readers reserved
                     │ reject                │ reject                ▼
                     ▼                       ▼                    ISSUED ──► CLOSED
                  RETURNED (requester can revise and resubmit, or withdraw)
```

- **Submit.** The engineer chooses the project and the readers, and gives the purpose, destination and date needed. The system checks that every reader is IN_STOCK, belongs to that project and is not in another open request.
- **PM approval.** The task goes to the project's PM, by email with Approve and Reject buttons, the same as the resource requests.
- **OM approval.** After the PM approves, the task goes to the operations managers. Any one of them can act.
- **Reject.** As in the request module, Reject sends the request back. The requester can revise and resubmit it, or withdraw it. "Reject permanently" is available only inside the system.
- **Reservation.** On final approval, the readers become RESERVED, and the inventory clerks are notified to prepare them.
- **Issue (handover).** The clerk and the engineer meet. The engineer scans each reader. A reader that is not in the request is refused, and the handover cannot finish while a reader is missing. On confirmation, the readers become ISSUED, and the engineer becomes their holder.
- **Deploy and return.** The engineer marks readers as deployed, with the site and date, or returns unused readers to a store.
- **Expiry.** If approved readers are not collected within a configurable number of days (default 10 working days), the clerk is reminded. A clerk can cancel the request, which releases the readers.

### 5.3 Separation of duties

- Nobody can approve their own request. If the requester is the project's PM, the PM step is recorded as "not applicable: the requester is the PM" and the request goes straight to the OM. Decision D3 asks the business to confirm this.
- The person who approves a request cannot also record the handover of it, unless the administrator turns this rule off for a small team.

---

## 6. Barcode scanning on mobile

### 6.1 How it works

The registration and handover pages open the phone's rear camera inside the browser. No app needs to be installed.

1. The engineer taps the scan button next to the Serial number field. The browser asks once for permission to use the camera.
2. The page reads barcodes from the live camera image. It supports Code 128, Code 39, EAN/UPC, QR and Data Matrix, which covers the label formats that suppliers commonly use.
3. When a code is read, the phone vibrates, and the value appears in the field for the engineer to confirm.

The page uses the browser's built-in barcode reader (the `BarcodeDetector` interface) where it is available, mainly Chrome on Android. Elsewhere, notably Safari on iPhone, it uses a well-established open-source reader library (ZXing). Camera access needs HTTPS, which ERS already uses.

### 6.2 Labels with several barcodes

Reader labels often carry several barcodes, such as the serial number, MAC address and model number. The page handles this as follows:

- When a model has a serial number pattern, any code that does not match the pattern is ignored. The engineer just points the camera at the label.
- When several codes match, or there is no pattern, the page lists them and the engineer taps the right one.
- A torch button and a tap-to-focus hint help with small labels in dim stores.

### 6.3 Other ways to enter a serial number

- **Typing**, for damaged labels.
- **Handheld scanners.** A Bluetooth or USB barcode scanner works like a keyboard, so it can fill the field without any extra setup. This is useful at a desk with a large delivery.

### 6.4 Batch registration of a delivery

Deliveries usually contain many readers of the same model for the same project. The registration flow is therefore built around the delivery:

1. **Start a receipt.** Enter the supplier, delivery order number, project, model, store location and warranty dates once.
2. **Scan readers continuously.** Each scan adds a reader to the list immediately, with a beep and a counter. The page warns straight away about duplicates within the delivery, or a serial number that is already in the system.
3. **Optional details.** Tap any reader in the list to add optional fields such as FR ID, versions or mounting type. These can also be added later, from the reader's page or by Excel import.
4. **Save.** All readers are saved together, in one transaction.

---

## 7. Pages

### 7.1 Mobile-first pages, for engineers and clerks

| Page | Purpose |
|---|---|
| Register delivery | The batch flow in Section 6.4 |
| Find a reader | Scan or type a serial number to see the reader's details, status, location, holder and history |
| Request readers | Choose a project, then add readers by scanning or by choosing from the available stock list, and submit |
| My requests | The status of my withdrawal requests, with Revise, Withdraw and Confirm receipt actions |
| My readers | Readers I currently hold, with Mark deployed, Return and Report fault actions |
| Handover | For the clerk: open an approved request, and the engineer scans each reader to confirm |

### 7.2 Desktop pages, for clerks, PMs, the OM and management

| Page | Purpose |
|---|---|
| Inventory list | Filter by project, model, status, location and warranty end date. Export to Excel |
| Reader details | All fields, the movement history, and actions allowed for the current state |
| Withdrawal approvals | The PM's and OM's inbox, the same layout as the resource approvals |
| Warranty | Readers whose warranty ends within the next 30, 60 or 90 days |
| Reports | Stock by project, location, model and status. Movements per month |
| Administration | Models, projects with their PMs, locations, suppliers, and Excel import of existing readers |

### 7.3 Navigation

Inventory is not a separate area. Its pages appear in the combined OpsHub menu described in `platform-architecture.md`, Section 3: withdrawal approvals appear in the shared Approvals inbox, the person's withdrawals and readers appear in My work, "Request readers" and "Register delivery" appear under + New, and the project page has an Inventory tab. The Inventory section of the menu holds Readers, Deliveries, Withdrawals and Warranty.

### 7.4 Notifications

The module uses the existing email outbox. It sends:

- approval emails to the PM and the OM, with Approve and Reject buttons;
- decision emails to the requester;
- a "ready for collection" email to the requester and the clerks;
- a reminder for readers that have not been collected;
- a weekly warranty summary to the OM and the clerks.

### 7.5 Network connection

The first release needs a network connection. Mobile data is normally available in stores and offices, and an online-only design avoids the risk of two engineers working on the same reader from out-of-date copies. If stores turn out to have poor coverage, a later version can queue scans on the phone and send them when the connection returns. The database would still check every scan for duplicates and conflicts at that point.

---

## 8. Architecture

### 8.1 A module of the platform

Inventory is built as a module that follows the module contract in `platform-architecture.md`, Section 4.2. It uses the platform core for accounts and permissions, projects and locations, the approval engine, notifications, history, numbering, import and export, and search. It owns only the inventory records and rules.

```
backend/src/opshub/modules/inventory/
  domain/      reader lifecycle and withdrawal rules
  models.py    tables prefixed inv_
  services/    deliveries, readers, withdrawals, handover, stocktake, reports
  api.py       /api/v1/inventory/...
  templates/   email templates
  module.py    the module definition: permissions, menu, approval route, home and search providers
frontend/src/modules/inventory/
  pages, components (including the camera scanner), routes, module.ts
```

### 8.2 Approval route

The withdrawal approval runs on the shared approval engine with the route "PM of the project, then any operations manager", and a skip rule when the requester is the PM. Reservation of readers on approval, and their release on rejection, are hooks the engine calls. The withdrawal_tasks table in Section 4.5 is therefore not needed; the engine's shared approval tasks are used instead.

### 8.3 API

The API follows the conventions already used in ERS: REST, JSON, `/api/v1`, CSRF protection, plain-language error messages, and a `version` field for updates. Examples:

| Method and path | Purpose |
|---|---|
| `GET /inventory/assets?serial=&project=&status=&...` | Search readers |
| `GET /inventory/assets/{id}` | Reader details with history |
| `GET /inventory/assets/lookup?serial=` | Fast lookup after a scan |
| `POST /inventory/receipts` | Register a delivery with its readers |
| `POST /inventory/assets/{id}/actions/{action}` | Lifecycle actions such as return, deploy or report fault |
| `POST /inventory/withdrawals` and `.../submit` | Create and submit a withdrawal request |
| `POST /inventory/withdrawals/{id}/decision` | Approve or reject |
| `POST /inventory/withdrawals/{id}/handover` | Confirm the scanned readers at handover |
| `GET /inventory/reports/...`, `GET .../export.xlsx` | Reports and Excel export |

### 8.4 Capacity

A few thousand readers and their movements need only a few megabytes. SQLite and the current e2-micro server handle this easily. Barcode decoding runs on the phone, not on the server, so scanning adds no load to the server.

---

## 9. Security and data quality

- **Access.** Every endpoint checks the user's role, and PMs see only their own projects' requests.
- **Audit.** Every change is in the movement ledger. Corrections by an administrator need a reason and are shown in the history.
- **Data quality.** Master data lists, serial number patterns, duplicate checks, and dates checked against each other (for example, the warranty end must not be before its start).
- **No sensitive information.** The forms carry the same reminder as the request form. Labels are not photographed in the first release, so no images are stored.
- **Backups.** The existing daily database backup covers the new tables.

---

## 10. Phased delivery

| Phase | Content | Value |
|---|---|---|
| 1. Register and find | Master data, mobile batch registration with scanning, the reader list and details, the movement history, Excel import of existing readers, and Excel export | Every reader is recorded at delivery and can be found by serial number |
| 2. Withdraw and issue | Withdrawal requests, PM and OM approval (including by email), reservation, handover by scanning, deploy, return and report fault | Controlled and traceable stock movements |
| 3. Monitor | Warranty reminders and report, stock reports, and stocktake by scanning | Fewer missed warranties, and regular checks that the records match the stores |

Each phase is released separately, with an additive database migration and no downtime beyond the normal deployment.

---

## 11. Acceptance criteria for Phase 1

- An engineer can register a delivery of 20 readers on a phone in under five minutes, using the camera.
- Scanning a label with several barcodes picks the serial number when the model has a pattern.
- Registering a serial number that already exists is refused with a clear message that names the existing reader.
- Any reader can be found by scanning its label, and its page shows its full history.
- Existing readers can be imported from Excel, with a preview of what will be added and what will be skipped.

---

## 12. Decisions needed from the business

| No. | Question | Recommendation |
|---|---|---|
| D1 | Who are the inventory clerks, and is it the same people who hand readers over? | Support engineers, as described in the requirement |
| D2 | Do engineers request specific readers (by serial number), or a model and a quantity, with the clerk choosing the readers? | Allow both. The engineer can scan specific readers, or ask for a quantity of a model, and the clerk then picks the readers at handover. Specific readers alone is simpler, if that is enough |
| D3 | When the requester is the project's PM, should the PM step be skipped (OM only), or go to another person? | Skip the PM step, record why, and keep the OM approval |
| D4 | Is there one OM, or several? Can any OM approve? | Any active OM can approve, as with team leaders today |
| D5 | Do issued readers come back to the store, or stay at the site permanently? | Support both: Deploy for permanent installation, Return for unused readers |
| D6 | Which store locations exist today? | The administrator enters them in Phase 1 |
| D7 | Is there an existing spreadsheet of readers to import? | Import it in Phase 1, with the preview |
| D8 | Should the supplier's delivery order or warranty documents be attached as files? | Not in the first release. Record the document numbers instead |
| D9 | What should the module be called in the menu? | "Inventory" |
