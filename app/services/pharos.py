"""
Pharos GraphQL API integration.

Provides text-to-GraphQL capability for querying IDG (Illuminating the Druggable Genome)
including:
- Targets: TDL classifications, disease associations, protein interactions
- Ligands: Drug bioactivity data, target activities, SMILES structures
- Diseases: Disease hierarchies, target associations
- Multi-target/ligand search with faceted filtering
"""
import re
import json
import httpx
from litellm import completion
from app.config import settings
from typing import Optional, Dict, List


# Pharos GraphQL API endpoint
PHAROS_API_URL = "https://pharos-api.ncats.io/graphql"


# Combined schema documentation for LLM context
PHAROS_UNIFIED_SCHEMA = """
# Pharos GraphQL API - Complete Query Guide

## Overview

Pharos provides 5 query types. Choose the appropriate one based on the question:

1. **target** (singular) - Query a specific protein/gene (e.g., "What is BRCA1?")
2. **targets** (plural) - Search multiple targets with filters (e.g., "Find understudied GPCRs")
3. **ligand** (singular) - Query a specific drug/compound (e.g., "What is imatinib?")
4. **ligands** (plural) - Search multiple ligands (e.g., "Find kinase inhibitors")
5. **disease** (singular) - Query a disease (e.g., "What is Alzheimer's disease?")

## QUERY TYPE 1: target (singular)

**USE FOR:** Questions about specific genes/proteins (BRCA1, ADORA1, TP53, etc.)

**Basic Structure:**
```graphql
query {
  target(q:{sym:"GENE_SYMBOL"}) {
    FIELDS
  }
}
```

**Available Fields:**
- sym, name, tdl, fam, novelty, description
- diseaseAssociationDetails { name, dataType, evidence }
- ppiTargetInteractionDetails { ppitypes, score, interaction_type, evidence }

**Example:**
```graphql
query {
  target(q:{sym:"BRCA1"}) {
    sym
    name
    tdl
    fam
    novelty
    description
    diseaseAssociationDetails {
      name
      dataType
      evidence
    }
    ppiTargetInteractionDetails {
      ppitypes
      score
      interaction_type
      evidence
    }
  }
}
```

## QUERY TYPE 2: targets (plural)

**USE FOR:** Finding multiple targets with filters (e.g., "Find understudied GPCRs")

**Basic Structure:**
```graphql
query {
  targets(filter: {
    facets: [{facet: "FACET_NAME", values: ["VALUE"]}]
  }) {
    targets(top: 10) {
      sym
      name
      tdl
      fam
      novelty
    }
  }
}
```

**Available Facets:**
- "Target Development Level": ["Tclin", "Tchem", "Tbio", "Tdark"]
- "Protein Class": ["GPCR", "Kinase", "Ion Channel", etc.]
- associatedDisease: "disease name"

**Example:**
```graphql
query {
  targets(filter: {
    facets: [{
      facet: "Target Development Level",
      values: ["Tdark", "Tbio"]
    }]
  }) {
    targets(top: 20) {
      sym
      name
      tdl
      fam
      novelty
    }
  }
}
```

## QUERY TYPE 3: ligand (singular)

**USE FOR:** Questions about specific drugs/compounds (imatinib, aspirin, metformin)

**Basic Structure:**
```graphql
query {
  ligand(ligid: "DRUG_NAME") {
    FIELDS
  }
}
```

**Available Fields:**
- name, description, isdrug, smiles
- synonyms { name, value }
- activities { target { sym, name, tdl, fam }, type, value, moa }

**Example:**
```graphql
query {
  ligand(ligid: "imatinib") {
    name
    description
    isdrug
    smiles
    activities {
      target {
        sym
        name
        tdl
        fam
      }
      type
      value
      moa
    }
  }
}
```

## QUERY TYPE 4: ligands (plural)

**USE FOR:** Searching multiple ligands by pattern

**Basic Structure:**
```graphql
query {
  ligands(filter: {name: "PATTERN"}) {
    count
    ligands(top: 10) {
      name
      description
      isdrug
    }
  }
}
```

## QUERY TYPE 5: disease (singular)

**USE FOR:** Questions about diseases ONLY (Alzheimer's disease, asthma, cancer)
**DO NOT USE for genes/proteins even if question mentions diseases!**

**Basic Structure:**
```graphql
query {
  disease(name: "DISEASE_NAME") {
    FIELDS
  }
}
```

**Available Fields:**
- name, mondoDescription, uniprotDescription, doDescription
- targetCounts { name, value }
- children { name, mondoDescription }

**Example:**
```graphql
query {
  disease(name: "Alzheimer disease") {
    name
    mondoDescription
    doDescription
    targetCounts {
      name
      value
    }
    children {
      name
      mondoDescription
    }
  }
}
```

## CRITICAL DECISION RULES

1. If question asks about a GENE/PROTEIN (BRCA1, ADORA1, TP53, etc.) → Use **target** query
   - Even if question mentions "diseases" or "interactions"
   - Example: "What is BRCA1 and its disease associations?" → target query, NOT disease query

2. If question asks to FIND/SEARCH multiple targets → Use **targets** query
   - Example: "Find understudied GPCRs" → targets query with facets

3. If question asks about a DRUG/COMPOUND → Use **ligand** query
   - Example: "What is imatinib?" → ligand query

4. If question asks to SEARCH drugs → Use **ligands** query

5. If question asks about a DISEASE entity → Use **disease** query
   - Example: "What is Alzheimer's disease?" → disease query
   - But "What proteins are linked to Alzheimer's?" → targets query with filter

## Examples of Correct Query Selection

Q: "What is BRCA1? Show me disease associations and protein interactions"
→ Use **target** query (it's a gene, not a disease)

Q: "What is imatinib and what targets does it act on?"
→ Use **ligand** query (it's a drug)

Q: "Find understudied GPCR targets"
→ Use **targets** query with facets

Q: "What is Alzheimer's disease?"
→ Use **disease** query (asking about the disease itself)

Q: "What proteins are associated with Alzheimer's?"
→ Use **targets** query with filter (searching for proteins)

## Schema Documentation for Target Query Guide

## API Endpoint
https://pharos-api.ncats.io/graphql

## Complete List of Available Target Fields

**Basic Fields (always available on target query):**
- `sym` - Gene symbol (e.g., "ADORA1", "DRD2")
- `name` - Full protein/target name
- `tdl` - Target Development Level (Tclin, Tchem, Tbio, Tdark)
- `fam` - Protein family (GPCR, Kinase, Ion Channel, etc.)
- `novelty` - Novelty score (0-1, higher = more understudied)
- `description` - Text description of the target

**Nested/Complex Fields (return arrays or objects):**
- `diseaseAssociationDetails` - Disease associations (returns array)
  - Fields: `name`, `dataType`, `evidence`
  - Note: Does NOT support `top` parameter
- `ppiTargetInteractionDetails` - Protein-protein interactions (returns array)
  - Fields: `ppitypes`, `score`, `interaction_type`, `evidence`
  - Note: Does NOT support `top` parameter

**Fields NOT available in Pharos API:**
- ❌ `ligandCount` / `drugCount` - Not queryable
- ❌ `ligands` / `drugs` - Not available in target query
- ❌ Bioactivity filtering - Cannot filter by activity values
- ❌ Ligand sorting - Cannot sort by number of ligands

**For ligand/drug information:** Use DrugCentral database or check `tdl` field (Tclin/Tchem targets have drugs/ligands)

## Core Concept: The `target` Query

ALL Pharos queries use the `target` query with parameter `q` (query filters).

**Basic Structure:**
```graphql
query {
  target(q:{FILTER}) {
    FIELDS_YOU_WANT
  }
}
```

## Rule #1: Finding Targets by Gene Symbol

**Use `sym` filter for gene symbols**

Simple example:
```graphql
query {
  target(q:{sym:"ADORA1"}) {
    name
    sym
    tdl
    fam
    novelty
  }
}
```

## Rule #2: Getting Basic Target Info

**Essential fields** everyone should query:
- `sym` - Gene symbol (ADORA1, DRD2, etc.)
- `name` - Full protein name
- `tdl` - Target Development Level (Tclin/Tchem/Tbio/Tdark)
- `fam` - Protein family (GPCR, Kinase, Ion Channel, etc.)
- `novelty` - Novelty score (0-1, higher = more understudied)

Example:
```graphql
query {
  target(q:{sym:"DRD2"}) {
    sym
    name
    tdl
    fam
    novelty
  }
}
```

## Rule #3: Getting Disease Associations

**Use nested `diseaseAssociationDetails` field**

Available disease fields:
- `name` - Disease name
- `dataType` - Association type (e.g., "Genetic Association", "Literature")
- `evidence` - Supporting evidence

Example - Simple:
```graphql
query {
  target(q:{sym:"ADORA1"}) {
    sym
    name
    diseaseAssociationDetails {
      name
      dataType
      evidence
    }
  }
}
```

**Note:** `diseaseAssociationDetails` does NOT support `top` parameter. It returns all disease associations for the target (may be null if no associations exist).

Example:
```graphql
query {
  target(q:{sym:"EGFR"}) {
    sym
    name
    diseaseAssociationDetails {
      name
      dataType
      evidence
    }
  }
}
```

## Rule #4: Getting Drug Information

**Note:** Pharos doesn't provide direct ligandCount/drugCount fields.
For drug/ligand information, you can:
1. Check the `tdl` field (Tclin targets have approved drugs)
2. Use DrugCentral database for specific drug counts and ligand data
3. Query the target's description which may mention drug development status

Example - Get target info that indicates druggability:
```graphql
query {
  target(q:{sym:"GPER1"}) {
    sym
    name
    tdl
    fam
    novelty
    description
  }
}
```

**TDL indicates druggability:**
- Tclin = Has approved drugs (most druggable)
- Tchem = Has chemical probes/ligands
- Tbio = Biological annotation only
- Tdark = Poorly characterized (least druggable)

## Rule #5: Getting Protein-Protein Interactions

**Use nested `ppiTargetInteractionDetails` field**

Available PPI fields:
- `ppitypes` - Interaction type
- `score` - Interaction confidence score
- `interaction_type` - Type of interaction
- `evidence` - Supporting evidence

Example - Simple:
```graphql
query {
  target(q:{sym:"TP53"}) {
    sym
    name
    ppiTargetInteractionDetails {
      ppitypes
      score
      interaction_type
      evidence
    }
  }
}
```

**Note:** `ppiTargetInteractionDetails` does NOT support `top` parameter. It returns all available interactions (may be null if no interactions exist).

Example:
```graphql
query {
  target(q:{sym:"BRCA1"}) {
    sym
    name
    ppiTargetInteractionDetails {
      ppitypes
      score
      interaction_type
      evidence
    }
  }
}
```

## Rule #6: Searching Multiple Targets with Filters

**Use `targets` (plural) query for searching across targets with filters.**

The `targets` query structure is nested and uses facets for filtering:

```graphql
query {
  targets(filter: {
    facets: [{
      facet: "Target Development Level",
      values: ["Tdark", "Tbio"]
    }]
  }) {
    targets(top: 10) {
      sym
      name
      tdl
      fam
      novelty
    }
  }
}
```

**Common filter facets:**
- "Target Development Level" - values: ["Tclin", "Tchem", "Tbio", "Tdark"]
- "Protein Class" - protein family classification
- "Associated Disease" - filter by disease associations

**Example - Find understudied targets (Tdark/Tbio):**
```graphql
query {
  targets(filter: {
    facets: [{
      facet: "Target Development Level",
      values: ["Tdark", "Tbio"]
    }]
  }) {
    targets(top: 20) {
      sym
      name
      tdl
      fam
      novelty
    }
  }
}
```

**Example - Find GPCRs:**
```graphql
query {
  targets(filter: {
    facets: [{
      facet: "Protein Class",
      values: ["GPCR"]
    }]
  }) {
    targets(top: 10) {
      sym
      name
      tdl
      fam
    }
  }
}
```

**Example - Find targets by disease:**
```graphql
query {
  targets(filter: {
    associatedDisease: "Alzheimer"
  }) {
    targets(top: 10) {
      sym
      name
      tdl
      diseaseAssociationDetails {
        name
        dataType
        evidence
      }
    }
  }
}
```

**For specific genes, use `target` (singular) with aliases:**
```graphql
query {
  adora1: target(q:{sym:"ADORA1"}) {
    sym
    name
    tdl
  }
  adora2a: target(q:{sym:"ADORA2A"}) {
    sym
    name
    tdl
  }
}
```

## Complete Examples

### Example 1: SIMPLE - Basic Target Info
**Question:** "What is ADORA1?"

```graphql
query {
  target(q:{sym:"ADORA1"}) {
    sym
    name
    tdl
    fam
    novelty
  }
}
```

### Example 2: COMPLEX - Target + Diseases + Druggability
**Question:** "Tell me about GPER1, its diseases, and how druggable it is"

```graphql
query {
  target(q:{sym:"GPER1"}) {
    sym
    name
    tdl
    fam
    novelty
    description
    diseaseAssociationDetails {
      name
      dataType
      evidence
    }
  }
}
```

### Example 3: SUPER-COMPLEX - Everything + Interactions
**Question:** "What is BRCA1? Show diseases, druggability, and protein interactions"

```graphql
query {
  target(q:{sym:"BRCA1"}) {
    sym
    name
    tdl
    fam
    novelty
    description
    diseaseAssociationDetails {
      name
      dataType
      evidence
    }
    ppiTargetInteractionDetails {
      ppitypes
      score
      interaction_type
      evidence
    }
  }
}
```

### Example 4: SUPER-COMPLEX - Multiple Targets Comparison
**Question:** "Compare ADORA1, ADORA2A, and ADORA2B - show TDL, novelty, and druggability"

```graphql
query {
  adora1: target(q:{sym:"ADORA1"}) {
    sym
    name
    tdl
    fam
    novelty
    description
  }
  adora2a: target(q:{sym:"ADORA2A"}) {
    sym
    name
    tdl
    fam
    novelty
    description
  }
  adora2b: target(q:{sym:"ADORA2B"}) {
    sym
    name
    tdl
    fam
    novelty
    description
  }
}
```

### Example 5: SEARCH - Find Understudied Targets
**Question:** "Show me understudied protein targets with known bioactivity data"

```graphql
query {
  targets(filter: {
    facets: [{
      facet: "Target Development Level",
      values: ["Tdark", "Tbio"]
    }]
  }) {
    targets(top: 20) {
      sym
      name
      tdl
      fam
      novelty
      description
    }
  }
}
```

### Example 6: SEARCH - Find GPCR Targets for Disease
**Question:** "Find GPCR targets associated with Alzheimer's disease"

```graphql
query {
  targets(filter: {
    associatedDisease: "Alzheimer",
    facets: [{
      facet: "Protein Class",
      values: ["GPCR"]
    }]
  }) {
    targets(top: 15) {
      sym
      name
      tdl
      fam
      diseaseAssociationDetails {
        name
        dataType
        evidence
      }
    }
  }
}
```

## Important Notes

- **Always include `sym` and `name`** in your query for context
- **NEVER use `top` parameter** - Fields like `diseaseAssociationDetails` and `ppiTargetInteractionDetails` do NOT support it
- **For multiple genes** use GraphQL aliases (see Example 4), NOT `targets` query
- **Field names are case-sensitive**: use exact names shown above
- **Nested fields may return `null`** if no data exists for that target
- **Return ONLY the GraphQL query** - no explanations, no markdown formatting
"""


# Ligand query schema
PHAROS_LIGAND_SCHEMA = """
# Pharos GraphQL API - Ligand Query Guide

## Core Concept: The `ligand` Query

Query drugs/ligands by name to get bioactivity data and target interactions.

**Basic Structure:**
```graphql
query {
  ligand(ligid: "DRUG_NAME") {
    FIELDS_YOU_WANT
  }
}
```

## Available Ligand Fields

**Basic Fields:**
- `name` - Drug/ligand name
- `description` - Detailed description
- `isdrug` - Boolean indicating if it's an approved drug
- `smiles` - SMILES chemical structure notation

**Nested Fields:**
- `synonyms` - Array of alternative names
  - Fields: `name`, `value`
- `activities` - Array of target bioactivity data
  - `target` - Nested target object with `sym`, `name`, `tdl`, `fam`
  - `type` - Activity type (e.g., "IC50", "Ki", "EC50")
  - `value` - Activity measurement value
  - `moa` - Mechanism of action

## Example Queries

### Example 1: Basic Ligand Info
**Question:** "What is imatinib?"

```graphql
query {
  ligand(ligid: "imatinib") {
    name
    description
    isdrug
    smiles
  }
}
```

### Example 2: Ligand with Bioactivity
**Question:** "Show me the bioactivity profile for haloperidol"

```graphql
query {
  ligand(ligid: "haloperidol") {
    name
    description
    isdrug
    smiles
    activities {
      target {
        sym
        name
        tdl
        fam
      }
      type
      value
      moa
    }
  }
}
```

### Example 3: Complete Ligand Profile
**Question:** "Get full information about aspirin including synonyms and all target activities"

```graphql
query {
  ligand(ligid: "aspirin") {
    name
    description
    isdrug
    smiles
    synonyms {
      name
      value
    }
    activities {
      target {
        sym
        name
        tdl
        fam
      }
      type
      value
      moa
    }
  }
}
```

## Important Notes
- Use drug/compound names (e.g., "imatinib", "aspirin", "haloperidol")
- Returns null if ligand not found
- Activities array may be empty if no bioactivity data available
"""


# Disease query schema
PHAROS_DISEASE_SCHEMA = """
# Pharos GraphQL API - Disease Query Guide

## Core Concept: The `disease` Query

Query diseases by name to get hierarchies and target associations.

**Basic Structure:**
```graphql
query {
  disease(name: "DISEASE_NAME") {
    FIELDS_YOU_WANT
  }
}
```

## Available Disease Fields

**Basic Fields:**
- `name` - Disease identifier/name
- `mondoDescription` - MONDO ontology description
- `uniprotDescription` - UniProt database description
- `doDescription` - Disease Ontology description

**Nested Fields:**
- `targetCounts` - Target statistics
  - Fields: `name`, `value`
- `children` - Child diseases in hierarchy
  - Fields: `name`, `mondoDescription`

## Example Queries

### Example 1: Basic Disease Info
**Question:** "What is asthma?"

```graphql
query {
  disease(name: "asthma") {
    name
    mondoDescription
    uniprotDescription
    doDescription
  }
}
```

### Example 2: Disease with Hierarchy
**Question:** "Show me the disease hierarchy for Alzheimer's disease"

```graphql
query {
  disease(name: "Alzheimer disease") {
    name
    mondoDescription
    doDescription
    children {
      name
      mondoDescription
    }
  }
}
```

### Example 3: Complete Disease Profile
**Question:** "Get full information about breast cancer including target counts"

```graphql
query {
  disease(name: "breast cancer") {
    name
    mondoDescription
    uniprotDescription
    doDescription
    targetCounts {
      name
      value
    }
    children {
      name
      mondoDescription
    }
  }
}
```

## Important Notes
- Use disease names (e.g., "asthma", "Alzheimer disease", "breast cancer")
- Returns null if disease not found
- Children array shows disease subtypes/hierarchy
"""


# Ligands plural search schema
PHAROS_LIGANDS_SCHEMA = """
# Pharos GraphQL API - Ligands (Plural) Search Guide

## Core Concept: The `ligands` Query

Search multiple ligands with filters.

**Basic Structure:**
```graphql
query {
  ligands(filter: {FILTERS}) {
    count
    ligands(top: N) {
      FIELDS_YOU_WANT
    }
  }
}
```

## Available Filters
- `filter: {name: "PATTERN"}` - Search by name pattern
- Supports various filtering options

## Example Query

### Example: Search Ligands by Name
**Question:** "Find ligands with 'inhibitor' in the name"

```graphql
query {
  ligands(filter: {name: "inhibitor"}) {
    count
    ligands(top: 10) {
      name
      description
      isdrug
      activities {
        target {
          sym
          name
        }
        type
        value
      }
    }
  }
}
```

## Important Notes
- Returns count + array of ligands
- Use `top` parameter to limit results
- Good for exploratory searches
"""


async def generate_pharos_graphql(question: str) -> tuple[str, dict | None]:
    """
    Generate GraphQL query from natural language question using LLM.

    Uses unified schema that includes all query types (target, targets, ligand, ligands, disease).
    The LLM decides which query type to use based on the question.

    Args:
        question: User's natural language question about targets, ligands, or diseases

    Returns:
        Tuple of (GraphQL query string, token usage dict)

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a Pharos GraphQL expert. Generate a GraphQL query for the following question.

API: Pharos GraphQL API (https://pharos-api.ncats.io/graphql)

{PHAROS_UNIFIED_SCHEMA}

User question: {question}

CRITICAL RULES:
1. Read the CRITICAL DECISION RULES section carefully to choose the right query type
2. ONLY use fields and filters shown in the schema examples above
3. If a field or filter is not in an example, it does NOT exist in the API
4. Copy the exact structure from the most similar example
5. Do not invent or assume any fields, filters, or parameters

Instructions:
- Return ONLY a valid GraphQL query
- Use exact field names and structure from examples
- Do not include explanations or markdown formatting
- Return the GraphQL query directly without any wrapper text

GraphQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    graphql = response.choices[0].message.content.strip()

    # Extract GraphQL from markdown if present
    pattern = r'```(?:graphql)?\s*(.*?)\s*```'
    match = re.search(pattern, graphql, re.DOTALL | re.IGNORECASE)
    if match:
        graphql = match.group(1).strip()

    # Get token usage
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

    return graphql, usage


async def execute_pharos_query(graphql: str) -> dict:
    """
    Execute GraphQL query against Pharos API.

    Args:
        graphql: GraphQL query string

    Returns:
        Dict with error status and data/message

    Raises:
        Exception: If query execution fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                PHAROS_API_URL,
                json={"query": graphql}
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                return {
                    "error": True,
                    "message": str(data["errors"])
                }

            return {
                "error": False,
                "data": data.get("data", {})
            }

    except Exception as e:
        return {
            "error": True,
            "message": f"Query execution failed: {str(e)}"
        }


async def query_pharos_api(question: str) -> tuple[str, dict | None]:
    """
    Query Pharos GraphQL API using natural language.

    This is the main function exposed as a tool to the LLM. It automatically detects
    the query type and routes to the appropriate Pharos API endpoint:

    - Target queries: Gene symbols, protein info, TDL, novelty, diseases, PPIs
    - Ligand queries: Drug bioactivity, target activities, SMILES, MOA
    - Disease queries: Disease hierarchies, target associations, ontologies
    - Multi-target/ligand search: Faceted search across targets or ligands

    Args:
        question: Natural language question about targets, ligands, or diseases

    Returns:
        Tuple of (Formatted string with query results, token usage dict)

    Examples:
        TARGETS:
        - "What is ADORA1?"
        - "Show me disease associations for GPER1"
        - "Compare ADORA1, ADORA2A, and ADORA2B"
        - "Find understudied GPCR targets"

        LIGANDS:
        - "What is imatinib?"
        - "Show me the bioactivity profile for aspirin"
        - "Get SMILES structure for metformin"

        DISEASES:
        - "What is Alzheimer's disease?"
        - "Show me the disease hierarchy for breast cancer"
        - "Get target counts for asthma"
    """
    usage = None
    try:
        # Generate GraphQL using unified schema (LLM decides query type)
        graphql, usage = await generate_pharos_graphql(question)

        # Execute query
        result = await execute_pharos_query(graphql)

        if result["error"]:
            return f"Error: {result['message']}", usage

        # Format results for LLM
        data_str = json.dumps(result['data'], indent=2)
        if len(data_str) > 5000:
            data_str = data_str[:5000] + "\n... (truncated to conserve tokens)"

        output = f"Pharos Query Results:\n\n"
        output += f"GraphQL: {graphql}\n\n"
        output += f"Data:\n{data_str}\n"

        return output, usage

    except Exception as e:
        return f"Error querying Pharos: {str(e)}", usage


# ============================================================================
# LIGAND QUERIES
# ============================================================================

async def generate_pharos_ligand_graphql(question: str) -> tuple[str, dict | None]:
    """
    Generate GraphQL ligand query from natural language question using LLM.

    Args:
        question: User's natural language question about drugs/ligands

    Returns:
        Tuple of (GraphQL query string, token usage dict)

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a Pharos GraphQL expert. Generate a ligand query for the following question.

API: Pharos GraphQL API (https://pharos-api.ncats.io/graphql)
Schema documentation:
{PHAROS_LIGAND_SCHEMA}

User question: {question}

CRITICAL RULES:
1. ONLY use fields and filters shown in the schema examples above
2. If a field or filter is not in an example, it does NOT exist in the API
3. Copy the exact structure from the most similar example
4. Do not invent or assume any fields, filters, or parameters

Instructions:
- Return ONLY a valid GraphQL query
- Use exact field names and structure from examples
- Do not include explanations or markdown formatting
- Return the GraphQL query directly without any wrapper text

GraphQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    graphql = response.choices[0].message.content.strip()

    # Extract GraphQL from markdown if present
    pattern = r'```(?:graphql)?\s*(.*?)\s*```'
    match = re.search(pattern, graphql, re.DOTALL | re.IGNORECASE)
    if match:
        graphql = match.group(1).strip()

    # Get token usage
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

    return graphql, usage


async def query_pharos_ligand(question: str) -> tuple[str, dict | None]:
    """
    Query Pharos GraphQL API for ligand/drug bioactivity data.

    This function queries drugs/ligands to get bioactivity profiles, target activities,
    SMILES structures, and mechanism of action.

    Args:
        question: Natural language question about drugs/ligands

    Returns:
        Tuple of (Formatted string with query results, token usage dict)

    Examples:
        - "What is imatinib?"
        - "Show me the bioactivity profile for aspirin"
        - "Get target activities for haloperidol"
        - "What is the SMILES structure for metformin?"
    """
    usage = None
    try:
        # Generate GraphQL from question
        graphql, usage = await generate_pharos_ligand_graphql(question)

        # Execute query
        result = await execute_pharos_query(graphql)

        if result["error"]:
            return f"Error: {result['message']}", usage

        # Format results for LLM
        data_str = json.dumps(result['data'], indent=2)
        if len(data_str) > 5000:
            data_str = data_str[:5000] + "\n... (truncated to conserve tokens)"

        output = f"Pharos Ligand Query Results:\n\n"
        output += f"GraphQL: {graphql}\n\n"
        output += f"Data:\n{data_str}\n"

        return output, usage

    except Exception as e:
        return f"Error querying Pharos ligands: {str(e)}", usage


# ============================================================================
# DISEASE QUERIES
# ============================================================================

async def generate_pharos_disease_graphql(question: str) -> tuple[str, dict | None]:
    """
    Generate GraphQL disease query from natural language question using LLM.

    Args:
        question: User's natural language question about diseases

    Returns:
        Tuple of (GraphQL query string, token usage dict)

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a Pharos GraphQL expert. Generate a disease query for the following question.

API: Pharos GraphQL API (https://pharos-api.ncats.io/graphql)
Schema documentation:
{PHAROS_DISEASE_SCHEMA}

User question: {question}

CRITICAL RULES:
1. ONLY use fields and filters shown in the schema examples above
2. If a field or filter is not in an example, it does NOT exist in the API
3. Copy the exact structure from the most similar example
4. Do not invent or assume any fields, filters, or parameters

Instructions:
- Return ONLY a valid GraphQL query
- Use exact field names and structure from examples
- Do not include explanations or markdown formatting
- Return the GraphQL query directly without any wrapper text

GraphQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    graphql = response.choices[0].message.content.strip()

    # Extract GraphQL from markdown if present
    pattern = r'```(?:graphql)?\s*(.*?)\s*```'
    match = re.search(pattern, graphql, re.DOTALL | re.IGNORECASE)
    if match:
        graphql = match.group(1).strip()

    # Get token usage
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

    return graphql, usage


async def query_pharos_disease(question: str) -> tuple[str, dict | None]:
    """
    Query Pharos GraphQL API for disease information and hierarchies.

    This function queries diseases to get hierarchies, target associations,
    and ontology descriptions.

    Args:
        question: Natural language question about diseases

    Returns:
        Tuple of (Formatted string with query results, token usage dict)

    Examples:
        - "What is asthma?"
        - "Show me the disease hierarchy for Alzheimer's disease"
        - "Get target counts for breast cancer"
        - "What are the subtypes of diabetes?"
    """
    usage = None
    try:
        # Generate GraphQL from question
        graphql, usage = await generate_pharos_disease_graphql(question)

        # Execute query
        result = await execute_pharos_query(graphql)

        if result["error"]:
            return f"Error: {result['message']}", usage

        # Format results for LLM
        data_str = json.dumps(result['data'], indent=2)
        if len(data_str) > 5000:
            data_str = data_str[:5000] + "\n... (truncated to conserve tokens)"

        output = f"Pharos Disease Query Results:\n\n"
        output += f"GraphQL: {graphql}\n\n"
        output += f"Data:\n{data_str}\n"

        return output, usage

    except Exception as e:
        return f"Error querying Pharos diseases: {str(e)}", usage


# ============================================================================
# LIGANDS PLURAL SEARCH
# ============================================================================

async def generate_pharos_ligands_search_graphql(question: str) -> tuple[str, dict | None]:
    """
    Generate GraphQL ligands (plural) search query from natural language question using LLM.

    Args:
        question: User's natural language question about searching ligands

    Returns:
        Tuple of (GraphQL query string, token usage dict)

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a Pharos GraphQL expert. Generate a ligands (plural) search query for the following question.

API: Pharos GraphQL API (https://pharos-api.ncats.io/graphql)
Schema documentation:
{PHAROS_LIGANDS_SCHEMA}

User question: {question}

CRITICAL RULES:
1. ONLY use fields and filters shown in the schema examples above
2. If a field or filter is not in an example, it does NOT exist in the API
3. Copy the exact structure from the most similar example
4. Do not invent or assume any fields, filters, or parameters

Instructions:
- Return ONLY a valid GraphQL query
- Use exact field names and structure from examples
- Do not include explanations or markdown formatting
- Return the GraphQL query directly without any wrapper text

GraphQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    graphql = response.choices[0].message.content.strip()

    # Extract GraphQL from markdown if present
    pattern = r'```(?:graphql)?\s*(.*?)\s*```'
    match = re.search(pattern, graphql, re.DOTALL | re.IGNORECASE)
    if match:
        graphql = match.group(1).strip()

    # Get token usage
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

    return graphql, usage


async def query_pharos_ligands_search(question: str) -> tuple[str, dict | None]:
    """
    Search multiple ligands in Pharos using filters.

    This function searches across ligands for exploratory analysis.

    Args:
        question: Natural language question about searching ligands

    Returns:
        Tuple of (Formatted string with query results, token usage dict)

    Examples:
        - "Find ligands with 'inhibitor' in the name"
        - "Search for kinase inhibitors"
        - "Find approved drugs targeting GPCRs"
    """
    usage = None
    try:
        # Generate GraphQL from question
        graphql, usage = await generate_pharos_ligands_search_graphql(question)

        # Execute query
        result = await execute_pharos_query(graphql)

        if result["error"]:
            return f"Error: {result['message']}", usage

        # Format results for LLM
        data_str = json.dumps(result['data'], indent=2)
        if len(data_str) > 5000:
            data_str = data_str[:5000] + "\n... (truncated to conserve tokens)"

        output = f"Pharos Ligands Search Results:\n\n"
        output += f"GraphQL: {graphql}\n\n"
        output += f"Data:\n{data_str}\n"

        return output, usage

    except Exception as e:
        return f"Error searching Pharos ligands: {str(e)}", usage
