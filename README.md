# GitHub Repository Intelligence Dashboard

A unified, production-grade platform for GitHub repository analysis — combining **metadata extraction**, **CI/CD pipeline scanning**, and **dependency health scoring** into one dashboard.

> Built as a combined project integrating three independent analysis systems into a single, cohesive platform.

---

## 🚀 Features

### 📊 Repository Metadata (Module 1)
- Extract repository info, stars, forks, language, topics
- Full commit history timeline
- Top contributors with contribution counts
- Complete file tree structure
- README rendering

### ⚙️ CI/CD Pipeline Analysis (Module 2)
- Detect pipelines across **9 platforms**: GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, Travis CI, Drone CI, Bitbucket Pipelines, TeamCity
- Structural analysis: triggers, stages, jobs, steps
- **16-rule security checker** with grades (A–F)
- Best practices detection and recommendations
- Complexity scoring and parallelism analysis

### 📦 Dependency Health (Module 3)
- Detect ecosystems: Python, Node.js, Java, Go, Rust, Ruby, PHP
- Parse dependency manifests and lockfiles
- Health score (0–100) with risk levels
- Dependabot vulnerability alerts
- External API lookups for latest versions

### 🔍 Unified Dashboard
- **Single input** — enter `owner/repo` and get all 3 analyses
- **Live progress** via Server-Sent Events (SSE)
- **Tabbed interface** — Overview, CI/CD, Dependencies, History
- **Dark mode** premium UI with GitHub-inspired design

---

## 📋 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_ORG/github-repo-intelligence.git
cd github-repo-intelligence
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up your GitHub token
```bash
# Copy the template
copy .env.example .env

# Edit .env and add your GitHub Personal Access Token
# Create one at: https://github.com/settings/tokens
# Scopes needed: repo (read access)
```

### 5. Run the server
```bash
python server.py
```

### 6. Open in browser
```
http://localhost:8000
```

---

## 🏗️ Architecture

```
github-repo-intelligence/
├── server.py                 # FastAPI app — main entry point
├── requirements.txt          # Python dependencies
├── .env                      # GitHub token config (gitignored)
│
├── core/                     # Shared utilities
│   ├── config.py             # Centralized settings
│   ├── database.py           # SQLAlchemy engine (SQLite)
│   └── github_client.py      # Unified GitHub REST API client
│
├── modules/                  # Analysis engines
│   ├── metadata/             # Repo metadata extraction
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── extractor.py      # Extraction logic
│   │   └── routes.py         # /api/meta/* endpoints
│   │
│   ├── cicd/                 # CI/CD pipeline analysis
│   │   ├── analyzer.py       # Pipeline structure parser
│   │   ├── detector.py       # Platform detection
│   │   ├── security_checker.py # 16-rule security engine
│   │   ├── scanner.py        # Repo scanning logic
│   │   └── routes.py         # /api/cicd/* endpoints
│   │
│   └── deps/                 # Dependency health analysis
│       ├── analysis.py       # Analysis pipeline
│       ├── detector.py       # Ecosystem detection
│       ├── scorer.py         # Health scoring
│       ├── parsers/          # 7 language parsers
│       └── routes.py         # /api/deps/* endpoints
│
├── frontend/                 # React dashboard served from /react
│   ├── src/                  # React + TypeScript source
│   └── dist/                 # Built frontend assets
│
├── static/                   # Shared static assets, including CodeFlow
│   └── codeflow/
│
└── data/                     # Runtime data (gitignored)
    ├── app.db                # SQLite database
    └── reports/              # Generated reports
```

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /` | GET | Dashboard UI |
| `POST /api/analyze/full` | POST | Run all 3 analyses (SSE stream) |
| `POST /api/batch/analyze` | POST | Run full metadata + CI/CD + dependency batch analysis (SSE) |
| `POST /api/meta/extract` | POST | Extract metadata only |
| `GET /api/meta/repos` | GET | List extracted repos |
| `GET /api/meta/repos/{id}/metrics` | GET | Full metrics for a repo |
| `POST /api/cicd/scan` | POST | Scan CI/CD pipelines |
| `GET /api/cicd/stream/{job_id}` | GET | SSE progress stream |
| `GET /api/cicd/jobs/{job_id}` | GET | Get scan results |
| `POST /api/deps/analyze` | POST | Analyze dependencies |
| `POST /api/deps/analyze/batch` | POST | Dependency-only batch analysis (SSE) |
| `GET /api/deps/history` | GET | Analysis history |
| `GET /api/rate-limit` | GET | GitHub API rate limit |
| `GET /api/health` | GET | Server health check |

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **Database** | SQLite (via SQLAlchemy ORM) |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **API** | GitHub REST API v3 |
| **Streaming** | Server-Sent Events (SSE) |

---

## 👥 Credits

| Module | Developer |
|---|---|
| Repository Metadata Extraction | Mohit |
| CI/CD Pipeline Analysis | Satyam |
| Dependency Health Analysis | Arun |
| System Integration & Dashboard | Arun |

---

## 📄 License

Internal project — not for public distribution.
