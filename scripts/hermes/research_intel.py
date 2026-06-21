#!/usr/bin/env python3
"""Hermes Research Intelligence pilot CLI.

This script is intentionally conservative. It creates auditable research and
GTM-enrichment artifacts, but keeps cookie access and Clay spend behind explicit
operator gates.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


TODAY = dt.datetime.now().strftime("%Y-%m-%d")
DEFAULT_POLICY = Path.home() / ".hermes" / "research-intel" / "policy.yaml"
DEFAULT_ARTIFACT_ROOT = Path("artifacts") / "research-intel"
SECRET_ENV_FILE = Path.home() / ".hermes" / ".env"
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.3"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "research-intel"


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    for path in [
        Path("research") / "briefs",
        Path("research") / "sources",
        Path("research") / "notes",
        Path("reports"),
        DEFAULT_ARTIFACT_ROOT,
        Path("tasks"),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_secret_env(path: Path = SECRET_ENV_FILE) -> dict:
    loaded = []
    if not path.exists():
        return {"path": str(path), "present": False, "loaded_keys": loaded}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return {"path": str(path), "present": True, "loaded_keys": loaded}


def run_command(argv: list[str], timeout: int = 45) -> dict:
    try:
        proc = subprocess.run(
            argv,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "argv": argv,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "ok": False, "error": str(exc)}


def command_version(name: str) -> dict:
    path = shutil.which(name)
    result = {"name": name, "present": bool(path), "path": path}
    if not path:
        return result
    for flag in ["--version", "version"]:
        out = run_command([path, flag], timeout=8)
        if out.get("ok") or out.get("stdout") or out.get("stderr"):
            result["version_probe"] = {
                "flag": flag,
                "ok": out.get("ok", False),
                "output": "\n".join(
                    part for part in [out.get("stdout", ""), out.get("stderr", "")] if part
                )[:1200],
            }
            break
    return result


def policy_summary(policy_path: Path) -> dict:
    if not policy_path.exists():
        return {
            "path": str(policy_path),
            "present": False,
            "cookie_access": "disabled",
            "note": "Create this file to allowlist cookie-backed platforms.",
        }
    text = policy_path.read_text(encoding="utf-8", errors="replace")
    cookie_enabled = bool(re.search(r"allow_cookie_access\s*:\s*true", text, re.I))
    clay_spend = bool(re.search(r"allow_clay_spend\s*:\s*true", text, re.I))
    platforms = []
    in_cookie_platforms = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("cookie_platforms:"):
            in_cookie_platforms = True
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                platforms.extend(
                    item.strip().strip("'\"")
                    for item in inline.strip("[]").split(",")
                    if item.strip()
                )
            continue
        if in_cookie_platforms:
            if raw_line and not raw_line.startswith((" ", "\t", "-")):
                in_cookie_platforms = False
            elif stripped.startswith("-"):
                platforms.append(stripped[1:].strip().strip("'\""))
    return {
        "path": str(policy_path),
        "present": True,
        "cookie_access": "allowlisted" if cookie_enabled else "disabled",
        "clay_spend_policy": "allowlisted" if clay_spend else "disabled",
        "allowlisted_platforms": platforms,
    }


def secret_signal(name: str) -> str:
    return "present" if os.environ.get(name) else "missing"


def redact_url(value: str | None) -> str:
    if not value:
        return "missing"
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return "configured-invalid-url"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def classify_clay_url(value: str | None) -> dict:
    if not value:
        return {
            "configured": False,
            "classification": "missing",
            "post_safe": False,
            "reason": "No Clay URL configured.",
        }
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "configured": True,
            "classification": "invalid",
            "post_safe": False,
            "reason": "URL must be an absolute http(s) endpoint.",
        }
    if parsed.netloc == "app.clay.com" and "/workbooks/" in parsed.path:
        return {
            "configured": True,
            "classification": "clay_workbook_ui",
            "post_safe": False,
            "reason": "This is the Clay workbook/table UI URL, not the table webhook endpoint.",
        }
    if parsed.netloc == "app.clay.com":
        return {
            "configured": True,
            "classification": "clay_app_ui",
            "post_safe": False,
            "reason": "app.clay.com URLs are browser UI routes and are not safe to POST from Hermes.",
        }
    return {
        "configured": True,
        "classification": "candidate_webhook_endpoint",
        "post_safe": True,
        "reason": "The URL is not a Clay app UI route. Treat it as a candidate webhook only after human approval.",
    }


def request_json(url: str, payload: dict, headers: dict, timeout_seconds: int) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "json": json.loads(raw) if raw else {},
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:2000]}
        return {"ok": False, "status": exc.code, "json": parsed}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


def response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("transcript")
                if text:
                    chunks.append(str(text))
    return "\n".join(chunks).strip()


def safe_error(value) -> object:
    if isinstance(value, str):
        value = re.sub(r"https://console\.x\.ai/team/[a-f0-9-]+", "https://console.x.ai/team/<team-id>", value)
        value = re.sub(r"(xai-)[A-Za-z0-9_-]+", r"\1<redacted>", value)
        return value
    if isinstance(value, dict):
        return {key: safe_error(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_error(item) for item in value]
    return value


def doctor(args: argparse.Namespace) -> int:
    secret_env = load_secret_env()
    policy = policy_summary(Path(args.policy))
    tools = [command_version(name) for name in ["agent-reach", "yt-dlp", "gh", "hermes"]]
    status = {
        "checked_at": timestamp(),
        "cwd": str(Path.cwd()),
        "policy": policy,
        "tools": tools,
        "secrets": {
            "CLAY_API_KEY": secret_signal("CLAY_API_KEY"),
            "CLAY_MCP_URL": secret_signal("CLAY_MCP_URL"),
            "XAI_API_KEY": secret_signal("XAI_API_KEY"),
        },
        "secret_env": {
            "path": secret_env["path"],
            "present": secret_env["present"],
            "loaded_key_count": len(secret_env["loaded_keys"]),
        },
        "env": {
            "HERMES_BIN": os.environ.get("HERMES_BIN", "unset"),
            "HERMES_REMOTE_WORKSPACE": os.environ.get("HERMES_REMOTE_WORKSPACE", "unset"),
        },
        "completion_mode": "review-required for auth, spend, cookie access, gateway integration, or automation",
    }
    agent_reach = shutil.which("agent-reach")
    if agent_reach and not args.quick:
        probe = run_command([agent_reach, "doctor"], timeout=args.timeout)
        status["agent_reach_doctor"] = {
            "ok": probe.get("ok", False),
            "returncode": probe.get("returncode"),
            "stdout_tail": probe.get("stdout", "")[-3000:],
            "stderr_tail": probe.get("stderr", "")[-3000:],
        }
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def init_policy(args: argparse.Namespace) -> int:
    policy_path = Path(args.policy)
    if policy_path.exists() and not args.force:
        print(json.dumps({
            "policy": str(policy_path),
            "created": False,
            "reason": "already exists; pass --force to overwrite",
            "summary": policy_summary(policy_path),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    content = """# Hermes Research Intelligence policy
# Default is conservative: no cookie-backed access and no Clay spend.

allow_cookie_access: false
cookie_platforms: []

allow_clay_spend: false
max_records_default: 5
budget_actions_default: 10

xai_research_enabled: true
xai_default_model: grok-4.3

notes:
  - Public data and API/OAuth routes should be tried before cookie-backed routes.
  - Clay spend requires human approval and a bounded record/action budget.
  - Gateway, scheduled jobs, CRM writes, and outbound sending remain review-required.
"""
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(content, encoding="utf-8")
    policy_path.chmod(0o600)
    print(json.dumps({
        "policy": str(policy_path),
        "created": True,
        "summary": policy_summary(policy_path),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def clay_smoke(args: argparse.Namespace) -> int:
    load_secret_env()
    policy = policy_summary(Path(args.policy))
    key_present = bool(os.environ.get("CLAY_API_KEY"))
    webhook_url = os.environ.get("CLAY_WEBHOOK_URL")
    workbook_url = os.environ.get("CLAY_WORKBOOK_URL")
    result = {
        "checked_at": timestamp(),
        "clay_api_key": "present" if key_present else "missing",
        "clay_mcp_url": secret_signal("CLAY_MCP_URL"),
        "clay_webhook_url": redact_url(webhook_url),
        "clay_webhook_url_classification": classify_clay_url(webhook_url),
        "clay_workbook": {
            "url": redact_url(workbook_url),
            "workspace_id": secret_signal("CLAY_WORKSPACE_ID"),
            "workbook_id": secret_signal("CLAY_WORKBOOK_ID"),
            "table_id": secret_signal("CLAY_TABLE_ID"),
            "view_id": secret_signal("CLAY_VIEW_ID"),
        },
        "policy": policy,
        "no_spend": True,
        "live_enrichment_enabled": False,
        "reason": "Dry-run remains the default. Clay table webhooks can trigger enrichments and spend.",
        "next_step": "Set CLAY_WEBHOOK_URL only to the table's POST endpoint, then use clay-webhook-smoke before any approved send.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if key_present else 4


def parse_key_values(values: list[str]) -> dict:
    payload = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"field must be key=value: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"field key is empty: {item}")
        payload[key] = value
    return payload


def clay_webhook_smoke(args: argparse.Namespace) -> int:
    load_secret_env()
    policy = policy_summary(Path(args.policy))
    url = args.url or os.environ.get("CLAY_WEBHOOK_URL") or os.environ.get("CLAY_WORKBOOK_URL")
    url_status = classify_clay_url(url)
    payload = parse_key_values(args.field or [])
    result = {
        "checked_at": timestamp(),
        "url": redact_url(url),
        "url_status": url_status,
        "payload_keys": sorted(payload),
        "policy": policy,
        "dry_run": not args.confirm_send,
        "no_spend": not args.confirm_send,
        "completion_mode": "review-required before Clay row send",
    }
    if not args.confirm_send:
        result["result"] = "validated_without_post"
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if url_status["configured"] else 4
    if not url_status["post_safe"]:
        result["result"] = "refused"
        result["reason"] = url_status["reason"]
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 4
    if policy.get("clay_spend_policy") != "allowlisted":
        result["result"] = "refused"
        result["reason"] = "Policy does not set allow_clay_spend: true."
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 4
    if args.budget_actions <= 0:
        result["result"] = "refused"
        result["reason"] = "--budget-actions must be greater than zero for an approved Clay webhook send."
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 4
    if not payload:
        result["result"] = "refused"
        result["reason"] = "At least one --field key=value is required for an approved Clay webhook send."
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 4
    response = request_json(url, payload, {}, args.timeout)
    result["result"] = "posted" if response.get("ok") else "post_failed"
    result["response"] = safe_error(response)
    result["no_spend"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response.get("ok") else 5


def xai_responses(prompt: str, model: str, timeout_seconds: int, use_x_search: bool) -> dict:
    load_secret_env()
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "XAI_API_KEY missing"}
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
    }
    if use_x_search:
        payload["tools"] = [{"type": "x_search"}]
    result = request_json(
        f"{XAI_BASE_URL}/responses",
        payload,
        {"Authorization": f"Bearer {api_key}"},
        timeout_seconds,
    )
    if result.get("json"):
        result["output_text"] = response_text(result["json"])
        usage = result["json"].get("usage")
        if usage:
            result["usage"] = usage
    return result


def xai_smoke(args: argparse.Namespace) -> int:
    prompt = "Reply with exactly: HERMES_XAI_OK"
    result = xai_responses(prompt, args.model, args.timeout, use_x_search=False)
    safe = {
        "checked_at": timestamp(),
        "ok": result.get("ok", False),
        "status": result.get("status"),
        "model": args.model,
        "output_text": result.get("output_text", "")[:200],
        "usage": result.get("usage"),
        "error": safe_error(result.get("error") or result.get("json", {}).get("error")),
        "mode": "xAI Responses API key smoke; no x_search tool",
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if safe["ok"] else 4


def xai_search(args: argparse.Namespace) -> int:
    ensure_dirs()
    slug = slugify(args.slug or args.query)
    paths = artifact_paths(slug)
    paths["artifact_dir"].mkdir(parents=True, exist_ok=True)
    prompt = (
        "Use X search as a research signal channel. Return concise Korean bullets. "
        "Include only claims that are supported by current X search results. "
        f"Research query: {args.query}"
    )
    result = xai_responses(prompt, args.model, args.timeout, use_x_search=True)
    record = {
        "ok": result.get("ok", False),
        "status": result.get("status"),
        "model": args.model,
        "query": args.query,
        "retrieved_at": timestamp(),
        "method": "xAI Responses API x_search",
        "output_text": result.get("output_text", ""),
        "usage": result.get("usage"),
        "error": safe_error(result.get("error") or result.get("json", {}).get("error")),
    }
    append_jsonl(paths["raw"], record)
    append_jsonl(paths["audit"], {
        "event": "xai_search",
        "at": timestamp(),
        "ok": record["ok"],
        "model": args.model,
        "query": args.query,
        "usage": record.get("usage"),
        "completion_mode": "done for report-only signal collection; review-required before automation",
    })
    append_jsonl(paths["sources"], {
        "url": "https://api.x.ai/v1/responses",
        "title": f"xAI X Search signal: {args.query}",
        "publisher": "xAI API",
        "retrieved_at": record["retrieved_at"],
        "relevance": "X/Twitter current signal channel for Research Intelligence pilot",
        "trust_note": f"server-side x_search tool ok={record['ok']}; usage metadata recorded when returned",
    })
    write_text(
        paths["brief"],
        f"""# xAI X Search Brief

- question: {args.query}
- scope: X/Twitter current signal collection only
- exclusions: no Hermes provider switch, no cookie scraping, no gateway automation
- output format: source ledger, raw API summary, report
- completion mode: report-only done; automation/provider changes review-required
""",
    )
    write_text(
        paths["report"],
        f"""# xAI X Search Signal Report

## Query
{args.query}

## Result
{record.get("output_text") or "No output text returned."}

## Evidence
- Source ledger: `{paths["sources"]}`
- Raw/audit artifact directory: `{paths["artifact_dir"]}`

## Notes
- xAI is used as a research channel only.
- Hermes default provider was not changed.
- Cookie scraping, Clay spend, gateway integration, and recurring automation remain review-required.
""",
    )
    print(json.dumps({
        "ok": record["ok"],
        "artifact_dir": str(paths["artifact_dir"]),
        "source_ledger": str(paths["sources"]),
        "report": str(paths["report"]),
        "usage": record.get("usage"),
        "completion_mode": "done for report-only signal collection",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if record["ok"] else 4


def artifact_paths(slug: str) -> dict[str, Path]:
    dated_slug = slug if slug.startswith(TODAY) else f"{TODAY}-{slug}"
    artifact_dir = DEFAULT_ARTIFACT_ROOT / dated_slug
    return {
        "artifact_dir": artifact_dir,
        "brief": Path("research") / "briefs" / f"{dated_slug}.md",
        "sources": Path("research") / "sources" / f"{dated_slug}.jsonl",
        "notes": Path("research") / "notes" / f"{dated_slug}.md",
        "report": Path("reports") / f"{dated_slug}.md",
        "audit": artifact_dir / "audit.jsonl",
        "raw": artifact_dir / "raw.jsonl",
        "candidates": artifact_dir / "candidates.jsonl",
        "enriched": artifact_dir / "enriched.jsonl",
        "dashboard": artifact_dir / "dashboard.html",
    }


def public_fetch(url: str, timeout_seconds: int) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "HermesResearchIntel/0.1 (+source-ledger; public-fetch)"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(1_000_000)
            content_type = response.headers.get("content-type", "")
        text = raw.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else url
        clean = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        clean = re.sub(r"(?s)<[^>]+>", " ", clean)
        clean = html.unescape(re.sub(r"\s+", " ", clean)).strip()
        return {
            "ok": True,
            "url": url,
            "title": title,
            "content_type": content_type,
            "text_preview": clean[:4000],
            "retrieved_at": timestamp(),
            "method": "public_fetch",
        }
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {
            "ok": False,
            "url": url,
            "title": url,
            "error": str(exc),
            "retrieved_at": timestamp(),
            "method": "public_fetch",
        }


def agent_reach_read(url: str, timeout_seconds: int) -> dict | None:
    agent_reach = shutil.which("agent-reach")
    if not agent_reach:
        return None
    out = run_command([agent_reach, "read", url], timeout=timeout_seconds)
    if not out.get("ok"):
        return {
            "ok": False,
            "url": url,
            "title": url,
            "error": out.get("stderr") or out.get("stdout") or out.get("error"),
            "retrieved_at": timestamp(),
            "method": "agent-reach read",
        }
    text = out.get("stdout", "")
    title = text.splitlines()[0].strip() if text.splitlines() else url
    return {
        "ok": True,
        "url": url,
        "title": title[:200],
        "text_preview": text[:4000],
        "retrieved_at": timestamp(),
        "method": "agent-reach read",
    }


def infer_source(url: str) -> str:
    host = re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower())
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "github.com" in host:
        return "github"
    if "reddit.com" in host:
        return "reddit"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    if "linkedin.com" in host:
        return "linkedin"
    return host or "web"


def collect(args: argparse.Namespace) -> int:
    ensure_dirs()
    slug = slugify(args.slug or args.query or "research-intel")
    paths = artifact_paths(slug)
    paths["artifact_dir"].mkdir(parents=True, exist_ok=True)
    query = args.query or "(URL-only collection)"
    sources = args.sources or ["web", "youtube", "github", "reddit", "rss", "x"]

    append_jsonl(paths["audit"], {
        "event": "collect_started",
        "at": timestamp(),
        "query": query,
        "sources": sources,
        "cookie_access": "requested" if args.allow_cookies else "disabled",
        "completion_mode": "review-required if cookies, OAuth, or paid enrichment are used",
    })

    write_text(
        paths["brief"],
        f"""# Research Intelligence Brief

- question: {query}
- scope: research intelligence and GTM signal collection
- region: unspecified
- time period: current unless input sources state otherwise
- exclusions: no unapproved cookie access, no Clay spend, no gateway automation
- output format: source ledger, notes, report, optional dashboard
- freshness requirement: verify current claims at collection time
- completion mode: report-only is done; auth/spend/cookie/gateway changes are review-required
""",
    )

    records = []
    if args.allow_cookies:
        policy = policy_summary(Path(args.policy))
        if policy.get("cookie_access") != "allowlisted":
            append_jsonl(paths["audit"], {
                "event": "cookie_access_refused",
                "at": timestamp(),
                "reason": "allow_cookie_access is not true in policy file",
                "policy": policy,
            })
            print(f"cookie access refused; policy file does not allow it: {args.policy}", file=sys.stderr)
            return 3

    for url in args.url:
        result = agent_reach_read(url, args.timeout) if args.prefer_agent_reach else None
        if result is None or not result.get("ok"):
            fallback = public_fetch(url, args.timeout)
            if result is not None and not result.get("ok"):
                fallback["fallback_from"] = result
            result = fallback
        records.append(result)
        append_jsonl(paths["raw"], result)
        append_jsonl(paths["sources"], {
            "url": url,
            "title": result.get("title", url),
            "publisher": infer_source(url),
            "retrieved_at": result.get("retrieved_at", timestamp()),
            "relevance": f"Input source for query: {query}",
            "trust_note": f"{result.get('method', 'unknown')} ok={result.get('ok')}",
        })

    if not args.url:
        append_jsonl(paths["audit"], {
            "event": "no_urls_supplied",
            "at": timestamp(),
            "note": "Query-only live search is intentionally not enabled until each platform route is validated.",
        })

    candidate_records = []
    for idx, record in enumerate(records, start=1):
        if not record.get("ok"):
            continue
        candidate = {
            "candidate_id": f"candidate-{idx:03d}",
            "name": record.get("title", "Untitled source")[:160],
            "source_url": record.get("url"),
            "source": infer_source(record.get("url", "")),
            "score": 50,
            "rationale": "Seed candidate from collected source; requires human review before Clay enrichment.",
            "evidence": record.get("text_preview", "")[:800],
        }
        candidate_records.append(candidate)
        append_jsonl(paths["candidates"], candidate)

    write_text(
        paths["notes"],
        f"""# Research Intelligence Notes

## Observations
- Collected URL count: {len(args.url)}
- Successful public/Agent-Reach records: {sum(1 for item in records if item.get("ok"))}
- Candidate seed records: {len(candidate_records)}
- Requested source families: {", ".join(sources)}

## Counter-Evidence And Uncertainty
- Query-only platform search is not enabled by default in this pilot surface.
- Cookie-backed access requires `{args.policy}` with `allow_cookie_access: true`.
- X/Grok OAuth and Clay credentials are detected by doctor but not printed here.

## Next Action
- Review source ledger before enrichment.
- Narrow candidates before running Clay dry-run or approved spend.
""",
    )

    write_text(
        paths["report"],
        f"""# Research Intelligence Collection Report

## Conclusion
The pilot collection created an auditable source ledger and candidate seed file for `{query}`.

## Evidence
- Brief: `{paths["brief"]}`
- Source ledger: `{paths["sources"]}`
- Raw records: `{paths["raw"]}`
- Candidate seeds: `{paths["candidates"]}`

## Risks
- Paid enrichment, OAuth, cookie routes, gateway integration, and recurring automation remain review-required.
- Source quality depends on route availability and current platform access rules.

## Next Research Suggestions
- Run `research-intel-enrich --dry-run` on the candidate seed file.
- Use `research-intel-report` to generate the dashboard after enrichment.
""",
    )

    append_jsonl(paths["audit"], {
        "event": "collect_finished",
        "at": timestamp(),
        "artifact_dir": str(paths["artifact_dir"]),
        "source_ledger": str(paths["sources"]),
        "report": str(paths["report"]),
        "candidate_count": len(candidate_records),
    })
    print(json.dumps({
        "artifact_dir": str(paths["artifact_dir"]),
        "brief": str(paths["brief"]),
        "source_ledger": str(paths["sources"]),
        "notes": str(paths["notes"]),
        "report": str(paths["report"]),
        "candidates": str(paths["candidates"]),
        "completion_mode": "done unless auth/spend/cookie/gateway changes were used",
    }, ensure_ascii=False, indent=2))
    return 0


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def enrich(args: argparse.Namespace) -> int:
    ensure_dirs()
    input_path = Path(args.input)
    records = load_records(input_path)
    if args.max_records <= 0:
        print("--max-records must be greater than zero", file=sys.stderr)
        return 2
    selected = records[: args.max_records]
    slug = slugify(args.slug or input_path.stem)
    paths = artifact_paths(slug)
    enrich_report = Path("reports") / f"{paths['artifact_dir'].name}-clay-dry-run.md"
    paths["artifact_dir"].mkdir(parents=True, exist_ok=True)
    policy = policy_summary(Path(args.policy))
    clay_key_present = bool(os.environ.get("CLAY_API_KEY") or os.environ.get("CLAY_MCP_URL"))
    real_spend_requested = bool(args.confirm_spend)

    if real_spend_requested:
        if not clay_key_present:
            print("Clay credentials are not present in the remote environment.", file=sys.stderr)
            return 4
        if policy.get("clay_spend_policy") != "allowlisted":
            print("Clay spend refused; policy file does not set allow_clay_spend: true.", file=sys.stderr)
            return 4
        if args.budget_actions <= 0:
            print("--budget-actions must be set for approved Clay spend.", file=sys.stderr)
            return 4
        print("Approved Clay spend path is intentionally not implemented in this pilot CLI.", file=sys.stderr)
        print("Use this dry-run output for human review before wiring the official Clay MCP/API.", file=sys.stderr)
        return 5

    append_jsonl(paths["audit"], {
        "event": "enrich_dry_run_started",
        "at": timestamp(),
        "input": str(input_path),
        "selected_records": len(selected),
        "budget_actions": args.budget_actions,
    })
    for idx, record in enumerate(selected, start=1):
        enriched = {
            "record_id": record.get("candidate_id") or record.get("id") or f"record-{idx:03d}",
            "name": record.get("name") or record.get("company") or record.get("title") or "Unknown",
            "source_url": record.get("source_url") or record.get("url"),
            "status": "dry_run",
            "would_call": "Clay MCP/API enrichment",
            "budget_actions": args.budget_actions,
            "notes": "No Clay action executed. Human approval required for spend.",
        }
        append_jsonl(paths["enriched"], enriched)

    write_text(
        enrich_report,
        f"""# Clay Enrichment Dry Run

## Conclusion
Prepared {len(selected)} records for Clay enrichment dry-run. No paid provider action was executed.

## Evidence
- Input: `{input_path}`
- Dry-run output: `{paths["enriched"]}`
- Audit log: `{paths["audit"]}`

## Risks
- Real Clay spend requires credentials, `allow_clay_spend: true`, `--budget-actions`, and `--confirm-spend`.
- The official Clay MCP/API shape must be verified before enabling live enrichment.

## Completion
completion mode: review-required before real spend
""",
    )
    append_jsonl(paths["audit"], {
        "event": "enrich_dry_run_finished",
        "at": timestamp(),
        "enriched": str(paths["enriched"]),
        "report": str(enrich_report),
    })
    print(json.dumps({
        "artifact_dir": str(paths["artifact_dir"]),
        "enriched": str(paths["enriched"]),
        "report": str(enrich_report),
        "dry_run": True,
        "completion_mode": "review-required before real spend",
    }, ensure_ascii=False, indent=2))
    return 0


def find_artifact_dir(slug_or_path: str | None) -> Path:
    if slug_or_path:
        path = Path(slug_or_path)
        if path.exists():
            return path
        dated = DEFAULT_ARTIFACT_ROOT / slug_or_path
        if dated.exists():
            return dated
        today_path = DEFAULT_ARTIFACT_ROOT / f"{TODAY}-{slugify(slug_or_path)}"
        if today_path.exists():
            return today_path
        return today_path
    candidates = sorted(DEFAULT_ARTIFACT_ROOT.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    return DEFAULT_ARTIFACT_ROOT / f"{TODAY}-research-intel"


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def make_dashboard(artifact_dir: Path, output: Path) -> None:
    source_matches = list(Path("research/sources").glob(f"*{artifact_dir.name.split('-', 3)[-1]}*.jsonl"))
    sources = count_jsonl(source_matches[0]) if source_matches else 0
    candidates = count_jsonl(artifact_dir / "candidates.jsonl")
    enriched = count_jsonl(artifact_dir / "enriched.jsonl")
    audit = count_jsonl(artifact_dir / "audit.jsonl")
    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes Research Intelligence</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #202124; }}
    main {{ max-width: 960px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 24px 0; }}
    .metric {{ border: 1px solid #d8dde3; border-radius: 8px; padding: 16px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    code {{ background: #f4f6f8; padding: 2px 5px; border-radius: 4px; }}
    .warn {{ border-left: 4px solid #b7791f; padding-left: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>Hermes Research Intelligence</h1>
  <p>Artifact: <code>{html.escape(str(artifact_dir))}</code></p>
  <section class="grid">
    <div class="metric"><span>Source Ledger Rows</span><strong>{sources}</strong></div>
    <div class="metric"><span>Candidate Seeds</span><strong>{candidates}</strong></div>
    <div class="metric"><span>Enrichment Rows</span><strong>{enriched}</strong></div>
    <div class="metric"><span>Audit Events</span><strong>{audit}</strong></div>
  </section>
  <p class="warn">Clay spend, cookie access, OAuth changes, gateway integration, and recurring automation remain review-required.</p>
</main>
</body>
</html>"""
    write_text(output, html_doc)


def report(args: argparse.Namespace) -> int:
    ensure_dirs()
    artifact_dir = find_artifact_dir(args.artifact)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dashboard = artifact_dir / "dashboard.html"
    make_dashboard(artifact_dir, dashboard)
    report_path = Path("reports") / f"{artifact_dir.name}-operations-dashboard.md"
    write_text(
        report_path,
        f"""# Research Intelligence Operations Dashboard

## Summary
- Artifact directory: `{artifact_dir}`
- Dashboard: `{dashboard}`
- Source rows are counted from the matching source ledger when available.
- Candidate and enrichment rows are counted from artifact JSONL files.

## Review Gates
- Cookie-backed access: review-required
- xAI/Grok OAuth auth changes: review-required
- Clay spend: review-required
- Gateway/MCP/recurring automation integration: review-required
""",
    )
    print(json.dumps({
        "artifact_dir": str(artifact_dir),
        "dashboard": str(dashboard),
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


def evaluate(args: argparse.Namespace) -> int:
    ensure_dirs()
    artifact_dir = find_artifact_dir(args.artifact)
    eval_report = Path("reports") / f"{TODAY}-research-intel-pilot-evaluation.md"
    next_steps = Path("tasks") / "research-intel-next-steps.md"
    candidates = count_jsonl(artifact_dir / "candidates.jsonl")
    enriched = count_jsonl(artifact_dir / "enriched.jsonl")
    audit = count_jsonl(artifact_dir / "audit.jsonl")
    write_text(
        eval_report,
        f"""# Research Intelligence Pilot Evaluation

## Evaluation Target
- Artifact directory: `{artifact_dir}`
- Evaluated at: {timestamp()}

## Criteria
- Candidate company/person recommendations must be source-backed.
- Clay enrichment must show useful reachable GTM data relative to cost.
- Public data routes must degrade gracefully when OAuth or cookie routes fail.

## Current Signals
- Candidate seed rows: {candidates}
- Enrichment rows: {enriched}
- Audit events: {audit}

## Assessment
- Source-backed recommendation quality: needs human review.
- Clay enrichment value: dry-run until approved spend is wired.
- Fallback behavior: public collection path is available; cookie and spend paths remain gated.

## Completion
completion mode: done for report-only evaluation; review-required before production workflow changes
""",
    )
    write_text(
        next_steps,
        """# Research Intelligence Next Steps

## Promote
- Keep `research-intel-doctor`, `research-intel-collect`, `research-intel-enrich`, and `research-intel-report` as manual CLI entrypoints.
- Promote only source routes that have successful source-ledger evidence.

## Gate
- Require HIL Approval Summary for Discord/Hermes research or GTM requests.
- Require explicit budget and policy allowlist before Clay spend.
- Require cookie platform allowlist before browser-session access.

## Defer
- Do not attach this flow to Hermes gateway automation yet.
- Do not create scheduled jobs until one manual recurring use case has passed review.
- Do not write to CRM or send outreach automatically.
""",
    )
    print(json.dumps({
        "evaluation_report": str(eval_report),
        "next_steps": str(next_steps),
        "completion_mode": "done for report-only evaluation",
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes Research Intelligence pilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="Check local/remote tool readiness")
    doctor_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    doctor_parser.add_argument("--quick", action="store_true")
    doctor_parser.add_argument("--timeout", type=int, default=45)
    doctor_parser.set_defaults(func=doctor)

    policy_parser = sub.add_parser("init-policy", help="Create conservative policy gates")
    policy_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    policy_parser.add_argument("--force", action="store_true")
    policy_parser.set_defaults(func=init_policy)

    clay_parser = sub.add_parser("clay-smoke", help="Check Clay key and spend policy without enrichment")
    clay_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    clay_parser.set_defaults(func=clay_smoke)

    clay_webhook_parser = sub.add_parser("clay-webhook-smoke", help="Validate Clay webhook settings without posting by default")
    clay_webhook_parser.add_argument("--url")
    clay_webhook_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    clay_webhook_parser.add_argument("--field", action="append", default=[])
    clay_webhook_parser.add_argument("--budget-actions", type=int, default=0)
    clay_webhook_parser.add_argument("--timeout", type=int, default=45)
    clay_webhook_parser.add_argument("--confirm-send", action="store_true")
    clay_webhook_parser.set_defaults(func=clay_webhook_smoke)

    xai_smoke_parser = sub.add_parser("xai-smoke", help="Run minimal xAI API key smoke without x_search")
    xai_smoke_parser.add_argument("--model", default=XAI_DEFAULT_MODEL)
    xai_smoke_parser.add_argument("--timeout", type=int, default=45)
    xai_smoke_parser.set_defaults(func=xai_smoke)

    xai_search_parser = sub.add_parser("xai-search", help="Use xAI X Search as a research signal channel")
    xai_search_parser.add_argument("--query", required=True)
    xai_search_parser.add_argument("--slug")
    xai_search_parser.add_argument("--model", default=XAI_DEFAULT_MODEL)
    xai_search_parser.add_argument("--timeout", type=int, default=90)
    xai_search_parser.set_defaults(func=xai_search)

    collect_parser = sub.add_parser("collect", help="Create research/source-ledger artifacts")
    collect_parser.add_argument("--slug")
    collect_parser.add_argument("--query")
    collect_parser.add_argument("--url", action="append", default=[])
    collect_parser.add_argument("--sources", nargs="+")
    collect_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    collect_parser.add_argument("--allow-cookies", action="store_true")
    collect_parser.add_argument("--prefer-agent-reach", action="store_true")
    collect_parser.add_argument("--timeout", type=int, default=30)
    collect_parser.set_defaults(func=collect)

    enrich_parser = sub.add_parser("enrich", help="Prepare Clay enrichment dry-run output")
    enrich_parser.add_argument("--input", required=True)
    enrich_parser.add_argument("--slug")
    enrich_parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    enrich_parser.add_argument("--max-records", type=int, required=True)
    enrich_parser.add_argument("--budget-actions", type=int, default=0)
    enrich_parser.add_argument("--confirm-spend", action="store_true")
    enrich_parser.set_defaults(func=enrich)

    report_parser = sub.add_parser("report", help="Generate an operations dashboard")
    report_parser.add_argument("--artifact")
    report_parser.set_defaults(func=report)

    evaluate_parser = sub.add_parser("evaluate", help="Write pilot evaluation and next-step docs")
    evaluate_parser.add_argument("--artifact")
    evaluate_parser.set_defaults(func=evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"research_intel error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
