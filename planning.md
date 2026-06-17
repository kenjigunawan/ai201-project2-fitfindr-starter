# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock secondhand listings dataset for items matching a natural-language description, optionally filtered by size and a maximum price, and returns the matches ranked by relevance score so the agent can pick the best candidate to style.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g. `"vintage graphic tee"`). Used for keyword scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): Optional size string (e.g. `"M"`, `"W30"`). Case-insensitive substring match against the listing's `size` field. `None` skips the size filter.
- `max_price` (float | None): Optional inclusive price ceiling. `None` skips the price filter.

**What it returns:**
A `list[dict]` of matching listings sorted by relevance score, highest first. Each dict carries the full listing schema:
- `id` (str), `title` (str), `description` (str), `category` (str, one of tops/bottoms/outerwear/shoes/accessories),
- `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair),
- `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str: depop/thredUp/poshmark).

Listings that score 0 on keyword overlap are dropped. Returns `[]` when nothing matches.

**What happens if it fails or returns nothing:**
The tool itself never raises — it returns `[]`. The planning loop checks for the empty list and short-circuits: it sets `session["error"]` to `"No listings matched — try a different description, size, or price range."` and skips `suggest_outfit` and `create_fit_card`. Downstream tools are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the selected listing plus the user's wardrobe and asks the LLM (Groq `llama-3.3-70b-versatile`) to propose 1–2 complete outfits built around the new item, naming specific wardrobe pieces by name when the wardrobe has items.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` (the candidate purchase). Provides title, description, category, style_tags, colors — used in the prompt so the LLM understands the piece's vibe.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe-item dicts. Each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. The list may be empty (new-user case).

**What it returns:**
A non-empty `str` containing the LLM's outfit suggestions.
- If the wardrobe has items: the string references specific wardrobe pieces by name (e.g. "pair with your baggy straight-leg jeans and chunky white sneakers").
- If the wardrobe is empty: the string is general styling advice for the new item — what categories/colors/vibes pair well — rather than inventing wardrobe pieces.

**What happens if it fails or returns nothing:**
The empty-wardrobe branch is handled inside the tool, so it still returns a useful string in that case. If the LLM call errors or returns whitespace, the planning loop treats the suggestion as missing: it sets `session["error"]` to `"Could not generate an outfit suggestion. Please try again."` and skips `create_fit_card` (which needs a real outfit string).

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, shareable OOTD-style caption (2–4 sentences) for the thrifted find — the kind of thing someone would actually post on Instagram or TikTok — naturally mentioning the item title, price, and platform in a casual voice.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Provides the styling context the caption riffs on.
- `new_item` (dict): The listing dict for the thrifted item. Used to pull `title`, `price` (as `$<price>`), and `platform` so the caption mentions each once.

**What it returns:**
A `str` (2–4 sentences) reading like a real OOTD caption — casual and specific to the outfit's vibe, mentioning the item title, `$price`, and `platform` exactly once each. Uses a higher LLM temperature (~0.9) so repeated runs on the same input produce different wording.

**What happens if it fails or returns nothing:**
The tool guards against an empty / whitespace-only `outfit` argument by returning a descriptive error string (e.g. `"Cannot create fit card: no outfit suggestion was provided."`) instead of raising. The agent stores that string in `session["fit_card"]` so the UI surfaces what went wrong instead of crashing the run.

---

### Additional Tools (if any)

_None for the required milestones. May add a `price_check` stretch tool later — will update this section before starting it._

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a linear pipeline where each step inspects the previous step's output and either advances or short-circuits. Concrete branches:

1. **Initialize** the session via `_new_session(query, wardrobe)`.
2. **Parse the query** into `{description, size, max_price}` using lightweight regex / string parsing (size patterns like `size M` / `M`; price patterns like `under $30`, `<= 30`; remaining text becomes `description`). Store in `session["parsed"]`.
3. **Call `search_listings(**session["parsed"])`.** Store the result in `session["search_results"]`.
   - **If `session["search_results"] == []`:** set `session["error"] = "No listings matched — try a different description, size, or price range."` and **return the session immediately**. Do NOT call `suggest_outfit` or `create_fit_card`.
   - **Else:** set `session["selected_item"] = session["search_results"][0]` (top-ranked match) and proceed.
4. **Call `suggest_outfit(session["selected_item"], session["wardrobe"])`.** Store the result in `session["outfit_suggestion"]`.
   - **If `session["outfit_suggestion"]` is empty or whitespace-only:** set `session["error"] = "Could not generate an outfit suggestion. Please try again."` and **return the session**. Do NOT call `create_fit_card`. (Note: the tool's empty-wardrobe branch returns general styling advice, so this branch only fires on a real LLM failure.)
   - **Else:** proceed.
5. **Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.** Store the result in `session["fit_card"]`.
6. **Return** the session.

The loop "knows it's done" when either (a) `session["fit_card"]` is set, or (b) `session["error"]` was set by one of the guards.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()` in `agent.py`) is the source of truth for the run. Each step writes its output into the dict and reads the previous step's output from it. The dict is also what `run_agent()` returns to `app.py`, so the UI always has the full trail.

| Key | Type | Written by | Read by |
|-----|------|------------|---------|
| `query` | str | `_new_session` (user input) | parse step |
| `parsed` | dict | parse step | `search_listings` call |
| `search_results` | list[dict] | `search_listings` step | selection step |
| `selected_item` | dict / None | selection step | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | dict | `_new_session` (from caller / Gradio radio) | `suggest_outfit` |
| `outfit_suggestion` | str / None | `suggest_outfit` step | `create_fit_card`, UI |
| `fit_card` | str / None | `create_fit_card` step | UI |
| `error` | str / None | any guard that triggers early return | UI (checked first — non-None means stop and show the error) |

Tools themselves are pure functions of their args — they never see the session. Only the planning loop reads/writes the session, which keeps each tool independently testable.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | `search_listings` returns `[]` (no listing matched the description / size / max_price) | Set `session["error"] = "No listings matched — try a different description, size, or price range."`, skip `suggest_outfit` and `create_fit_card`, and return the session. The UI shows this message in the listing panel and leaves the outfit and fit-card panels empty. |
| suggest_outfit | `wardrobe["items"]` is an empty list (new user with no wardrobe) | The tool itself branches: it sends a "general styling advice" prompt to the LLM and returns the resulting string. The agent does not branch — it proceeds normally to `create_fit_card`, and the user sees real styling advice instead of an error. (If the LLM call itself returns whitespace, the planning loop sets `session["error"] = "Could not generate an outfit suggestion. Please try again."` and skips `create_fit_card`.) |
| create_fit_card | `outfit` argument is empty or whitespace-only (suggest_outfit produced nothing usable) | The tool returns the string `"Cannot create fit card: no outfit suggestion was provided."` instead of raising. The agent stores it in `session["fit_card"]` so the user sees an explanatory message in the fit-card panel rather than a crashed UI. |

---

## Architecture

```mermaid
flowchart TD
    U["User query<br/>+ wardrobe choice"] --> H["app.py: handle_query"]
    H --> A["agent.run_agent(query, wardrobe)"]

    A --> S0["_new_session<br/>builds session dict"]
    S0 --> P["Parse query →<br/>description / size / max_price"]
    P -->|writes session.parsed| T1["Tool 1: search_listings"]

    T1 -->|results == []| E1["Set session.error =<br/>'No listings matched...'"]
    E1 --> R["Return session"]

    T1 -->|results non-empty<br/>writes session.search_results| SEL["selected_item = results[0]<br/>writes session.selected_item"]
    SEL --> T2["Tool 2: suggest_outfit<br/>(selected_item, wardrobe)"]

    T2 -->|wardrobe empty| T2a["LLM: general styling advice"]
    T2 -->|wardrobe has items| T2b["LLM: outfit using named pieces"]
    T2a --> OUT["writes session.outfit_suggestion"]
    T2b --> OUT

    OUT -->|empty / whitespace| E2["Set session.error =<br/>'Could not generate outfit...'"]
    E2 --> R

    OUT -->|valid suggestion| T3["Tool 3: create_fit_card<br/>(outfit, selected_item)"]
    T3 -->|writes session.fit_card| R

    R --> H2["app.py renders 3 panels:<br/>listing / outfit / fit card<br/>or error message"]
```

**Session state** (read/written by the planning loop, never by the tools):
`query` → `parsed` → `search_results` → `selected_item` → `outfit_suggestion` → `fit_card`, plus `wardrobe` (from the caller) and `error` (set by any guard).

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

I'll use **Claude (Sonnet 4.6 in Claude Code)** for each tool, one at a time, so I can test each in isolation before chaining them.

- **`search_listings`** — I'll give Claude the **Tool 1** spec block above (what-it-does, input parameters, return value, failure mode), the existing skeleton + docstring in `tools.py`, and `utils/data_loader.py`. I'll ask Claude to implement: load via `load_listings()` → filter by `size` (case-insensitive substring) and `max_price` (≤) → score each remaining listing by keyword overlap with `description` across `title` + `description` + `style_tags` → drop score-0 rows → sort descending by score. I'll verify against three queries before trusting it:
  1. `search_listings("vintage graphic tee", None, 30.0)` → must return at least one tee, ranked above non-tees.
  2. `search_listings("designer ballgown", "XXS", 5.0)` → must return `[]`.
  3. `search_listings("jeans", "W30", None)` → results must all have `"W30"` in their `size` field (case-insensitive).

- **`suggest_outfit`** — I'll give Claude the **Tool 2** spec block, one example listing dict (e.g. `lst_006`), and `data/wardrobe_schema.json` so it sees the exact wardrobe shape. I'll ask Claude to branch on `len(wardrobe["items"]) == 0` and use the existing `_get_groq_client()` helper. Verify by calling it once with `get_example_wardrobe()` (expect named pieces like "baggy straight-leg jeans" to appear in the output) and once with `get_empty_wardrobe()` (expect general styling advice with no invented wardrobe items).

- **`create_fit_card`** — I'll give Claude the **Tool 3** spec block and an example `(outfit, new_item)` pair. I'll ask Claude to (a) guard against an empty/whitespace `outfit`, (b) build a prompt that constrains length to 2–4 sentences and requires the item title, `$price`, and `platform` to each appear exactly once, (c) call the LLM at temperature ~0.9. Verify by running the tool 3 times on the same input — outputs should vary in wording, and each must include the title, the price, and the platform.

**Milestone 4 — Planning loop and state management:**

For `run_agent()` in `agent.py`, I'll give Claude:
- The **Planning Loop** and **State Management** sections above (the numbered branches with exact error strings).
- The **Architecture** Mermaid diagram.
- The skeleton of `agent.py` (including `_new_session` and the docstring TODO steps).
- The completed `tools.py`.

I'll ask Claude to implement `run_agent()` following the 7 numbered steps using the session keys exactly as listed in the State Management table — no new keys and no extra branching beyond the two early-return guards. I'll verify with the existing `EXAMPLE_QUERIES` in `app.py`: every happy-path query must populate `fit_card` and leave `error=None`; the `"designer ballgown size XXS under $5"` query must set `error` and leave `outfit_suggestion`/`fit_card` as `None`.

For `handle_query()` in `app.py`, I'll give Claude the same Planning Loop section plus the Gradio panel layout already in `app.py`, and ask it to: (a) guard against empty queries, (b) pick the wardrobe via the radio choice, (c) call `run_agent()`, (d) if `session["error"]` is set, show it in the listing panel with empty strings for the other two, else format `selected_item` into a readable listing string and return it along with `outfit_suggestion` and `fit_card`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do (in 2–3 sentences):**
FitFindr takes a natural-language thrifting request, parses out the description / size / price ceiling, and triggers `search_listings` to find matching secondhand items; the top result then triggers `suggest_outfit` against the user's wardrobe (or general styling advice if the wardrobe is empty), which in turn triggers `create_fit_card` to write a shareable caption. If `search_listings` returns nothing, the agent stops, surfaces a helpful "no matches — try different filters" message, and never calls `suggest_outfit` or `create_fit_card` with empty input; if `suggest_outfit` returns nothing, the agent stops before `create_fit_card`; if `create_fit_card` gets empty input, it returns a descriptive error string instead of crashing.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
The agent parses the user's query; what they look for (which category), their budget, and their size.

Concretely: parsing yields `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}` (no size was specified in this query). The agent stores it in `session["parsed"]` and calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`.

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
Step 1 returns a listing that matches the query.

In this run the top match is likely `lst_006` (`"Graphic Tee — 2003 Tour Bootleg Style"`, $24, `depop`, condition `good`) — it scores high on the `"vintage"` + `"graphic tee"` keywords and sits under the $30 ceiling. The agent stores it in `session["selected_item"]`.

If the return is nonempty; then Fitfindr looks into the user's wardrobe, with the new_item; and suggests a new outfit with the wardrobe and the new_item.

Concretely: `suggest_outfit(new_item=lst_006_dict, wardrobe=example_wardrobe)` is called. The LLM sees the graphic tee plus the wardrobe (baggy jeans `w_001`, chunky white sneakers `w_007`, vintage black denim jacket `w_006`, etc.) and returns something like: *"Pair the bootleg tee with your baggy straight-leg jeans and chunky white sneakers for an easy streetwear look — throw the vintage black denim jacket on top to layer."* The string is stored in `session["outfit_suggestion"]`.

If the return is empty; this means the user's input doesn't match what is required. The agent can prompt for the empty descriptions/parsing, or reparse the input. If the input was parsed correctly; then the agent can suggest a different outfit combination, or a change in one of the attributes (like price, size, or category/description).

In this implementation, an empty `search_results` short-circuits the loop: `session["error"]` is set to `"No listings matched — try a different description, size, or price range."` and we return immediately without calling `suggest_outfit` or `create_fit_card`.

**Step 3:**
<!-- Continue until the full interaction is complete -->
Lastly, create fit card;

Concretely: `create_fit_card(outfit=<the string from Step 2>, new_item=lst_006_dict)` is called. The LLM returns a 2–4 sentence OOTD caption mentioning the title, `$24`, and `depop` naturally — e.g. *"Snagged this 2003 tour bootleg tee off depop for $24 and immediately threw it on with my baggy jeans and chunky sneakers. Vintage black denim jacket on top to layer it up. Felt unreasonably good walking out of the house."* The string is stored in `session["fit_card"]`.

**Final output to user:**
<!-- What does the user actually see at the end? -->
The Gradio UI shows three panels side by side:

- **🛍️ Top listing found** — formatted details of `session["selected_item"]`: title, price, platform, condition, size, and description.
- **👗 Outfit idea** — the `session["outfit_suggestion"]` string from Tool 2.
- **✨ Your fit card** — the `session["fit_card"]` caption from Tool 3.

If `session["error"]` was set at any earlier step, the user sees the error message in the listing panel and the other two panels are empty.
