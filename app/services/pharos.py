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


# Minimal schema for token efficiency
PHAROS_SCHEMA = """
Pharos GraphQL API - Generate queries using these patterns:

Basic fields: sym, name, tdl, fam, novelty, description
Nested fields: diseaseAssociationDetails{name,dataType,evidence}, ppiTargetInteractionDetails{ppitypes,score}

Single target:
query { target(q:{sym:"GENE"}) { sym name tdl } }

With diseases:
query { target(q:{sym:"GENE"}) { sym name tdl diseaseAssociationDetails{name dataType} } }

Multiple targets:
query {
  g1: target(q:{sym:"GENE1"}) { sym name tdl }
  g2: target(q:{sym:"GENE2"}) { sym name tdl }
}

Search by TDL:
query { targets(filter:{facets:[{facet:"Target Development Level",values:["Tdark"]}]}) { targets(top:10) { sym name tdl } } }

Return ONLY the GraphQL query, no explanations.
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
