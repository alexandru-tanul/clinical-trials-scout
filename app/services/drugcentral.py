"""
DrugCentral database integration.

Provides text-to-SQL capability for querying pharmaceutical data.
"""
import re
from tortoise import Tortoise
from litellm import completion
from app.config import settings
from typing import Optional


# Minimal schema for token efficiency
DRUGCENTRAL_SCHEMA = """
DrugCentral PostgreSQL - Use these views and patterns:

Views:
- drug_search_all: drug_id, primary_name, all_synonyms, chemical_formula
- drug_info: drug_id, drug_name, molecular_weight, chemical_formula
- drug_targets: drug_id, drug_name, target_name, target_class, gene, action_type
- drug_products: drug_id, drug_name, product_name, dosage_form
- fda_approved_drugs: drug_id, drug_name, fda_approval_date, applicant_company

Find drug by name:
SELECT * FROM drug_search_all WHERE primary_name ILIKE '%name%' OR all_synonyms ILIKE '%name%' LIMIT 10

Find targets:
SELECT target_name, gene, action_type FROM drug_targets WHERE drug_name ILIKE '%name%' LIMIT 10

Find by protein:
SELECT drug_name, target_name, gene FROM drug_targets WHERE target_name ILIKE '%protein%' LIMIT 10

Use ILIKE for searches, always LIMIT results.
"""


async def execute_drugcentral_query(sql: str) -> dict:
    """
    Execute raw SQL query against DrugCentral database.

    Args:
        sql: SQL query to execute

    Returns:
        Dict with columns, rows, and row_count

    Raises:
        Exception: If query execution fails
    """
    conn = Tortoise.get_connection("drugcentral")

    # Add LIMIT if not present
    if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        sql = sql.rstrip(';') + ' LIMIT 100'

    # Set timeout
    await conn.execute_query("SET statement_timeout = '30s'")

    try:
        result = await conn.execute_query_dict(sql)

        if not result:
            return {
                "columns": [],
                "rows": [],
                "row_count": 0
            }

        columns = list(result[0].keys()) if result else []
        rows = [tuple(row.values()) for row in result]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }
    finally:
        await conn.execute_query("RESET statement_timeout")


async def generate_drugcentral_sql(question: str) -> str:
    """
    Generate SQL query from natural language question.

    Args:
        question: User's natural language question about drugs

    Returns:
        SQL query string

    Raises:
        Exception: If LLM API call fails
    """
    prompt = f"""You are a PostgreSQL SQL expert. Generate a SQL query for the following question.

Database: DrugCentral PostgreSQL database
Schema information:
{DRUGCENTRAL_SCHEMA}

User question: {question}

CRITICAL RULES:
1. ONLY use tables and columns shown in the schema documentation above
2. If a table or column is not in the schema, it does NOT exist in the database
3. Copy the exact structure and JOIN patterns from the most similar schema example
4. Do not invent or assume any tables, columns, or relationships

Instructions:
- Return ONLY a valid PostgreSQL SELECT query
- Use exact table and column names from schema
- Limit results to 100 rows with LIMIT clause
- Do not include explanations or markdown formatting
- Return the SQL query directly without any wrapper text

SQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    sql = response.choices[0].message.content.strip()

    # Extract SQL from markdown if present
    pattern = r'```(?:sql)?\s*(.*?)\s*```'
    match = re.search(pattern, sql, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()

    return sql


def is_safe_sql_query(sql: str) -> tuple[bool, str]:
    """
    Validate SQL query is safe (read-only SELECT).

    Args:
        sql: SQL query to validate

    Returns:
        Tuple of (is_safe, error_message)
    """
    dangerous_keywords = ['DELETE', 'DROP', 'TRUNCATE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE']
    sql_upper = sql.upper()

    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return False, f"Unsafe SQL operation detected: {keyword}"

    if not sql_upper.strip().startswith('SELECT'):
        return False, "Only SELECT queries are allowed"

    return True, ""


async def query_drugcentral_database(question: str) -> str:
    """
    Query DrugCentral database using natural language.

    This is the main function that will be exposed as a tool to the LLM.

    Args:
        question: Natural language question about drugs, targets, or pharmaceutical data

    Returns:
        Formatted string with query results

    Examples:
        - "What drugs target GPER?"
        - "Show me FDA approved orphan drugs from 2023"
        - "Find all kinase inhibitors"
        - "What is the mechanism of action for semaglutide?"
    """
    try:
        # Generate SQL from question
        sql = await generate_drugcentral_sql(question)
        print(f"[DEBUG] DrugCentral generated SQL: {sql}")

        # Validate SQL is safe
        is_safe, error_msg = is_safe_sql_query(sql)
        if not is_safe:
            return f"Error: {error_msg}"

        # Execute query
        result = await execute_drugcentral_query(sql)

        # Format results
        if result["row_count"] == 0:
            return f"No results found in DrugCentral database.\n\nSQL Query: {sql}"

        # Format as structured text for LLM
        output = f"DrugCentral Query Results ({result['row_count']} rows):\n\n"
        output += f"SQL: {sql}\n\n"
        output += f"Columns: {', '.join(result['columns'])}\n\n"

        # Include first 20 rows
        for i, row in enumerate(result['rows'][:20], 1):
            row_dict = dict(zip(result['columns'], row))
            output += f"{i}. {row_dict}\n"

        if result['row_count'] > 20:
            output += f"\n... and {result['row_count'] - 20} more results"

        return output

    except Exception as e:
        return f"Error querying DrugCentral: {str(e)}"


# Note: Auto-enrichment functions have been removed.
# Pharos is now a separate, independent tool that the LLM can call when needed.
# See app/pharos.py for Pharos functionality.


def _get_tdl_description(tdl: Optional[str]) -> str:
    """Get human-readable description of TDL classification."""
    descriptions = {
        'Tclin': 'Clinical - proven drug target',
        'Tchem': 'Chemogenomic - has active compounds',
        'Tbio': 'Biological - limited drug data',
        'Tdark': 'Dark - poorly studied/understudied'
    }
    return descriptions.get(tdl, 'Unknown classification')


def _get_novelty_level(novelty: float) -> str:
    """Convert novelty score to human-readable level."""
    if novelty > 0.7:
        return 'High'
    elif novelty > 0.4:
        return 'Medium'
    else:
        return 'Low'


# DEPRECATED: query_drugcentral_with_pharos() has been removed.
# Use query_drugcentral_database() for DrugCentral queries.
# The LLM will call query_pharos_api() separately when needed.
# This ensures clean separation of concerns between databases.
