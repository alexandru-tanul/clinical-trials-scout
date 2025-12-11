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

When users ask about trials:
1. Search using the tool
2. Present results as a table (no intro text)
3. Add research insights after the table

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
                "name": "search_clinical_trials",
                "description": "Search for clinical trials from ClinicalTrials.gov database. Use this when users ask about clinical trials, medical studies, or research for specific conditions. Returns detailed trial information including eligibility, locations, and status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "condition": {
                            "type": "string",
                            "description": "The medical condition or disease to search for (e.g., 'Breast Cancer', 'Type 2 Diabetes', 'Alzheimer Disease')"
                        },
                        "intervention": {
                            "type": "string",
                            "description": "The type of intervention or treatment (e.g., 'Drug', 'Behavioral', 'Surgery')"
                        },
                        "location": {
                            "type": "string",
                            "description": "Geographic location for trials (e.g., 'California', 'New York', 'United States')"
                        },
                        "status": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Trial recruitment status. Options: RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, SUSPENDED, TERMINATED, WITHDRAWN"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of trials to return (default: 5, max: 50)"
                        }
                    },
                    "required": ["condition"]
                }
            }
        }
    ]
