# PSBU OpsHub: Platform Architecture

| Item | Value |
|---|---|
| System | PSBU OpsHub (proposed name; currently "Engineering Resource Requests") |
| Scope | One system with a shared core and business modules: Resources (live) and Inventory (new) |
| Status | Draft for review. Replaces the earlier proposal that treated inventory as a separate area. |
| Date | 12 Nov 2026 |
| Related | `inventory-module-design.md` (inventory module details), `系统设计说明书.md` (resource module) |

## 1. Why one system

Resource requests and inventory serve the same people: project managers, engineers, team leaders, directors and operations managers. Two separate areas would mean two inboxes, two places to look for a project, and duplicated accounts, projects and approval logic. The system is therefore designed as one platform with:

- one address, one account and one sign-in;
- one menu, organised by the person's tasks first and by module second;
- one approvals inbox and one "My work" page across all modules;
- one shared list of projects, teams, locations and users;
- a shared core that every module uses, so new modules can be added without changing the core or the existing modules.

## 2. Name

The current name, "Engineering Resource Requests", describes only the first module. The proposed name is **OpsHub**, shown as "PSBU OpsHub" with the subtitle "Engineering Operations". Alternatives are PSBU Workbench, FieldDesk and Atlas. The name is one setting (`app_name`) that is used in the browser title, sign-in page, menu and emails. The address psbu.duckdns.org stays, because it names the business unit rather than a module.

Internally, the code package is renamed from `erf` to `opshub` during Phase 0. The database file, its data and the migration history are kept.

## 3. Navigation

### 3.1 Menu structure

```
OpsHub
[ + New ]                     start anything the person may create, from any module
Home                          needs your action, figures for your roles, across modules
Approvals            (5)      one inbox for every module, with a module filter
My work                       my requests of every type, my assignments, readers I hold
Projects                      one page per project, with a tab per module
RESOURCES
  Resource requests
  Resource load
INVENTORY
  Readers
  Deliveries                  inventory clerks
  Withdrawals
  Warranty
INSIGHTS
  Reports                     one page, a tab per module
SYSTEM
  Administration              users, roles, projects, locations, modules, approval routes
```

The top bar holds a global search (by number, serial number, project or person) and, on phones, a Scan button that opens the camera and goes straight to the scanned reader.

### 3.2 Rules

- Items appear only when the person has a permission that uses them. A module section disappears entirely when the person has nothing in it.
- The shared items at the top never change. A new module adds its own section, its entries under + New, its items in Approvals and My work, and its tabs in Projects, Reports and Administration. Nothing else in the menu moves.
- On a phone, the menu becomes a bottom bar: Home, Approvals, + New, Scan and Me. The full menu is still available from Me.

### 3.3 URLs

Shared pages: `/`, `/approvals`, `/my-work`, `/projects/:id`, `/reports`, `/admin`. Module pages sit under the module: `/resources/requests/...`, `/inventory/readers/...`. The existing addresses, such as `/requests/42` and the `/act/:token` email links, keep working through redirects, so old emails and bookmarks are not broken.

## 4. Architecture

### 4.1 Layers

The system stays one deployable application on the current server, in the style known as a modular monolith.

| Layer | Contents |
|---|---|
| Business modules | Resources, Inventory, and future modules. Each owns its data, rules, pages and API. |
| Platform core | Accounts and access, organisation (teams, projects, locations), approval engine, notifications (email queue, email action links, reminders, digests), history and audit, document numbering, Excel import and export, navigation and search. |
| Technical foundation | Vue 3 web app, FastAPI, SQLite with incremental migrations, Caddy, automatic deployment. Unchanged. |

### 4.2 Module contract

A module plugs into the core by providing one module definition, which the core reads at start-up. It declares:

| Item | Example for Inventory |
|---|---|
| Key, name and colour | `inventory`, "Inventory" |
| Permissions | `inventory.reader.view`, `inventory.delivery.register`, `inventory.withdrawal.create`, `inventory.withdrawal.handover` |
| Menu section and + New entries | Readers, Deliveries, Withdrawals, Warranty; "Request readers", "Register delivery" |
| Document types and approval routes | `inventory.withdrawal`: project PM, then operations manager |
| Home page providers | Tiles and "needs your action" items |
| Search providers | Serial number lookup |
| Project page tab, Reports tab, Administration tab | Readers on the project; stock report; reader models and suppliers |
| API router | `/api/v1/inventory/...` |
| Tables and migrations | Tables prefixed `inv_`, migrations in the single chain |
| Email templates and scheduled jobs | Ready for collection; warranty reminders |

The frontend has a matching module definition that registers its routes, menu items and page components.

### 4.3 Rules that keep the system extensible

1. A module uses the core only through the core's service interfaces. It never reads or writes another module's tables.
2. Modules connect to each other only through shared core records, mainly projects and users. For example, the project page asks each module for its tab; the modules do not know about each other.
3. Access is checked by permission, never by role name. Roles are named sets of permissions that the administrator can adjust, so a new role needs no code change.
4. Each module's tables carry its prefix (`res_`, `inv_`). All migrations stay in one chain and are additive, in line with the rule that production data is never replaced.
5. A module can be switched off in Administration. Its menu items, + New entries and home page items then disappear, and its data is kept.
6. Every document type gets its number from the numbering service (`ERR-`, `WDR-`, `GRN-`), so numbers are unique and readable across modules.

### 4.4 Approval engine

The approval engine is the most important shared part. Today the resource request workflow contains its own approval logic. In Phase 0 this logic is generalised:

- An **approval route** belongs to a document type and is a list of steps.
- Each **step** has an approver rule: a role (any director, any operations manager), the team leader of the request's team, the PM of the request's project, or a named person. A step can also have a skip rule, such as "skip when the requester is the approver", which is recorded in the history.
- The engine creates the tasks, sends the emails with Approve and Reject buttons, reminds, escalates, moves approvers when a team's approvers change, prevents self-approval and records every decision. These behaviours exist today for resource requests and become available to every module.
- A module keeps its own business rules around a decision, such as the team leader assigning engineers or the reservation of readers, through hooks that the engine calls on approval and rejection.

| Document type | Route |
|---|---|
| Resource request | Team leader of the team, then any director (unchanged) |
| Resource change | Team leader of the team (unchanged) |
| Reader withdrawal | PM of the project (skipped if the requester is the PM), then any operations manager |

### 4.5 Code structure

```
backend/src/opshub/
  platform/
    identity/      users, roles, permissions, sessions
    org/           teams, projects, locations
    approvals/     routes, steps, tasks, email action tokens
    notify/        outbox, templates, digests, reminders
    audit/         history of every record
    numbering/  imports/  search/  navigation/
  modules/
    resources/     domain, models, services, api, templates, module.py
    inventory/     domain, models, services, api, templates, module.py
  api/             app factory, router built from the modules
  db/  jobs/  core/
frontend/src/
  platform/        app shell, menu, + New, Approvals, My work, Projects, search
  modules/
    resources/     routes, pages, components, module.ts
    inventory/     routes, pages, components, scanner, module.ts
```

## 5. Shared data

| Record | Owner | Notes |
|---|---|---|
| Users, roles, permissions | Core | Unchanged accounts; roles become permission sets |
| Teams and team approvers | Core | Unchanged |
| Projects | Core | New list: WBS code, name, client, PM, active flag. Existing resource requests are linked to it during migration by matching their project names and WBS codes; anything unmatched is listed for the administrator to resolve. |
| Locations | Core | Stores and sites |
| Approval tasks and history | Core | One structure for every document type |
| Resource requests, allocations, changes | Resources | Existing tables, renamed with the `res_` prefix by migration |
| Readers, deliveries, withdrawals, reader history, models, suppliers | Inventory | New tables, `inv_` prefix |

## 6. Roles

| Role | Resources | Inventory |
|---|---|---|
| Requester / Project manager | Raise resource requests | Approve withdrawals for their projects (first level) |
| Engineer | Assignments and calendar invites | Request readers, handover, deploy, return, report faults |
| Team leader | Review requests and assign engineers | As an engineer |
| Director | Final approval of resource requests | View inventory and reports |
| Operations manager (new) | View resource load and reports | Final approval of withdrawals; all inventory |
| Inventory clerk (new) | None | Deliveries, handover, returns, repairs, stocktake |
| Viewer | Reports | Reports |
| Administrator | Users, roles, projects, locations, modules and approval routes | |

## 7. Delivery plan

| Phase | Content |
|---|---|
| 0. Platform foundation | New name; combined menu with + New, Approvals, My work and Projects; project list; permission-based roles; approval engine; code restructured into platform and modules. Resource requests move onto the core with no change for users. The existing automated tests must all pass unchanged, which confirms that behaviour is preserved. |
| 1. Inventory: register and find | See `inventory-module-design.md`, Phase 1 |
| 2. Inventory: withdraw and issue | See `inventory-module-design.md`, Phase 2 |
| 3. Monitor and extend | Warranty, stocktake, combined reports; then the next module using the same contract |

## 8. Decisions needed

| No. | Question | Recommendation |
|---|---|---|
| D1 | System name | OpsHub, shown as "PSBU OpsHub" |
| D2 | Should projects become a shared list with a PM for each? | Yes |
| D3 | Keep the address psbu.duckdns.org? | Yes |
| D4 | Which modules are likely next? | Name one or two now, so the core can be checked against them |
| D5 | Inventory decisions | See `inventory-module-design.md`, Section 12 |
