# Paper requirements: "The Interface Is a Variable" → interface-compiler

Status: **FROZEN (v1)**, plus the owner addendum in §8. This is the binding spec for the compiled view document's contract and for the element-to-affordance mapping. `PLAN.md` and the code must match it. Any change needs the owner's sign-off and a schema version bump.

Source paper: "The Interface Is a Variable: Measuring the Cost and Reliability of Purpose-Built UI Representations for LLM Agents", <https://akashnaren.github.io/research/agent-native-ui/paper.pdf> (sha256 `fdbd9cf0f27cb4e27c3f360dda6b092b2a256e077ccdf3bbd94678e28e4599f8`). Section numbers below refer to that PDF.

## 1. Contract (paper §2, §4.1)

- Exactly 4 top-level keys: `view`, `state`, `entities`, `affordances`. All extensions live under ONE optional top-level key, `x`. There is no top-level `provenance` key.
- Each affordance has exactly `id`, `enabled`, and `input`.
  - `input` is a JSON Schema: `{"type":"object","properties":{...},"required":[...]}`.
  - A no-argument action uses `{"type":"object","properties":{}}`.
- Extras go only under `affordance.x`:
  - `reason`, `tag` (`safe` | `mutating`), `label`, `locator`, `signature`, `grain`.
  - `source` (`compiled` | `owner`).
  - `verified` (`unverified` | `probed_ok` | `probed_failed` | `stopped_before_commit`) and `verified_at`.
- A mutating action on a real site can never reach `probed_ok`.
- Report the token cost of `x` separately from the core document.
- `view` is a semantic screen name such as `product`, `catalog` or `checkout`. It comes from the JSON-LD `@type`, the route, or the optional naming model. The route and the structure hash go in `x.signature`.
- `state` holds flat session fields: control values, ARIA states, and visible session counters such as a cart badge or the signed-in state.
- `entities` is an object keyed by entity name. Each value is a record or a list, with stable ids that action arguments reference. Only on-screen entities are listed, paged with an `x.page` cursor.
- Ids are task-level `verb_object` snake_case names (`open_product`, `set_size`, `add_to_cart`, `go_checkout`), NEVER DOM paths. The element's location goes in `x.locator`.
  - Repeated card links or buttons collapse, by repeated-subtree signature, into ONE parameterized affordance, e.g. `open_product(product_id)`.
- Matched grain: a per-session registry keeps the set of operations stable across looks. An action seen earlier but missing from the current screen stays listed with `enabled: false` and `x.reason: "not on this view"`.
- Enums are live truth: options that are disabled, `aria-disabled`, or sold out are dropped.
- Invariants:
  - Never advertise an action that would be rejected. This is a testable property, measured by the checker.
  - `enabled: true` means "worth attempting now", never "guaranteed to succeed".
  - The agent replies with one JSON action: `act(affordance_id, args)`.

## 2. The paper's printed example (target shape, §4.1)

```json
{"view":"product",
 "state":{"product_id":"tee-navy","selected_size":"L","cart_count":1,"address":"","order_count":0},
 "entities":{
   "product":{"id":"tee-navy","name":"Navy Crew Tee","price":28,"sizes_in_stock":["S","M","L"]},
   "cart":[{"product_id":"tee-navy","name":"Navy Crew Tee","size":"L","price":28}]},
 "affordances":[
   {"id":"open_product","enabled":true,"input":{"type":"object","properties":{"product_id":{"type":"string"}},"required":["product_id"]}},
   {"id":"set_size","enabled":true,"input":{"type":"object","properties":{"size":{"type":"string","enum":["S","M","L"]}},"required":["size"]}},
   {"id":"add_to_cart","enabled":true,"input":{"type":"object","properties":{}}},
   {"id":"go_catalog","enabled":true,"input":{"type":"object","properties":{}}},
   {"id":"go_checkout","enabled":true,"input":{"type":"object","properties":{}}},
   {"id":"set_address","enabled":false,"input":{"type":"object","properties":{"address":{"type":"string"}},"required":["address"]}},
   {"id":"pay","enabled":false,"input":{"type":"object","properties":{}}}]}
```

## 3. Widget mapping (one tested function per kind)

| Element | Becomes |
|---|---|
| Link | `go_<view>`. Repeated once per entity → `open_<entity>(<entity>_id)`. |
| Button outside a form | A verb with empty input. |
| Button, chip, or radio group | One `set_<field>` whose enum lists the enabled options. The selection goes to `state`. |
| Select | `set_<field>` with an enum of the enabled options. |
| Checkbox or switch | `set_<field>` with a boolean. |
| Text input or textarea outside a form | `set_<field>` with a string and the HTML constraints (pattern, min/max, length). |
| Text input or textarea inside a form | A property of `submit_<form>`, with `required` taken from the form. Current values mirror into `state`. |
| Form | `submit_<form>`, or `search` for `role=search`. The grain choice is recorded in `x.grain`. |
| Tabs | `open_tab` with an enum, plus `state.selected_tab`. |
| Disclosure or accordion | `toggle_<section>`. `aria-expanded` goes to `state`. |
| Menu | Items are listed when the menu is open. When it is collapsed they are `enabled: false` with `x.reason: "menu closed"`, plus an `open_menu` affordance. |
| Combobox or listbox | An enum if the options are known, otherwise a string. |
| Slider or spinbutton | A number with `aria-valuemin` / `aria-valuemax`. |
| Open dialog | Every affordance outside it is `enabled: false` with `x.reason: "blocked by dialog"`. |
| Pagination | `next_page` and `go_page(n)`. |
| Owner path (§8.4) | The same contract, so a site owner can drop in a serializer with `x.source: "owner"` and agents notice nothing. |

## 4. `act()` and counters

- `act()` rejects calls to `enabled: false` affordances without executing them and counts them as **ignored affordances**.
- **Illegal** calls (executed, then rejected or without effect) and **malformed** calls (unknown id, args that fail the schema, wrong shape) are counted separately.
- An `echo_errors` flag defaults to on for the product. Set it off to replicate the paper, whose view-document loop did not echo backend errors (§6.3, §9).
- Mutating actions still return a preview plus a confirm token. Checkout, pay, delete, and send stay hard-blocked.

## 5. Evaluation (paper §4-6)

- Arms:
  - an accessibility-tree arm (C2-like);
  - a flat-tools arm generated from the SAME affordances (C3-like);
  - the compiled view document (C4-like).
- All arms use identical shared prompt rules.
- Run the §6.5 ablation: the document with `enabled` and the argument constraints stripped.
- Headline grading is deterministic only. There is no LLM judge; any judge is secondary and off by default.
- Include refusal tasks (sold-out or unavailable), reported separately.
- Run at temperature 0 with a 20-step cap. Report a paired per-task bootstrap 95% CI and the cost-reliability frontier.
- Metrics:
  - success, tokens, steps, illegal, malformed, ignored-affordance rate, latency;
  - a model-free observation-cost baseline (tokens per look, fixed tokenizer).
- Eval A adds an oracle check: replay the Mind2Web human trajectories as affordance calls to measure oracle executability.

## 6. Reference set (approved)

- 21 hand-labeled real pages with 57 tasks, used as an eval fixture and as the **upper bound** (the paper's hand-written document plays the same role).
- Layout under `reference/`:
  - `pages.csv` is the index.
  - `docs/<slug>.json` holds the hand-written view document, strict 4 keys.
  - `tasks/<slug>.json` holds tasks to replay for the oracle-executability check.
  - `snapshots/` holds per page the saved HTML, a11y tree, and screenshot.
  - `selfcheck/` holds the human self-agreement data.
- Each compiled document is compared with `docs/` for agreement on fields, affordance ids, `enabled`, and enums, and `tasks/` are replayed.
- Ceiling: human self-agreement is 83 % on affordances and 100 % on `enabled`. Diff scores are read against that ceiling.
- The fixture directory ships empty and the files are copied in later. The harness must run cleanly with zero pages.

## 7. Wording

- Always say "compiled view document". Never write "C4" for our output, and never call it a standard. The paper says it "is not a proposed standard".
- State plainly that our `enabled` flag is page evidence plus probing, not backend truth. The paper calls this path "lossy, must be checked" (§8.3, Table 4).
- Compiling in the client (in the rendered browser page) is how single-page apps are handled. That is where their view state lives (§8.2).

## 8. Fixed converter rules R1-R5 (owner addendum, 2026-11-03)

These rules keep compiled output comparable with the reference set. They refine §1 and §3, and where they differ, they win.

- **R1.** Emit one `open_<entity>(id)` per entity type. Emit secondary row links only when a task needs them.
- **R2.** Controls behind a login are `enabled: false` (`x.reason: "requires sign-in"`).
- **R3.** Options hidden inside closed menus become free-text inputs, not enums.
- **R4.** Lists use a fixed length of 10.
- **R5.** Never emit flow-step affordances that aren't legal on the current view.

R5 refines the matched-grain rule in §1. Off-view **flow steps** (address, shipping, payment, pay, place order, …) are omitted rather than carried as `enabled: false`. Other earlier actions are still carried with `"not on this view"`. A flow step that is on the current view but currently disallowed is still listed with `enabled: false`. The paper's §4.1 listing, where `set_address` and `pay` appear disabled on the product view, is reproduced only by an explicit paper-replication option (`carry_flow_steps`), which is off by default.

## 9. Home

- Public repo: `akashnaren/interface-compiler`. Description: "Compile any website into an agent-usable interface with typed, checked actions."
- The paper source lives under `paper/` (the PDF plus its markdown source).
- Everything is repo-relative. No secrets, tokens, internal hostnames, or personal infrastructure details are committed.
