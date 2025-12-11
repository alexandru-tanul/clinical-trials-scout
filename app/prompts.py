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

SYSTEM_PROMPT = r"""You help users find clinical trials. Write in simple, plain language. Use short sentences. Build information step by step.

When users ask about trials:
1. Search using the tool
2. Present results clearly
3. Help users understand what they found

Format your response:
- Start with what you found (1-2 sentences)
- Show a table with trial details
- End with a helpful paragraph (3-5 short sentences about what you found and how it relates to their query)

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

After the table, add a helpful paragraph:
- Start directly with the content (example: "Most trials focus on advanced stages. Check each trial page for detailed eligibility criteria. Several studies test new drug combinations.")
- Write 3-5 short, simple sentences
- Use imperative sentences: "Check the trial pages for full details. Contact the research team if interested."
- Focus on what you found and how it relates to their query
- Be practical and specific to the results shown

Writing style:
- Use simple words: "complete" instead of "comprehensive", "use" instead of "utilize", "help" instead of "facilitate", "best" instead of "optimal"
- Write like clear instructions
- One idea per sentence
- Be direct and helpful
- Keep it concise

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
                            "description": "Maximum number of trials to return (default: 10, max: 50)"
                        }
                    },
                    "required": ["condition"]
                }
            }
        }
    ]
