# AGENTS.md

## 1. Role/Mission

**AI Real Estate Agent / Listing Filter**
=====================================

Our agent is designed to autonomously scrape and filter high-intent rental listings, catering to specific user constraints. We aim to maximize flexibility, cost-effectiveness, and comfort in finding the ideal rental situation.

The agent's primary mission is to:

* Browse high-relevant rental listings
* Apply user-defined filters and preferences
* Provide a curated list of suitable listings within a specified budget

## 2. Technical Stack

### Primary Technologies

* **Python** as the primary programming language
* **Selenium** for browser automation and web scraping
* **Geopy** for geocoding and geofencing
* **NLTK** for Natural Language Processing (NLP) and text filtering

### Dependencies

* **Pydantic** for data validation and modeling
* **Requests-HTML** for HTML parsing and scraping
* **Fuzzywuzzy** for string matching and filtering

### Databases

* **SQLite** for storing and managing filtered listings
* **Redis** (optional) for high-performance caching and sorting

## 3. Requirements

### Agent Requirements

1. Browse high-relevant rental listings using Selenium and HTML parsing
2. Apply user-defined filters and preferences using NLTK and Pydantic
3. Store and manage filtered listings in SQLite
4. Provide a curated list of suitable listings to the user
5. Save questions or uncertainties to QUESTIONS.md

### System Requirements

1. **Free Resources**: Utilize free online resources and databases for data scraping and filtering
2. **Independent Decision-Making**: Make decisions autonomously without external input or bias
3. **Adaptability**: Adjust filtering criteria and parameters based on changing user preferences

### API Requirements

1. **Geofencing API**: Utilize a free Geofencing API (e.g., Google Maps or GeoNames)
2. **Web Scraping API**: Utilize a free web scraping API (e.g., Scrapy or ParseHub)

## 4. File Structure

```markdown
agents/
|__ README.md
|__ AGENTS.md
|__ agents.py
|__ scraper.py
|__ filer.py
|__ utils.py
|__ requirements.txt
|__ .gitignore
|__ QUESTIONS.md
gitignore/
requirements/
utils/
```

## 5. Testing Requirements

1. **Unit Testing**: Implement unit tests for individual functions and modules using Pytest
2. **Integration Testing**: Perform integration tests to validate the entire agent pipeline using Cypress
3. **System Testing**: Conduct system tests to verify the agent's performance and adaptability

## 6. Git Protocol

* **Branching**: Use feature branches (e.g., `feature/new-filter`) for development and merge into `main` when complete
* **Pull Requests**: Review and approve pull requests before merging into `main`
* **Release**: Use tags (e.g., `v0.1.0`) to mark releases and create changelogs in RELEASES.md

## 7. Completion Criteria

1. **Filtered Listings**: Successfully filter and retrieve relevant rentals within the specified budget
2. **Independent Decision-Making**: Automate filtering and decision-making processes without external input
3. **Adaptability**: Adjust filtering criteria to accommodate changing user preferences

When these requirements are met, our AI Real Estate Agent / Listing Filter will be considered complete and ready for deployment.