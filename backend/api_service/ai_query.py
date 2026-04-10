from __future__ import annotations

import json
import os
from typing import Any, Dict

from .settings import Settings, load_local_env

_ALLOWED_TOP_LEVEL = {
    "run_profile",
    "energy_model_engine",
    "target_year",
    "target_scenario_id",
    "scenario_patch",
    "levers",
    "geography_focus",
    "updates",
    "warnings",
    "message",
}

_ALLOWED_SCENARIO_PATCH = {"family", "pathway", "generation", "transmission", "policy"}
_ALLOWED_LEVERS = {
    "demand_multiplier",
    "renewables_capex_multiplier",
    "fossil_fuel_price_multiplier",
    "carbon_price_usd_per_tco2",
}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def _runtime_ai_config(settings: Settings) -> Dict[str, Any]:
    cfg = settings.runtime_config if isinstance(settings.runtime_config, dict) else {}
    ai_cfg = cfg.get("ai") if isinstance(cfg.get("ai"), dict) else {}
    return ai_cfg if isinstance(ai_cfg, dict) else {}


def _resolve_ai_client(settings: Settings):
    load_local_env()
    ai_cfg = _runtime_ai_config(settings)
    api_key = _env("AZURE_OPENAI_API_KEY") or _env("OPENAI_API_KEY")
    deployment = _env("AZURE_OPENAI_DEPLOYMENT") or _env("OPENAI_FILTER_MODEL") or str(ai_cfg.get("deployment") or "").strip()
    azure_endpoint = (
        _env("AZURE_OPENAI_ENDPOINT")
        or _env("OPENAI_ENDPOINT")
        or _env("OPENAI_API_BASE")
        or str(ai_cfg.get("azure_endpoint") or "").strip()
    )
    api_version = _env("AZURE_OPENAI_API_VERSION") or str(ai_cfg.get("azure_api_version") or "2025-01-01-preview").strip()

    if not api_key:
        return None, "Azure/OpenAI API key is not configured in .env."
    if not deployment:
        return None, "Azure/OpenAI deployment or model is not configured. Set AZURE_OPENAI_DEPLOYMENT or OPENAI_FILTER_MODEL."

    try:
        from openai import AzureOpenAI, OpenAI  # type: ignore
    except Exception:
        return None, "The openai Python package is not installed in this backend environment."

    if azure_endpoint:
        return (
            {
                "client": AzureOpenAI(api_key=api_key, azure_endpoint=azure_endpoint, api_version=api_version),
                "model": deployment,
                "provider": "azure_openai",
            },
            "",
        )

    return (
        {
            "client": OpenAI(api_key=api_key),
            "model": deployment,
            "provider": "openai",
        },
        "",
    )


def _system_prompt() -> str:
    return """
You are an EDIM scenario query planner. Convert the user's natural-language query into a strict JSON object for UI controls.
Return JSON only, no markdown.

Schema:
{
  "message": "short human-readable summary",
  "run_profile": "dev|analysis|full|null",
  "energy_model_engine": "calliope|osemosys|null",
  "target_year": 2030_or_2050_or_null,
  "target_scenario_id": "S1|S2|null",
  "scenario_patch": {
    "family": "pathway_2040|transmission_only|null",
    "pathway": "STEPS|AC|null",
    "generation": "legacy|new|null",
    "transmission": "legacy|new|null",
    "policy": true_or_false_or_null
  },
  "levers": {
    "demand_multiplier": number_or_null,
    "renewables_capex_multiplier": number_or_null,
    "fossil_fuel_price_multiplier": number_or_null,
    "carbon_price_usd_per_tco2": number_or_null
  },
  "geography_focus": {
    "type": "global|country|subregion|region|null",
    "label": "display label or null",
    "country_iso3": "ISO3 or null",
    "location_id": "Calliope location id or null",
    "region": "normalized region id such as west_africa or null",
    "pool": "power pool such as WAPP or null"
  },
  "updates": [{"parameter":"UI parameter name", "value":"selected value", "reason":"why the query implies this"}],
  "warnings": ["uncertainty or missing information"]
}

Rules:
- Use only settings that are clearly implied by the query. Use null when uncertain.
- If the query names Calliope or OSeMOSYS, set energy_model_engine accordingly. Otherwise leave it null.
- S1 means decarbonization/full decarbonization. S2 means national policy target/NDC/current national policy.
- AC means Announced Commitments; STEPS means Stated Policies.
- Clamp lever values conceptually to UI ranges: demand 0.8-1.4, renewables CAPEX 0.7-1.5, fossil cost 0.7-1.8, carbon price 0-300.
- If the query says a percentage increase, convert to multiplier 1 + percent/100. If decrease, 1 - percent/100.
- For geography, prefer ISO3 country codes when a country is named. Use global for Africa-wide/all countries/global.
- Explain every non-null setting in updates.
""".strip()


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty model response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object")
    return parsed


def _clean_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {key: plan.get(key) for key in _ALLOWED_TOP_LEVEL if key in plan}

    scenario_patch = cleaned.get("scenario_patch")
    if isinstance(scenario_patch, dict):
        cleaned["scenario_patch"] = {
            key: value for key, value in scenario_patch.items() if key in _ALLOWED_SCENARIO_PATCH and value is not None
        }
    else:
        cleaned["scenario_patch"] = {}

    levers = cleaned.get("levers")
    if isinstance(levers, dict):
        cleaned["levers"] = {key: value for key, value in levers.items() if key in _ALLOWED_LEVERS and value is not None}
    else:
        cleaned["levers"] = {}

    focus = cleaned.get("geography_focus")
    cleaned["geography_focus"] = focus if isinstance(focus, dict) else {}

    engine = str(cleaned.get("energy_model_engine") or "").strip().lower()
    cleaned["energy_model_engine"] = engine if engine in {"calliope", "osemosys"} else None

    updates = cleaned.get("updates")
    cleaned["updates"] = [row for row in updates if isinstance(row, dict)] if isinstance(updates, list) else []
    warnings = cleaned.get("warnings")
    cleaned["warnings"] = [str(row) for row in warnings if str(row).strip()] if isinstance(warnings, list) else []
    cleaned["message"] = str(cleaned.get("message") or "Azure OpenAI returned a scenario configuration plan.")
    return cleaned


def plan_scenario_query(payload: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    query = str((payload or {}).get("query") or "").strip()
    if not query:
        return {
            "ok": False,
            "source": "azure_openai",
            "message": "No query was provided. Enter a new query with scenario, year, lever, or geography intent.",
            "plan": {},
            "updates": [],
            "warnings": [],
        }

    resolved, config_error = _resolve_ai_client(settings)
    if config_error:
        return {
            "ok": False,
            "source": "azure_openai",
            "message": config_error,
            "plan": {},
            "updates": [],
            "warnings": ["Falling back to the local deterministic parser in the frontend is recommended."],
        }

    context = {
        "query": query,
        "current": (payload or {}).get("current") or {},
        "available": (payload or {}).get("available") or {},
    }

    try:
        response = resolved["client"].chat.completions.create(
            model=resolved["model"],
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
            ],
        )
        content = response.choices[0].message.content or ""
        plan = _clean_plan(_extract_json_object(content))
    except Exception as exc:
        return {
            "ok": False,
            "source": resolved.get("provider", "azure_openai"),
            "message": "The AI planner could not produce a valid scenario plan. Enter a clearer query or use the manual controls.",
            "plan": {},
            "updates": [],
            "warnings": [str(exc)[:240]],
        }

    has_plan = bool(
        plan.get("run_profile")
        or plan.get("energy_model_engine")
        or plan.get("target_year")
        or plan.get("target_scenario_id")
        or plan.get("scenario_patch")
        or plan.get("levers")
        or plan.get("geography_focus")
    )
    return {
        "ok": has_plan,
        "source": resolved.get("provider", "azure_openai"),
        "message": plan.get("message") or ("AI planner returned a scenario configuration." if has_plan else "The AI planner did not infer any setting."),
        "plan": plan,
        "updates": plan.get("updates") or [],
        "warnings": plan.get("warnings") or [],
    }
