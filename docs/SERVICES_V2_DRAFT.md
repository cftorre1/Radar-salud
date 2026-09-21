# Services V2 — draft for review

This file is intentionally a draft to review before implementation expands.

## DISCOVER
One product, many filters/tags — not separate Radars.

Candidate Discover categories:
- Regulation & policy
- Legal / judicial
- Market / corporate movements
- Providers / capacity / infrastructure
- Insurance / Isapres / Fonasa
- Occupational health / mutuals / SUSESO / COMPIN
- Public procurement / opportunities
- Innovation / startups / funding
- Talent / executive moves / hiring
- Data releases / statistics / surveys
- International / Radar Mundo

Candidate event types (orthogonal to category):
- REGULATION_CIRCULAR
- REGULATION_RESOLUTION
- REGULATION_OFFICIAL_LETTER
- LAW_OR_POLICY_CHANGE
- COURT_CASE_FILED
- COURT_DECISION
- INVESTMENT_ANNOUNCEMENT
- FACILITY_OPENING
- CAPACITY_EXPANSION
- M_AND_A
- PARTNERSHIP
- PRODUCT_OR_SERVICE_LAUNCH
- EXECUTIVE_MOVE
- JOB_POSTING
- HIRING_CLUSTER
- PUBLIC_TENDER
- CONTRACT_AWARD
- FINANCIAL_RESULT
- FUNDING_ROUND
- STARTUP_LAUNCH
- DATA_RELEASE
- SURVEY_RELEASE
- TECHNOLOGY_ADOPTION
- OTHER

Candidate institution types:
- REGULATOR
- MINISTRY_OR_PUBLIC_AGENCY
- ISAPRE
- FONASA
- PRIVATE_PROVIDER
- PUBLIC_PROVIDER
- MUTUAL
- ISL
- COMPIN
- PHARMA
- LABORATORY
- PHARMACY
- HEALTHTECH
- BIOTECH
- INSURTECH
- STARTUP
- TECHNOLOGY_VENDOR
- CONSULTING_OR_ADVISORY
- UNIVERSITY_OR_RESEARCH
- INVESTOR
- EMPLOYER
- OTHER

Candidate strategic themes:
- AI
- DIGITAL_TRANSFORMATION
- INTEROPERABILITY
- REMOTE_MONITORING
- PREVENTION
- VALUE_BASED_CARE
- MANAGED_CARE
- AMBULATORY_SHIFT
- CAPACITY_EXPANSION
- REGIONAL_EXPANSION
- CONSOLIDATION
- VERTICAL_INTEGRATION
- COST_MANAGEMENT
- FINANCIAL_PRESSURE
- REGULATORY_CHANGE
- JUDICIALIZATION
- WORKFORCE_TRANSFORMATION
- CYBERSECURITY
- PATIENT_EXPERIENCE
- MENTAL_HEALTH
- ONCOLOGY
- HOME_CARE
- AGING
- PHARMA_ACCESS
- PUBLIC_PRIVATE_COLLABORATION

## WATCH
A user-defined filter over DISCOVER. Any combination of:
- institution/entity
- institution type
- event type
- strategic theme
- topic
- geography
- legal/regulatory object

Only WATCH can generate an immediate intraday notification.

## CONNECT
Candidate relationship types:
- SAME_ENTITY
- SAME_THEME
- SAME_MARKET_MOVEMENT
- SEQUENCE
- SUPPORTS
- CONTRADICTS
- SUPPLIER_CUSTOMER
- OWNERSHIP_OR_CONTROL
- TALENT_PLUS_TECH
- TENDER_PLUS_INVESTMENT
- LEGAL_PLUS_REGULATORY

## TREND
Candidate lifecycle:
- Emerging
- Accelerating
- Established
- Cooling

Initial deterministic activation gate:
- >= 5 related Signals
- >= 3 distinct entities
- enough average confidence
- current window compared against previous window

TREND can aggregate by institution type, e.g. “private providers”, “Isapres”, “mutuals”, not only by named company.

## BENCHMARK
Initially measures observed public activity, not subjective quality.
Examples:
- announced investments
- expansion Signals
- hiring intensity
- AI/digital Signals
- tender participation/awards where public data permits
- regulatory/legal exposure counts with careful context

## ASK
Answers only from Radar knowledge and linked sources. It should be able to query:
- Signals
- Connections
- Trends
- benchmarks
- entities
- time windows
- institution types
- countries
