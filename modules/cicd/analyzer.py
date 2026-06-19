"""
CI/CD Pipeline Analyzer Module

Parses YAML / Groovy pipeline definitions and extracts deeply structured
information including:

  • Triggers, stages, jobs, steps, env vars
  • Features: caching, matrix builds, manual approval, security scanning, notifications
  • Complexity score  (stages × jobs × avg_steps, capped at 100)
  • Parallelism ratio (parallel jobs / total jobs)
  • Estimated duration heuristic (minutes)
  • Best practices detected
  • AI-style improvement recommendations
"""

import re
import yaml
from pathlib import Path


# ── Estimated step duration heuristics (seconds) ─────────────────────────────
STEP_DURATION_HINTS = {
    "checkout":       10,
    "install":       120,
    "npm install":   120,
    "npm ci":         90,
    "pip install":    60,
    "build":         180,
    "test":          120,
    "lint":           30,
    "docker build":  240,
    "docker push":    90,
    "deploy":        120,
    "security":      180,
    "scan":          120,
    "default":        60,
}


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_pipeline(file_path: str, platform: str) -> dict:
    """
    Parse and analyze a CI/CD pipeline file.

    Args:
        file_path: Absolute or relative path to the pipeline file.
        platform:  Platform name (from detector.py).

    Returns:
        dict with comprehensive pipeline structure and quality metrics.
    """
    content = Path(file_path).read_text(encoding="utf-8", errors="replace")

    if platform == "Jenkins":
        result = _analyze_jenkinsfile(content, file_path)
    else:
        result = _analyze_yaml_pipeline(content, file_path, platform)

    # Post-process: add quality metrics and recommendations
    if "error" not in result:
        result.update(_compute_metrics(result))
        result["recommendations"] = _generate_recommendations(result)
        result["best_practices"]  = _detect_best_practices(result)

    return result


# ── YAML Pipeline ─────────────────────────────────────────────────────────────

def _analyze_yaml_pipeline(content: str, file_path: str, platform: str) -> dict:
    """Analyze any YAML-based pipeline file."""
    try:
        config = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return {"error": f"YAML parse error: {e}", "file": file_path, "platform": platform}

    if not isinstance(config, dict):
        return {"error": "Invalid pipeline structure (expected YAML mapping)", "file": file_path, "platform": platform}

    analysis = _base_dict(file_path, platform, content)

    extractors = {
        "GitHub Actions":       _extract_github_actions,
        "GitLab CI":            _extract_gitlab_ci,
        "Azure DevOps":         _extract_azure_devops,
        "CircleCI":             _extract_circleci,
        "Travis CI":            _extract_travis_ci,
        "Drone CI":             _extract_drone_ci,
        "Bitbucket Pipelines":  _extract_bitbucket,
    }

    extractor = extractors.get(platform, _extract_generic_yaml)
    analysis.update(extractor(config))
    return analysis


def _base_dict(file_path: str, platform: str, content: str) -> dict:
    return {
        "file":              file_path,
        "platform":          platform,
        "raw_content":       content,
        "name":              None,
        "pipeline_type":     None,
        "triggers":          [],
        "stages":            [],
        "jobs":              [],
        "env_vars":          [],
        "artifacts":         [],
        "services":          [],
        "caching":           False,
        "matrix_builds":     False,
        "manual_approval":   False,
        "notifications":     False,
        "security_scanning": False,
        "line_count":        len(content.splitlines()),
    }


# ── GitHub Actions ────────────────────────────────────────────────────────────

def _extract_github_actions(config: dict) -> dict:
    result = {}
    result["name"] = config.get("name", "Unnamed Workflow")

    # Triggers
    triggers = config.get("on", config.get(True, {}))
    if isinstance(triggers, str):
        result["triggers"] = [triggers]
    elif isinstance(triggers, list):
        result["triggers"] = [str(t) for t in triggers]
    elif isinstance(triggers, dict):
        result["triggers"] = list(triggers.keys())
    else:
        result["triggers"] = []

    # Jobs
    jobs_raw = config.get("jobs", {})
    job_list = []
    for job_id, job_cfg in jobs_raw.items():
        if not isinstance(job_cfg, dict):
            continue
        needs = job_cfg.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        steps_raw = job_cfg.get("steps", [])
        steps = []
        for step in steps_raw:
            if isinstance(step, dict):
                steps.append({
                    "name": step.get("name", step.get("uses", step.get("run", "Step"))[:50] if step.get("run") else step.get("uses", "Step")),
                    "uses": step.get("uses"),
                    "run":  step.get("run"),
                    "env":  step.get("env", {}),
                })
        job_list.append({
            "name":      job_cfg.get("name", job_id),
            "id":        job_id,
            "runner":    job_cfg.get("runs-on", "unknown"),
            "needs":     needs,
            "condition": job_cfg.get("if"),
            "steps":     steps,
            "env":       job_cfg.get("env", {}),
            "strategy":  job_cfg.get("strategy", {}),
        })

    result["jobs"]   = job_list
    result["stages"] = [j["name"] for j in job_list]

    # Global env vars
    env_vars = config.get("env", {})
    if isinstance(env_vars, dict):
        result["env_vars"] = list(env_vars.keys())

    # Feature flags (string search on full config repr)
    raw = str(config).lower()
    result["matrix_builds"]     = "matrix" in raw
    result["caching"]           = "cache" in raw
    result["security_scanning"] = any(k in raw for k in ["codeql", "snyk", "semgrep", "audit", "trivy", "gitleaks"])
    result["notifications"]     = any(k in raw for k in ["slack", "teams", "email", "notify"])
    result["manual_approval"]   = "environment" in raw and ("production" in raw or "approval" in raw)
    result["services"]          = _extract_services_from_raw(raw)

    return result


# ── GitLab CI ─────────────────────────────────────────────────────────────────

def _extract_gitlab_ci(config: dict) -> dict:
    result = {}
    KEYWORDS = {"stages", "variables", "image", "services", "cache",
                "before_script", "after_script", "default", "include",
                "workflow", "pages", "rules"}

    result["stages"]   = config.get("stages", [])
    result["name"]     = "GitLab CI Pipeline"

    variables = config.get("variables", {})
    result["env_vars"] = list(variables.keys()) if isinstance(variables, dict) else []

    jobs = []
    for key, val in config.items():
        if key in KEYWORDS or not isinstance(val, dict):
            continue
        if "stage" not in val and "script" not in val:
            continue
        needs = val.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        steps = [{"name": cmd[:60], "run": cmd} for cmd in val.get("script", [])]
        jobs.append({
            "name":          key,
            "id":            key,
            "stage":         val.get("stage", "default"),
            "image":         val.get("image", config.get("image", "default")),
            "needs":         needs,
            "when":          val.get("when", "on_success"),
            "allow_failure": val.get("allow_failure", False),
            "steps":         steps,
        })
        if val.get("when") == "manual":
            result["manual_approval"] = True

    result["jobs"]    = jobs
    result["triggers"] = (
        ["workflow:rules"] if "workflow" in config else ["push (default)"]
    )

    result["caching"]           = "cache" in config
    raw = str(config).lower()
    result["security_scanning"] = any(k in raw for k in ["sast", "dast", "semgrep", "audit", "security"])
    result["notifications"]     = any(k in raw for k in ["slack", "email", "notify"])

    return result


# ── Azure DevOps ──────────────────────────────────────────────────────────────

def _extract_azure_devops(config: dict) -> dict:
    result = {}
    result["name"] = config.get("name", "Azure Pipeline")

    trigger = config.get("trigger", [])
    if isinstance(trigger, list):
        result["triggers"] = [f"branch: {b}" for b in trigger] or ["push (default)"]
    elif isinstance(trigger, dict):
        branches_raw = trigger.get("branches", {})
        if isinstance(branches_raw, dict):
            branches = branches_raw.get("include", [])
        elif isinstance(branches_raw, list):
            branches = branches_raw
        else:
            branches = []
        if not isinstance(branches, list):
            branches = [branches] if branches else []
        result["triggers"] = [f"branch: {b}" for b in branches]
    else:
        result["triggers"] = [str(trigger)] if trigger else ["push (default)"]

    stage_list, job_list = [], []
    for stage in config.get("stages", []):
        if not isinstance(stage, dict):
            continue
        stage_name = stage.get("stage", "unnamed")
        stage_list.append(stage_name)
        for job in stage.get("jobs", []):
            if not isinstance(job, dict):
                continue
            steps = []
            for step in job.get("steps", []):
                if isinstance(step, dict):
                    steps.append({
                        "name":   step.get("displayName", step.get("task", "Step")),
                        "task":   step.get("task"),
                        "script": step.get("script"),
                    })
            job_list.append({
                "name":  job.get("displayName", job.get("job", "unnamed")),
                "id":    job.get("job", "unnamed"),
                "stage": stage_name,
                "pool":  job.get("pool", {}),
                "steps": steps,
            })

    # Flat job list (no stages)
    for job in config.get("jobs", []):
        if isinstance(job, dict):
            job_list.append({
                "name":  job.get("displayName", job.get("job", "unnamed")),
                "id":    job.get("job", "unnamed"),
                "steps": [],
            })

    result["stages"]   = stage_list or [j["name"] for j in job_list]
    result["jobs"]     = job_list
    result["env_vars"] = list(config.get("variables", {}).keys()) if isinstance(config.get("variables"), dict) else []

    raw = str(config).lower()
    result["caching"]           = "cache" in raw
    result["matrix_builds"]     = "matrix" in raw
    result["security_scanning"] = any(k in raw for k in ["sonar", "snyk", "security", "sast"])
    result["notifications"]     = any(k in raw for k in ["email", "slack", "teams"])

    return result


# ── CircleCI ──────────────────────────────────────────────────────────────────

def _extract_circleci(config: dict) -> dict:
    result = {"name": "CircleCI Pipeline"}
    jobs_raw = config.get("jobs", {})
    job_list = []

    for job_name, job_cfg in jobs_raw.items():
        if not isinstance(job_cfg, dict):
            continue
        steps = []
        for step in job_cfg.get("steps", []):
            if isinstance(step, str):
                steps.append({"name": step})
            elif isinstance(step, dict):
                key = next(iter(step))
                steps.append({"name": key, "config": step[key]})
        job_list.append({
            "name":   job_name,
            "id":     job_name,
            "docker": job_cfg.get("docker", []),
            "steps":  steps,
        })

    result["jobs"]    = job_list
    result["stages"]  = [j["name"] for j in job_list]
    workflows = config.get("workflows", {})
    result["triggers"] = list(workflows.keys()) if workflows else ["default"]

    raw = str(config).lower()
    result["caching"]           = "restore_cache" in raw or "save_cache" in raw
    result["matrix_builds"]     = "matrix" in raw
    result["security_scanning"] = any(k in raw for k in ["snyk", "semgrep", "audit"])
    result["notifications"]     = any(k in raw for k in ["slack", "email"])

    return result


# ── Travis CI ─────────────────────────────────────────────────────────────────

def _extract_travis_ci(config: dict) -> dict:
    result = {"name": "Travis CI Pipeline"}
    branches_raw = config.get("branches", {})
    if isinstance(branches_raw, dict):
        result["triggers"] = branches_raw.get("only", ["push (default)"])
    elif isinstance(branches_raw, list):
        result["triggers"] = branches_raw
    else:
        result["triggers"] = ["push (default)"]
        
    result["stages"]   = config.get("stages", ["default"])

    jobs_cfg = config.get("jobs", config.get("matrix", {}))
    job_list = []
    if isinstance(jobs_cfg, dict):
        for job in jobs_cfg.get("include", []):
            if isinstance(job, dict):
                job_list.append({
                    "name":  job.get("name", job.get("stage", "unnamed")),
                    "stage": job.get("stage", "default"),
                    "steps": [{"run": s} for s in (job.get("script", []) or [])],
                })
    result["jobs"]     = job_list
    
    env_raw = config.get("env", {})
    if isinstance(env_raw, dict):
        result["env_vars"] = list(env_raw.get("global", []))
    elif isinstance(env_raw, list):
        result["env_vars"] = env_raw
    else:
        result["env_vars"] = []

    raw = str(config).lower()
    result["caching"]           = "cache" in raw
    result["security_scanning"] = "audit" in raw

    return result


# ── Drone CI ──────────────────────────────────────────────────────────────────

def _extract_drone_ci(config: dict) -> dict:
    result = {"name": "Drone CI Pipeline"}
    steps = config.get("steps", [])
    job_list = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cmds = step.get("commands", [])
        job_list.append({
            "name":  step.get("name", "step"),
            "id":    step.get("name", "step").lower().replace(" ", "_"),
            "image": step.get("image", ""),
            "steps": [{"run": c} for c in cmds],
        })
    result["jobs"]    = job_list
    result["stages"]  = [j["name"] for j in job_list]
    
    trigger_raw = config.get("trigger", {})
    if isinstance(trigger_raw, dict):
        result["triggers"] = [trigger_raw.get("event", "push")]
    elif isinstance(trigger_raw, list):
        result["triggers"] = trigger_raw
    else:
        result["triggers"] = [str(trigger_raw)] if trigger_raw else ["push"]

    raw = str(config).lower()
    result["caching"]           = "cache" in raw
    result["security_scanning"] = any(k in raw for k in ["trivy", "snyk", "audit"])

    return result


# ── Bitbucket Pipelines ───────────────────────────────────────────────────────

def _extract_bitbucket(config: dict) -> dict:
    result = {"name": "Bitbucket Pipeline"}
    pipelines = config.get("pipelines", {})
    if not isinstance(pipelines, dict):
        pipelines = {}
    default_steps = pipelines.get("default", [])
    if not isinstance(default_steps, list):
        default_steps = []
    job_list = []

    for item in default_steps:
        if not isinstance(item, dict):
            continue
        step = item.get("step", {})
        if isinstance(step, dict):
            cmds = step.get("script", [])
        else:
            cmds = []
        if not isinstance(cmds, list):
            cmds = [cmds] if cmds else []
        job_list.append({
            "name":  step.get("name", "step") if isinstance(step, dict) else "step",
            "id":    (step.get("name", "step").lower().replace(" ", "_")) if isinstance(step, dict) else "step",
            "image": step.get("image", "") if isinstance(step, dict) else "",
            "steps": [{"run": c} for c in cmds if isinstance(c, str)],
        })

    result["jobs"]    = job_list
    result["stages"]  = [j["name"] for j in job_list]
    result["triggers"] = ["push (default)"]

    raw = str(config).lower()
    result["caching"]           = "caches" in raw
    result["security_scanning"] = any(k in raw for k in ["pipe: atlassian/checkmarx", "snyk", "audit"])

    return result


# ── Generic YAML fallback ─────────────────────────────────────────────────────

def _extract_generic_yaml(config: dict) -> dict:
    result = {"name": "Pipeline"}
    raw = str(config).lower()
    result["caching"]           = "cache" in raw
    result["security_scanning"] = any(k in raw for k in ["security", "audit", "scan", "sast"])
    result["jobs"]              = []
    result["stages"]            = []
    result["triggers"]          = ["push (default)"]
    return result


# ── Jenkins ───────────────────────────────────────────────────────────────────

def _analyze_jenkinsfile(content: str, file_path: str) -> dict:
    """Analyze a Jenkins declarative or scripted pipeline (Groovy DSL)."""
    analysis = _base_dict(file_path, "Jenkins", content)
    analysis["name"] = "Jenkinsfile Pipeline"

    # Pipeline type
    if "pipeline {" in content:
        analysis["pipeline_type"] = "Declarative"
    elif "node {" in content or "node(" in content:
        analysis["pipeline_type"] = "Scripted"
    else:
        analysis["pipeline_type"] = "Unknown"

    # Stages
    stage_pattern = r"stage\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
    stages = re.findall(stage_pattern, content)
    analysis["stages"] = stages

    # Steps within each stage
    stage_blocks = re.findall(
        r"stage\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}",
        content, re.DOTALL
    )
    jobs = []
    for stage_name, block in stage_blocks:
        sh_cmds  = re.findall(r"sh\s+['\"]([^'\"]+)['\"]", block)
        bat_cmds = re.findall(r"bat\s+['\"]([^'\"]+)['\"]", block)
        all_cmds = sh_cmds + bat_cmds
        jobs.append({
            "name":  stage_name,
            "id":    stage_name.lower().replace(" ", "_"),
            "steps": [{"run": cmd[:80]} for cmd in all_cmds],
        })
    # Fallback: no steps parsed
    if not jobs:
        jobs = [{"name": s, "id": s.lower().replace(" ", "_"), "steps": []} for s in stages]

    analysis["jobs"] = jobs

    # Environment variables
    env_section = re.search(r"environment\s*\{([^}]+)\}", content, re.DOTALL)
    if env_section:
        env_pairs = re.findall(r"^\s*(\w+)\s*=", env_section.group(1), re.MULTILINE)
        analysis["env_vars"] = env_pairs

    # Triggers
    trigger_section = re.search(r"triggers\s*\{([^}]+)\}", content, re.DOTALL)
    if trigger_section:
        analysis["triggers"] = [trigger_section.group(1).strip()]
    else:
        analysis["triggers"] = ["SCM checkout (default)"]

    # Features
    analysis["manual_approval"]   = "input" in content.lower()
    analysis["security_scanning"] = any(k in content.lower() for k in ["security", "audit", "scan", "sonar", "trivy"])
    analysis["notifications"]     = "mail" in content.lower() or "slack" in content.lower()
    analysis["caching"]           = "stash" in content.lower() or "unstash" in content.lower()

    return analysis


# ── Quality Metrics ───────────────────────────────────────────────────────────

def _compute_metrics(analysis: dict) -> dict:
    """Compute complexity, parallelism, and estimated duration."""
    jobs   = analysis.get("jobs", [])
    stages = analysis.get("stages", [])

    total_jobs   = len(jobs)
    total_stages = len(stages)
    total_steps  = sum(len(j.get("steps", [])) for j in jobs)
    avg_steps    = (total_steps / total_jobs) if total_jobs else 0

    # Complexity: logarithmic scale capped at 100
    raw_complexity = total_stages * max(total_jobs, 1) * max(avg_steps, 1)
    complexity_score = min(100, int(raw_complexity * 2))

    # Parallelism: jobs that have `needs` dependencies vs independents
    jobs_with_deps = sum(1 for j in jobs if j.get("needs"))
    parallel_jobs  = total_jobs - jobs_with_deps
    parallelism_ratio = round(parallel_jobs / total_jobs, 2) if total_jobs else 0.0

    # Estimated duration (very rough heuristic)
    estimated_seconds = 0
    for job in jobs:
        for step in job.get("steps", []):
            name = (step.get("name") or step.get("run") or "").lower()
            matched = False
            for keyword, secs in STEP_DURATION_HINTS.items():
                if keyword in name:
                    estimated_seconds += secs
                    matched = True
                    break
            if not matched:
                estimated_seconds += STEP_DURATION_HINTS["default"]
    estimated_minutes = max(1, estimated_seconds // 60)

    return {
        "total_steps":       total_steps,
        "avg_steps_per_job": round(avg_steps, 1),
        "complexity_score":  complexity_score,
        "parallelism_ratio": parallelism_ratio,
        "estimated_minutes": estimated_minutes,
    }


# ── Recommendations ───────────────────────────────────────────────────────────

def _generate_recommendations(analysis: dict) -> list[dict]:
    """Generate actionable improvement recommendations."""
    recs = []

    if not analysis.get("caching"):
        recs.append({
            "priority": "HIGH",
            "title":    "Add Dependency Caching",
            "detail":   "Cache node_modules / pip packages between runs to cut build time by 40–70%.",
            "icon":     "⚡",
        })

    if not analysis.get("matrix_builds") and analysis.get("platform") == "GitHub Actions":
        recs.append({
            "priority": "MEDIUM",
            "title":    "Consider Matrix Builds",
            "detail":   "Test across multiple Node.js/Python versions in parallel with a strategy matrix.",
            "icon":     "🔀",
        })

    if not analysis.get("security_scanning"):
        recs.append({
            "priority": "HIGH",
            "title":    "Add Security Scanning",
            "detail":   "Integrate CodeQL, Semgrep, or Trivy to catch vulnerabilities before they reach production.",
            "icon":     "🔒",
        })

    if not analysis.get("notifications"):
        recs.append({
            "priority": "LOW",
            "title":    "Add Failure Notifications",
            "detail":   "Send Slack/email alerts on pipeline failures so the team can react quickly.",
            "icon":     "🔔",
        })

    if not analysis.get("manual_approval") and "deploy" in str(analysis.get("stages", [])).lower():
        recs.append({
            "priority": "HIGH",
            "title":    "Add Production Approval Gate",
            "detail":   "Require manual approval before production deployments to prevent accidental releases.",
            "icon":     "🚦",
        })

    if analysis.get("parallelism_ratio", 1.0) < 0.3 and len(analysis.get("jobs", [])) > 3:
        recs.append({
            "priority": "MEDIUM",
            "title":    "Increase Job Parallelism",
            "detail":   "Most jobs run sequentially. Split independent jobs (lint, test, security) to run in parallel.",
            "icon":     "🚀",
        })

    if analysis.get("estimated_minutes", 0) > 30:
        recs.append({
            "priority": "MEDIUM",
            "title":    "Optimise Pipeline Duration",
            "detail":   f"Estimated duration is ~{analysis.get('estimated_minutes')} min. Enable caching and parallelism to reduce it.",
            "icon":     "⏱️",
        })

    return recs


def _generate_recommendations(analysis: dict) -> list[dict]:
    """Generate actionable improvement recommendations."""
    recs = []

    if not analysis.get("caching"):
        recs.append({
            "priority": "HIGH",
            "title":    "Add Dependency Caching",
            "detail":   "Cache node_modules / pip packages between runs to cut build time by 40–70%.",
            "icon":     "⚡",
        })

    if not analysis.get("matrix_builds") and analysis.get("platform") == "GitHub Actions":
        recs.append({
            "priority": "MEDIUM",
            "title":    "Consider Matrix Builds",
            "detail":   "Test across multiple Node.js/Python versions in parallel with a strategy matrix.",
            "icon":     "🔀",
        })

    if not analysis.get("security_scanning"):
        recs.append({
            "priority": "HIGH",
            "title":    "Add Security Scanning",
            "detail":   "Integrate CodeQL, Semgrep, or Trivy to catch vulnerabilities before they reach production.",
            "icon":     "🔒",
        })

    if not analysis.get("notifications"):
        recs.append({
            "priority": "LOW",
            "title":    "Add Failure Notifications",
            "detail":   "Send Slack/email alerts on pipeline failures so the team can react quickly.",
            "icon":     "🔔",
        })

    if not analysis.get("manual_approval") and "deploy" in str(analysis.get("stages", [])).lower():
        recs.append({
            "priority": "HIGH",
            "title":    "Add Production Approval Gate",
            "detail":   "Require manual approval before production deployments to prevent accidental releases.",
            "icon":     "🚦",
        })

    if analysis.get("parallelism_ratio", 1.0) < 0.3 and len(analysis.get("jobs", [])) > 3:
        recs.append({
            "priority": "MEDIUM",
            "title":    "Increase Job Parallelism",
            "detail":   "Most jobs run sequentially. Split independent jobs (lint, test, security) to run in parallel.",
            "icon":     "🚀",
        })

    if analysis.get("estimated_minutes", 0) > 30:
        recs.append({
            "priority": "MEDIUM",
            "title":    "Optimise Pipeline Duration",
            "detail":   f"Estimated duration is ~{analysis.get('estimated_minutes')} min. Enable caching and parallelism to reduce it.",
            "icon":     "⏱️",
        })

    return recs


# ── Best Practices Detection ──────────────────────────────────────────────────

def _detect_best_practices(analysis: dict) -> list[str]:
    """Return a list of things the pipeline is already doing right."""
    good = []
    if analysis.get("caching"):           good.append("✅ Dependency caching enabled")
    if analysis.get("matrix_builds"):     good.append("✅ Matrix builds for cross-version testing")
    if analysis.get("security_scanning"): good.append("✅ Security scanning integrated")
    if analysis.get("notifications"):     good.append("✅ Failure notifications configured")
    if analysis.get("manual_approval"):   good.append("✅ Manual approval gate before deploy")
    if analysis.get("parallelism_ratio", 0) > 0.5:
        good.append("✅ Good job parallelism")
    if analysis.get("env_vars"):          good.append("✅ Environment variables parameterised")
    if analysis.get("pipeline_type") == "Declarative":
        good.append("✅ Declarative pipeline syntax (recommended)")
    return good


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_services_from_raw(raw: str) -> list[str]:
    """Best-effort extract service names from stringified config."""
    services = []
    for svc in ["postgres", "mysql", "redis", "mongodb", "elasticsearch", "rabbitmq"]:
        if svc in raw:
            services.append(svc)
    return services
