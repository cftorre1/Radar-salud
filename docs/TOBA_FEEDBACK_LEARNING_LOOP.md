# Alicanto — Learning Loop from Toba feedback

Every material finding from Toba is treated as a system-learning incident.

## Mandatory closure
A finding is not closed when the visible defect disappears. It is closed only when:
1. the specific defect is corrected;
2. the miss is explained;
3. a preventive capability is added;
4. that capability is tested or otherwise evidenced;
5. the incident is recorded for recurrence detection.

## Root-cause questions
- Why did Builder create this?
- Why did Reviewer not catch it?
- Why did QA not catch it?
- Was the requirement absent, ambiguous, or ignored?
- Could a deterministic check have detected it?
- Is this a repeated judgment class deserving a specialist agent?
- What owner action was required, and how do we remove that action next time?

## Preventive hierarchy
Prefer the cheapest reliable prevention:
1. deterministic invariant/test;
2. browser/visual QA assertion;
3. reviewer checklist/rule;
4. domain-specific reviewer/agent;
5. observability/watchdog;
6. architecture change.

Do not create agents when a deterministic rule is stronger.

## Owner-time objective
All design choices should push Alicanto toward 30–60 minutes/week of Toba involvement.
A change that improves the product but adds recurring owner supervision is incomplete.
