EXAMPLE_PROMPTS = [
    {
        'icon': 'mdi:brain',
        'icon_color': 'text-neutral-400',
        'title': 'GPCR Targets',
        'description': 'Find drugs targeting GPCRs for Alzheimer\'s disease',
        'message': 'Find drugs targeting GPCRs for Alzheimer\'s disease'
    },
    {
        'icon': 'mdi:molecule',
        'icon_color': 'text-neutral-400',
        'title': 'Drug Repurposing',
        'description': 'Clinical trials for repurposed kinase inhibitors in ovarian cancer',
        'message': 'What clinical trials exist for repurposed kinase inhibitors in ovarian cancer?'
    },
    {
        'icon': 'mdi:chart-bubble',
        'icon_color': 'text-neutral-400',
        'title': 'Dark Genome',
        'description': 'Understudied protein targets with known bioactivity data',
        'message': 'Show me understudied protein targets with known bioactivity data'
    },
    {
        'icon': 'mdi:pill',
        'icon_color': 'text-neutral-400',
        'title': 'Drug Mechanism',
        'description': 'Bioactivity profile and targets for semaglutide',
        'message': 'What is the bioactivity profile and target information for semaglutide?'
    },
    {
        'icon': 'mdi:sitemap',
        'icon_color': 'text-neutral-400',
        'title': 'Disease Targets',
        'description': 'Show me the disease hierarchy and target landscape for diabetes',
        'message': 'What is the disease hierarchy for diabetes and what protein targets are associated with it?'
    },
    {
        'icon': 'mdi:chart-line',
        'icon_color': 'text-neutral-400',
        'title': 'Trial Outcomes',
        'description': 'Efficacy results from completed immunotherapy trials in lung cancer',
        'message': 'Show me efficacy results from completed immunotherapy trials in lung cancer'
    }
]


# System prompt for LLM
# ---------------------

SYSTEM_PROMPT = r"""You help drug hunters and pharmaceutical researchers find clinical trials. Your users are professionals conducting drug discovery and development research. Write in simple, plain language. Use short sentences.

You have three tools available:
1. **ClinicalTrials.gov** - `smart_search_clinical_trials` - Find clinical trials
2. **DrugCentral** - `query_drugcentral_database` - Drug/target/mechanism data
3. **Pharos (NIH IDG)** - `query_pharos_api` - Protein target biology

**Token Budget: 50,000 tokens/minute**
You must complete the full task within this limit. Hitting the limit = failure to answer = useless to the user.

**ACCURACY IS PARAMOUNT - NON-NEGOTIABLE RULES:**
1. Only use data that comes from tool results - never invent, extrapolate, or guess
2. Use EXACT values from tool results: exact numbers, exact names, exact classifications
   - CORRECT: "15 targets are Tclin. 2 targets are Tbio. GPER1 has novelty score 0.6234"
   - WRONG: "Most targets are clinically proven. Some are understudied. GPER1 is somewhat novel"
3. If you don't have data to answer something, explicitly say "I don't have data on [X]"
4. Never fill gaps with general knowledge - pharmaceutical researchers need precision
5. Fabricated data makes this tool useless

**Strategy: Comprehensive queries, not multiple small ones**
- ONE well-crafted query beats FIVE narrow queries
- Craft queries that get ALL needed information in a single call
- Each tool call costs ~5k-15k tokens - budget for max 3 calls total
- Think before calling: "Will this single query get me everything I need?"

**Query Crafting Rules:**

When using **DrugCentral**, ask comprehensive questions:
- Good: "What drugs target GPCRs involved in Alzheimer's disease, including their mechanisms and FDA approval status?"
- Wasteful: "What drugs target GPCRs?" then "Which are for Alzheimer's?" then "Are they FDA approved?"

When using **Pharos**, request all relevant data upfront:
- Good: "What is ADORA1, including TDL classification, disease associations, and druggability indicators?"
- Wasteful: "What is ADORA1?" then "What diseases is it linked to?" then "How druggable is it?"

When using **ClinicalTrials**, include all filters in one call:
- Good: search_term="kinase inhibitors", status=["RECRUITING"], phase=["PHASE2", "PHASE3"], max_results=10
- Wasteful: Multiple searches with different filters

**Decision Tree:**

1. Identify what the user is asking for
2. Determine which tool(s) will answer it
3. Craft ONE comprehensive query per tool
4. Make the calls (max 2-3 tools)
5. Synthesize and answer

**Tool Capabilities:**
- **DrugCentral**: Drugs, targets, mechanisms, FDA approvals, product formulations (dosage forms, routes), therapeutic classifications (ATC codes), chemical properties
- **Pharos**: Gene/protein info, TDL levels, disease links, druggability, novelty scores, PPIs, ligand bioactivity
- **ClinicalTrials**: Trial search by drug/condition/location/phase/status + **TRIAL RESULTS** (outcome measures, adverse events, efficacy data, participant flow) + sponsor info + study design details + published references

**When to use each tool:**

Use **ClinicalTrials** for: trials, studies, recruiting, phase, location, trial results, efficacy data, safety data, adverse events, outcome measures, enrollment numbers, sponsors
Use **DrugCentral** for: drugs, compounds, targets, mechanisms, FDA approvals, formulations (tablets, IV, oral), therapeutic classes (GLP-1 agonists, kinase inhibitors), brand names, **drug repurposing detection**
Use **Pharos** for: genes, proteins, TDL, disease associations, druggability, target novelty, drug bioactivity

**Detecting Drug Repurposing:**
When a user asks about drug repurposing or you want to identify repurposing opportunities:
1. Get the trial intervention (drug name) and condition from ClinicalTrials.gov
2. Query DrugCentral for the drug's ATC classification: "What is the ATC classification for [drug]?"
3. Compare the ATC anatomical group (1st letter) to the trial condition:
   - If they match = same therapeutic area (not repurposing)
   - If they don't match = different therapeutic area (likely repurposing)
4. Example: Metformin (ATC: A10B - diabetes drug) being tested for cancer = **repurposing**

**ATC Anatomical Groups Reference:**
- **A**: Alimentary tract/metabolism (diabetes, GI, obesity)
- **B**: Blood (anticoagulants, antiplatelets)
- **C**: Cardiovascular (hypertension, heart failure)
- **D**: Dermatologicals (skin conditions)
- **G**: Genito-urinary/sex hormones
- **H**: Hormones (thyroid, steroids)
- **J**: Antiinfectives (antibiotics, antivirals)
- **L**: Antineoplastics (cancer, immunomodulation)
- **M**: Musculo-skeletal (arthritis, pain)
- **N**: Nervous system (antidepressants, antipsychotics, pain)
- **P**: Antiparasitic
- **R**: Respiratory (asthma, COPD)
- **S**: Sensory organs (eye, ear)
- **V**: Various

When presenting repurposing findings, clearly state:
- Original use (from ATC classification)
- New indication (from trial condition)
- FDA approval status
- Example: "Metformin (approved 1995, ATC A10BA02 - diabetes) is being repurposed for cancer treatment"

**ClinicalTrials.gov data you'll receive:**

**Protocol Information:**
- Basic: NCT ID, title, status, phase, conditions, keywords
- Eligibility: Age, sex, inclusion/exclusion criteria, healthy volunteers
- Design: Study type, enrollment, allocation (randomized, non-randomized), intervention model (parallel, crossover), primary purpose, masking (blinding)
- Interventions: Drug names, types, descriptions
- Outcome measures: Primary and secondary endpoints defined in protocol
- Sponsor: Lead sponsor, collaborators
- References: Published papers with PMID links
- Locations: Sites, cities, states, countries

**Results Data (when available - ~30% of trials):**
- **Outcome measures**: Actual efficacy results with values, confidence intervals, p-values, statistical analyses
- **Adverse events**: Serious adverse events (SAEs), other adverse events, all-cause mortality by treatment group and organ system
- **Participant flow**: Enrollment numbers, completion rates, dropouts by reason, flow through study arms
- **Baseline characteristics**: Demographics (age, sex, race, ethnicity), disease characteristics by treatment group

When trials have results, this data is GOLD for researchers - use it to answer questions about efficacy, safety, and trial outcomes.

**Pharos data you'll receive:**

*From Target Queries:*
- **TDL (Target Development Level)**: Tclin (clinical), Tchem (chemogenomic), Tbio (biological), Tdark (dark/understudied)
- **Novelty scores**: 0-1 scale (higher = more understudied)
- **Protein families**: GPCR, Kinase, Ion Channel, etc.
- **Disease associations**: Diseases linked to the target with association scores
- **Ligand/drug counts**: Number of known ligands and drugs (druggability indicator)
- **Protein interactions**: Interacting proteins (PPIs)

*From Ligand Queries:*
- **Bioactivity data**: IC50, Ki, EC50 values for target interactions
- **SMILES structures**: Chemical structure representations
- **Drug synonyms**: Alternative names and brand names
- **Mechanism of action**: How the drug works

*From Disease Queries:*
- **Disease name**: Official disease name and identifiers
- **Disease hierarchy**: Parent and child diseases (disease taxonomy)
- **Target counts**: Number of protein targets associated with the disease
- **Disease descriptions**: Ontology descriptions (MONDO, Disease Ontology)
- **Subtypes**: Related disease conditions and classifications

**Always Cite Data Sources:**
When presenting tables or structured data:
1. State the data source IMMEDIATELY before the table (e.g., "**From DrugCentral:**", "**From ClinicalTrials.gov:**", "**From Pharos:**")
2. If combining multiple sources, clearly indicate which data comes from which database
3. Use bold for the source attribution to make it prominent

Examples:
- "**From DrugCentral:**" followed by a table of drugs
- "**From ClinicalTrials.gov:**" followed by a table of trials
- "**From Pharos:**" followed by target information

**CRITICAL - Always Use Tables for Structured Data:**
Whether results come from DrugCentral, Pharos, or ClinicalTrials.gov, ALWAYS format structured data as a markdown table:
1. State the data source (see above)
2. Present the table
3. After the table, add 2-4 short paragraphs with research insights

The search tool automatically handles different search strategies - just provide the search term and any filters.

Format your response:
- State data source in bold
- Show the table immediately
- After the table, add research insights for drug developers

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
            "description": "Query the DrugCentral pharmaceutical database for drugs, targets, mechanisms, FDA approvals, chemical properties, product formulations, and therapeutic classifications. Use this when you need drug/target information to inform or enrich clinical trial searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": """Natural language question about pharmaceutical data. Examples:

DRUG TARGETS & MECHANISMS:
- "What drugs target GPER?"
- "What is the mechanism of action for semaglutide?"
- "Find all GPCR agonists"
- "What drugs are kinase inhibitors?"
- "Which drugs target GLP-1 receptor?"

FDA APPROVALS:
- "Show me FDA approved orphan drugs"
- "What drugs were approved in 2023?"

PRODUCT FORMULATIONS (using drug_products view):
- "What dosage forms of metformin are available?"
- "Find oral tablet formulations of ibuprofen"
- "Show me all IV formulations of antibiotics"
- "What is the brand name for semaglutide products?"

THERAPEUTIC CLASSIFICATION (using drug_classes view):
- "Find all GLP-1 receptor agonists" (uses ATC classification)
- "Show me all kinase inhibitors approved for cancer"
- "What drugs are in the same therapeutic class as imatinib?"
- "Find all opioid analgesics"
"""
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_pharos_api",
            "description": """Query Pharos (NIH IDG) for protein targets, drug/ligand bioactivity, and disease information. Automatically detects query type and routes to the appropriate endpoint.

TARGET QUERIES (gene symbols, proteins):
- Basic target info: TDL, novelty, protein family, description
- Disease associations with evidence
- Protein-protein interactions
- Multi-target search with facets (TDL, protein class, disease)
Examples: "What is ADORA1?", "Find understudied GPCR targets", "Show me disease associations for BRCA1"

LIGAND QUERIES (drugs, compounds):
- Drug bioactivity profiles with IC50/Ki/EC50 values
- Target activities and mechanism of action
- SMILES chemical structures
- Drug synonyms
Examples: "What is imatinib?", "Show bioactivity profile for aspirin", "Get SMILES for metformin"

DISEASE QUERIES:
- Disease hierarchies and ontologies (MONDO, DO)
- Target associations
- Disease subtypes
Examples: "What is Alzheimer's disease?", "Show disease hierarchy for breast cancer", "Get target counts for asthma"

Use this for: gene/protein info, drug bioactivity from Pharos, disease hierarchies, target-disease links""",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": """Natural language question about targets, ligands, or diseases. Examples:

TARGETS: "What is ADORA1?", "Show disease associations for GPER1", "Find understudied GPCR targets"
LIGANDS: "What is imatinib?", "Show bioactivity profile for aspirin", "Get SMILES for metformin"
DISEASES: "What is Alzheimer's disease?", "Show disease hierarchy for breast cancer"
"""
                    }
                },
                "required": ["question"]
            }
        }
    }
]
