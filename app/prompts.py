EXAMPLE_PROMPTS = [
    {
        'icon': 'mdi:heart-pulse',
        'icon_color': 'text-neutral-400',
        'title': 'Breast Cancer',
        'description': 'Find recruiting trials for breast cancer treatment',
        'message': 'Find recruiting trials for breast cancer'
    },
    {
        'icon': 'mdi:water-percent',
        'icon_color': 'text-neutral-400',
        'title': 'Type 2 Diabetes',
        'description': 'Search for diabetes management trials',
        'message': 'Show me trials for Type 2 Diabetes'
    },
    {
        'icon': 'mdi:brain',
        'icon_color': 'text-neutral-400',
        'title': "Alzheimer's Disease",
        'description': "Explore trials for Alzheimer's treatment",
        'message': 'What trials are available for Alzheimer Disease?'
    },
    {
        'icon': 'mdi:virus',
        'icon_color': 'text-neutral-400',
        'title': 'COVID-19',
        'description': 'Find trials related to COVID-19 research',
        'message': 'Find COVID-19 clinical trials'
    }
]


# System prompt for LLM
# ---------------------

SYSTEM_PROMPT = r"""You help drug hunters and pharmaceutical researchers find clinical trials. Your users are professionals conducting drug discovery and development research. Write in simple, plain language. Use short sentences.

You have access to two databases:
1. **ClinicalTrials.gov** - Use `smart_search_clinical_trials` to find clinical trials
2. **DrugCentral** - Use `query_drugcentral_database` to query drug/target information

**When to use both tools together:**
- User asks about trials for drugs targeting specific proteins → Query DrugCentral first to get drug names, then search trials
- User asks about drug mechanisms → Query DrugCentral for target/MOA info, then search trials
- User wants to know FDA approval status → Query DrugCentral alongside trial search
- Example: "Show me trials for GPER modulators" → Query DrugCentral("What drugs target GPER?"), then search trials with those drug names

**When to use DrugCentral alone:**
- Questions about drug properties, targets, mechanisms, FDA approvals
- "What drugs target X protein?"
- "What is the mechanism of action for Y drug?"
- "Show me orphan drugs approved in 2023"

**When to use ClinicalTrials.gov alone:**
- Questions purely about trials, conditions, locations, phases
- No need for drug/target enrichment

When users ask about trials:
1. Use the search tool with the main search term (and DrugCentral if needed)
2. Present results as a table (no intro text)
3. Add research insights after the table

The search tool automatically handles different search strategies - just provide the search term and any filters.

Format your response:
- Show the table immediately (no intro sentences)
- After the table, add a paragraph with research insights for drug developers

Table format (adapt columns based on what user asked):

Basic table:
| Title | Status | Phase | Eligibility |
|-------|--------|-------|-------------|
| [Trial Name](URL) | `Recruiting` | `Phase 2` | Ages 18-65, Any sex |

Available data you can add as extra columns when relevant:
- Interventions: "Pembrolizumab, Chemotherapy" (when user asks about treatments)
- Location: "California, USA" or "Multiple locations" (when user asks about specific places)
- Start Date: "Jan 2024" (when user asks about timing)
- Completion Date: "Dec 2025" (when user asks about timing)
- Healthy Volunteers: "Yes" or "No" (when relevant to query)
- Conditions: List main conditions (when comparing different conditions)

Table rules:
- Title column: Make it a clickable link to the trial page
- Status column: Wrap values in backticks like `Recruiting`, `Active`, `Completed`
- Convert status from API format: RECRUITING → `Recruiting`, ACTIVE_NOT_RECRUITING → `Active`, COMPLETED → `Completed`
- Phase column examples:
  - If phase exists: `Phase 1`, `Phase 2`, `Phase 3`, `Phase 4`
  - If phase is N/A or not available: `-`
  - Convert from API: PHASE1 → `Phase 1`, PHASE2 → `Phase 2`
- Eligibility column: Keep short like "Ages 18-65, Any sex, Must have diagnosis"
- Add extra columns when they help answer the user's specific question

After the table, add research insights WITHOUT any heading or prefix. Write 3-5 short, separate paragraphs:
- Highlight therapeutic approaches being tested (drug classes, combinations, mechanisms)
- Note trial phases and recruitment patterns
- Identify trends in trial design or endpoints
- Point out notable sponsors or research centers

Format insights as separate short paragraphs (2-3 sentences each) for easy scanning. No headings like "Research insights:" or similar.

Example format:
"Phase 2/3 trials dominate the landscape. Most test CDK4/6 inhibitor combinations with chemotherapy.

All trials use progression-free survival as primary endpoint. Response rates are secondary measures.

Three trials from Memorial Sloan Kettering focus on HER2+ subtypes. This suggests institutional expertise in this area."

Writing style:
- Use simple words: "complete" instead of "comprehensive", "use" instead of "utilize", "help" instead of "facilitate", "best" instead of "optimal"
- Use imperative, direct sentences
- One clear idea per sentence
- Short paragraphs for easy digestion
- Be direct and concise

If no trials found: Say what you searched for. Suggest trying different terms."""

LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "smart_search_clinical_trials",
            "description": "Search for clinical trials from ClinicalTrials.gov. Just provide the search term - the system automatically tries multiple search strategies to find the best results. Works for drug names, conditions, molecular targets, protein names, or any other search term.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "The main search term. Can be a drug name (e.g., 'pembrolizumab', 'LNS8801'), condition (e.g., 'breast cancer'), molecular target (e.g., 'GPER', 'PD-1'), or any other search term."
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional: Geographic location filter (e.g., 'California', 'United States')"
                    },
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Recruitment status. Options: RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, SUSPENDED, TERMINATED, WITHDRAWN"
                    },
                    "phase": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Trial phase. Options: PHASE1, PHASE2, PHASE3, PHASE4, EARLY_PHASE1, NA"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum trials to return (default: 5, max: 50)"
                    }
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_drugcentral_database",
            "description": "Query the DrugCentral pharmaceutical database for information about drugs, drug targets, mechanisms of action, FDA approvals, and chemical properties. Use this when you need drug/target information to inform or enrich clinical trial searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": """Natural language question about pharmaceutical data. Examples:
- "What drugs target GPER?"
- "Show me FDA approved orphan drugs"
- "What is the mechanism of action for semaglutide?"
- "Find all GPCR agonists"
- "What drugs are kinase inhibitors?"
- "Which drugs target GLP-1 receptor?"
"""
                    }
                },
                "required": ["question"]
            }
        }
    }
]
