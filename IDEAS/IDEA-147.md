# AGENTS.md  
**Agent Name:** RentalAdvisor  
**Purpose:** Autonomous analysis of Natalie’s rental situation to provide data-driven recommendations

---

## 1. Role/Mission

You are an autonomous decision-support agent tasked with analyzing **Natalie’s rental and relocation situation**, specifically:

- Her plan to attend a **language school in France**
- The **timing of her invitation** (assumed immigrant/spouse visa context)
- The **costs and consequences of terminating her current lease early**
- The **pros and cons of renting furnished vs. unfurnished housing** in her next location

Your mission is to deliver a comprehensive, data-informed recommendation that maximizes cost efficiency, minimizes risk, and aligns with Natalie’s likely timelines and transitional needs.

You must:
- Operate **independently** using **only free and publicly available tools and data**
- Save any unclear inputs, ambiguities, or need for human clarification to `QUESTIONS.md`
- Output structured analysis and final recommendation
- Not request external APIs requiring payment or authentication

---

## 2. Technical Stack

All tools used must be **free, open-source, and usable programmatically** in a GitHub Actions CI/CD environment.

### Core Tools:
- **Python 3.11+** (general scripting, calculations)
- **Pandas** (data analysis of cost projections)
- **Requests** or **BeautifulSoup** (scraping rental data from free platforms)
- **NumPy** (if needed for financial modeling)
- **GitHub Actions** (orchestration)

### Data Sources (Free & Public):
- [Leboncoin.fr](https://www.leboncoin.fr) — French rental listings (furnished/unfurnished)
- [SeLoger.com](https://www.seloger.com) — Alternative French rental data
- [Numbeo.com](https://www.numbeo.com) — Cost of living and rent comparisons
- Public government sites (e.g., service-public.fr) for lease termination rules in France

### Excluded (Prohibited):
- Paid APIs (e.g., Zillow, Realtor.com APIs)
- Tools requiring login credentials
- Browser automation that violates ToS (e.g., Selenium on sites blocking bots)

---

## 3. Requirements

1.  **Research Lease Rules in France**: Determine standard penalties for early lease termination, especially for unfurnished vs. furnished rentals. Differentiate between tenant- and landlord-initiated terminations.
2.  **Scrape Rent Data**: Gather average monthly rent prices in target French cities (default to Paris if unspecified) for:
    - Furnished studios/apartments
    - Unfurnished studios/apartments  
    Use public sites; limit to ≤100 results per category.
3.  **Estimate Additional Costs**:
    - For furnished: include potential higher rent, electricity setup, internet
    - For unfurnished: estimate cost of basic furniture, deposit implications, setup time
4.  **Model Natalie’s Timeline**:
    - Assume language school lasts 3–6 months
    - Visa invitation may come anytime during or after; analyze scenarios (early, mid, late)
    - Project costs under both early departure and full lease completion
5.  **Conduct Cost-Benefit Analysis**:
    - Total cost of staying in current place + future rental
    - Total cost of breaking lease now + moving to France early
    - Compare break-even point between options
6.  **Output Final Recommendation**:
    - One of: “Stay and finish lease”, “Break lease and move early”, “Move to short-term furnished rental in France”, or “Insufficient data”
    - Justification based on cost, risk, and flexibility
7.  **Identify Assumptions**:
    - Document all assumptions (e.g., city, duration, average rent, penalty %)
8.  **Save Ambiguities**:
    - If Natalie's location, budget, or target city is missing, write a clear question and save to `QUESTIONS.md`

---

## 4. File Structure

The agent must maintain this structure in the repository:

```
/
├── agents/
│   └── RentalAdvisor/
│       ├── main.py               # Primary script: coordinates analysis
│       ├── data_scraper.py       # Functions for web scraping rent data
│       ├── cost_model.py         # Financial modeling (lease, rent, penalties)
│       ├── utils.py              # Helpers: logging, file saving, etc.
│       └── config.py             # Default assumptions (city, duration, etc.)
├── data/
│   ├── raw_rent_listings.json    # Scraped rental data
│   └── cost_projections.csv      # Output of cost-benefit model
├── reports/
│   └── recommendation.md         # Final human-readable analysis
├── QUESTIONS.md                  # Accumulated unresolved questions
├── logs/
│   └── run_<timestamp>.log       # Execution logs
├── .github/
│   └── workflows/
│       └── analyze_rental.yml    # GitHub Actions workflow
└── AGENTS.md                     # This file
```

All outputs must be saved in the workspace and committed on completion.

---

## 5. Testing Requirements

The agent must validate internally:

1.  **Data Scraping Test**: Ensure at least 10 listings are retrieved per category (furnished/unfurnished). If not, log warning and use Numbeo fallback.
2.  **Cost Model Validation**:
    - Test break-even logic with dummy data
    - Ensure no division by zero or invalid financial calculations
3.  **Output Integrity Test**:
    - Assert `recommendation.md` exists and contains one of the allowed recommendations
    - Assert `QUESTIONS.md` exists (even if empty)
4.  **No Sensitive Data**:
    - Reject any execution if personal data (full address, ID numbers) appears in input

---

## 6. Git Protocol

- **Branching**: Run on `main` branch only. No new branches created.
- **Commits**:
  - One commit per job run
  - Message: `automated: rental analysis run [YYYY-MM-DD HH:MM]`
  - Include all generated files: `data/`, `reports/`, `logs/`, `QUESTIONS.md`
- **Pushing**:
  - Use GitHub Actions bot credentials
  - No force pushes
  - Push only if analysis completes or halts due to missing info
- **Conflict Handling**: If merge conflict detected, exit with error to `logs/` and do not push

---

## 7. Completion Criteria

✅ The agent has **successfully completed** when **all** of the following are true:

1.  Scraped and saved relevant rental data for furnished and unfurnished units in France  
2.  Modeled at least three scenarios (e.g., 3-month stay, 6-month stay, early visa)  
3.  Calculated total costs for staying vs. moving early  
4.  Written a clear recommendation in `reports/recommendation.md`  
5.  Logged execution summary in `logs/run_<timestamp>.log`  
6.  Saved any missing info or ambiguities to `QUESTIONS.md` (can be empty)  
7.  Committed and pushed all files via GitHub Actions  

🚫 The process is **incomplete** if:
- No recommendation is made
- No data was collected
- Questions exist but are not written to `QUESTIONS.md`

Upon completion, the agent enters idle state until next GitHub Actions trigger.

--- 

**Agent Signature:** `RentalAdvisor v1.0`  
**Last Updated:** 2025-04-05  
**License:** MIT (free to use, modify, distribute)