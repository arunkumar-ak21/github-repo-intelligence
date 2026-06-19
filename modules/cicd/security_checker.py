"""
CI/CD Pipeline Security Checker Module

Checks pipeline definitions against 16 security best-practice rules covering:
  - Secrets management         - Dependency safety
  - Privilege escalation       - Runner hardening
  - Supply-chain attacks       - Audit & compliance
  - Dangerous commands         - Network hygiene

Every rule includes a `remediation` field with an actionable fix.
"""

import re

# ── Security Rule Registry ────────────────────────────────────────────────────

SECURITY_RULES = [
    # ── Secrets & Credentials ────────────────────────────────────────────────
    {
        "id": "SEC-001",
        "name": "Hardcoded Secrets",
        "severity": "CRITICAL",
        "category": "Secrets Management",
        "description": "Potential hardcoded secrets or API keys detected in pipeline.",
        "remediation": (
            "Move all secrets into your platform's secret store (GitHub Secrets, GitLab CI Variables, "
            "Jenkins Credentials). Reference them as ${{ secrets.MY_SECRET }} or $MY_SECRET. "
            "Never embed raw values in pipeline files."
        ),
        "patterns": [
            r"(?i)(password|passwd|secret|api_key|apikey|token|access_key)\s*[:=]\s*['\"][^${\s][^'\"]{6,}['\"]",
            r"(?i)AKIA[0-9A-Z]{16}",        # AWS Access Key ID
            r"(?i)ghp_[a-zA-Z0-9]{36}",    # GitHub Personal Access Token
            r"(?i)sk-[a-zA-Z0-9]{48}",     # OpenAI API key
            r"(?i)xox[baprs]-[0-9A-Za-z\-]+",  # Slack token
        ],
    },
    {
        "id": "SEC-006",
        "name": "Secrets in Logs",
        "severity": "HIGH",
        "category": "Secrets Management",
        "description": "Pipeline may be printing secrets to console output / build logs.",
        "remediation": (
            "Never echo or print secret values. Use `::add-mask::$SECRET` in GitHub Actions, "
            "or set `masked: true` in GitLab CI to redact values from logs automatically."
        ),
        "patterns": [
            r"echo\s+.*\$\{?\s*(SECRET|TOKEN|PASSWORD|KEY|PASS)",
            r"print.*\b(secret|token|password|key)\b",
            r"console\.log.*\b(secret|token|password|key)\b",
        ],
    },
    {
        "id": "SEC-010",
        "name": "Exposed Secret Variable Names",
        "severity": "MEDIUM",
        "category": "Secrets Management",
        "description": "Environment variable names suggest sensitive data that may be exposed.",
        "remediation": (
            "Audit all environment variable definitions. Ensure values come from a secret store, "
            "not hardcoded strings. Consider prefixing internal vars differently to distinguish them."
        ),
        "patterns": [
            r"(?i)env\s*:\s*\n.*\b(PRIVATE_KEY|DATABASE_URL|DB_PASSWORD|SMTP_PASS|REDIS_URL)\b",
            r"(?i)(PRIVATE_KEY|DATABASE_URL|DB_PASSWORD|SMTP_PASS)\s*[:=]\s*\S{8,}",
        ],
    },

    # ── Privilege & Permissions ───────────────────────────────────────────────
    {
        "id": "SEC-002",
        "name": "Privileged Container Mode",
        "severity": "HIGH",
        "category": "Privilege Escalation",
        "description": "Container running in privileged mode grants full host kernel access.",
        "remediation": (
            "Remove `--privileged` or `privileged: true` from your Docker definitions. "
            "Use Linux capabilities sparingly with `--cap-add` only when absolutely required."
        ),
        "patterns": [r"--privileged", r"privileged:\s*true"],
    },
    {
        "id": "SEC-007",
        "name": "Overly Broad Permissions",
        "severity": "HIGH",
        "category": "Privilege Escalation",
        "description": "write-all or broad write permissions granted to the pipeline token.",
        "remediation": (
            "Follow the principle of least privilege. Set `permissions: read-all` at the workflow "
            "level, then grant specific write permissions only to the jobs that need them (e.g., "
            "`contents: write` for release jobs only)."
        ),
        "patterns": [r"permissions:\s*write-all", r"permissions:\s*\{\s*\}"],
    },
    {
        "id": "SEC-015",
        "name": "Unsafe Git Operations",
        "severity": "MEDIUM",
        "category": "Privilege Escalation",
        "description": "Use of --no-verify or --force push bypasses safety checks.",
        "remediation": (
            "Remove `git push --force` and `git commit --no-verify`. These bypass branch "
            "protection rules and pre-commit hooks. Use `--force-with-lease` when necessary."
        ),
        "patterns": [
            r"git\s+.*--no-verify",
            r"git\s+push\s+.*--force(?!-with-lease)",
        ],
    },

    # ── Supply Chain ──────────────────────────────────────────────────────────
    {
        "id": "SEC-003",
        "name": "Unpinned Actions / Images",
        "severity": "MEDIUM",
        "category": "Supply Chain",
        "description": "Using @latest, @main or :latest tags can introduce supply-chain attacks.",
        "remediation": (
            "Pin GitHub Actions to a specific commit SHA: `uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`. "
            "Pin Docker images to a digest: `image: node:20-alpine@sha256:...`. "
            "Use a tool like Dependabot or Renovate to automate updates."
        ),
        "patterns": [
            r"uses:\s*\S+@(main|master|latest|HEAD)",
            r"image:\s*\S+:latest",
        ],
    },
    {
        "id": "SEC-009",
        "name": "Unpinned pip / npm Dependencies",
        "severity": "LOW",
        "category": "Supply Chain",
        "description": "Installing packages without version pins or integrity hashes is risky.",
        "remediation": (
            "Use lockfiles: `pip install -r requirements.txt` with hashed requirements "
            "(`pip-compile --generate-hashes`), or `npm ci` instead of `npm install`. "
            "Never use `pip install --upgrade` in pipelines without pinned versions."
        ),
        "patterns": [
            r"pip\s+install\s+(?!-r)(?!--upgrade\s+-r)\S+(?<![0-9])\s",
            r"npm\s+install\s+(?!--save-dev\s+\S+@)\S+\s",
        ],
    },

    # ── Dangerous Commands ────────────────────────────────────────────────────
    {
        "id": "SEC-004",
        "name": "Dangerous Shell Patterns",
        "severity": "HIGH",
        "category": "Dangerous Commands",
        "description": "curl|bash, wget|bash, or eval patterns execute untrusted remote code.",
        "remediation": (
            "Never pipe downloaded content directly to a shell. Instead, download to a file, "
            "verify its checksum, then execute. Replace `eval` with explicit variable assignment."
        ),
        "patterns": [
            r"curl\s+.*\|\s*(bash|sh)",
            r"wget\s+.*\|\s*(bash|sh)",
            r"\beval\b\s+[\"']?\$",
            r"curl\s+-s\S*\s+https?://\S+\s*\|",
        ],
    },
    {
        "id": "SEC-016",
        "name": "Deprecated / EOL Runtime Versions",
        "severity": "LOW",
        "category": "Dangerous Commands",
        "description": "Pipeline references an end-of-life runtime version with known CVEs.",
        "remediation": (
            "Upgrade to a supported LTS version. For Node.js use 20.x or 22.x, "
            "Python 3.10+, Java 17+ or 21+, Ruby 3.2+. Check endoflife.date for schedules."
        ),
        "patterns": [
            r"node[:\s-](0\.|4\.|6\.|8\.|10\.|12\.|14\.|16\.)",
            r"python[:\s-](2\.|3\.[0-7]\.)",
            r"java[:\s-](1\.[0-8]|[89]|1[0-6])\b",
            r"ruby[:\s-](1\.|2\.[0-6]\.)",
        ],
    },

    # ── Audit & Scanning ──────────────────────────────────────────────────────
    {
        "id": "SEC-005",
        "name": "Missing Security Scanning",
        "severity": "LOW",
        "category": "Audit & Scanning",
        "description": "No SAST, dependency, or secret scanning step detected in the pipeline.",
        "check_type": "absence",
        "remediation": (
            "Add at least one security scanning step. Recommended free options: "
            "CodeQL (GitHub Actions), Semgrep, Trivy (container scanning), "
            "Snyk, or `npm audit` / `pip audit` for dependency checks."
        ),
        "expected_patterns": [
            r"(?i)(codeql|snyk|semgrep|trivy|sonar|audit|sast|dast|grype|gitleaks|trufflehog|security[\._-]scan)",
        ],
    },
    {
        "id": "SEC-011",
        "name": "Missing Artifact Integrity Check",
        "severity": "LOW",
        "category": "Audit & Scanning",
        "description": "Artifacts are uploaded or downloaded without checksum verification.",
        "check_type": "conditional_absence",
        "remediation": (
            "Generate a SHA256 checksum alongside your artifacts: `sha256sum artifact.tar.gz > artifact.sha256`. "
            "Verify it before use: `sha256sum -c artifact.sha256`. "
            "In GitHub Actions, artifacts are automatically checksummed by the runner."
        ),
        "trigger_patterns": [r"upload-artifact", r"download-artifact", r"artifacts:"],
        "expected_patterns": [r"sha256|sha512|checksum|md5sum|integrity"],
    },

    # ── Runner Hardening ──────────────────────────────────────────────────────
    {
        "id": "SEC-008",
        "name": "Self-Hosted Runners",
        "severity": "MEDIUM",
        "category": "Runner Hardening",
        "description": "Self-hosted runners may have persistent state or elevated access.",
        "remediation": (
            "Harden self-hosted runners: run as a dedicated low-privilege user, "
            "use ephemeral runners (new VM per job), apply OS security patches regularly, "
            "restrict network access, and enable runner autoscaling with labels."
        ),
        "patterns": [r"runs-on:\s*self-hosted", r"tags:\s*\[.*self.hosted.*\]"],
    },
    {
        "id": "SEC-012",
        "name": "Missing Job Timeout",
        "severity": "LOW",
        "category": "Runner Hardening",
        "description": "No timeout defined for jobs — runaway jobs waste resources and may indicate compromise.",
        "check_type": "absence",
        "remediation": (
            "Set explicit timeouts: `timeout-minutes: 30` in GitHub Actions, "
            "`timeout: 30m` in GitLab CI, or `timeout(time: 30, unit: 'MINUTES')` in Jenkins. "
            "A good default is 30–60 minutes for build jobs."
        ),
        "expected_patterns": [
            r"timeout[_-]minutes\s*:",
            r"timeout\s*:\s*\d",
            r"timeout\s*\(\s*time\s*:",
        ],
    },

    # ── Compliance ────────────────────────────────────────────────────────────
    {
        "id": "SEC-013",
        "name": "Missing CODEOWNERS / Approval Gate",
        "severity": "LOW",
        "category": "Compliance",
        "description": "No CODEOWNERS or required approval step detected for production deployments.",
        "check_type": "conditional_absence",
        "remediation": (
            "Add a CODEOWNERS file to require PR reviews for pipeline changes. "
            "Add a manual approval gate before production deployments using "
            "`environment: production` in GitHub Actions or `when: manual` in GitLab CI."
        ),
        "trigger_patterns": [r"(?i)production|prod\b|deploy.prod"],
        "expected_patterns": [
            r"environment:\s*production",
            r"when:\s*manual",
            r"input\s*\{",
            r"approval",
        ],
    },
]


# ── Severity Weights ──────────────────────────────────────────────────────────

SEVERITY_WEIGHTS = {
    "CRITICAL": 25,
    "HIGH":     15,
    "MEDIUM":    8,
    "LOW":       3,
}


# ── Main Checker ──────────────────────────────────────────────────────────────

def run_security_checks(content: str, platform: str = "generic") -> dict:
    """
    Run all security rules against raw pipeline content.

    Args:
        content:  Raw text of the pipeline file.
        platform: CI/CD platform name (used for platform-specific skips).

    Returns:
        dict with keys:
          score          int        0-100
          grade          str        A/B/C/D/F
          findings       list[dict] issues found
          passed         list[dict] rules that passed
          total_checks   int
          issues_found   int
          checks_passed  int
          categories     dict       category → {passed, failed}
    """
    findings: list[dict] = []
    passed:   list[dict] = []
    lines = content.splitlines()

    for rule in SECURITY_RULES:
        rule_id    = rule["id"]
        check_type = rule.get("check_type", "presence")

        # ── presence: flag if pattern IS found ──────────────────────────────
        if check_type == "presence":
            matched      = False
            matched_lines: list[dict] = []

            for pattern in rule["patterns"]:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        matched = True
                        matched_lines.append({"line_num": i, "content": line.strip()})

            if matched:
                findings.append(_make_finding(rule, matched_lines[:5]))
            else:
                passed.append(_make_passed(rule))

        # ── absence: flag if expected pattern is MISSING ─────────────────────
        elif check_type == "absence":
            found = any(
                re.search(p, content)
                for p in rule["expected_patterns"]
            )
            if found:
                passed.append(_make_passed(rule))
            else:
                findings.append(_make_finding(rule, []))

        # ── conditional_absence: only flag if trigger is present ─────────────
        elif check_type == "conditional_absence":
            trigger_hit = any(
                re.search(p, content, re.IGNORECASE)
                for p in rule.get("trigger_patterns", [])
            )
            if not trigger_hit:
                passed.append(_make_passed(rule))
                continue

            found = any(
                re.search(p, content, re.IGNORECASE)
                for p in rule["expected_patterns"]
            )
            if found:
                passed.append(_make_passed(rule))
            else:
                findings.append(_make_finding(rule, []))

    # ── Score ─────────────────────────────────────────────────────────────────
    total_deductions = sum(
        SEVERITY_WEIGHTS.get(f["severity"], 0) for f in findings
    )
    score = max(0, 100 - total_deductions)

    # ── Category breakdown ────────────────────────────────────────────────────
    categories: dict[str, dict] = {}
    for rule in SECURITY_RULES:
        cat = rule.get("category", "General")
        if cat not in categories:
            categories[cat] = {"passed": 0, "failed": 0}

    for f in findings:
        cat = f.get("category", "General")
        if cat in categories:
            categories[cat]["failed"] += 1

    for p in passed:
        cat = p.get("category", "General")
        if cat in categories:
            categories[cat]["passed"] += 1

    return {
        "score":         score,
        "grade":         _get_grade(score),
        "findings":      findings,
        "passed":        passed,
        "total_checks":  len(SECURITY_RULES),
        "issues_found":  len(findings),
        "checks_passed": len(passed),
        "categories":    categories,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_finding(rule: dict, matched_lines: list) -> dict:
    return {
        "rule_id":      rule["id"],
        "name":         rule["name"],
        "severity":     rule["severity"],
        "category":     rule.get("category", "General"),
        "description":  rule["description"],
        "remediation":  rule.get("remediation", ""),
        "matched_lines": matched_lines,
    }


def _make_passed(rule: dict) -> dict:
    return {
        "rule_id":  rule["id"],
        "name":     rule["name"],
        "category": rule.get("category", "General"),
    }


def _get_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def get_severity_color(severity: str) -> str:
    """Return a hex colour for a given severity level."""
    return {
        "CRITICAL": "#ef4444",
        "HIGH":     "#f97316",
        "MEDIUM":   "#eab308",
        "LOW":      "#22d3ee",
    }.get(severity, "#94a3b8")


def get_all_categories() -> list[str]:
    """Return unique category names in definition order."""
    seen: set[str] = set()
    cats: list[str] = []
    for rule in SECURITY_RULES:
        cat = rule.get("category", "General")
        if cat not in seen:
            seen.add(cat)
            cats.append(cat)
    return cats
