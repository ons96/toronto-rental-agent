# AGENTS.md - AI-Powered Housing Search Agent

## 1. Role/Mission

### Primary Objective
Build an autonomous AI agent system that searches, filters, and recommends rental housing listings based on user-specified criteria. The agent must independently browse rental platforms, apply intelligent filtering, and present ranked recommendations—all using free resources only.

### Target User Context
- **User**: Natalie
- **Location**: Near BDO workplace (Downtown/Toronto area)
- **Budget**: Maximum $1,300/month including utilities
- **Ideal Move-in**: May 1st (with flexibility since traveling in May)
- **Lease Requirement**: Prefer short-term/no 1-year lease (must investigate termination clauses)
- **Living Preferences**: Private bedroom, max 4 people in unit, in-building laundry, gym nearby, walking distance to work and Pilates

### Mission Scope
1. Research and identify free rental listing data sources
2. Build an AI-powered web browsing/search agent
3. Implement multi-criteria filtering (budget, location, amenities, lease terms)
4. Create a ranking system based on user priorities
5. Generate a recommendation report with rationale

---

## 2. Technical Stack

### Constraint: FREE Resources Only
> **CRITICAL**: All external APIs, tools, and services must have a free tier or be completely open-source. No paid subscriptions. If no free option exists, document in QUESTIONS.md.

### Core Technologies

| Component | Selected Free Tool | Notes |
|-----------|-------------------|-------|
| **Runtime** | Python 3.11+ | Standard AI agent environment |
| **HTTP Requests** | `requests` + `httpx` | For API calls and web scraping |
| **Web Automation** | `playwright` (free tier) or `selenium` | For browsing dynamic listings |
| **Geocoding** | Nominatim (OpenStreetMap) | Free geocoding API |
| **LLM/AI** | Ollama with Mistral or Llama2 (local) | Free open-source LLM |
| **Data Storage** | JSON/SQLite (local file) | No external DB needed |
| **Output Format** | Markdown/HTML report | Human-readable results |

### Rental Listing Sources (Research Required)
Investigate these free/commercial APIs:
1. **Rentals.ca** - Check for public API or scraping feasibility
2. **Kijiji** - Has unofficial API access (research)
3. **Facebook Marketplace** - No public API; may require manual entry
4. **Craigslist** - Often free, simpler listings
5. **Rentfaster** - Regional (Alberta focus, may not apply)

### Data Handling
- **Input**: User criteria via JSON configuration file
- **Processing**: Local Python with AI model running locally via Ollama
- **Output**: Markdown report with ranked listings + rationale

---

## 3. Requirements (Numbered)

### Phase 1: Research & Discovery
1. [ ] Investigate free rental listing APIs (Rentals.ca, Kijiji, Craigslist)
1. [ ] Determine feasibility of scraping vs. API access
1. [ ] Map BDO office location to coordinates for proximity search
1. [ ] Research Toronto neighborhoods within walking distance to BDO
1. [ ] Document any rate limits or API constraints in RESEARCH.md

### Phase 2: Core Agent Development
2. [ ] Create `config/user_criteria.json` with all filtering parameters:
   - Max rent: $1,300 including utilities
   - Max commute: walking distance preferred (estimate 2km radius)
   - Move-in: May 1st flexible
   - Lease: short-term or negotiable (document rules)
   - Bedrooms: private bedroom required
   - Building amenities: laundry required, gym preferred
   - Unit size: max 4 occupants
   
2. [ ] Build geocoding module using Nominatim API
2. [ ] Implement listing fetch module (API or scraper)
2. [ ] Create filtering engine with multi-criteria scoring
2. [ ] Build AI ranking system using local LLM

### Phase 3: Intelligence & Recommendations
3. [ ] Develop NLP parser for listing descriptions
3. [ ] Implement proximity calculator (walking distance estimation)
3. [ ] Create amenity detection (laundry, gym, storage keywords)
3. [ ] Build lease flexibility detector (keyword analysis)
3. [ ] Generate ranked recommendations with justification

### Phase 4: Output & Documentation
4. [ ] Create formatted recommendation report (Markdown)
4. [ ] Generate QUESTIONS.md with any blockers
5. [ ] Document findings about lease termination rules in Ontario
5. [ ] Document furniture moving vs. selling cost analysis

### Non-Functional Requirements
6. [ ] All external calls must use free tier only (document if unavailable)
6. [ ] Agent must run autonomously without human intervention
6. [ ] Must save decision points and questions to QUESTIONS.md
6. [ ] Must validate all dependencies are free/open-source

---

## 4. File Structure

```
housing-search-agent/
├── AGENTS.md                          # This file
├── README.md                          # Project overview
├── config/
│   ├── user_criteria.json            # Natalie's search parameters
│   └── settings.json                # API keys, config (all free)
├── src/
│   ├── __init__.py
│   ├── main.py                       # Entry point
│   ├── geocoder.py                   # Nominatim integration
│   ├── fetcher.py                    # Rental listing fetch
│   ├── filter.py                     # Criteria filtering engine
│   ├── ranker.py                     # AI-powered ranking
│   ├── parser.py                     # NLP for listings
│   └── report.py                     # Report generation
├── data/
│   ├── listings.json                # Raw fetched listings
│   ├── filtered.json                # Filtered results
│   └── recommendations.md              # Final output report
├── scripts/
│   ├── setup.sh                      # Environment setup
│   └── run.sh                        # Run agent
├── tests/
│   ├── test_geocoder.py
│   ├── test_filter.py
│   └── test_integration.py
├── RESEARCH.md                      # API research findings
├── QUESTIONS.md                     # Blockers and questions for human
└── .github/
    └── workflows/
        └── agent.yml                # GitHub Actions workflow
```

---

## 5. Testing Requirements

### Unit Tests
- **test_geocoder.py**: Verify Nominatim returns correct coordinates for BDO address
- **test_filter.py**: Verify filtering logic correctly excludes over-budget listings
- **test_parser.py**: Verify NLP correctly extracts amenities from listing text

### Integration Tests
- **test_fetch_integration.py**: Verify listing fetch from at least one source
- **test_end_to_end.py**: Full pipeline from config → recommendations

### Validation Tests
- [ ] All filtered listings must be ≤ $1,300/month
- [ ] All recommendations must be within configured proximity radius
- [ ] All must have private bedroom mentioned
- [ ] At least 80% must have laundry (either in-unit or building)
- [ ] Report must include justification for each recommendation

### Performance Requirements
- [ ] Full run must complete within 30 minutes (GitHub Actions timeout)
- [ ] Must handle rate limiting gracefully (retry with backoff)
- [ ] Must fail gracefully if all APIs unavailable

---

## 6. Git Protocol

### Branching Strategy
```
main                    # Production-ready results
├── research/          # API investigation progress
├── development/       # Feature development
└── recommendations/      # Final ranked findings
```

### Commit Format
```bash
# Feature development
git checkout -b feature/geocoder
git commit -m "feat: add Nominatim geocoding module"

# Research findings
git commit -m "docs: document Rentals.ca API findings in RESEARCH.md"

# Blocking issues
git commit -m "chore: add question about lease termination to QUESTIONS.md"
```

### Workflow
1. **Daily**: Commit progress at end of each work session
2. **Blockers**: Immediately save questions to QUESTIONS.md
3. **Cleanup**: Remove any test credentials or paid API keys
4. **Final**: Push recommendations report to main

---

## 7. Completion Criteria

### Must Have
- [ ] At least 5 verified rental listings matching ≥80% of criteria
- [ ] Recommendations ranked with clear justification
- [ ] All listings within budget and proximity requirements
- [ ] QUESTIONS.md contains any unresolved blockers
- [ ] RESEARCH.md documents API/source findings

### Must Document
- [ ] Lease termination rules in Ontario for September departure
- [ ] Furniture moving vs. selling cost analysis
- [ ] Walking distance neighborhoods to BDO
- [ ] Any alternative amenity options (Pilates nearby)

### Quality Standards
- [ ] Code runs without paid dependencies
- [ ] Report is clear and actionable for user
- [ ] All filtering decisions are logged and justified
- [ ] Agent makes independent decisions (saves questions only when blocked)

### Success Metrics
The agent is considered complete when:
1. User can review recommendations and make informed decision
2. All legal/lease questions are researched and documented
3. Cost-benefit analysis for furniture is included
4. Agent has demonstrated independent filtering and reasoning

---

### Notes for Autonomous Agent
- **Running on GitHub Actions**: Use standard Linux runner
- **Time Constraint**: 30-minute timeout per run
- **Decision Authority**: Agent should make filtering decisions independently; only save clarification questions to QUESTIONS.md
- **Free Resources Priority**: If scraping is blocked, fall back to manual listing sources; do not use paid APIs

> **Proceed with development. Begin with research phase. Document findings in RESEARCH.md. Save all questions to QUESTIONS.md.**