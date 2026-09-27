# Code Analyser

> **IBM Bob 2.0 Hackathon Submission** — September 25–27, 2026

An AI-powered code analysis platform built with **IBM Bob 2.0** that helps developers understand unfamiliar codebases, detect issues, and improve software quality.

---

## 🚀 Project Overview

Code Analyser uses IBM Bob 2.0 to analyze repositories, surface bugs, review architecture, and generate actionable insights — turning hours of manual code review into minutes of automated, AI-assisted analysis.

### Problem Statement

Developers waste significant time onboarding to unfamiliar codebases, manually reviewing code for bugs and security issues, and preparing for code reviews. There is no easy way to get an instant, structured understanding of a repository's health, architecture, and risks.

### Solution

Code Analyser leverages IBM Bob 2.0's Agent mode, parallel subagents, and document understanding to:

- Automatically map repository architecture and dependencies
- Detect bugs, security vulnerabilities, and code smells
- Generate structured onboarding guides for new developers
- Produce evidence-backed code review reports
- Track code health over time

---

## 🤖 IBM Bob 2.0 Usage

This project was built entirely with IBM Bob 2.0 as the primary development partner:

- **Agent mode** — used for autonomous code analysis workflows
- **Parallel subagents** — dispatched for simultaneous analysis of multiple modules
- **Document understanding** — used to parse requirements and generate documentation
- **Custom modes** — defined for specialized analysis tasks (security, architecture, onboarding)

See [`bob_sessions/`](./bob_sessions/) for IBM Bob task session summary screenshots from each team member.

---

## 📁 Project Structure

```
code-analyser/
├── src/                        # Application source code
├── bob_sessions/               # IBM Bob task session summary screenshots (REQUIRED)
├── submission/                 # Hackathon submission assets
│   ├── screenshots/            # App screenshots and Bob session evidence
│   ├── problem-solution.md     # Problem & Solution Statement (≤500 words)
│   ├── bob-usage-statement.md  # IBM Bob Usage Statement (≤500 words)
│   └── slide-presentation.pdf  # Slide deck (to be added)
├── docs/                       # Documentation
├── .env.example                # Environment variable template
├── .gitignore                  # Ignores credentials and build artifacts
├── .bobignore                  # Prevents Bob from logging credentials
└── SECURITY.MD                 # Security guidelines
```

---

## ⚙️ Setup

```bash
# 1. Clone the repository
git clone https://github.com/Poornasri2003/code-analyser.git
cd code-analyser

# 2. Copy environment variables template
cp .env.example .env

# 3. Add your IBM Cloud credentials to .env
# (Never commit the .env file)

# 4. Install dependencies
npm install   # or pip install -r requirements.txt
```

---

## 🔒 Security

- All credentials are stored in `.env` (never committed)
- See [SECURITY.MD](./SECURITY.MD) for full guidelines
- `.bobignore` prevents IBM Bob from logging any credential patterns

---

## 📋 Submission Checklist

- [ ] Public code repository
- [ ] IBM Bob task session summary screenshots in `bob_sessions/`
- [ ] Problem & Solution Statement (≤500 words) — `submission/problem-solution.md`
- [ ] IBM Bob Usage Statement (≤500 words) — `submission/bob-usage-statement.md`
- [ ] Video demonstration (≤3 min, ≥90s showing solution)
- [ ] Slide presentation
- [ ] Cover image
- [ ] Demo application URL

---

## 👤 Team

| Name | GitHub |
|---|---|
| Poornasri | [@Poornasri2003](https://github.com/Poornasri2003) |

---

## 🏆 Hackathon

[IBM Bob 2.0 Hackathon — lablab.ai](https://lablab.ai) · Sep 25–27, 2026 · Prize pool: $12,000
