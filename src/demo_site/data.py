"""Static, fictitious data for the Contoso Insurance demo site.

Everything here is invented for demos. No real people, policies, or credentials.
"""

from __future__ import annotations

PRODUCTS: list[dict] = [
    {
        "slug": "auto-basic",
        "name": "Auto Basic",
        "type": "auto",
        "monthly_premium": 39.0,
        "deductible": 1000,
        "coverage_limit": 25000,
        "highlights": ["Third-party liability", "Roadside assistance (3 calls/year)"],
        "exclusions": ["Own-vehicle damage", "Glass repair"],
    },
    {
        "slug": "auto-plus",
        "name": "Auto Plus",
        "type": "auto",
        "monthly_premium": 64.0,
        "deductible": 500,
        "coverage_limit": 75000,
        "highlights": ["Collision cover", "Glass repair", "Unlimited roadside assistance"],
        "exclusions": ["Rental car while repaired"],
    },
    {
        "slug": "auto-premium",
        "name": "Auto Premium",
        "type": "auto",
        "monthly_premium": 98.0,
        "deductible": 250,
        "coverage_limit": 150000,
        "highlights": ["Collision and theft", "Rental car while repaired", "New-car replacement (2 years)"],
        "exclusions": ["Racing events"],
    },
    {
        "slug": "home-basic",
        "name": "Home Basic",
        "type": "home",
        "monthly_premium": 22.0,
        "deductible": 1500,
        "coverage_limit": 150000,
        "highlights": ["Fire and lightning", "Burglary"],
        "exclusions": ["Water damage", "Storm damage"],
    },
    {
        "slug": "home-plus",
        "name": "Home Plus",
        "type": "home",
        "monthly_premium": 37.0,
        "deductible": 750,
        "coverage_limit": 300000,
        "highlights": ["Fire, burglary and water damage", "Temporary accommodation (30 days)"],
        "exclusions": ["Flood"],
    },
    {
        "slug": "home-premium",
        "name": "Home Premium",
        "type": "home",
        "monthly_premium": 58.0,
        "deductible": 250,
        "coverage_limit": 600000,
        "highlights": ["All Home Plus benefits", "Flood and storm damage", "Accidental damage"],
        "exclusions": ["Wear and tear"],
    },
    {
        "slug": "travel-single",
        "name": "Travel Single-trip",
        "type": "travel",
        "monthly_premium": 9.0,
        "deductible": 100,
        "coverage_limit": 50000,
        "highlights": ["Medical emergencies abroad", "Lost baggage up to $1,500"],
        "exclusions": ["Trips longer than 30 days"],
    },
    {
        "slug": "travel-annual",
        "name": "Travel Annual multi-trip",
        "type": "travel",
        "monthly_premium": 18.0,
        "deductible": 100,
        "coverage_limit": 150000,
        "highlights": ["Unlimited trips up to 45 days each", "Trip cancellation", "Flight delay compensation"],
        "exclusions": ["Extreme sports without add-on"],
    },
]

COVERAGE: dict[str, list[str]] = {
    "auto": ["Basic", "Plus", "Premium"],
    "home": ["Basic", "Plus", "Premium"],
    "travel": ["Single-trip", "Annual multi-trip"],
}

CLAIM_CATEGORIES: dict[str, list[str]] = {
    "auto": ["Collision", "Theft", "Glass damage", "Roadside assistance"],
    "home": ["Water damage", "Fire", "Burglary", "Storm damage"],
    "travel": ["Lost baggage", "Medical emergency", "Trip cancellation", "Flight delay"],
}

ARTICLES: list[dict] = [
    {
        "slug": "how-to-file-a-claim",
        "title": "How to file a claim online",
        "category": "claims",
        "summary": "File a claim in four steps: policyholder, policy, incident and review.",
        "body": "Use the online claim wizard. Have your policy number (format CI-123456), the incident date "
        "and a short description ready. Claims with a police report need the report number (format PR-1234). "
        "You receive a claim reference such as CLM-2026-01234 immediately after submission.",
        "tags": ["claim", "file", "online", "wizard"],
    },
    {
        "slug": "claim-processing-times",
        "title": "How long does a claim take?",
        "category": "claims",
        "summary": "Most claims are decided within 10 business days.",
        "body": "Simple glass and roadside claims are usually settled within 3 business days. Most other claims are "
        "decided within 10 business days. Claims above $25,000 or involving police reports can take up to 30 days.",
        "tags": ["claim", "time", "processing", "sla"],
    },
    {
        "slug": "what-is-a-deductible",
        "title": "What is a deductible?",
        "category": "policies",
        "summary": "The amount you pay before your insurance pays out.",
        "body": "A deductible is the part of each claim you pay yourself. Plans with a lower deductible have a "
        "higher monthly premium. Example: Home Plus has a $750 deductible, Home Premium has a $250 deductible.",
        "tags": ["deductible", "premium", "policy"],
    },
    {
        "slug": "water-damage-coverage",
        "title": "Water damage: what's covered",
        "category": "home",
        "summary": "Burst pipes are covered by Home Plus and Home Premium. Floods only by Home Premium.",
        "body": "Sudden and accidental water damage such as a burst pipe is covered by Home Plus and Home Premium. "
        "Home Basic does not cover water damage. Flooding from outside the home is only covered by Home Premium. "
        "Report water damage within 14 days and keep photos of the damage.",
        "tags": ["water", "damage", "home", "flood", "pipe"],
    },
    {
        "slug": "fire-damage-claims",
        "title": "Fire damage claims",
        "category": "home",
        "summary": "All home plans cover fire and lightning.",
        "body": "Every home plan covers fire and lightning. Home Plus and Home Premium also pay for temporary "
        "accommodation while your home is repaired.",
        "tags": ["fire", "home", "accommodation"],
    },
    {
        "slug": "theft-and-police-reports",
        "title": "Theft claims and police reports",
        "category": "claims",
        "summary": "Theft claims require a police report number.",
        "body": "For burglary or vehicle theft you must report the incident to the police within 48 hours and add the "
        "police report number (format PR-1234) to your claim.",
        "tags": ["theft", "burglary", "police", "report"],
    },
    {
        "slug": "lost-baggage",
        "title": "Travel insurance: lost baggage",
        "category": "travel",
        "summary": "Lost baggage is covered up to $1,500 on single-trip and $3,000 on annual plans.",
        "body": "Report lost baggage to the airline first and keep the property irregularity report. Single-trip "
        "plans pay up to $1,500 and annual multi-trip plans up to $3,000 per trip.",
        "tags": ["travel", "baggage", "luggage", "airline"],
    },
    {
        "slug": "annual-multi-trip",
        "title": "Annual multi-trip policy explained",
        "category": "travel",
        "summary": "Unlimited trips per year, each up to 45 days.",
        "body": "The annual multi-trip plan covers unlimited trips per policy year as long as each trip is no longer "
        "than 45 days. It includes trip cancellation and flight delay compensation.",
        "tags": ["travel", "annual", "multi-trip", "cancellation"],
    },
    {
        "slug": "glass-repair",
        "title": "Windshield and glass repair",
        "category": "auto",
        "summary": "Glass repair is included in Auto Plus and Auto Premium with no deductible.",
        "body": "Chips and cracks in your windshield are repaired without a deductible on Auto Plus and Auto Premium. "
        "Auto Basic does not include glass repair.",
        "tags": ["glass", "windshield", "auto", "repair"],
    },
    {
        "slug": "add-a-driver",
        "title": "How to add a driver to your auto policy",
        "category": "auto",
        "summary": "Add a named driver from your account page or by calling an agent.",
        "body": "Named drivers can be added at any time. Drivers under 25 increase the premium by 35 percent.",
        "tags": ["driver", "auto", "policy", "premium"],
    },
    {
        "slug": "switching-plans",
        "title": "Switching plans",
        "category": "policies",
        "summary": "You can upgrade at any time and downgrade at renewal.",
        "body": "Upgrades take effect the next day. Downgrades take effect at your next renewal date. There is no fee "
        "for switching.",
        "tags": ["switch", "upgrade", "downgrade", "plan"],
    },
    {
        "slug": "contact-an-agent",
        "title": "Contacting a local agent",
        "category": "support",
        "summary": "Use Find an agent to search by city, specialty and language.",
        "body": "Local agents can help with complex claims, commercial cover and multi-policy discounts. Use the Find an "
        "agent page to filter by city, specialty and spoken language.",
        "tags": ["agent", "contact", "support", "local"],
    },
]

CITIES = ["Seattle", "Chicago", "Austin", "Boston", "Denver"]
SPECIALTIES = ["Auto", "Home", "Travel", "Commercial"]
LANGUAGES = ["English", "Spanish", "French", "Vietnamese", "Mandarin"]

AGENTS: list[dict] = [
    {"name": "Ana Morales", "city": "Seattle", "specialties": ["Home", "Auto"], "languages": ["English", "Spanish"],
     "phone": "+1 206-555-0141", "email": "ana.morales@contoso-insurance.example", "rating": 4.9},
    {"name": "Tom Nguyen", "city": "Seattle", "specialties": ["Travel", "Auto"], "languages": ["English", "Vietnamese"],
     "phone": "+1 206-555-0178", "email": "tom.nguyen@contoso-insurance.example", "rating": 4.6},
    {"name": "Grace Li", "city": "Chicago", "specialties": ["Home", "Commercial"], "languages": ["English", "Mandarin"],
     "phone": "+1 312-555-0102", "email": "grace.li@contoso-insurance.example", "rating": 4.8},
    {"name": "Marcus Johnson", "city": "Chicago", "specialties": ["Auto"], "languages": ["English"],
     "phone": "+1 312-555-0166", "email": "marcus.johnson@contoso-insurance.example", "rating": 4.3},
    {"name": "Sofia Garcia", "city": "Austin", "specialties": ["Home", "Travel"], "languages": ["English", "Spanish"],
     "phone": "+1 512-555-0119", "email": "sofia.garcia@contoso-insurance.example", "rating": 4.7},
    {"name": "Liam O'Brien", "city": "Boston", "specialties": ["Commercial", "Home"], "languages": ["English", "French"],
     "phone": "+1 617-555-0133", "email": "liam.obrien@contoso-insurance.example", "rating": 4.5},
    {"name": "Priya Raman", "city": "Boston", "specialties": ["Auto", "Travel"], "languages": ["English"],
     "phone": "+1 617-555-0187", "email": "priya.raman@contoso-insurance.example", "rating": 4.9},
    {"name": "Noah Becker", "city": "Denver", "specialties": ["Home", "Auto", "Travel"], "languages": ["English"],
     "phone": "+1 720-555-0150", "email": "noah.becker@contoso-insurance.example", "rating": 4.4},
]
