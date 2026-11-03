# interface-compiler: v1 build plan

> Compile any website into an agent-usable interface with typed, checked actions.

This plan is for the builder. It is meant to be executed top to bottom without guessing. The binding spec for the document contract and the element mapping is [`docs/PAPER-REQUIREMENTS.md`](docs/PAPER-REQUIREMENTS.md), which is **frozen**. If this plan and that file ever disagree, that file wins, and the builder fixes this plan in the same commit.

Contents:

0. Ground rules
1. What v1 is
2. Repository and module layout
3. Data model and JSON Schema (frozen v1)
4. Extraction pipeline
5. Element → affordance mapping (the centerpiece), incl. §5.6 fixed converter rules R1-R5
6. Affordance id stability scheme
7. Checker design
8. Runtime: sessions, `act`, counters
9. Delivery: MCP server, HTTP API, CLI
10. Optional local naming models
11. Evaluation harnesses
12. Dependencies (pinned majors)
13. Test plan
14. Build order (milestones M0-M12) with acceptance criteria
15. Open items the builder must confirm, not guess

---

## 0. Ground rules (non-negotiable)

- **Cost.** $0. No paid APIs. The only models allowed are optional local ones (Ollama). Everything must work with them disabled.
- **Public repo.** No secrets, tokens, internal hostnames, private-network device names, or personal infrastructure details. Examples use `localhost`, `127.0.0.1`, or `<your-host>`. Tokens come from environment variables and never appear in files.
- **Portable.** Every path is repo-relative or XDG-relative. Nothing assumes a particular machine.
- **Git.** Small commits, one logical change each. Never `--no-verify`, never force-push. No CI or workflow files (`.github/workflows` etc.) in v1.
- **Docs.** Only `README.md` and `PLAN.md`, plus `docs/PAPER-REQUIREMENTS.md` (frozen spec) and `paper/`. No other markdown docs.
- **Wording.** Say "compiled view document". Never write "C4" for our output, and never call it a standard.
- **Web conduct** (product, tests, and evals alike):
  - No logins and no saved cookies; every browser context is ephemeral.
  - Respect robots.txt. Skip sites that ban bots or AI agents, need a login, or are adult, gambling, or banking sites.
  - Use an honest user agent and a low request rate.
  - Never evade bot walls or captchas. A wall is logged as `blocked` and the run moves on.
- **Test only on real public sites, never on demo sites** (no saucedemo, opencart demo, books.toscrape, and so on). Unit tests use local HTML fixtures, which are not "sites".

## 1. What v1 is

v1 is one Python core with three thin front doors: a CLI, an MCP server, and an HTTP API. Given a public URL, it:

1. opens the page in headless Chromium (Playwright, viewport 1280×800, the paper's setting);
2. reads the accessibility (AX) tree, DOM form facts, JSON-LD/microdata, and WebMCP tools;
3. maps every interactive element to an affordance (§5);
4. emits a **compiled view document**: `view`, `state`, `entities`, `affordances`, plus optional `x`;
5. on `act`:
   - validates `args` against the affordance's `input`;
   - gates mutating actions (preview + confirm token; checkout, pay, delete, and send are hard-blocked);
   - runs the action with non-GET requests intercepted;
   - checks the predicted effect against the observed one, demoting liars.

v1 is not:

- per-site manifests;
- logins or saved cookies;
- a public endpoint, CI, or a hosted service;
- a vision model;
- a paid LLM.

## 2. Repository and module layout

```text
interface-compiler/
├── README.md
├── PLAN.md
├── LICENSE                      # owner picks; builder leaves a TODO in README until then
├── pyproject.toml               # uv-managed; package `interface_compiler`; script `interface-compiler`
├── uv.lock
├── .gitignore                   # .venv, __pycache__, .pytest_cache, runs/, *.sqlite
├── docs/
│   └── PAPER-REQUIREMENTS.md    # frozen spec (already committed)
├── paper/
│   ├── paper.pdf                # fetched in M0, sha256 verified
│   ├── paper.md                 # markdown source (see §15 item 1)
│   └── SHA256SUMS
├── reference/                   # hand-labeled upper-bound fixture (21 pages, 57 tasks); ships EMPTY
│   ├── pages.csv                # later: slug,url,… index
│   ├── docs/.gitkeep            # later: <slug>.json = hand-written view doc, strict 4 keys
│   ├── tasks/.gitkeep           # later: <slug>.json = tasks for oracle replay
│   ├── snapshots/.gitkeep       # later: saved HTML, a11y tree, screenshot per page
│   └── selfcheck/.gitkeep       # later: human self-agreement data (ceiling: 83 % affordances, 100 % enabled)
├── evals/
│   └── sites/
│       └── smoke.txt            # 3 live smoke URLs (§13.4)
├── src/interface_compiler/
│   ├── __init__.py              # __version__
│   ├── contract/                # the frozen document contract
│   │   ├── __init__.py
│   │   ├── models.py            # pydantic models: ViewDoc, Affordance, AffordanceX, DocX, Effect, ActResult
│   │   ├── schemas/
│   │   │   ├── view-doc.v1.json # JSON Schema (§3.2)
│   │   │   └── effect.v1.json   # JSON Schema for act() effect (§3.4)
│   │   ├── validate.py          # validate_doc(), validate_effect(), validate_args(affordance, args)
│   │   ├── transforms.py        # strip_x() (paper-strict), ablate() (§6.5 ablation), to_flat_tools()
│   │   └── tokens.py            # count_tokens(core) vs count_tokens(x); fixed tokenizer o200k_base
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── engine.py            # one Browser per process; context factory (ephemeral, 1280x800)
│   │   ├── collect.js           # in-page collector: DOM facts + hit tests + validity (§4 step 3)
│   │   ├── webmcp_shim.js       # init script capturing WebMCP tool registrations (§4 step 4)
│   │   ├── facts.py             # PageFacts / ElementFact dataclasses + collect_facts(page)
│   │   └── raw.py               # raw_snapshot(page): Playwright aria snapshot (baseline / fallback)
│   ├── policy/
│   │   ├── __init__.py
│   │   ├── robots.py            # robots.txt fetch+cache (protego); AI-agent ban detection
│   │   ├── walls.py             # bot-wall / captcha / login-wall detection
│   │   ├── exclusions.py        # adult / gambling / banking exclusion
│   │   └── ratelimit.py         # per-host min interval, per-site look budget
│   ├── extract/                 # page facts -> doc parts (rules first)
│   │   ├── __init__.py
│   │   ├── landmarks.py         # landmark of each element; skeleton hash
│   │   ├── repeats.py           # repeated-subtree signatures -> groups
│   │   ├── structured.py        # JSON-LD + microdata (extruct) -> typed objects, potentialAction
│   │   ├── view.py              # view name + x.signature
│   │   ├── state.py             # flat state fields
│   │   ├── entities.py          # entities (JSON-LD objects + repeated groups), ids, paging
│   │   ├── lexicon.py           # verb vocabulary, view lexicon, field aliases, hard-block verbs
│   │   └── naming.py            # slugify, field names, verb_object composition
│   ├── mapping/                 # CENTERPIECE: one function per element kind (§5)
│   │   ├── __init__.py          # map_element() dispatch table + MapContext + MapResult
│   │   ├── input_schema.py      # HTML constraints -> JSON Schema property
│   │   ├── enabled.py           # universal enabled/reason rules
│   │   ├── link.py              # map_link, map_link_group
│   │   ├── button.py            # map_button
│   │   ├── choice.py            # map_choice_group (button/chip/radio groups)
│   │   ├── select.py            # map_select
│   │   ├── toggle.py            # map_checkbox (checkbox, switch)
│   │   ├── text.py              # map_text_field (input types, textarea), outside forms
│   │   ├── form.py              # map_form (grain decision, submit_<form>/search/verb)
│   │   ├── tabs.py              # map_tabs
│   │   ├── disclosure.py        # map_disclosure (disclosure, accordion, details/summary)
│   │   ├── menu.py              # map_menu
│   │   ├── combobox.py          # map_combobox (combobox, listbox)
│   │   ├── range.py             # map_range (slider, spinbutton, input[type=range])
│   │   ├── dialog.py            # apply_dialog (post-pass) + map_dialog_close
│   │   ├── pagination.py        # map_pagination
│   │   ├── declared.py          # map_schema_org_action (JSON-LD potentialAction)
│   │   └── webmcp.py            # map_webmcp_tool
│   ├── compile.py               # pipeline orchestrator: facts -> ViewDoc (§4)
│   ├── registry.py              # per-session matched-grain registry + id assignment (§6)
│   ├── cache.py                 # sqlite at $XDG_CACHE_HOME/interface-compiler/cache.sqlite
│   ├── checker/                 # §7
│   │   ├── __init__.py
│   │   ├── tags.py              # safe | mutating | hard_blocked classification
│   │   ├── precheck.py          # static pre-check every look
│   │   ├── intercept.py         # route handler: abort non-GET, record request shape
│   │   ├── probe.py             # throwaway-context probes (safe run, stop-before-commit)
│   │   ├── effect.py            # predict() / observe() / compare()
│   │   ├── demotion.py          # scoped, expiring demotions (sqlite)
│   │   └── confirm.py           # one-time confirm tokens
│   ├── runtime/                 # §8
│   │   ├── __init__.py
│   │   ├── sessions.py          # SessionManager: ids, idle timeout, caps, doc_rev
│   │   ├── actions.py           # perform(affordance, args) via x.locator
│   │   ├── counters.py          # illegal / malformed / ignored / stale / blocked
│   │   └── service.py           # Service.open/act/observe/back/close/raw_snapshot (the ONE core API)
│   ├── naming_models/           # §10, optional
│   │   ├── __init__.py
│   │   ├── ollama.py            # httpx client: /api/embed, /api/chat (JSON mode, temperature 0)
│   │   └── namer.py             # embed-to-verb, LLM-name-leftovers, template cache
│   ├── server/                  # §9
│   │   ├── __init__.py
│   │   ├── mcp_server.py        # MCP tools over stdio + streamable HTTP
│   │   ├── http_api.py          # FastAPI /v1/* (+ mounts MCP at /mcp)
│   │   └── security.py          # bind guard, bearer auth, Origin validation
│   ├── evals/                   # §11
│   │   ├── __init__.py
│   │   ├── mind2web.py          # Eval A (offline)
│   │   ├── live.py              # Eval B (Online-Mind2Web sites, safe only)
│   │   ├── reference.py         # reference/ loader + per-page diff score + oracle replay
│   │   ├── arms.py              # agent arms: a11y tree, flat tools, compiled doc, ablation
│   │   ├── agent.py             # local-model agent loop (temp 0, 20-step cap)
│   │   ├── grading.py           # deterministic graders
│   │   ├── stats.py             # paired bootstrap CI, frontier
│   │   └── report.py            # JSON + markdown tables into runs/<timestamp>/
│   └── cli.py                   # Typer app, entry point `interface-compiler`
└── tests/
    ├── conftest.py              # fixture HTTP server (127.0.0.1, random port), browser fixture
    ├── fixtures/
    │   ├── html/                # one file per element kind + composite pages (§13.1)
    │   ├── reference_sample/    # synthetic reference pair for loader/diff tests
    │   └── mind2web_sample/     # 3 tiny hand-made rows in Mind2Web shape (no download)
    ├── unit/                    # pure-python tests (no browser)
    ├── mapping/                 # one test file per mapping kind (browser + fixtures)
    ├── checker/
    ├── server/
    ├── evals/
    └── live/                    # marked @pytest.mark.live, skipped unless --live
```

Rules for this layout:

- `runtime/service.py` is the only core API. The CLI, MCP server, and HTTP API are thin adapters (no logic beyond argument parsing and serialization), so all three behave identically.
- `mapping/*` functions are pure over `ElementFact` inputs (no Playwright calls). They are tested with facts collected from fixtures and with hand-built facts.
- Runs and reports go to `runs/` (gitignored).

## 3. Data model and JSON Schema (FROZEN v1)

### 3.1 Document shape

Exactly as in `docs/PAPER-REQUIREMENTS.md` §1:

```text
ViewDoc
  view: str                       # semantic screen name, ^[a-z][a-z0-9_]*$
  state: {str: str|int|float|bool|null}   # FLAT
  entities: {str: Record | [Record]}      # keyed by entity name; records are flat-ish objects
  affordances: [Affordance]
  x?: DocX                        # the ONLY extension point at top level

Affordance
  id: str                         # verb_object snake_case, ^[a-z][a-z0-9_]*$
  enabled: bool
  input: {"type":"object","properties":{...},"required"?:[...]}
  x?: AffordanceX

AffordanceX (all optional)
  reason: str                     # why enabled:false (or why demoted), human-readable, stable phrases (§5.2)
  tag: "safe" | "mutating"
  label: str                      # visible/accessible name, e.g. "Add to bag"
  locator: Locator                # how to find and invoke it (§3.3)
  signature: str                  # stable identity hash (§6.1)
  grain: "single" | "field" | "form" | "collapsed" | "declared"
  source: "compiled" | "owner"
  verified: "unverified" | "probed_ok" | "probed_failed" | "stopped_before_commit"
  verified_at: RFC 3339 timestamp

DocX (all optional)
  schema_version: "1"
  source: "compiled" | "owner"
  url: str
  title: str
  signature: {route: str, skeleton_hash: str, template: str}
  page: {<entity_name>: {offset: int, limit: int, total: int|null, next: str|null}}
  state_from: {<state_key>: "control"|"aria"|"badge"|"session"|"url"}
  entities_from: {<entity_name>: "jsonld"|"microdata"|"repeat"|"webmcp"}
  precheck: {ok: int, failed: int}
  registry: {carried: int, dropped: int}
  blocked: {kind: "robots"|"bot_wall"|"login"|"excluded"|"captcha", detail: str} | null
```

Serialization rules:

- Omit `required` when it is empty (the paper prints `{"type":"object","properties":{}}`).
- Key order is `view, state, entities, affordances, x`.
- Affordances are sorted by first-seen order in the session registry, so order is stable across looks.
- `paper-strict` mode = `strip_x(doc)`, which yields exactly 4 keys.

### 3.2 `view-doc.v1.json` (write exactly this, then extend only inside `x`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:interface-compiler:schema:view-doc:1",
  "title": "Compiled view document, v1",
  "type": "object",
  "required": ["view", "state", "entities", "affordances"],
  "additionalProperties": false,
  "properties": {
    "view": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
    "state": {
      "type": "object",
      "additionalProperties": {"type": ["string", "number", "integer", "boolean", "null"]}
    },
    "entities": {
      "type": "object",
      "additionalProperties": {
        "oneOf": [
          {"$ref": "#/$defs/record"},
          {"type": "array", "items": {"$ref": "#/$defs/record"}}
        ]
      }
    },
    "affordances": {"type": "array", "items": {"$ref": "#/$defs/affordance"}},
    "x": {"$ref": "#/$defs/doc_x"}
  },
  "$defs": {
    "record": {
      "type": "object",
      "additionalProperties": {
        "type": ["string", "number", "integer", "boolean", "null", "array"],
        "items": {"type": ["string", "number", "integer", "boolean", "null"]}
      }
    },
    "affordance": {
      "type": "object",
      "required": ["id", "enabled", "input"],
      "additionalProperties": false,
      "properties": {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "enabled": {"type": "boolean"},
        "input": {"$ref": "#/$defs/input"},
        "x": {"$ref": "#/$defs/affordance_x"}
      }
    },
    "input": {
      "type": "object",
      "required": ["type", "properties"],
      "additionalProperties": false,
      "properties": {
        "type": {"const": "object"},
        "properties": {"type": "object", "additionalProperties": {"$ref": "#/$defs/prop"}},
        "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": true, "minItems": 1}
      }
    },
    "prop": {
      "type": "object",
      "required": ["type"],
      "additionalProperties": false,
      "properties": {
        "type": {"enum": ["string", "number", "integer", "boolean", "array"]},
        "enum": {"type": "array", "minItems": 1},
        "format": {"enum": ["email", "uri", "date", "time", "date-time", "tel"]},
        "pattern": {"type": "string"},
        "minLength": {"type": "integer", "minimum": 0},
        "maxLength": {"type": "integer", "minimum": 0},
        "minimum": {"type": "number"},
        "maximum": {"type": "number"},
        "multipleOf": {"type": "number", "exclusiveMinimum": 0},
        "items": {"$ref": "#/$defs/prop"}
      }
    },
    "affordance_x": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "reason": {"type": "string"},
        "tag": {"enum": ["safe", "mutating"]},
        "label": {"type": "string"},
        "locator": {"$ref": "#/$defs/locator"},
        "signature": {"type": "string"},
        "grain": {"enum": ["single", "field", "form", "collapsed", "declared"]},
        "source": {"enum": ["compiled", "owner"]},
        "verified": {"enum": ["unverified", "probed_ok", "probed_failed", "stopped_before_commit"]},
        "verified_at": {"type": "string", "format": "date-time"}
      }
    },
    "locator": {
      "type": "object",
      "required": ["kind"],
      "properties": {
        "kind": {"enum": ["ax", "form", "group", "repeat", "jsonld", "webmcp", "registry"]},
        "role": {"type": "string"},
        "name": {"type": "string"},
        "landmark": {"type": "string"},
        "nth": {"type": "integer", "minimum": 0},
        "css": {"type": "string"},
        "fields": {"type": "object", "additionalProperties": {"type": "string"}},
        "options": {"type": "object", "additionalProperties": {"type": "string"}},
        "repeat": {"type": "string"},
        "item_key": {"type": "string"},
        "url_template": {"type": "string"},
        "method": {"type": "string"},
        "tool": {"type": "string"},
        "named_by": {"enum": ["rule", "embed", "llm", "declared"]}
      }
    },
    "doc_x": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "schema_version": {"const": "1"},
        "source": {"enum": ["compiled", "owner"]},
        "url": {"type": "string"},
        "title": {"type": "string"},
        "signature": {
          "type": "object",
          "properties": {"route": {"type": "string"}, "skeleton_hash": {"type": "string"}, "template": {"type": "string"}}
        },
        "page": {"type": "object"},
        "state_from": {"type": "object"},
        "entities_from": {"type": "object"},
        "precheck": {"type": "object"},
        "registry": {"type": "object"},
        "blocked": {"type": ["object", "null"]}
      }
    }
  }
}
```

Notes for the builder:

- `locator` keeps `additionalProperties` open on purpose. It is an internal invocation recipe, and the owner path (`source: "owner"`) may carry its own.
- Every other object is closed.
- `prop.description` is intentionally absent. Human text goes in `x.label`, so the core stays as lean as the paper's.
- Records allow one level of scalar arrays (the paper's `sizes_in_stock`). Nested objects are flattened (`price.amount` → `price`, currency → `price_currency`).

### 3.3 Locator semantics

| `kind` | Meaning | Invocation in `runtime/actions.py` |
|---|---|---|
| `ax` | Single element by role + accessible name, scoped to landmark, `nth` among equal matches; `css` fallback | `page.get_by_role(role, name=name, exact=True).nth(nth)` within landmark locator; fallback `page.locator(css)` |
| `form` | A form; `fields` maps input property → field css; submit button css in `css` | fill each field from args, then click submit |
| `group` | Choice group / select / tabs / menu; `options` maps enum value → option css (or option value for `<select>`) | click / `select_option` the mapped option |
| `repeat` | Collapsed parameterized action; `repeat` = item container css, `item_key` = how an item yields its entity id (`href:/p/:id`, `data-id`, `jsonld:@id`); `css` = target within item | find the item whose key equals the arg, click target |
| `jsonld` | schema.org `potentialAction`; `url_template`, `method` | GET → navigate to expanded template; non-GET → treated as mutating form submit |
| `webmcp` | WebMCP tool; `tool` = tool name | call captured `execute` in page with args |
| `registry` | Carried from an earlier look ("not on this view") | never invoked; act returns `disabled` |

### 3.4 `effect.v1.json` and act response

```text
ActResult
  status: "ok" | "stale" | "disabled" | "invalid_args" | "needs_confirmation" | "blocked" | "error"
  doc_rev: int
  doc: ViewDoc
  effect?: {
    predicted: {kind: "navigate"|"state_change"|"aria_change"|"entities_change"|"dialog"|"none"|"unknown", detail: obj}
    observed:  {url_before, url_after, view_before, view_after, state_diff: obj, entities_diff: obj,
                main_status: int|null, dialogs: [str], console_errors: [str]}
    match: bool | null            # null when nothing was executed
    blocked_requests: [{method, url, fields: {name: value|"<redacted>"}, reason}]
    demoted: [{affordance_id, reason, expires_at, expires_after_looks}]
  }
  preview?: {method, url, fields: {...}, client_validation: {valid: bool, messages: [str]}}   # needs_confirmation
  confirm_token?: str                                                                         # needs_confirmation
  error?: {code: str, message: str, details?: obj}        # present iff echo_errors=true and something failed
  counters: {illegal: int, malformed: int, ignored: int, stale: int, blocked: int, acts: int}
```

`effect.v1.json` uses `$id: "urn:interface-compiler:schema:effect:1"` and encodes exactly this.

## 4. Extraction pipeline (`compile.py`)

Each look runs these steps in order. Rules decide structure, `enabled`, and schemas. Models (§10) may only rename.

1. **Policy gate** (first `open` per host, and on navigation to a new host):
   - robots.txt check;
   - exclusion list;
   - rate limiter.
   On failure, return a doc with `view: "blocked"`, `state: {}`, `entities: {}`, `affordances: []`, and `x.blocked` set. No crawling past that point.
2. **Load and settle.**
   - Wait for `domcontentloaded`, then `networkidle` with a 5 s cap, then 300 ms of DOM quiet (a MutationObserver window), with a total settle cap of 8 s.
   - Run the wall checks (`policy/walls.py`). A bot wall or captcha returns `x.blocked.kind = "bot_wall" | "captcha"`; a login wall returns `"login"`.
3. **Collect facts** (`browser/facts.py` and `collect.js`).
   - CDP `Accessibility.getFullAXTree` through `context.new_cdp_session(page)`. Keep nodes with interactive roles (`link, button, checkbox, radio, switch, textbox, searchbox, combobox, listbox, option, menu, menuitem, menuitemcheckbox, menuitemradio, tab, tablist, slider, spinbutton, dialog, alertdialog`) plus landmarks and headings.
   - Join each node to its DOM element by `backendDOMNodeId` (`DOM.describeNode` / `DOM.resolveNode`), then evaluate `collect.js` on those elements in one round trip.
   - For each element, `collect.js` returns:
     - `tag`, `type`, `name`, `id`, `href` (absolute), `form` (owner form index), `method`/`action` of the owner form;
     - attributes `disabled`, `readonly`, `aria-disabled`, `inert` (self or ancestor), `hidden`, `aria-hidden`;
     - `required`, `pattern`, `min`, `max`, `step`, `minlength`, `maxlength`, `value`, `checked`, `selected`;
     - `<option>` list with `{value, label, disabled}`;
     - the ARIA states `aria-expanded`, `aria-selected`, `aria-checked`, `aria-pressed`, `aria-current`, `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, `aria-haspopup`, `aria-controls`;
     - bbox, `visible` (non-zero size and not `visibility:hidden`/`display:none`);
     - `covered` (hit test: `document.elementFromPoint` at the bbox centre is not the element or a descendant);
     - `in_viewport`;
     - for forms, `form.checkValidity()` and per-field `validationMessage`;
     - `landmark` (nearest ancestor landmark role + its accessible name);
     - `css` (a unique, short selector, preferring `#id`, then `[name]`, then a `:nth-of-type` path);
     - `skeleton_path` (tag+role path for the repeat detector);
     - `label_text` (`<label for>`, wrapping label, `aria-labelledby`, placeholder, `legend`);
     - `group_key` (radio `name`, `role=radiogroup` parent, `fieldset`, toolbar of `aria-pressed` chips).
   - Also capture an open modal: `<dialog open>` with `:modal`, or `[role=dialog|alertdialog][aria-modal=true]` that is visible.
4. **Structured data.**
   - `extruct` on `page.content()` for JSON-LD and microdata, yielding typed objects and `potentialAction`.
   - WebMCP: `webmcp_shim.js` is added with `context.add_init_script`. It wraps `document.modelContext` and `navigator.modelContext`, both the `registerTool` and the `provideContext({tools})` forms, recording `{name, description, inputSchema, annotations}` and keeping `execute` callable through `window.__icWebMCP.call(name, args)`. The builder confirms the API surface against the current proposal (§15 item 3).
5. **Groups.**
   - `repeats.py` computes for every element container a structural signature: `sha1(tag/role path of the subtree, depth ≤ 4, text stripped)`.
   - Sibling sets of ≥ 3 nodes sharing a signature, each containing a link or button, form a **repeat group** (cards, rows, list items, result items).
   - Links inside `main` prose (inline `<a>` in `<p>`/`<li>` text with no repeat group) form the special group `link`.
   - Each repeat group marks one **primary link** per item (R1, §5.6). Every other link in the item is a **secondary row link**.
6. **Map** every element / group / form / declared action with the `mapping/` dispatch (§5). The output is candidate affordances plus `state` contributions plus entity contributions.
7. **Declared wins.** WebMCP tools and schema.org actions take precedence over inferred affordances. When a declared action targets the same form (same action URL path) or the same URL template, the inferred affordance is dropped.
8. **Entities** (`entities.py`):
   - JSON-LD/microdata objects (`Product`, `Offer`, `Event`, `Article`, `Recipe`, `JobPosting`, `LocalBusiness`, `BreadcrumbList`, …) become a record keyed by the snake_case type (`product`).
   - Repeat groups become a list keyed by the entity name: the JSON-LD `ItemList` member type if present, else a lexicon match on container/heading text, else the naming model, else `item`. The list key is plural (`products`); a single main object is singular (`product`).
   - Groups that resolve to the same entity type are merged into one list (deduplicated by id, DOM order), because R1 allows only one `open_<entity>` per type.
   - Entity ids, in this order:
     1. JSON-LD `@id` / `sku` / `productID`;
     2. `data-id`/`data-*-id`;
     3. the id-like path segment of the item's link (`/p/123` → `123`, `/wiki/Foo` → `Foo`);
     4. `slug(title)[:40]` + `-` + `sha1(href)[:6]`.
   - Record fields: `id`, `name` (heading or link text), and `price`/`price_currency`/`rating`/`date` when present. Keep at most 6 scalar fields; the rest are dropped.
   - Paging (R4, §5.6): every list has a **fixed length of 10**. It holds the first 10 rendered (visible) items in DOM order, independent of viewport or scroll position, so docs compare across machines. `x.page.<entity> = {offset, limit: 10, total, next}`, where `next` is an opaque cursor accepted by `observe(page=...)`, which returns the next 10.
9. **State** (`state.py`):
   - control values: choice → `selected_<field>`, text → `<field>`, checkbox → `<field>`;
   - ARIA: `selected_tab`, `<section>_expanded`, pressed chips;
   - counters: `<thing>_count` from badges (an element whose accessible name or class matches the counter lexicon, e.g. cart/bag/basket/notifications, holding a number);
   - `signed_in` (bool, true if a sign-out/account-name affordance exists);
   - `page` (current pagination `aria-current`).
   Provenance goes in `x.state_from`. No `title` and no raw URL in `state`; they go in `x.title` and `x.url`.
10. **View** (`view.py`), in precedence order:
    1. `x.source == "owner"` → the owner's view;
    2. JSON-LD main-entity type map (`Product`→`product`, `ItemList`/`CollectionPage`/`OfferCatalog`→`catalog`, `SearchResultsPage`→`search_results`, `CheckoutPage`→`checkout`, `Article`/`NewsArticle`/`BlogPosting`→`article`, `FAQPage`→`faq`, `ProfilePage`→`profile`);
    3. `og:type`;
    4. the route lexicon (`/cart`→`cart`, `/checkout`→`checkout`, `/search`/`?q=`→`search_results`, `/login`→`sign_in`, `/docs`/`/doc`→`docs`, …);
    5. the naming model (if on);
    6. the first static route segment slug;
    7. `page`.
    `x.signature`:
    - `route` is the path with ids normalized (`/p/123` → `/p/:id`, numbers → `:n`, uuids/hex ≥ 8 → `:id`, slugs in known entity positions → `:slug`);
    - `skeleton_hash` is `sha1(landmark + heading-level skeleton)[:12]`;
    - `template` is `sha1(route + skeleton_hash)[:12]`.
11. **Ids** (`registry.py`, §6): assign stable ids, resolve collisions, and carry earlier non-flow ids as `enabled:false` / `"not on this view"`. Flow-step ids are never carried (R5, §5.6).
12. **Enabled post-passes**, in this order:
    1. dialog (`apply_dialog`);
    2. collapsed menus;
    3. login-gated controls (R2, §5.6);
    4. checker pre-check (§7.2);
    5. active demotions (§7.5);
    6. policy hard-blocks (§7.1).
    The first reason that applies wins and is written to `x.reason`.
13. **Tag** each affordance `safe` | `mutating` (§7.1), and set `x.source` and `x.verified`.
14. **Validate** against `view-doc.v1.json` (always, in tests and in production; a failure is a bug and raises).

## 5. Element → affordance mapping (the centerpiece)

### 5.1 Function contract

```python
# mapping/__init__.py
@dataclass(frozen=True)
class MapContext:
    page_url: str
    view_hint: str | None
    landmark_names: dict[str, str]
    lexicon: Lexicon
    namer: Namer | None          # optional model naming (§10); None = rules only

@dataclass
class MapResult:
    affordances: list[Affordance]          # ids are PROVISIONAL (registry finalizes, §6)
    state: dict[str, Scalar]               # contributions to state
    state_from: dict[str, str]
    entities: dict[str, Record | list[Record]]  # contributions (repeat groups, declared)

def map_link(el: ElementFact, ctx: MapContext) -> MapResult: ...
def map_link_group(group: RepeatGroup, ctx: MapContext) -> MapResult: ...
def map_button(el: ElementFact, ctx: MapContext) -> MapResult: ...
def map_choice_group(group: ChoiceGroup, ctx: MapContext) -> MapResult: ...   # button/chip/radio
def map_select(el: ElementFact, ctx: MapContext) -> MapResult: ...
def map_checkbox(el: ElementFact, ctx: MapContext) -> MapResult: ...          # checkbox, switch
def map_text_field(el: ElementFact, ctx: MapContext) -> MapResult: ...        # outside forms
def map_form(form: FormFact, ctx: MapContext) -> MapResult: ...               # includes in-form fields
def map_tabs(tablist: ElementFact, tabs: list[ElementFact], ctx) -> MapResult: ...
def map_disclosure(el: ElementFact, ctx: MapContext) -> MapResult: ...
def map_menu(button: ElementFact, items: list[ElementFact], ctx) -> MapResult: ...
def map_combobox(el: ElementFact, options: list[OptionFact] | None, ctx) -> MapResult: ...
def map_range(el: ElementFact, ctx: MapContext) -> MapResult: ...             # slider, spinbutton
def apply_dialog(doc_affordances, dialog: DialogFact, ctx) -> list[Affordance]: ...  # post-pass
def map_pagination(nav: PaginationFact, ctx: MapContext) -> MapResult: ...
def map_schema_org_action(action: dict, ctx: MapContext) -> MapResult: ...
def map_webmcp_tool(tool: dict, ctx: MapContext) -> MapResult: ...

DISPATCH: dict[Kind, Callable] = {...}    # Kind is an Enum; the dispatcher uses match + assert_never
```

Every mapper sets `x.label`, `x.locator`, `x.grain`, `x.tag` (provisional; §7.1 finalizes), `x.source="compiled"`, and `x.verified="unverified"`.

### 5.2 Universal `enabled` / `x.reason` rules (`mapping/enabled.py`)

Evaluated per element. The first match wins. Reason strings are fixed phrases, so tests and agents can match on them.

| # | Condition | `x.reason` |
|---|---|---|
| 1 | not rendered, zero-size, `display:none`, `visibility:hidden` | `"not visible"` |
| 2 | `disabled` attribute (self or `fieldset[disabled]` ancestor) | `"disabled"` |
| 3 | `aria-disabled="true"` | `"aria-disabled"` |
| 4 | `inert` self/ancestor | `"inert"` |
| 5 | covered at centre by another element (hit test) and not inside the open dialog | `"covered"` |
| 6 | control is behind a login (R2, §5.6) | `"requires sign-in"` |
| 7 | field grain (§5.4 form rule) and owning form `checkValidity()` false | `"missing: <field>[, <field>…]"` (fields whose `validationMessage` is non-empty) |
| 8 | all options of a choice/select are disabled or sold out | `"no options available"` |

The post-passes add these reasons:

- `"blocked by dialog"`
- `"menu closed"`
- `"not on this view"`
- `"precheck: no live element"`
- `"precheck: dom says disabled"`
- `"demoted: <why> (until <time> or <n> looks)"`
- `"hard-blocked in v1: <verb>"`

Elements that are off-screen (scrolled away) are still enabled; Playwright scrolls them into view on act.

### 5.3 Input schema from HTML (`mapping/input_schema.py`)

| HTML | JSON Schema property |
|---|---|
| `input[type=text|search|password|tel]`, `textarea` | `{"type":"string"}` (+ `format:"tel"` for tel) |
| `input[type=email]` | `{"type":"string","format":"email"}` |
| `input[type=url]` | `{"type":"string","format":"uri"}` |
| `input[type=date]` / `time` / `datetime-local` | `format: "date"` / `"time"` / `"date-time"` |
| `input[type=number]` | `{"type":"number"}`; `"integer"` when `step` is an integer or absent and `min`/`max` are integers |
| `input[type=range]`, `role=slider`, `role=spinbutton` | number/integer with `minimum`/`maximum` from `min`/`max` or `aria-valuemin`/`aria-valuemax`, `multipleOf` from `step` |
| `pattern` | `pattern` anchored as `^(?:…)$` (HTML patterns are implicitly anchored) |
| `minlength` / `maxlength` | `minLength` / `maxLength` |
| `min` / `max` (number) | `minimum` / `maximum` |
| `required` | name added to `required` |
| `<select>` | `{"type":"string","enum":[enabled option labels]}`; `multiple` → `{"type":"array","items":{"type":"string","enum":[…]}}` |
| radio group | `{"type":"string","enum":[enabled labels]}` |
| checkbox / switch | `{"type":"boolean"}` |
| `input[type=file|hidden|submit|reset|image|button]` | never a property (`file` makes the form `mutating` and hard-blocked: `"hard-blocked in v1: upload"`) |

Further rules:

- **Enum values** are trimmed option labels (as in the paper's `"S","M","L"`). If labels collide, use the `value` attribute instead. `x.locator.options` maps each enum value to the option.
- **Dropped options:**
  - `disabled` or `aria-disabled`;
  - placeholder options (`value=""` and first);
  - options whose text matches `/(sold ?out|out of stock|unavailable|not available)/i`.
- **Field names** (`naming.py`), in this order:
  1. label text slug;
  2. the `name` attribute if it is not cryptic (cryptic means fewer than 2 letters, contains `[`, or looks like a hash or uuid);
  3. placeholder slug;
  4. `id` slug;
  5. `field_<n>`.
  Then apply aliases:
  - `q|s|query|search|keywords?|k|search_query` → `query`;
  - `e_mail|mail|email_address` → `email`;
  - `zip|postcode|postal` → `postal_code`.
  Slug = lowercase ASCII, non-alnum → `_`, collapse `_`, ≤ 32 chars, strip a leading digit.

### 5.4 Per-kind rules

The "id" column gives the **provisional** id. The registry may disambiguate it (§6.2).

| Kind (function) | Id | `enabled` / reason | `input` | `state` / entities | Grain |
|---|---|---|---|---|---|
| Link, single (`map_link`) | `go_<view>`, where `<view>` = view name of the target route via the §4 step 10 route lexicon, else slug of the link text. Same-page `#anchor` links → `go_<anchor_slug>`. `rel=next/prev` → pagination. | universal | `{}` | — | single |
| Link group (`map_link_group`: repeat group whose target is a link, or the main-prose `link` group) | exactly **one** `open_<entity>` per entity type over the items' primary links (R1), e.g. `open_product`, `open_article`; prose → `open_link`. Secondary row links (comments, author, domain, …) are omitted unless requested (R1). | true if ≥ 1 visible item, else `"not visible"` | `{"<entity>_id":{"type":"string"}}`, required. **No enum** (id references, paper §7.1); valid ids are the ones listed in `entities` (10 per page, R4), and `act` checks membership. | `entities.<entities>` list | collapsed |
| Button, outside a form (`map_button`) | verb from the lexicon (§5.5) applied to the label, optionally `_<object>`; unknown label → `slug(label)`, prefixed `do_` if it does not start with a verb | universal | `{}` | `aria-pressed` toggle buttons → `state.<slug>` bool | single |
| Button/chip/radio group (`map_choice_group`) | `set_<field>` (field = group label / fieldset legend / radio `name`) | universal; `"no options available"` if none | `{"<field>":{"type":"string","enum":[enabled]}}`, required | `state.selected_<field>` = current selection or `""` | field |
| Select (`map_select`) | `set_<field>` | universal / no options | enum of enabled options (array if `multiple`), required | `state.selected_<field>` | field |
| Checkbox/switch (`map_checkbox`) | `set_<field>` | universal | `{"<field>":{"type":"boolean"}}`, required | `state.<field>` bool | field |
| Text input/textarea outside a form (`map_text_field`) | `set_<field>` | universal (+ `readonly` → `"read-only"`) | §5.3 property, required | `state.<field>` = current value (password → `"<redacted>"`) | field |
| Form (`map_form`) | see "form grain" below | grain rule | grain rule | in-form current values → `state.<field>` | form or field |
| Tabs (`map_tabs`) | `open_tab`; 2+ tablists → `open_<tablist>_tab` | true if ≥ 1 enabled tab | `{"tab":{"type":"string","enum":[enabled tab names]}}`, required | `state.selected_tab` (or `selected_<tablist>_tab`) | field |
| Disclosure/accordion/`<details>` (`map_disclosure`) | `toggle_<section>` (section = button text / summary text) | universal | `{}` | `state.<section>_expanded` bool | single |
| Menu of actions (`map_menu`: `menuitem` links/buttons) | `open_menu` (2+ menus → `open_<menu>_menu`); each item mapped by its own kind (menuitem → button rule; link item → link rule) | button universal; items: if menu collapsed → `false`, `"menu closed"` (only if items exist in DOM; otherwise items appear after `open_menu`) | `{}` for `open_menu` | `state.<menu>_menu_open` bool | single |
| Menu of options (`map_menu`: `menuitemradio`/`menuitemcheckbox`, or a custom dropdown whose options sit in a closed popup) | `set_<field>` | universal | **R3:** popup closed → `{"type":"string"}` (free text, no enum, even if the options exist in the DOM); popup open → enum of visible enabled options | `state.selected_<field>` | field |
| Combobox/listbox (`map_combobox`) | `set_<field>` | universal | options **visible now** (expanded listbox, or an always-rendered `role=listbox`) → enum; collapsed popup (`aria-expanded=false`) or unknown options → `{"type":"string"}` (+ text constraints) (R3). A native `<select>` is not a closed menu; it keeps its enum (§5.3). | `state.<field>` | field |
| Slider/spinbutton (`map_range`) | `set_<field>` | universal | number/integer with min/max/multipleOf | `state.<field>` = `aria-valuenow`/value | field |
| Open modal dialog (`apply_dialog`) | dialog's own controls map normally; its close button → `close_dialog` | everything outside the dialog → `false`, `"blocked by dialog"` | — | `state.dialog_open` = dialog's slug | — |
| Pagination (`map_pagination`) | `next_page`, `prev_page`, `go_page` | `next_page`/`prev_page` false when absent/disabled/`aria-disabled` | `go_page`: `{"page":{"type":"integer","enum":[visible page numbers]}}` | `state.page` = `aria-current` page | single / field |
| schema.org action (`map_schema_org_action`) | `snake(@type minus "Action")`: `SearchAction`→`search`, `BuyAction`→`buy`, `OrderAction`→`order`, … | true (declared), then policy | properties from `query-input`/`*-input` (`"required name=search_term_string"` → property named via alias table, e.g. `query`, with `required`); URL template placeholders | — | declared |
| WebMCP tool (`map_webmcp_tool`) | `snake(tool name)` | true, then policy | the tool's `inputSchema`, normalized to the §3.2 `prop` subset (unknown keywords dropped; nested objects → flattened with `_`) | — | declared |

**Form grain rule** (`map_form`). This is the rule that reproduces the paper's `set_size` + `add_to_cart`:

- **Field grain.** The form has no free-text inputs (only selects, radios, chips, checkboxes, ranges), and its single submit button's label maps to a known lexicon verb (e.g. `add_to_cart`). Then:
  - each control → its own `set_<field>` (as above);
  - the submit → `<verb>` with `{}` input;
  - `enabled` = the form's `checkValidity()`, else `"missing: <fields>"`.
  Recorded as `x.grain: "field"`.
- **Form grain** (otherwise). One affordance:
  - `search` if `role=search`, or the form contains a single `type=search` input or a `query`-aliased field;
  - else `<verb>` if the submit label maps to a lexicon verb (`sign_in`, `subscribe`, …);
  - else `submit_<form>` (form = `aria-label` / `name` / `id` / heading / legend slug).
  Its properties are all non-hidden fields; `required` comes from the field attributes. `enabled` is false only for a disabled submit or a disabled fieldset, never because fields are empty (the args fill them). Recorded as `x.grain: "form"`.

### 5.5 Lexicon (`extract/lexicon.py`)

A data module, not code paths. Each entry is canonical verb → regex list over normalized labels (lowercase, punctuation stripped). The first match wins, and the order matters.

- Hard-block verbs (§7.1), matched first:
  - `pay`: `pay( now)?`, `complete (purchase|payment)`, `submit payment`;
  - `place_order`: `place (my )?order`, `confirm (order|purchase)`, `buy now`, `purchase`;
  - `checkout_submit`: a form submit on a `checkout` view;
  - `delete`: `delete`, `remove (account|address|card)`, `close account`;
  - `send`: `send( message)?`, `post( comment| reply)?`, `publish`, `tweet`, `submit (review|comment)`.
- Mutating verbs:
  - `add_to_cart`: `add to (cart|bag|basket|trolley)`;
  - `add_to_wishlist`;
  - `subscribe`: `subscribe`, `sign up`, `join`, `newsletter`;
  - `sign_in`: `sign in`, `log in`, `login`;
  - `sign_out`;
  - `register`;
  - `apply_coupon`;
  - `update_quantity`;
  - `remove_from_cart`;
  - `save`;
  - `submit`;
  - `vote`, `like`, `follow`, `book`, `reserve`.
- Safe verbs:
  - `search`;
  - `go_<view>` / `open_<entity>` (links);
  - `next_page`: `next`, `›`, `»`, `more`, `load more`, `show more results`;
  - `prev_page`: `prev(ious)?`, `‹`, `«`;
  - `filter`, `sort`, `show_more`, `expand`, `collapse`, `close_dialog`: `close`, `×`, `dismiss`, `no thanks`;
  - `accept_cookies`, `reject_cookies`, `open_menu`, `play`, `pause`, `share`;
  - `copy`, `print`, `download`;
  - `go_back`.
- View lexicon (route keyword → view): `cart|bag|basket`→`cart`, `checkout`→`checkout`, `search|results`→`search_results`, `login|signin|sign-in`→`sign_in`, `account|profile`→`account`, `wiki`→`article`, `docs|documentation|reference`→`docs`, `news|article|story`→`article`, `category|collections?|shop|products`→`catalog`, `product|item|p|dp`→`product`, `/`→`home`.
- Counter lexicon: `cart|bag|basket|trolley`→`cart_count`, `notifications?|alerts?`→`notification_count`, `messages?|inbox`→`message_count`.
- Login-gate lexicon (R2):
  - labels: `^(sign|log) ?in to `, `login required`, `members only`, `account required`;
  - login routes: `/login`, `/signin`, `/sign-in`, `/account/login`, `/auth`, `/session/new`, or any path with a `next=`/`return(To|_to|Url)=`/`redirect=` param pointing back to this site.
- Flow-step lexicon (R5):
  - ids `set_address`, `set_shipping*`, `set_delivery*`, `set_billing*`, `set_payment*`, `set_card*`, `apply_coupon`, `pay`, `place_order`, `checkout_submit`, `continue_to_*`, `next_step`, `confirm_*`, `review_order`;
  - any affordance first seen on a view in `{cart, checkout, payment, shipping, review, confirmation}` whose `x.grain` is `field` or `form`.

### 5.6 Fixed converter rules R1-R5 (reference-comparable output)

These five rules are fixed by the owner so that compiled docs stay comparable with the hand-labeled reference set (§11.3). They are also recorded in `docs/PAPER-REQUIREMENTS.md` §8. They are defaults that are always on. The only switches are the two explicit options named below, and the headline eval numbers always use the defaults.

| Rule | Statement | Implementation | Tests (M3/M4) |
|---|---|---|---|
| **R1** | Emit one `open_<entity>(id)` per entity type. Emit secondary row links only when a task needs them. | In `repeats.py`, the **primary link** of an item is the link whose `href` yields the entity id (§4 step 8), tie-broken by: inside a heading, then the largest text box, then the first in DOM order. Only primary links feed `open_<entity>`. Same-type groups are merged (§4 step 8). Secondary links are computed and kept off the doc. They are emitted only when the caller passes `include_secondary=[...]`: a list of `"<entity>.<link_slug>"` keys or affordance ids such as `open_comments` (an `open`/`observe` option on CLI, MCP, and HTTP). They are then emitted as `open_<entity>_<link_slug>(<entity>_id)`, e.g. `open_story_comments(story_id)`. Reference replay (§11.3) passes exactly the secondary ids its tasks reference. | `link_group.html` with title + comments + author links per card → only `open_product`; two product carousels → one `open_product`, merged list; with `include_secondary=["product.reviews"]` → also `open_product_reviews`. |
| **R2** | Controls behind a login are `enabled: false`. | v1 never signs in, so `state.signed_in` is always false. A control is login-gated if any of these holds: its link/form target matches a login route (§5.5); its label matches the login-gate lexicon; `aria-describedby`/`title` text says sign-in is required; or a safe probe of it landed on a `sign_in` view (then the demotion reason is `"requires sign-in"` and it is cached per template). Result: `enabled: false`, `x.reason: "requires sign-in"`. The plain sign-in link itself (`go_sign_in`) is navigation and stays enabled. A start page that is entirely behind a login is still a `blocked: login` doc (§4 step 2). | `login_gated.html`: "Log in to vote" button, `/vote?id=1&goto=…` link that redirects to `/login`, form posting to `/login?next=…` → each `enabled:false`, `"requires sign-in"`; `go_sign_in` enabled. |
| **R3** | Options hidden inside closed menus become free-text inputs, not enums. | `map_combobox`/`map_menu` (§5.4): if the option popup is closed (`aria-expanded="false"`, `hidden`, `display:none`, or not rendered), the property is `{"type":"string"}` even when the options exist in the DOM. When the popup is open, the visible enabled options become an enum. A native `<select>` and always-visible radio/chip groups keep enums. At act time, the string is matched to an option by case-insensitive exact label, then unique prefix. No match → `invalid_args` (`no_such_option`). | `combobox.html` closed vs open → string vs enum; `menu_options.html` (sort-by dropdown with `menuitemradio`) closed → string; act with a bad option → `invalid_args`. |
| **R4** | Lists use a fixed length of 10. | Every `entities` list holds at most 10 records: the first 10 rendered items in DOM order (§4 step 8). Paging via `x.page` returns the next 10. This applies to merged lists too. Enums are not lists and are not truncated. | `link_group_long.html` with 37 cards → 10 records, `x.page.products == {offset:0, limit:10, total:37, next:<cursor>}`; `observe(page=…)` → items 11-20. |
| **R5** | Never emit flow-step affordances that aren't legal on the current view. | Flow steps are identified by the flow-step lexicon (§5.5). The registry (§6.2 step 4) never carries a flow-step id onto a view where it is absent. It is simply omitted: no `"not on this view"` entry. A flow step that **is** on the current view but currently disallowed (e.g. a disabled Pay button on checkout) is still emitted with `enabled: false` and its reason, because it is on this view. Non-flow ids (navigation, search, `open_<entity>`) keep the matched-grain carry-over. The paper-replication option `carry_flow_steps=true` (default **false**; CLI `--carry-flow-steps`, used only by the paper-replication agent arm) restores the paper's §4.1 behaviour of listing `set_address` and `pay` disabled on the product view. | `minishop` flow (§13.2): on the product view, `set_address` and `pay` are **absent** by default and present with `enabled:false` under `carry_flow_steps=true`. |

## 6. Affordance id stability scheme

### 6.1 Signature

`x.signature` is computed per affordance as `sha1(kind | role | normalized_label | landmark_role+name | form_signature | group_signature)[:12]`.

- `normalized_label` = lowercase, digits → `#`, whitespace collapsed. So "Cart (3)" and "Cart (4)" match.
- `form_signature` = `sha1(sorted field names + method + action path)`.
- `group_signature` = repeat-group structural signature, or the choice-group key.

It never includes css paths, nth, or text content of repeat items, so reorders and content changes keep it.

### 6.2 Id assignment (`registry.py`)

1. Each mapper proposes a provisional id (§5.4).
2. The registry keeps two maps per session:
   - `signature → id`, the first assignment wins forever within the session;
   - `id → signature`.
   It also keeps a per-template table in the sqlite cache, `(site, template, signature) → id`, so a new session on the same template gets the same ids.
3. **Collisions** (two different signatures with the same provisional id on one look). Disambiguate by appending, in order:
   1. the landmark suffix (`_header`, `_nav`, `_main`, `_aside`, `_footer`, `_dialog`);
   2. the slug of the landmark's accessible name;
   3. `_2`, `_3`, … by DOM order.
   The first-seen element keeps the bare id.
4. **Matched grain.** Flow-step ids are excluded (R5, §5.6): they are never carried unless `carry_flow_steps=true`. Any other id in the session registry that is absent from this look is emitted with:
   - `enabled: false`, `x.reason: "not on this view"`;
   - its last `input`;
   - `x.locator.kind: "registry"`.
   Cap at 100 carried ids per session (LRU by last-seen look). Dropped count → `x.registry.dropped`.
5. Ids depend only on (provisional id, signature, first-seen order), never on DOM paths. Reloading the same page in a fresh session yields identical ids (tested, §13).

## 7. Checker design

### 7.1 Tags and hard-blocks (`checker/tags.py`)

| Condition | Tag |
|---|---|
| Link (GET navigation) to same or other page | safe |
| Form with `method=get` (incl. `search`) | safe |
| ARIA-only widgets: tabs, disclosure, menu open, dialog close, client-side `set_*` on controls outside a POST form | safe |
| `set_*` / field-grain controls inside a POST form | safe (they only change client state); the form's verb is mutating |
| Form with `method=post` (or `dialog` / JS-submitted with unknown method) | mutating |
| Button whose verb is in the mutating list | mutating |
| schema.org action with non-GET method or non-search type; WebMCP tool without `annotations.readOnlyHint: true` | mutating |
| Unknown / unclassifiable | **mutating** |
| Any affordance that fired a first-party non-GET request when executed or probed | re-tagged **mutating** (+ demotion record if it was advertised safe) |

**Hard-blocked in v1.** Hard-blocked means `enabled: false`, `x.reason: "hard-blocked in v1: <verb>"`, and `act` returns `blocked` with no override, not even with a confirm token. It applies to:

- the verbs `pay`, `place_order`, `checkout_submit`, `delete`, `send`, and `upload`;
- schema.org `BuyAction`, `OrderAction`, `PayAction`, `DeleteAction`, `SendAction`, `CommunicateAction`;
- WebMCP tools whose name matches those verbs.

`go_checkout` (a GET link to a checkout page) is navigation and stays safe. Any non-GET request issued while on a `checkout` view is hard-blocked at the interceptor regardless of tag.

### 7.2 Static pre-check every look (`checker/precheck.py`)

For every non-registry affordance:

- Its locator resolves to ≥ 1 live node (`count() > 0`). For `repeat`, every listed entity id resolves to an item.
- The DOM still agrees with `enabled`, re-read via a single `collect.js` call:
  - not disabled / aria-disabled / inert;
  - visible;
  - not covered.

A failure sets `enabled: false` with `"precheck: no live element"` or `"precheck: dom says disabled"`. Totals go in `x.precheck`.

### 7.3 Request interception (`checker/intercept.py`)

`context.route("**/*", handler)` is installed on every context, always.

- `GET`, `HEAD`, and `OPTIONS` continue.
- Any other method is **aborted**, unless an armed confirm window (§7.6) matches it exactly. Each abort is recorded as `{method, url, fields, reason, initiator_first_party, during_action}`.
  - `fields` = parsed form/JSON/multipart field names with values. Values are replaced by `"<redacted>"` when the field name matches `/pass|pwd|card|cc-|cvv|cvc|ssn|iban|account.?num|token|secret|otp|pin/i` or the source input is `type=password`.
  - `during_action` = the request was issued within 2 s after an act's click/submit.
- `navigator.sendBeacon` and `ping` requests are aborted and logged as `background`. They never trigger re-tagging.
- `context.set_extra_http_headers` is never used to fake identity. The user agent is Chromium's default UA + ` interface-compiler/<version> (+https://github.com/akashnaren/interface-compiler)`.
- Downloads are disabled, service workers are blocked (`service_workers="block"`), and JS dialogs are auto-dismissed and recorded.

### 7.4 Probes and the effect check (`checker/probe.py`, `checker/effect.py`)

- **Safe act** (live session): `predict()` from the mapping:
  - link → navigate to `href` route;
  - tab → `selected_tab = arg`;
  - disclosure → `<section>_expanded` flips;
  - `set_*` → `state[...] == arg`;
  - `next_page` → URL or entity ids change;
  - GET form → navigation with the expected query keys;
  - dialog close → no dialog.

  Then execute, then `observe()`:
  - URL before/after, view/signature;
  - state diff, entities diff;
  - main document status;
  - console errors, JS dialogs;
  - intercepted requests.

  `compare()` gives `match`, with these rules:
  - **Lying affordance:** `match == false`, or the main status ≥ 400, or an error toast/`role=alert` appeared with error words.
  - **Re-tag:** a first-party non-GET was aborted during the action; it becomes mutating.
- **Safe probe** (checker CLI / evals / re-promotion). The same steps run in a **throwaway context**. A new context navigates to the session's current URL, replays the session's `set_*` actions since the last navigation, executes, compares, and is closed.
- **Stop-before-commit probe** (mutating). It runs in a throwaway context:
  1. replay the state;
  2. fill args;
  3. click;
  4. the interceptor aborts the non-GET.

  It records:
  - whether the browser blocked it first (client validation: `checkValidity()` false plus messages);
  - the would-be method, URL, and field names (= the real argument shape).

  The outcome is `x.verified: "stopped_before_commit"`. `probed_ok` is unreachable for mutating affordances on non-local hosts: enforced in `AffordanceX.verified` setter logic and asserted in tests.
- `x.verified_at` is set on every probe.

### 7.5 Demotion (`checker/demotion.py`)

- The key is `(site, view signature.template, affordance id)`. Stored in sqlite at `$XDG_CACHE_HOME/interface-compiler/cache.sqlite` (default `~/.cache/...`) for evals, and in memory for product sessions.
- A demotion is created when:
  - a safe act/probe does not match;
  - or the main status ≥ 400;
  - or an advertised-safe action fires a non-GET;
  - or a mutating probe shows the advertised args were rejected client-side despite `enabled: true`.
- It expires after `N=5` looks **or** a TTL of 30 min, whichever comes first.
- On expiry, the affordance stays `enabled: false`, `"demoted: awaiting re-probe"` until a re-probe runs (safe probe or stop-before-commit probe) and passes. It is **never silently re-promoted**.
- Every create/expire/re-promote event is appended to `effect.demoted` and to the eval trace.

### 7.6 Confirm tokens (`checker/confirm.py`)

The first `act` on a mutating (non-hard-blocked) affordance runs the stop-before-commit probe and returns:

- `status: "needs_confirmation"`;
- a `preview` (`method`, `url`, redacted `fields`, `client_validation`);
- a `confirm_token` = `secrets.token_urlsafe(24)`, bound to `(session_id, affordance_id, doc_rev, sha256(canonical args), sha256(preview))`. It is single use with a 120 s TTL.

A second `act` with a valid token:

1. arms a **confirm window** in the live context that allows exactly one first-party non-GET matching the preview's method, URL path, and field-name set, for 5 s;
2. performs the action;
3. aborts all other non-GETs as usual.

Token mismatch, expiry, or reuse → `status: "blocked"`, code `confirm_invalid`. Evals and tests never confirm on real sites.

## 8. Runtime: sessions, `act`, counters

- `SessionManager`:
  - One Chromium per process (`headless=True`).
  - One `BrowserContext` per `session_id` (`secrets.token_urlsafe(16)`), with viewport 1280×800, `locale="en-US"`, no `storage_state`, `accept_downloads=False`, and `service_workers="block"`.
  - Idle timeout 10 min (a background sweeper closes the context).
  - Max sessions from `IC_MAX_SESSIONS` (default 4); beyond that, `open` returns error `capacity`.
  - Nothing is written to disk except the sqlite name/demotion cache (no cookies, no page content).
- `doc_rev` is an int per session, incremented whenever the core document (`strip_x`) hash changes.
- `act(session_id, affordance_id, args, doc_rev, confirm_token=None)` runs these checks in order:
  1. Unknown session → `error` (`unknown_session`).
  2. `doc_rev` ≠ current → `stale` + fresh doc. Counts `stale`.
  3. Unknown `affordance_id`, or args not an object → `invalid_args` (`unknown_affordance` / `bad_shape`). Counts `malformed`.
  4. `enabled: false`:
     - hard-blocked → `blocked`, counts `blocked`;
     - otherwise → `disabled`, with no execution and counts `ignored`.
  5. `validate_args(input, args)` fails → `invalid_args` with the jsonschema error path/message. Counts `malformed`. For `repeat` locators, an arg id not among the listed entities → `invalid_args` (`unknown_entity_id`).
  6. Mutating and no token → `needs_confirmation` (§7.6).
  7. Execute (safe, or confirmed mutating) → effect check. A non-match or error counts `illegal`. The status is `ok` or `error`.
  8. Re-compile → new doc + `doc_rev`.
- **echo_errors.** Default `true` (CLI flag `--echo-errors/--no-echo-errors`, server env `IC_ECHO_ERRORS`, HTTP/MCP per-session option in `open`). When off, `error` is omitted from results, which replicates the paper's view-document loop. Counters are always kept.
- `observe(session_id, page=None)` re-compiles without acting. `page` = `{entity: cursor}` for paging.
- `back(session_id)` = `page.go_back()` + compile.
- `close(session_id)` destroys the context.
- `raw_snapshot(session_id)` returns Playwright's `page.locator("body").aria_snapshot()` (YAML text) as the fallback and baseline.

## 9. Delivery

### 9.1 MCP server (`server/mcp_server.py`)

Server name: `interface-compiler`. Built on the official `mcp` Python SDK's FastMCP-style server (§12). Tools:

| Tool | Input (JSON) | Output |
|---|---|---|
| `open` | `{url: string, echo_errors?: bool=true, include_x?: bool=true, include_secondary?: string[]=[], carry_flow_steps?: bool=false}` | `{session_id, doc_rev, doc}` |
| `act` | `{session_id, affordance_id, args: object = {}, doc_rev: int, confirm_token?: string}` | `ActResult` (§3.4) |
| `observe` | `{session_id, page?: {entity: cursor}, include_secondary?: string[]}` | `{doc_rev, doc}` |
| `back` | `{session_id}` | `{doc_rev, doc}` |
| `close` | `{session_id}` | `{ok: true}` |
| `raw_snapshot` | `{session_id}` | `{snapshot: string}` |

Each tool description states the safety contract in one line, e.g. for `act`: "Mutating actions return needs_confirmation with a preview; checkout/pay/delete/send are blocked." Tool outputs are returned as structured content (JSON) plus a text rendering of the same JSON.

Transports:

- `interface-compiler serve mcp` = **stdio** (default).
- `interface-compiler serve http` = one ASGI app on `127.0.0.1:47615` that mounts **MCP Streamable HTTP at `/mcp`** and the **HTTP API at `/v1`**.

Sessions are app-level `session_id`s passed in every call; protocol-level sessions are not relied on.

### 9.2 HTTP API (`server/http_api.py`, FastAPI), a 1:1 mirror

| Method + path | Body | Success | Errors |
|---|---|---|---|
| `POST /v1/sessions` | `{url, echo_errors?, include_x?, include_secondary?, carry_flow_steps?}` | `201 {session_id, doc_rev, doc}` | `403 blocked` (policy), `503 capacity` |
| `GET /v1/sessions/{id}/doc` | — (query `page.<entity>=cursor`) | `200 {doc_rev, doc}` | `404` |
| `POST /v1/sessions/{id}/act` | `{affordance_id, args, doc_rev, confirm_token?}` | `200 ActResult` | `409 stale`, `409 disabled`, `422 invalid_args`, `428 needs_confirmation`, `403 blocked`; the body is always an `ActResult` |
| `POST /v1/sessions/{id}/back` | — | `200 {doc_rev, doc}` | `404` |
| `GET /v1/sessions/{id}/raw` | — | `200 {snapshot}` | `404` |
| `DELETE /v1/sessions/{id}` | — | `200 {ok:true}` | `404` |
| `GET /v1/schema` | — | `200 {view_doc: <schema>, effect: <schema>, version: "1"}` | — |
| `GET /healthz` | — | `200 {ok:true, version}` (no auth) | — |

### 9.3 Network security (`server/security.py`)

- The default bind is `127.0.0.1`. `--host` accepts only:
  - loopback addresses;
  - RFC 1918 private addresses;
  - CGNAT `100.64.0.0/10` (private overlay networks);
  - IPv6 ULA/loopback.
- It refuses `0.0.0.0`, `::`, and any public address with exit code 2 and a clear message.
- Bearer token: required for every route except `/healthz`, on both `/mcp` and `/v1`, read from env `IC_TOKEN`. If `IC_TOKEN` is unset and the host is not loopback → refuse to start. If it is unset on loopback → generate one, print it once to stderr, and keep it in memory only. Compare tokens with `hmac.compare_digest`.
- `Origin` validation: if an `Origin` header is present, it must be in `IC_ALLOWED_ORIGINS` (default: none except `http://localhost:*` / `http://127.0.0.1:*`), else `403`. This is the DNS-rebinding defence the MCP transport spec requires.
- The README states plainly: never expose this through a public tunnel or reverse proxy.

### 9.4 CLI (`cli.py`, Typer; entry point `interface-compiler`)

```text
interface-compiler open <url> [--no-x] [--naming off|embed|llm] [--stats] [--out FILE]
                       [--include-secondary product.reviews,...] [--carry-flow-steps]
    # compile one page, print the doc JSON to stdout. --stats prints core vs x tokens to stderr.
interface-compiler open --html FILE [--base-url URL]
    # compile a saved HTML snapshot offline (all network aborted); used by reference + Mind2Web evals
interface-compiler run <url> --step '<affordance_id> <json-args>' [--step ...] [--confirm-none]
    # open + sequential acts in one session; prints every ActResult as JSON Lines. Never confirms.
interface-compiler check <url> [--max-probes 10] [--probe-disabled]
    # precheck + safe probes + stop-before-commit probes; prints a JSON report
interface-compiler raw <url>                     # Playwright aria snapshot (baseline)
interface-compiler schema [view-doc|effect]      # print JSON Schema
interface-compiler validate <file.json>          # validate a doc; exit 0/1
interface-compiler serve mcp                     # stdio MCP
interface-compiler serve http [--host 127.0.0.1] [--port 47615]
interface-compiler eval mind2web [--split test_website|test_domain|test_task] [--limit N] [--naming ...]
interface-compiler eval live [--sites FILE] [--max-looks 30] [--min-interval 5] [--probe-disabled]
interface-compiler eval reference [--dir reference] [--offline | --live]   # default --offline (snapshots)
interface-compiler eval agent --arms a11y,flat,doc,ablation --model ollama:qwen3:1.7b [--tasks ...]
interface-compiler models check                  # report Ollama reachability + pulled models (no installs)
```

Exit codes: `0` ok, `1` validation/check failure, `2` usage or policy refusal, `3` blocked by site policy (robots/wall/login/excluded).

## 10. Optional local naming models (`naming_models/`)

- Off by default (`--naming off`). The modes are `embed` (an embedding model only) and `llm` (embeddings + small LLM for leftovers).
- Backend: a local Ollama HTTP API at `IC_OLLAMA_URL` (default `http://localhost:11434`). Models: `embeddinggemma` (embeddings) and `qwen3:1.7b` (or `qwen3:0.6b`).
- `models check` only reports whether these are pulled. The README tells the user to `ollama pull` them. The tool never auto-downloads.
- **What models may do (only these):**
  1. map a button/link label that missed the lexicon to a lexicon verb (cosine ≥ 0.60 against verb exemplar embeddings, else keep the rule name);
  2. name a leftover repeat group (entity name) or a view when rules fell through to `item`/`page`. The LLM is called in JSON mode at temperature 0 with ≤ 20 strings in. The output must match `^[a-z][a-z0-9_]{1,30}$`, otherwise it is discarded.
- Models never decide structure, `enabled`, tags, or schemas.
- Results are cached by `(site, template)` in the sqlite cache, so it is one call per new template. The cache key includes the model name and the prompt version.
- Provenance: `x.locator.named_by = "embed" | "llm"`.
- Any Ollama error → silent fallback to rules plus a single stderr warning per process.

## 11. Evaluation harnesses

All eval outputs go to `runs/<UTC timestamp>-<eval>/`:

- `config.json`, which includes the git SHA, dataset revisions, site list hash, CPU/RAM of the eval machine, and naming mode;
- `traces.jsonl`;
- `summary.json`;
- `summary.md`, the table pasted into the README.

### 11.1 Eval A: Mind2Web offline (no network)

- **Data:** HF dataset `osunlp/Multimodal-Mind2Web` (test splits `test_website`, `test_domain`, `test_task`), via `datasets`. Record the dataset revision SHA. Confirm column names first (§15 item 4). Expected columns: `action_uid`, `raw_html`, `cleaned_html`, `operation`, `pos_candidates`, `confirmed_task`, `website`, `annotation_id`, `target_action_index`, `action_reprs`.
- **Loading a page:** `page.set_content(raw_html)` in a context whose router **aborts every request**, so it is fully offline. Then the normal pipeline runs, minus the policy gate.
- **Target matching:** `pos_candidates[*].backend_node_id` is matched to the element carrying the `backend_node_id` attribute in `raw_html`. That element is "covered" by an affordance if any of these hold:
  - it is the locator target;
  - it is a field in a form affordance;
  - it is an option of a group;
  - it is an item of a repeat group;
  - it is within 2 ancestor levels of one of the above.
- **Metrics** (per split, macro over steps and over tasks):
  - **Action coverage:** the target is covered by an affordance of compatible kind (`CLICK` → any; `TYPE` → a text property or `set_*` string; `SELECT` → enum containing the value), with `enabled: true`.
  - **Schema fit:** for `TYPE`/`SELECT`, `operation.value` validates against the property schema.
  - **Oracle executability:** each human step is translated into `act(affordance_id, args)` from the coverage match. A step is executable if the id exists, is enabled, and the args validate. A task is executable if all of its steps are. This is reported per step and per task.
  - **Doc size:** tokens (o200k_base) for:
    - the core doc and `x` separately;
    - the Playwright aria snapshot of the same page;
    - Mind2Web `cleaned_html`.
    Report the ratio aria/core.
  - **Model-free observation cost:** median tokens per look per representation (aria snapshot, flat tools from the same affordances, compiled doc core, compiled doc with x).
- **Fixed rules R1-R5 (§5.6) apply to the headline numbers.** The headline compile uses the defaults: no secondary links, 10-item lists, and closed-menu options as strings. Two diagnostic columns, never the headline, say how much the rules cost:
  - `+secondary`: steps whose target is a secondary row link count as covered when `include_secondary` contains that link. This answers R1's "only when a task needs them" on Mind2Web, where each step is a task need.
  - `+paging`: targets inside a list item beyond the first 10 count as covered if they are reachable through `x.page` cursors (R4).
  - For R3, a `SELECT` on a closed custom dropdown is checked for schema fit against the string property, and its value must also match an option label at act time (the `no_such_option` rule).
- **Ablation rows:** rules only, `+embed`, `+llm`.
- **Working targets** (not claims): coverage ≥ 85 %, aria/core token ratio ≥ 3.

### 11.2 Eval B: live, safe only (Online-Mind2Web sites)

- **Site list:** the start URLs of the Online-Mind2Web tasks (HF `osunlp/Online-Mind2Web`, record the revision), deduplicated by host. It is written to `runs/.../sites.txt` with its sha256.
- **Filters, applied before any request beyond robots.txt:**
  - robots disallows the path;
  - robots fully disallows any of the AI-agent user agents `GPTBot`, `ClaudeBot`, `Google-Extended`, `CCBot`, `PerplexityBot`, `Bytespider` (= "bans AI agents");
  - an exclusion category (adult, gambling, banking/finance accounts);
  - the start page needs a login (login wall at first look).
  Every skip is recorded with its reason. A bot wall mid-run → `blocked`, and the site is ended.
- **Limits:**
  - ≤ 30 looks per site;
  - ≥ 5 s between requests to a host (or robots `Crawl-delay` if larger);
  - one site at a time;
  - honest UA.
- **Procedure per site:**
  1. open;
  2. compile;
  3. pre-check;
  4. pick up to 10 safe affordances by seeded sampling (seed = sha1(host)) and run each as a **safe probe** in a throwaway context;
  5. for up to 5 mutating affordances run **stop-before-commit probes** (never confirm);
  6. with `--probe-disabled`, also try up to 5 `enabled: false` *safe* affordances in a throwaway context (hidden-affordance measurement).
- **Metrics:**
  - **Lying-affordance rate** = enabled safe affordances whose probe did not match, or that errored, / probed.
  - **Hidden-affordance rate** = disabled safe affordances that worked / probed.
  - **Stop-before-commit agreement** = mutating probes where a non-GET was captured or client validation blocked, / mutating probes.
  - **Re-tag rate** (safe → mutating).
  - **Coverage vs interactive AX nodes** = interactive AX nodes covered by any affordance / interactive AX nodes.
  - Latency per look, p50/p95 (open+compile; act+effect+compile).
  - Tokens: core doc vs `x` vs Playwright aria snapshot.
  - Blocked/skipped counts by reason.
  - Cost = $0.
- **Working targets:** lying ≤ 5 %.

### 11.3 Reference set (upper bound) — `evals/reference.py`

The reference set is a hand-labeled eval fixture: **21 real pages and 57 tasks**. It is copied into `reference/` later, and the repo ships the directory empty. Its layout:

```text
reference/
├── pages.csv              # one row per page: slug, url, … (header row; see "Loader")
├── docs/<slug>.json       # hand-written view document, STRICT 4 keys (no x)
├── tasks/<slug>.json      # tasks to replay on that page
├── snapshots/             # per page: saved HTML, a11y tree, screenshot
└── selfcheck/             # human self-agreement data (labeler vs labeler / re-label)
```

- **Loader:** `load_reference(dir="reference") -> ReferenceSet` (`pages: list[RefPage]`, `ceiling: Ceiling`).
  - **`pages.csv`** is the index. Read it with `csv.DictReader`. The required columns are `slug` and `url`; every other column is kept verbatim in `RefPage.meta` (e.g. category, captured date).
    - A row without a matching `docs/<slug>.json` is an error.
    - A `docs/` file without a row is a warning and is skipped.
  - **`docs/<slug>.json`** must validate against `view-doc.v1.json` **and** have exactly the 4 keys (`strip_x(doc) == doc`). Any `x` → a loader error.
  - **`tasks/<slug>.json`** is optional per page. Shape:

    ```json
    {"slug": "…", "tasks": [
      {"id": "t01", "expect": "success" | "refusal", "instruction": "…",
       "steps": [{"affordance_id": "…", "args": {}}],
       "check": {"final_view": "…", "state": {"k": "v"}, "url_matches": "regex"}}]}
    ```

    The URL comes from `pages.csv`. A `url` key inside the tasks file, if present, must match it.
  - **`snapshots/`**: the loader discovers per-slug files by prefix: `<slug>.html` (or `.mhtml`), the a11y tree as `<slug>.a11y.*`, and the screenshot as `<slug>.png`/`.jpg`. The builder confirms the exact names when the fixture arrives (§15 item 7) and changes only the discovery globs.
  - **`selfcheck/`**: parsed into `Ceiling(affordances=0.83, enabled=1.00, source=…)`. If the files are missing or unparseable, those constants are used, with `source="default (owner-reported)"` and a warning.
  - Expected counts once the fixture lands: 21 pages and 57 tasks. `eval reference` prints the counts it found and warns if they differ.
  - An empty dir → an empty set, and `eval reference` prints `0 reference pages; nothing to score` and exits 0.
- **Compile modes** (both reported; offline is the headline because it is deterministic and matches what the labelers saw):
  - `offline`: compile `snapshots/<slug>.html` with `open --html` (all network aborted, base URL = the `pages.csv` url).
  - `live`: compile the live URL under the usual politeness rules (the page may have drifted, so it is reported separately).
  - Both use the fixed rules R1-R5 (§5.6) with defaults, plus `include_secondary` = the secondary-link ids referenced by that page's tasks (R1 "only when a task needs them").
- **Per-page diff score** `diff(strip_x(compiled), reference_doc) -> PageScore`, comparing against `docs/`. Every component is in [0, 1], and the composite is the unweighted mean.
  - `view_match`: 1 if equal.
  - `state_keys`: Jaccard of key sets. `state_values`: agreement on shared keys (string-normalized).
  - `entity_keys`: Jaccard of entity names. `entity_ids`: mean Jaccard of id sets per shared list entity.
  - `affordance_ids`: precision, recall, and F1 of id sets. F1 enters the composite.
  - `enabled`: agreement on shared ids.
  - `enums`: mean Jaccard of enum sets over shared (id, property) pairs that have an enum in either doc.
  - `input_props`: mean Jaccard of property-name sets over shared ids.
- **Ceiling.** Human self-agreement across the set is **83 % on affordances** and **100 % on `enabled`**. The report prints each score next to its ceiling and a ceiling-normalized value (`affordance_ids.f1 / 0.83`, `enabled / 1.00`).
  - An affordance-id F1 at or near 0.83 means "as consistent as two human labelings". It is not a shortfall, and the README must say so.
  - Scores above the ceiling are reported as-is, with a note. They are not clipped.
- **Oracle replay** (57 tasks, from `tasks/`): for each task, open the page (live) and replay `steps` via `act`.
  - Safe steps execute.
  - Mutating steps stop at `needs_confirmation`, which counts as executable if the preview's field names cover the args.
  - Hard-blocked steps count as "blocked (by policy)" and are reported separately, not as failures.
  - Login-gated steps (R2, `"requires sign-in"`) count as "blocked (login)" and are reported separately.
  - Then the deterministic `check` runs.
  Metrics: step and task executability and check pass rate, with `refusal` tasks reported apart. A snapshot-only variant checks the step ids and args against the offline doc without executing.
- Reported both per page and aggregate, with the ceiling row. This is the **upper bound**: the README states that the reference docs are hand-labeled, as the paper's document was.

### 11.4 Agent arms (optional; local model; paper §4-6)

- **Arms**, built by `evals/arms.py` from ONE compile of each look:
  - `a11y`: the Playwright aria snapshot; actions `click(role,name)`, `fill(role,name,text)`, `select(role,name,option)`.
  - `flat`: tools generated from the same affordances (`to_flat_tools()`: name = id, parameters = `input`). The status reply is `{status, view, <≤2 state fields>}`, as in the paper's C3.
  - `doc`: the compiled view doc core (`strip_x`). Optionally `doc+x`.
  - `doc_paper` (optional, paper replication only): `doc` compiled with `carry_flow_steps=true` and `echo_errors=false`, to mirror the paper's §4.1 document and its loop. It is never a headline arm.
  - `ablation`: `transforms.ablate(doc)` removes `enabled` (all treated callable) and strips `enum`, `pattern`, `min*`/`max*`, and `required` (types are kept).
- **Shared prompt rules**, byte-identical across arms: follow the task exactly; stop if the item cannot be obtained; the site is the source of truth; reply with exactly one JSON action. On top of that, each arm gets a ≤ 3-line usage note, and every note is stored in the run config.
- **Loop:** temperature 0, cap 20 steps, memory = task + prior actions + current observation (the paper's policy). `echo_errors` is configurable (default on; off = paper replication).
- **Tasks:**
  - read/navigate-only Online-Mind2Web tasks with a deterministic check (final URL regex or extracted answer string);
  - `reference/tasks` (when present);
  - **refusal tasks**, e.g. "buy size X" where X is sold out on a reference page. The grade is: no `needs_confirmation` was requested for the forbidden combination, and the agent declared stop.
- **Grading:** deterministic only. No LLM judge (a judge is an off-by-default `--judge` stub that is never in the headline).
- **Stats:**
  - per-arm success, median input tokens, median steps, and illegal/malformed/ignored per step;
  - latency;
  - paired per-task differences (doc − flat, doc − a11y, doc − ablation) with **bootstrap 95 % CI** (10,000 resamples, seed 0);
  - a cost-reliability frontier (median input tokens vs success) as a table plus a PNG-free text plot.
  Success and refusal are reported separately. Models are never pooled.
- **Cost:** a local model only (`ollama:<model>`). Paid models are out of scope for v1.

## 12. Dependencies (pinned majors; Python 3.12; managed with `uv`)

| Package | Constraint | Why |
|---|---|---|
| `playwright` | `>=1.64,<2` | headless Chromium, CDP, routing |
| `mcp` | `>=2.3,<3` | official MCP SDK: stdio + Streamable HTTP server |
| `fastapi` | `>=0.162,<1` | HTTP API |
| `uvicorn` | `>=0.54,<1` | ASGI server |
| `pydantic` | `>=2.14,<3` | contract models |
| `jsonschema` | `>=4.26,<5` | Draft 2020-12 validation (doc + args) |
| `typer` | `>=0.27,<1` | CLI |
| `httpx` | `>=0.28,<1` | Ollama client, robots fetch, test client |
| `extruct` | `>=0.18,<1` | JSON-LD + microdata |
| `protego` | `>=0.7,<1` | robots.txt parsing |
| `tiktoken` | `>=0.14,<1` | fixed tokenizer (`o200k_base`) for token counts |
| eval extra: `datasets` | `>=5.1,<6` | Mind2Web / Online-Mind2Web |
| eval extra: `huggingface-hub` | `>=2.4,<3` | dataset revision pinning |
| dev: `pytest` | `>=9.2,<10` | tests |
| dev: `pytest-asyncio` | `>=1.4,<2` | async tests |
| dev: `ruff` | `>=0.17,<1` | lint + format |

- No torch, no transformers, no Node. Chromium is installed with `uv run playwright install chromium` (plus `--with-deps` on fresh Linux).
- `pyproject.toml` has extras `eval` and `dev`, script `interface-compiler = "interface_compiler.cli:app"`, and the ruff config (line length 100, target py312).
- The tiktoken BPE file is downloaded on first use. The builder caches it under the XDG cache and documents that offline evals need one prior online run.

## 13. Test plan

Run all tests with `uv run pytest` (live tests are excluded by default). `tests/conftest.py`:

- serves `tests/fixtures/html/` from a threaded `http.server` on `127.0.0.1:<random>`;
- provides a module-scoped browser;
- provides `compile_fixture(name) -> ViewDoc`;
- registers the `--live` option, which enables `@pytest.mark.live`.

### 13.1 Mapping fixtures (one HTML file + one test file per kind)

| Fixture | Asserts (at minimum) |
|---|---|
| `link.html` | nav links → `go_cart`, `go_catalog`; `#section` link → `go_<anchor>`; hidden link → `enabled:false`, `"not visible"` |
| `link_group.html` (8 product cards, 1 shuffled variant) | one `open_product` with `{"product_id":{"type":"string"}}` required; `entities.products` has 8 ids from `/p/<id>`; shuffled variant → identical id + signature |
| `button.html` | `Add to bag` → `add_to_cart` (mutating); `Show more` → `show_more` (safe); disabled → `"disabled"`; `aria-disabled` → `"aria-disabled"`; covered by overlay → `"covered"`; `aria-pressed` → state bool |
| `choice_group.html` (radio sizes S/M/L/XL with XL disabled; chip toolbar) | `set_size` enum `["S","M","L"]`; `state.selected_size` reflects checked |
| `select.html` (sizes with disabled + "XL – sold out" + placeholder) | enum excludes placeholder/disabled/sold out; `multiple` → array schema |
| `checkbox.html` (checkbox + `role=switch`) | `set_<field>` boolean; state bool |
| `text_inputs.html` (email, url, number min/max/step, date, tel, pattern, minlength/maxlength, textarea, readonly) | each property matches §5.3 exactly (golden JSON) |
| `form_search.html` (`role=search`, `name=q`) | `search` with `{"query":{"type":"string"}}`, grain `form`, tag `safe` |
| `form_contact.html` (POST, required email + message) | `submit_contact` (or lexicon verb), required `["email","message"]`, tag `mutating` |
| `form_product.html` (paper case: size select + Add to cart, POST) | `set_size` + `add_to_cart` (`{}`), grain `field`; with no size selected `add_to_cart.enabled == false`, `x.reason == "missing: size"`; after `set_size("L")` → enabled true |
| `tabs.html` | `open_tab` enum of tab names; `state.selected_tab`; two tablists → disambiguated ids |
| `disclosure.html` (button+aria-expanded, `<details>`) | `toggle_<section>`; `state.<section>_expanded` |
| `menu.html` (collapsed menu with items in DOM; second menu with items injected on open) | `open_menu`; items `"menu closed"`; after acting `open_menu`, items enabled |
| `combobox.html` (listbox options in DOM; free-text combobox) | enum vs string |
| `slider.html` (`input[type=range]`, `role=slider`, `role=spinbutton`) | integer/number with min/max/multipleOf |
| `dialog.html` (modal open) | all outside → `"blocked by dialog"`; `close_dialog` enabled; `state.dialog_open` |
| `pagination.html` | `next_page`, `prev_page` (disabled on page 1), `go_page` enum; `state.page` |
| `jsonld_search.html` (WebSite + SearchAction) | declared `search` wins over inferred search form (only one `search`); grain `declared` |
| `jsonld_product.html` (Product + Offer) | `view == "product"`; `entities.product` record with id/name/price |
| `webmcp.html` (registers a tool via `document.modelContext.registerTool`) | affordance from the tool; input normalized; tag mutating unless `readOnlyHint` |
| `minishop/` (`catalog.html`, `product.html`, `checkout.html`: a local reconstruction of the paper's MiniShop pages) | see §13.2 |
| **R1** `link_group_rows.html` (rows with title, comments, and author links; two same-type carousels) | one `open_<entity>` per type; secondary links absent by default; `include_secondary=["story.comments"]` → `open_story_comments(story_id)` appears; carousels merged into one list |
| **R2** `login_gated.html` ("Log in to vote" button, `/vote?…&goto=` link, form posting to `/login?next=…`, plain "Sign in" link) | gated controls `enabled:false`, `"requires sign-in"`; `go_sign_in` enabled |
| **R3** `menu_options.html` (sort-by dropdown with `menuitemradio`, closed/open variants) + `combobox.html` | closed → `{"type":"string"}`; open → enum; native `<select>` keeps enum; act with an unknown option → `invalid_args` (`no_such_option`) |
| **R4** `link_group_long.html` (37 cards) | list length exactly 10; `x.page.<entity>` `{offset:0, limit:10, total:37}`; next page → items 11-20 |
| **R5** `minishop/` flow (§13.2) | off-view flow steps omitted by default; carried as disabled only with `carry_flow_steps=true` |

### 13.2 Paper-faithfulness golden test (`tests/mapping/test_paper_example.py`)

The session does: open `minishop/catalog.html` → `open_product(tee-navy)` → `set_size(L)` → `add_to_cart` → `go_checkout` → `back`. The add-to-cart POST is served by the fixture server, which is local, so confirmation is allowed only for `127.0.0.1` fixture hosts. Assert on the product view, after `strip_x`:

- exactly the 4 keys;
- `view == "product"`;
- `state` ⊇ `{selected_size: "L", cart_count: 1}`;
- `entities.product.id == "tee-navy"`;
- the affordance id set ⊇ `{open_product, set_size, add_to_cart, go_catalog, go_checkout}` (`open_product` comes from a "You may also like" row on the fixture product page, so it is on this view);
- `set_size.input == {"type":"object","properties":{"size":{"type":"string","enum":["S","M","L"]}},"required":["size"]}` (byte-equal to the paper);
- `add_to_cart`, `go_catalog`, and `go_checkout` have `{"type":"object","properties":{}}`;
- **default (R5):** `set_address` and `pay` are **absent** from the product view; they are flow steps that are not legal here;
- **paper replication** (`carry_flow_steps=true`): `set_address.enabled == false` (reason `"not on this view"`) with input byte-equal to the paper's, and `pay.enabled == false`. This reproduces the paper's §4.1 affordance list.

Also validate the paper's printed example (from `docs/PAPER-REQUIREMENTS.md` §2, stored as `tests/fixtures/paper_example.json`) against `view-doc.v1.json`.

### 13.3 Contract, checker, runtime, server, eval unit tests

- **Contract:**
  - the paper example validates;
  - a 5th top-level key fails;
  - a top-level `provenance` fails;
  - an affordance extra key outside `x` fails;
  - `required: []` fails (it must be omitted);
  - `strip_x` → exactly 4 keys;
  - `ablate` removes `enabled` and constraints;
  - token counter reports core and x separately.
- **Id stability:**
  - compile the same fixture in two fresh sessions → identical `(id, signature)` lists;
  - the shuffled card order → identical;
  - "Cart (3)" vs "Cart (4)" → same signature;
  - a collision fixture (two "Search" buttons in header and footer) → `search` and `search_footer`;
  - matched grain: after navigating away, earlier **non-flow** ids are present with `"not on this view"`, and flow-step ids are absent (R5).
- **Checker:**
  - a POST form act without a token → `needs_confirmation`, preview has method `POST` and field names, and the fixture server **received zero POSTs** (the server counts requests);
  - with a valid token → exactly one POST;
  - token reuse → `blocked`;
  - hard-blocked `pay`/`place_order`/`delete`/`send` fixtures → `enabled:false`, `"hard-blocked in v1: …"`, and `act` → `blocked` even with a token; the server receives zero non-GETs;
  - a "safe-looking" link whose click handler issues a `fetch(..., {method:"POST"})` → aborted, re-tagged `mutating`, demotion recorded;
  - sendBeacon → aborted, no re-tag;
  - precheck: remove the element after compile → `"precheck: no live element"`;
  - demotion expiry after N looks → `"demoted: awaiting re-probe"` until a re-probe passes;
  - mutating on a non-local host can never be `probed_ok` (unit test on the setter);
  - redaction of password/card fields in previews.
- **Runtime counters:**
  - `act` on a disabled id → `disabled`, `ignored+1`, no request issued;
  - bad args → `invalid_args`, `malformed+1`, no click (the DOM is unchanged);
  - stale `doc_rev` → `stale` + fresh doc;
  - `echo_errors=false` → no `error` key.
- **Policy:**
  - a robots fixture (`Disallow: /`) → `blocked` with exit code 3;
  - an AI-agent ban fixture → blocked;
  - a captcha fixture (`iframe[src*=recaptcha]`) → `bot_wall`;
  - a login-wall fixture → `login`;
  - the rate limiter enforces the min interval (fake clock).
- **Server:**
  - stdio MCP: spawn `interface-compiler serve mcp`, list tools (exactly the 6), and call `open`/`act`/`observe`/`back`/`close` against a fixture;
  - HTTP: the same over `/mcp` with the official MCP client, and `/v1` with `httpx`;
  - missing/wrong bearer → 401;
  - bad `Origin` → 403;
  - `--host 0.0.0.0` → exit 2;
  - status codes per §9.2.
- **Evals:**
  - Mind2Web harness on `tests/fixtures/mind2web_sample/` (3 hand-made rows in the dataset's shape; no download) computes coverage/schema-fit/executability;
  - reference loader on an empty dir → an empty set;
  - `tests/fixtures/reference_sample/` mirrors the real layout with 2 synthetic pages: `pages.csv`, `docs/`, `tasks/`, `snapshots/<slug>.html`, and `selfcheck/`. Tests:
    - the loader reads it;
    - a doc carrying `x` is rejected;
    - a csv row without a doc is an error;
    - the missing-selfcheck fallback gives the ceiling 0.83/1.00;
  - diff on the sample gives known component scores (e.g. identical docs → all 1.0; one enum option removed → `enums` < 1; ceiling-normalized affordance F1 = F1/0.83);
  - offline compile of `snapshots/<slug>.html` makes no network request;
  - bootstrap CI on a known vector (seeded) matches stored numbers.

### 13.4 Live smoke (`tests/live/`, run with `uv run pytest -m live --live`)

`evals/sites/smoke.txt` lists three real public read-only pages:

- `https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol` (article);
- `https://docs.python.org/3/library/json.html` (docs);
- `https://news.ycombinator.com/` (news listing).

Fallbacks, used if one disallows us at test time: `https://developer.mozilla.org/en-US/docs/Web/HTML/Element/form` and `https://www.gutenberg.org/ebooks/search/?query=dickens` (only if robots allows).

Per site:

1. check robots (skip with reason if disallowed);
2. open (≥ 5 s between requests, ≤ 6 looks);
3. assert the doc validates;
4. assert `affordances` is non-empty and every id matches `^[a-z][a-z0-9_]*$`;
5. assert no hard-blocked action is enabled;
6. act on **one safe** affordance and assert `effect.match == true`:
   - Wikipedia: `open_link` with the first listed id, or a `toggle_*` section;
   - Python docs: `next_page` or a `go_*`;
   - HN: `next_page` ("More");
7. reopen in a fresh session and assert ≥ 95 % of ids are identical (pages change slightly);
8. assert zero non-GET requests left the browser (the interceptor log shows only aborted ones).

## 14. Build order (small, verifiable steps)

Each milestone ends with a commit (or a few small ones). The acceptance block must pass before the next milestone starts. "Expected" output is what the builder must show in its report.

### M0: repo seed

Create:

- `paper/paper.pdf`, fetched from <https://akashnaren.github.io/research/agent-native-ui/paper.pdf>;
- `paper/SHA256SUMS`;
- `paper/paper.md` (§15 item 1);
- `docs/PAPER-REQUIREMENTS.md` (as committed here);
- `README.md` (as committed here) and `PLAN.md`;
- `pyproject.toml` (package `interface_compiler`, src layout, extras, script entry point, ruff, pytest config with a `live` marker);
- `.gitignore`;
- `src/interface_compiler/__init__.py` (`__version__ = "0.1.0"`);
- a `cli.py` stub with `--version`;
- `tests/` skeleton (`conftest.py`, one smoke test importing the package);
- `reference/{docs,tasks,snapshots,selfcheck}/.gitkeep` (no `pages.csv` yet; the fixture is copied in later, §11.3);
- `evals/sites/smoke.txt`.

Acceptance:

```bash
sha256sum paper/paper.pdf
# expected: fdbd9cf0f27cb4e27c3f360dda6b092b2a256e077ccdf3bbd94678e28e4599f8  paper/paper.pdf
uv sync --all-extras && uv run playwright install chromium
uv run interface-compiler --version      # expected: interface-compiler 0.1.0
uv run pytest -q                          # expected: 1 passed
find reference -type f                   # expected: only the four .gitkeep files
git grep -nIiE '(\.ts\.net|tailscale|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})' -- ':!PLAN.md' || echo clean   # expected: clean
```

### M1: contract

`contract/` with both schemas, models, `validate`, `transforms`, and `tokens`. Plus `interface-compiler schema`, `validate`.

```bash
uv run interface-compiler validate tests/fixtures/paper_example.json   # expected: exit 0, "valid"
uv run interface-compiler schema view-doc | python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d['required']))"
# expected: ['affordances', 'entities', 'state', 'view']
uv run pytest tests/unit -q -k contract   # expected: all pass (≥ 8 tests)
```

### M2: browser + facts

Contents: `browser/engine.py`, `collect.js`, `facts.py`, `raw.py`; the fixture server; `interface-compiler raw`.

```bash
uv run pytest tests/unit -q -k facts      # expected: facts for every §13.1 fixture element (role, name, landmark, constraints, options, visible/covered)
uv run interface-compiler raw https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol | head -5   # expected: aria YAML lines
```

### M3: mapping (centerpiece)

All `mapping/*` functions, plus `input_schema.py`, `enabled.py`, and `lexicon.py`, with one test file per kind (§13.1). The fixed converter rules **R1-R4** (§5.6) are part of this milestone: R1's primary/secondary link split, R2's login gate, R3's closed-menu strings, and R4's 10-item lists. R5 needs the registry and lands in M4.

```bash
uv run pytest tests/mapping -q            # expected: all pass; ≥ 1 test file per kind (19 kinds/fixtures) + R1-R4 fixtures
uv run pytest tests/mapping -q -k "r1 or r2 or r3 or r4"   # expected: all pass, ≥ 12 tests
uv run pytest tests/mapping -q --collect-only | grep -c "test_"   # expected: ≥ 70
```

### M4: compile pipeline + ids + CLI `open`

Contents: `compile.py`, `extract/*`, `registry.py`, `cache.py`; R5 (flow steps never carried; `carry_flow_steps` option); `open --html`; the §13.2 golden test; id stability tests.

```bash
uv run pytest tests -q -m "not live"      # expected: all pass incl. test_paper_example (default R5 + carry_flow_steps variants)
uv run pytest tests -q -k r5              # expected: all pass
uv run interface-compiler open http://127.0.0.1:<fixture-port>/minishop/product.html --stats
# expected: JSON doc on stdout with keys view,state,entities,affordances,x; stderr "core_tokens=… x_tokens=…"
uv run interface-compiler open https://docs.python.org/3/library/json.html | uv run interface-compiler validate -
# expected: valid
```

After M4, regenerate the README's "before/after" and "one real page, end to end" sections from real output (§README TODO markers).

### M5: Eval A harness (Mind2Web offline) + reference loader/diff

Contents: `evals/mind2web.py`, `evals/reference.py` (loader + diff; oracle replay waits for M6), `stats.py`, `report.py`.

```bash
uv run pytest tests/evals -q              # expected: all pass (sample rows, empty reference dir, reference_sample layout, diff scores, ceiling)
uv run interface-compiler eval reference  # expected: "0 reference pages; nothing to score", exit 0
uv run interface-compiler eval reference --dir tests/fixtures/reference_sample --offline
# expected: per-page table + aggregate with ceiling row "affordances 0.83 / enabled 1.00" and normalized scores
uv run interface-compiler eval mind2web --split test_website --limit 50
# expected: runs/<ts>-mind2web/summary.md with coverage % (headline, +secondary, +paging), schema-fit %,
#           step/task executability %, token ratio
```

When the real fixture is copied in (21 pages, 57 tasks), the builder runs `eval reference --offline` and `eval reference --live` and reports `pages=21 tasks=57`, plus the per-page and aggregate scores next to the ceiling.

### M6: checker + runtime `act`

Contents: `checker/*`, `runtime/*`; CLI `run` and `check`; reference oracle replay.

```bash
uv run pytest tests/checker tests/unit -q   # expected: all pass incl. "fixture server received 0 POSTs"
uv run interface-compiler run http://127.0.0.1:<port>/minishop/product.html --step 'add_to_cart {}'
# expected: one JSON line, status "disabled" (no size) or "needs_confirmation" with preview.method "POST"
uv run interface-compiler check https://news.ycombinator.com/ --max-probes 3
# expected: JSON report; each probe has match true/false; zero non-GET sent
```

### M7: front doors

Contents: `server/*` (MCP stdio + HTTP, HTTP API, security).

```bash
uv run pytest tests/server -q             # expected: all pass (6 tools listed; 401/403/409/422/428 cases; bind guard)
IC_TOKEN=test uv run interface-compiler serve http --port 47615 &
curl -s -H 'Authorization: Bearer test' -X POST localhost:47615/v1/sessions -d '{"url":"https://docs.python.org/3/library/json.html"}' -H 'content-type: application/json' | python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d))"
# expected: ['doc', 'doc_rev', 'session_id']
uv run interface-compiler serve http --host 0.0.0.0   # expected: exit 2, refuses public bind
```

### M8: politeness + live smoke

Contents: `policy/*` fully wired; `tests/live`.

```bash
uv run pytest -m live --live -q           # expected: 3 passed (or skipped-with-reason if a site's robots disallows; ≥ 2 must pass)
```

### M9: Eval B harness (live, safe only)

```bash
uv run interface-compiler eval live --max-looks 30 --min-interval 5
# expected: runs/<ts>-live/summary.md: sites attempted/skipped(by reason)/blocked, lying %, hidden % (if flag),
#           stop-before-commit agreement %, coverage vs AX %, p50/p95 latency, token ratio, cost $0
```

### M10: optional naming models + lift

```bash
uv run interface-compiler models check    # expected: reachable true/false + which models present; never installs
uv run interface-compiler eval mind2web --split test_website --limit 200 --naming off
uv run interface-compiler eval mind2web --split test_website --limit 200 --naming embed
uv run interface-compiler eval mind2web --split test_website --limit 200 --naming llm
# expected: three summaries; README ablation table filled (rules / +embed / +llm)
uv run pytest -q                          # expected: all pass with Ollama absent (naming falls back silently)
```

### M11: agent arms (optional, local model)

```bash
uv run interface-compiler eval agent --arms a11y,flat,doc,ablation --model ollama:qwen3:1.7b --limit 30
# expected: per-arm table (success, median tokens, steps, illegal/malformed/ignored per step, latency),
#           paired bootstrap CIs, frontier table, refusals reported separately
```

### M12: README finalization

Fill every `TODO(Mx)` in the README with real outputs and numbers from `runs/` (cite the run directory names). Remove `PLAN.md` from the README's doc list only if the owner asks.

```bash
grep -n "TODO(" README.md                 # expected: no matches
```

## 15. Open items the builder must confirm, not guess

1. **`paper/paper.md`.** The markdown source is not public. If the owner has not supplied it by M0, commit `paper/paper.md` containing the title, abstract, citation, PDF URL, and sha256, plus the line "Full markdown source to be added by the author". Do not generate the paper text from the PDF.
2. **`mcp` SDK 2.x server API.** Confirm the current import path for the high-level server and for mounting Streamable HTTP inside an ASGI app before writing `server/mcp_server.py`. Tool names and shapes are fixed by §9.1 regardless.
3. **WebMCP surface.** Confirm `document.modelContext` vs the deprecated `navigator.modelContext`, and the `registerTool` / `provideContext` signatures, against the proposal's current text. Shim both.
4. **Mind2Web columns.** Load one row of `osunlp/Multimodal-Mind2Web` and print its keys before writing `evals/mind2web.py`. Adjust only the loader, not the metrics.
5. **Live smoke sites.** Re-check robots.txt for each smoke URL on the day of M8. Swap in a fallback rather than weakening any rule.
6. **License.** The owner chooses. The builder leaves `TODO(owner): license` in the README.
7. **Reference fixture details.** When the 21-page set lands, confirm the `pages.csv` header, the snapshot file names (HTML, a11y tree, screenshot), and the `selfcheck/` format. Adjust only the loader's column/glob/parse code. Never change the fixture files, and never tune the converter rules (R1-R5) per page to raise diff scores.
