"""
Pharos GraphQL API integration.

Provides text-to-GraphQL capability for querying IDG (Illuminating the Druggable Genome)
target data including TDL classifications, disease associations, ligand counts, and protein interactions.
"""
import re
import json
import httpx
from litellm import completion
from app.config import settings
from typing import Optional, Dict, List


# Pharos GraphQL API endpoint
PHAROS_API_URL = "https://pharos-api.ncats.io/graphql"


# Schema documentation for LLM context
PHAROS_SCHEMA = """
# Pharos GraphQL API - Target Query Guide

## API Endpoint
https://pharos-api.ncats.io/graphql

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

## Rule #6: Multiple Targets at Once

**IMPORTANT:** For multiple targets, query them individually in separate `target` queries.
The `targets` (plural) query has complex filtering syntax and is NOT recommended for simple multi-gene lookups.

**Best approach - Query each target separately:**
```graphql
query {
  adora1: target(q:{sym:"ADORA1"}) {
    sym
    name
    tdl
    fam
    novelty
  }
  adora2a: target(q:{sym:"ADORA2A"}) {
    sym
    name
    tdl
    fam
    novelty
  }
  adora2b: target(q:{sym:"ADORA2B"}) {
    sym
    name
    tdl
    fam
    novelty
  }
}
```

This approach uses GraphQL aliases to query multiple targets in a single request.

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

## Important Notes

- **Always include `sym` and `name`** in your query for context
- **NEVER use `top` parameter** - Fields like `diseaseAssociationDetails` and `ppiTargetInteractionDetails` do NOT support it
- **For multiple genes** use GraphQL aliases (see Example 4), NOT `targets` query
- **Field names are case-sensitive**: use exact names shown above
- **Nested fields may return `null`** if no data exists for that target
- **Return ONLY the GraphQL query** - no explanations, no markdown formatting
"""


async def generate_pharos_graphql(question: str) -> str:
    """
    Generate GraphQL query from natural language question using LLM.

    Args:
        question: User's natural language question about protein targets

    Returns:
        GraphQL query string

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a Pharos GraphQL expert. Generate a GraphQL query for the following question.

API: Pharos GraphQL API (https://pharos-api.ncats.io/graphql)
Schema documentation:
{PHAROS_SCHEMA}

User question: {question}

Instructions:
- Return ONLY a valid GraphQL query
- Do not include explanations or markdown formatting
- Use the exact field names from the schema
- Follow the examples for query structure
- Return the GraphQL query directly without any wrapper text

GraphQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )

    graphql = response.choices[0].message.content.strip()

    # Extract GraphQL from markdown if present
    pattern = r'```(?:graphql)?\s*(.*?)\s*```'
    match = re.search(pattern, graphql, re.DOTALL | re.IGNORECASE)
    if match:
        graphql = match.group(1).strip()

    return graphql


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


async def query_pharos_api(question: str) -> str:
    """
    Query Pharos GraphQL API using natural language.

    This is the main function exposed as a tool to the LLM.

    Args:
        question: Natural language question about protein targets

    Returns:
        Formatted string with query results

    Examples:
        - "What is ADORA1?"
        - "Show me disease associations for GPER1"
        - "How druggable is BRCA1? How many known ligands?"
        - "What proteins does TP53 interact with?"
        - "Compare ADORA1, ADORA2A, and ADORA2B"
    """
    try:
        # Generate GraphQL from question
        graphql = await generate_pharos_graphql(question)

        # Execute query
        result = await execute_pharos_query(graphql)

        if result["error"]:
            return f"Error: {result['message']}"

        # Format results for LLM
        output = f"Pharos Query Results:\n\n"
        output += f"GraphQL: {graphql}\n\n"
        output += f"Data:\n{json.dumps(result['data'], indent=2)}\n"

        return output

    except Exception as e:
        return f"Error querying Pharos: {str(e)}"
