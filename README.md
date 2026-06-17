# FitFindr

FitFindr is a multi-tool AI agent that helps a thrifter find secondhand pieces and figure out how to wear them. It takes a natural-language request ("vintage graphic tee under $30"), searches a mock listings dataset, suggests outfits using the user's existing wardrobe, and writes a shareable OOTD-style caption — handling the messy reality of what happens when a tool returns nothing.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # The three required tools
├── agent.py                   # Planning loop + session state
├── app.py                     # Gradio UI
├── planning.md                # Spec written before implementation
└── requirements.txt           # Python dependencies
```

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```
Then open the URL shown in your terminal (usually `http://localhost:7860`).

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format the agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items used for testing
- `empty_wardrobe`: a starting template for a new user (triggers the empty-wardrobe failure path)

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

---

## Tool Inventory

All three tools live in `tools.py`. The signatures below match the actual function definitions verbatim.

### `search_listings(description, size=None, max_price=None) -> list[dict]`

**Inputs**
- `description` (`str`) — keywords describing what the user wants (e.g. `"vintage graphic tee"`). Used for keyword scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (`str | None`) — optional case-insensitive substring match against the listing's `size` field. `None` skips the size filter.
- `max_price` (`float | None`) — optional inclusive price ceiling. `None` skips the price filter.

**Output** — A `list[dict]` of matching listings sorted by relevance score, highest first. Each dict carries the full listing schema (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`). Listings that score 0 on keyword overlap are dropped. Returns `[]` when nothing matches.

**Purpose** — Narrows 40 mock listings down to the candidates most worth styling. Never raises — returns `[]` so the planning loop can short-circuit cleanly.

### `suggest_outfit(new_item, wardrobe) -> str`

**Inputs**
- `new_item` (`dict`) — a listing dict from `search_listings` (the candidate purchase). Provides title, description, category, style_tags, colors that the LLM uses to understand the piece's vibe.
- `wardrobe` (`dict`) — a wardrobe dict with an `items` key containing a list of wardrobe-item dicts. May be empty.

**Output** — A non-empty `str` containing outfit ideas. If `wardrobe["items"]` is non-empty, the string names specific wardrobe pieces by name. If empty, the string is general styling advice for the new item — categories/colors/vibes — rather than invented wardrobe items.

**Purpose** — Bridges the listing search and the caption. Uses Groq `llama-3.3-70b-versatile` at temperature 0.6. Handles the new-user case (empty wardrobe) inside the tool so the agent doesn't need to branch.

### `create_fit_card(outfit, new_item) -> str`

**Inputs**
- `outfit` (`str`) — the outfit suggestion string returned by `suggest_outfit`.
- `new_item` (`dict`) — the listing dict for the thrifted item. Used to pull title, price (as `$<price>`), and platform.

**Output** — A 2–4 sentence OOTD-style caption naturally mentioning the title, `$price`, and `platform` once each. Different on every run for the same input (temperature 0.9). If `outfit` is empty or whitespace, returns the descriptive string `"Cannot create fit card: no outfit suggestion was provided."` instead of raising.

**Purpose** — Produces the user-facing artifact: something that actually sounds like a real OOTD post, not a product description.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"` (Example wardrobe selected in the UI)

**Step 1 — Tool called: `search_listings`**
- Tool: `search_listings(description="vintage graphic tee", size=None, max_price=30.0)` (parsed from the natural-language query in `agent._parse_query`)
- Why this tool: it's the only one that can narrow the 40-listing dataset down to candidates that match the user's request.
- Output: 22 ranked matches. Top result is `lst_002` — `"Y2K Baby Tee — Butterfly Print"`, $18, depop, condition `excellent`, style_tags `[y2k, vintage, graphic tee, cottagecore]`. Stored in `session["selected_item"]`.

**Step 2 — Tool called: `suggest_outfit`**
- Tool: `suggest_outfit(new_item=<lst_002 dict>, wardrobe=<example_wardrobe>)`
- Why this tool: now that we have a concrete candidate, we need to know whether and how it works with what the user already owns.
- Output: *"To create a cute and nostalgic outfit, pair the Y2K Baby Tee — Butterfly Print with the Baggy straight-leg jeans and the Chunky white sneakers for a playful, vintage-inspired look. The oversized fit of the jeans will balance out the cropped length of the tee…"* — references specific wardrobe pieces by name. Stored in `session["outfit_suggestion"]`.

**Step 3 — Tool called: `create_fit_card`**
- Tool: `create_fit_card(outfit=<the string from Step 2>, new_item=<lst_002 dict>)`
- Why this tool: turn the styling advice into something the user could actually post.
- Output: *"I just found the cutest Y2K Baby Tee — Butterfly Print on depop for $18.00 and I'm obsessed with how it adds a touch of vintage charm to my outfit. Paired it with my fave baggy jeans and chunky sneakers for a laid-back vibe, and threw on a grey crewneck…"* Stored in `session["fit_card"]`.

**Final output to user:** Three Gradio panels populate side-by-side — the listing details (title, price, platform, condition, size, description), the outfit suggestion, and the fit card. State flowed entirely through `session`; nothing was re-entered between steps.

---

## How the Planning Loop Works

`agent.run_agent` is a linear pipeline where each step inspects the previous step's output and either advances or short-circuits. The decision is not "which tool next" but "is what I just got back usable?"

1. **Initialize** the session via `_new_session(query, wardrobe)`.
2. **Parse the query** with `_parse_query` (regex for "under $30", "size M" / "W30" / "XS"; remainder becomes `description`). Store in `session["parsed"]`.
3. **Call `search_listings(**session["parsed"])`** and store in `session["search_results"]`.
   - **Branch A — empty results:** set `session["error"] = "No listings matched — try a different description, size, or price range."` and **return early**. `suggest_outfit` and `create_fit_card` are never called.
   - **Branch B — non-empty:** set `session["selected_item"] = session["search_results"][0]` and proceed.
4. **Call `suggest_outfit(selected_item, wardrobe)`** and store in `session["outfit_suggestion"]`.
   - **Branch A — empty/whitespace string:** set `session["error"]` and **return early**. `create_fit_card` is not called. (The empty-wardrobe case does not hit this branch because the tool itself returns general styling advice.)
   - **Branch B — valid suggestion:** proceed.
5. **Call `create_fit_card(outfit_suggestion, selected_item)`** and store in `session["fit_card"]`.
6. **Return** the session.

The loop knows it's done when either `session["fit_card"]` is set or `session["error"]` was set by one of the guards.

The behavior visibly differs based on what the tools return: with the impossible query `"designer ballgown size XXS under $5"`, the loop stops after Step 3 and `selected_item` / `outfit_suggestion` / `fit_card` all remain `None`. With a happy-path query, all three populate.

---

## State Management

A single `session` dict (created by `_new_session`) is the source of truth for one interaction. Each step writes its output into the dict and reads the previous step's output from it. The dict is also what `run_agent` returns, so `app.py:handle_query` always has the full trail.

| Key | Type | Written by | Read by |
|-----|------|------------|---------|
| `query` | `str` | `_new_session` (user input) | parse step |
| `parsed` | `dict` | parse step | `search_listings` call |
| `search_results` | `list[dict]` | search step | selection step |
| `selected_item` | `dict \| None` | selection step | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | `dict` | `_new_session` (Gradio radio choice) | `suggest_outfit` |
| `outfit_suggestion` | `str \| None` | `suggest_outfit` step | `create_fit_card`, UI |
| `fit_card` | `str \| None` | `create_fit_card` step | UI |
| `error` | `str \| None` | any guard that triggers early return | UI (checked first — non-`None` means stop and show the message) |

Tools never see the session — they are pure functions of their args. Only `run_agent` reads/writes the session. This keeps each tool independently testable; it also means state passing is observable: `session["selected_item"] is session["search_results"][0]` (identity equality, verified during Milestone 4 testing).

---

## Error Handling and Fail Points

Every tool handles its own failure mode without raising. The agent surfaces a specific, actionable message — never a stack trace and never silent failure. Each row below was triggered deliberately during Milestone 5 testing.

| Tool | Failure mode | Agent response | Concrete example from testing |
|------|--------------|----------------|-------------------------------|
| `search_listings` | Returns `[]` when nothing matches `description` / `size` / `max_price` | Planning loop sets `session["error"] = "No listings matched — try a different description, size, or price range."` and skips `suggest_outfit` and `create_fit_card`. UI shows the message in the listing panel; the outfit and fit-card panels stay empty. | `run_agent("designer ballgown size XXS under $5", get_example_wardrobe())` → `session["error"]` set; `selected_item`, `outfit_suggestion`, and `fit_card` all `None` (downstream tools confirmed uncalled). |
| `suggest_outfit` | `wardrobe["items"]` is an empty list (new-user case) | Tool branches internally and sends a "general styling advice" prompt to the LLM. Agent does not branch — it proceeds normally to `create_fit_card`, and the user sees real styling advice with no invented wardrobe pieces. | `suggest_outfit(results[0], get_empty_wardrobe())` for the Y2K Baby Tee returned a 5-sentence styling-advice string ("pair with high-waisted jeans or a flowy skirt… earth tones like beige or olive green… chunky sneakers and a denim jacket…") — no fabricated wardrobe items, no empty string, no exception. |
| `create_fit_card` | `outfit` argument is empty or whitespace-only | Tool returns the string `"Cannot create fit card: no outfit suggestion was provided."` instead of raising. Agent stores it in `session["fit_card"]` so the UI surfaces the explanation. | Both `create_fit_card("", listing)` and `create_fit_card("   ", listing)` returned the descriptive error string. No `ValueError`, no LLM call wasted on empty input. |

---

## Spec Reflection

**One way `planning.md` helped during implementation:** Writing out the planning-loop conditional logic before any code — the exact branches, the exact error strings, the `session["error"] = "..."` lines — meant that when I implemented `run_agent`, there were no design decisions left to make. The function was a near-direct transcription of the numbered steps. The same thing applied to error handling: each tool's failure mode was specified before I touched the code, so writing the empty-wardrobe branch inside `suggest_outfit` (instead of branching at the agent level) was a deliberate spec choice, not something I discovered while coding.

**One divergence from the spec, and why:** The spec described query parsing as "regex / string parsing or LLM extraction — document your choice." I went with regex (`_PRICE_RE`, `_SIZE_RE`) instead of LLM extraction because it was deterministic, free, instant, and easy to test against the five `EXAMPLE_QUERIES` in `app.py`. The downside: parsing is brittle on phrasings outside the examples (e.g. "around forty bucks" won't match the price regex). For this dataset and these example queries it's the right call; for a real product, an LLM extraction call would be worth the latency.

---

## AI Usage

I used Claude Code (Sonnet 4.6) for the implementation work, with planning.md as the source of truth. Below are concrete instances.

### Instance 1 — Implementing `search_listings`

**What I gave Claude:** the Tool 1 spec block from `planning.md` (the `description` / `size` / `max_price` parameter list with types and meanings, the return-shape description including all 11 listing fields, the "returns `[]`, never raises" failure clause), the `tools.py` skeleton, and `utils/data_loader.py`. I asked Claude to implement the function following the 5-step TODO in the docstring: load → filter by size/price → score by keyword overlap with description across title + description + style_tags → drop score-0 → sort descending.

**What it produced:** a working implementation that tokenized via `re.findall(r"[a-z0-9]+", text.lower())`, used set intersection for scoring, and sorted with `key=lambda pair: pair[0], reverse=True`. I verified it against the three queries I'd specified in the AI Tool Plan section of `planning.md`:
1. `"vintage graphic tee"` with `max_price=30` — returned 20+ tee-heavy results, Y2K Baby Tee ranked first. ✓
2. `"designer ballgown"` with `size="XXS"`, `max_price=5` — returned `[]`. ✓
3. `"jeans"` with `size="W30"` — returned only Levi's 501s (the one W30 entry). ✓

**What I overrode:** Claude's first draft kept the listing's `size` field comparison case-sensitive (a strict `==`), which would have broken on queries like `size="m"` matching `"M"`. I changed it to `size.lower() in item["size"].lower()` (substring, case-insensitive) so `"M"` matches both `"M"` and `"S/M"`, matching the spec.

### Instance 2 — Implementing `run_agent` in `agent.py`

**What I gave Claude:** the Planning Loop section of `planning.md` (the 7 numbered steps with exact error strings), the State Management table (the 8 session keys with their types and read/write owners), the Mermaid architecture diagram, and the `agent.py` skeleton with its `_new_session` already in place. The instruction was to follow the 7 steps using exactly the listed session keys — no new keys, no extra branches.

**What it produced:** a `run_agent` implementation that initialized via `_new_session`, called `_parse_query`, ran `search_listings(**parsed)`, used `if not session["search_results"]` to short-circuit with the exact spec error string, indexed `[0]` for the top result, called `suggest_outfit` and guarded its output with `not session["outfit_suggestion"] or not session["outfit_suggestion"].strip()`, and finally called `create_fit_card`. The state-passing check `session["selected_item"] is session["search_results"][0]` confirmed identity equality.

**What I overrode:** Claude's initial draft had a `try/except` around each LLM call that swallowed exceptions silently and set a generic "An error occurred" string. I removed it — silent exception-swallowing was explicitly out of scope for the spec (the planning loop only handles documented failure modes, not arbitrary LLM exceptions), and a vague error message contradicts the "specific, informative response" requirement. If an LLM call genuinely fails, I want the stack trace so I can debug, not a generic catch-all that hides what broke.

---

## Where Each Milestone Landed

- **Milestone 1** — `planning.md` "A Complete Interaction" section opens with the 2–3 sentence summary of what FitFindr does, what triggers each tool, and what happens on failure.
- **Milestone 2** — `planning.md` is fully filled in: Tools 1–3 specs, planning-loop conditional logic, state management table, error-handling table, Mermaid architecture diagram, AI Tool Plan, and the step-by-step interaction walkthrough.
- **Milestone 3** — `tools.py` has working implementations of all three tools, each tested in isolation against the 3 queries / 2 wardrobe states / 3-run variety check defined in the spec.
- **Milestone 4** — `agent.run_agent` and `app.handle_query` are wired together; state passes through the session dict; the no-results branch leaves `outfit_suggestion` and `fit_card` as `None`.
- **Milestone 5** — all three failure modes triggered deliberately and verified to produce specific, informative responses (see the Error Handling table above).
- **Milestone 6** — this README documents everything above.
