"""
ai_agent.py — Multi-provider AI report content generator.

Fallback chain (tries each until one succeeds):
  1. Google Gemini  (user's API key)
  2. Groq           (free, no credit card, OpenAI-compatible)
  3. OpenRouter     (free models, no credit card)
  4. Local Smart    (pure Python, zero API calls — always works)

If ALL remote providers fail, the local engine guarantees a result.
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── JSON Parsing ────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extract JSON from model response, handling markdown fences."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)


def _normalize_result(result: dict, from_date: str, to_date: str,
                      department: str, remarks: str,
                      employee_name: str, project_name: str,
                      model_used: str) -> dict:
    """Enforce exactly 3 tasks/upcoming and inject metadata."""
    performed = list(result.get("tasks_performed") or [])[:3]
    while len(performed) < 3:
        performed.append("-")
    result["tasks_performed"] = performed

    upcoming = list(result.get("upcoming_tasks") or [])[:3]
    while len(upcoming) < 3:
        upcoming.append({"task": "-", "date": to_date})
    result["upcoming_tasks"] = upcoming

    result.update({
        "department": department,
        "from_date": from_date,
        "to_date": to_date,
        "remarks": remarks,
        "employee_name": employee_name,
        "project_name": project_name,
        "_model_used": model_used,
    })
    return result


# ── System Prompt (shared across all providers) ────────────────────────────

SYSTEM_PROMPT = (
    "You are a professional technical report writer. "
    "Generate structured bi-weekly status report content.\n\n"
    "RULES:\n"
    "- Return ONLY a valid JSON object. No markdown fences, no explanation.\n"
    "- tasks_performed: exactly 3 concise professional strings (max 90 chars each).\n"
    "- upcoming_tasks: exactly 3 objects with keys 'task' (max 90 chars) and 'date' (MM/DD/YYYY).\n"
    "- Base upcoming dates roughly 1-2 weeks after the period end date.\n"
    "- Do NOT invent technologies or features not mentioned in the notes.\n"
    "- If fewer than 3 tasks are mentioned, derive logically related follow-up work.\n\n"
    'Return ONLY this JSON schema:\n'
    '{"tasks_performed": ["...", "...", "..."], '
    '"upcoming_tasks": [{"task": "...", "date": "MM/DD/YYYY"}, '
    '{"task": "...", "date": "MM/DD/YYYY"}, '
    '{"task": "...", "date": "MM/DD/YYYY"}]}'
)


def _build_user_msg(raw_notes: str, from_date: str, to_date: str,
                    department: str) -> str:
    return (
        f"Reporting period: {from_date} to {to_date}\n"
        f"Department: {department}\n\n"
        f"Raw notes:\n{raw_notes}"
    )


# ── Provider 1: Google Gemini ───────────────────────────────────────────────

def _try_gemini(user_msg: str, api_key: str) -> dict:
    """Call Google Gemini API using REST (no SDK dependency issues)."""
    if not api_key:
        raise ValueError("No Gemini API key")

    models = ["gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-2.0-flash"]

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_msg}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 429:
                time.sleep(1)
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_json(text), f"Gemini ({model})"
        except requests.exceptions.HTTPError as e:
            if "429" in str(e) or resp.status_code == 429:
                time.sleep(1)
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError):
            continue

    raise RuntimeError("All Gemini models returned errors")


# ── Provider 2: Groq (OpenAI-compatible, free) ─────────────────────────────

def _try_groq(user_msg: str, api_key: str) -> dict:
    """Call Groq API (OpenAI-compatible). Free, no credit card needed."""
    if not api_key:
        raise ValueError("No Groq API key")

    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

    for model in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(1)
                continue
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(text), f"Groq ({model})"
        except requests.exceptions.HTTPError:
            if resp.status_code == 429:
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError):
            continue

    raise RuntimeError("All Groq models returned errors")


# ── Provider 3: OpenRouter (free models, no credit card) ────────────────────

def _try_openrouter(user_msg: str, api_key: str) -> dict:
    """Call OpenRouter API with free models."""
    if not api_key:
        raise ValueError("No OpenRouter API key")

    models = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "openrouter/auto",
    ]

    for model in models:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://reportgenie.local",
                    "X-Title": "ReportGenie",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                },
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(1)
                continue
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(text), f"OpenRouter ({model})"
        except requests.exceptions.HTTPError:
            if resp.status_code == 429:
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError):
            continue

    raise RuntimeError("All OpenRouter models returned errors")


# ── Provider 4: Local Smart Engine (zero API, always works) ─────────────────

def _smart_local(raw_notes: str, from_date: str, to_date: str) -> dict:
    """
    Pure Python text processor. Parses bullet-point notes into clean tasks.
    No API calls. Never fails.
    """
    # Split on newlines, periods followed by space, and semicolons
    raw_lines = raw_notes.strip().split("\n")
    lines = []
    for raw_line in raw_lines:
        # Further split on ". " (sentence boundaries) and ";"
        sub_parts = re.split(r'(?:\.\s+|;\s*)', raw_line)
        lines.extend(sub_parts)

    tasks = []

    for line in lines:
        cleaned = re.sub(r"^[\s\-\*\•\▪\►\→\d\.]+", "", line).strip()
        # Remove trailing period
        cleaned = cleaned.rstrip(".")
        if not cleaned or len(cleaned) < 5:
            continue
        # Capitalize first letter
        cleaned = cleaned[0].upper() + cleaned[1:]
        # Truncate to 90 chars
        if len(cleaned) > 90:
            cleaned = cleaned[:87] + "..."
        tasks.append(cleaned)

    # Deduplicate while preserving order
    seen = set()
    unique_tasks = []
    for t in tasks:
        lower = t.lower()
        if lower not in seen:
            seen.add(lower)
            unique_tasks.append(t)

    # Take top 3 (or pad)
    performed = unique_tasks[:3]
    while len(performed) < 3:
        if len(unique_tasks) > len(performed):
            performed.append(unique_tasks[len(performed)])
        else:
            performed.append("-")

    # Generate upcoming dates
    try:
        base = datetime.strptime(to_date.strip(), "%m/%d/%Y")
    except ValueError:
        base = datetime.today()

    # Generate upcoming tasks from remaining notes or derive from performed
    remaining = unique_tasks[3:]
    upcoming = []
    for i, task in enumerate(remaining[:3]):
        d = (base + timedelta(weeks=1, days=i * 2)).strftime("%m/%d/%Y")
        upcoming.append({"task": task, "date": d})

    # If not enough remaining, derive follow-ups
    follow_up_prefixes = ["Continue work on", "Complete and test", "Review and finalize"]
    while len(upcoming) < 3:
        idx = len(upcoming)
        base_task = performed[idx] if idx < len(performed) and performed[idx] != "-" else "project tasks"
        # Create a derived follow-up
        prefix = follow_up_prefixes[idx % len(follow_up_prefixes)]
        derived = f"{prefix} {base_task.lower()}"
        if len(derived) > 90:
            derived = derived[:87] + "..."
        d = (base + timedelta(weeks=1, days=idx * 3)).strftime("%m/%d/%Y")
        upcoming.append({"task": derived, "date": d})

    return {
        "tasks_performed": performed,
        "upcoming_tasks": upcoming,
    }, "Local Smart Engine"


# ── Public API ──────────────────────────────────────────────────────────────

def generate_report_content(
    raw_notes: str,
    from_date: str,
    to_date: str,
    department: str = "Technology",
    remarks: str = "",
    employee_name: str = "Rohith Rudrapati",
    project_name: str = "Modelone",
    gemini_key: str = None,
    groq_key: str = None,
    openrouter_key: str = None,
    mode: str = "ai",
) -> dict:
    """
    Generate structured report content using the multi-provider fallback chain.

    mode:
      - "ai"    → try Gemini → Groq → OpenRouter → Local fallback
      - "smart" → skip all APIs, use local smart engine directly

    Returns a dict ready for pdf_writer.fill_report().
    """
    # Resolve keys from env if not provided
    g_key = gemini_key or os.getenv("GEMINI_API_KEY", "")
    gr_key = groq_key or os.getenv("GROQ_API_KEY", "")
    or_key = openrouter_key or os.getenv("OPENROUTER_API_KEY", "")

    user_msg = _build_user_msg(raw_notes, from_date, to_date, department)
    errors = []

    if mode == "smart":
        result, model = _smart_local(raw_notes, from_date, to_date)
        return _normalize_result(result, from_date, to_date, department,
                                 remarks, employee_name, project_name, model)

    # AI mode: cascade through providers
    providers = []
    if g_key:
        providers.append(("Gemini", lambda: _try_gemini(user_msg, g_key)))
    if gr_key:
        providers.append(("Groq", lambda: _try_groq(user_msg, gr_key)))
    if or_key:
        providers.append(("OpenRouter", lambda: _try_openrouter(user_msg, or_key)))

    for name, fn in providers:
        try:
            result, model = fn()
            return _normalize_result(result, from_date, to_date, department,
                                     remarks, employee_name, project_name, model)
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    # All remote providers failed or no keys configured — fall back to local
    result, model = _smart_local(raw_notes, from_date, to_date)
    if errors:
        model += " (API fallback)"
    return _normalize_result(result, from_date, to_date, department,
                             remarks, employee_name, project_name, model)
