"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_GROQ_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = set(_tokenize(description))

    scored: list[tuple[int, dict]] = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.lower() not in item["size"].lower():
            continue

        haystack = " ".join(
            [item["title"], item["description"], " ".join(item["style_tags"])]
        )
        item_tokens = set(_tokenize(haystack))
        score = len(query_tokens & item_tokens)
        if score == 0:
            continue
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_brief = (
        f"- Title: {new_item['title']}\n"
        f"- Category: {new_item['category']}\n"
        f"- Style tags: {', '.join(new_item['style_tags'])}\n"
        f"- Colors: {', '.join(new_item['colors'])}\n"
        f"- Description: {new_item['description']}"
    )

    items = wardrobe.get("items", [])
    if not items:
        user_prompt = (
            "A user is considering buying this secondhand piece but hasn't told us about "
            "their existing wardrobe yet:\n\n"
            f"{item_brief}\n\n"
            "Give them general styling ideas in 3–5 sentences: what categories of pieces "
            "to pair it with (e.g. wide-leg jeans, chunky boots), what colors and vibes "
            "complement it, and one or two specific outfit directions they could build "
            "around it. Do not invent specific wardrobe items they own."
        )
    else:
        wardrobe_lines = []
        for w in items:
            notes = f" — {w['notes']}" if w.get("notes") else ""
            wardrobe_lines.append(
                f"- {w['name']} ({w['category']}; colors: {', '.join(w['colors'])}; "
                f"tags: {', '.join(w['style_tags'])}){notes}"
            )
        user_prompt = (
            "A user is considering buying this secondhand piece:\n\n"
            f"{item_brief}\n\n"
            "Here is the user's existing wardrobe:\n"
            + "\n".join(wardrobe_lines)
            + "\n\nSuggest 1–2 complete outfits that build around the new piece using "
            "items they already own. Name the wardrobe pieces explicitly (use their names "
            "as written). Keep it under 5 sentences and stay specific to the vibe of the "
            "new item."
        )

    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a thoughtful personal stylist helping a thrifter decide how "
                    "to wear a secondhand find. Be concrete, casual, and specific."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.6,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "Cannot create fit card: no outfit suggestion was provided."

    client = _get_groq_client()

    user_prompt = (
        "Write an Instagram/TikTok-style OOTD caption (2–4 sentences) for this thrifted "
        "find. It should sound like a real post — casual, a little personal, capturing "
        "the vibe of the outfit. Mention each of these once, woven in naturally (not a "
        "list): the item title, the price as $<price>, and the platform.\n\n"
        f"Item title: {new_item['title']}\n"
        f"Price: ${new_item['price']:.2f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n\n"
        f"Outfit it's being worn in:\n{outfit}\n\n"
        "Return only the caption — no quotes, no preamble, no hashtags unless they feel "
        "natural."
    )

    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write short, authentic OOTD captions for thrifted finds. "
                    "Sound like a real person posting, not a brand."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.9,
    )
    return response.choices[0].message.content.strip()
