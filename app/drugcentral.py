"""
DrugCentral database integration.

Provides text-to-SQL capability for querying pharmaceutical data.
"""
import re
from tortoise import Tortoise
from litellm import completion
from app.config import settings


# Schema documentation for LLM context
DRUGCENTRAL_SCHEMA = """
# DrugCentral Database - Query Guide

## Core Tables

### 1. structures - Drug Structures
Main drug information table.

Key columns:
- `id` (integer) - Unique structure ID (PRIMARY KEY)
- `name` (varchar) - Primary drug name
- `cd_formula` (varchar) - Chemical formula
- `cd_molweight` (double) - Molecular weight
- `cas_reg_no` (varchar) - CAS registry number
- `smiles` (varchar) - SMILES structure
- `inchi` (varchar) - InChI identifier

**Find drug by name:**
```sql
SELECT id, name, cd_formula, cd_molweight
FROM structures
WHERE name ILIKE '%ibuprofen%'
LIMIT 10
```

### 2. synonyms - Drug Names and Synonyms
All drug names (brand names, generic names, etc.)

Key columns:
- `id` (integer) - Structure ID (→ structures.id)
- `name` (varchar) - Synonym/brand name
- `preferred_name` (smallint) - 1 if preferred name

**Find drug by any name (including brand names):**
```sql
SELECT DISTINCT s.id, s.name, s.cd_formula
FROM structures s
JOIN synonyms syn ON s.id = syn.id
WHERE syn.name ILIKE '%aspirin%' OR s.name ILIKE '%aspirin%'
LIMIT 10
```

### 3. act_table_full - Drug-Target Activities
Drug-target relationships and mechanisms of action.

Key columns:
- `struct_id` (integer) - Drug ID (→ structures.id)
- `target_id` (integer) - Target ID (→ target_dictionary.id)
- `target_name` (varchar) - Target protein name
- `target_class` (varchar) - Class (Kinase, Ion channel, Membrane receptor, etc.)
- `gene` (varchar) - Gene symbol(s)
- `accession` (varchar) - UniProt accession
- `action_type` (varchar) - INHIBITOR, AGONIST, ANTAGONIST, etc.
- `act_value` (double) - Activity value
- `act_unit` (varchar) - Unit (nM, uM, etc.)
- `act_type` (varchar) - IC50, Ki, EC50, etc.
- `moa` (smallint) - 1 if primary mechanism of action
- `tdl` (varchar) - Target Development Level (Tclin, Tchem, Tbio, Tdark)

**Find drugs targeting specific protein:**
```sql
SELECT DISTINCT s.name, atf.target_name, atf.target_class, atf.gene, atf.action_type
FROM structures s
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE atf.target_name ILIKE '%estrogen receptor%'
   OR atf.gene ILIKE '%ESR%'
LIMIT 10
```

**Find all drugs by target class:**
```sql
SELECT s.name, atf.target_name, atf.gene, atf.action_type
FROM structures s
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE atf.target_class = 'Kinase'
LIMIT 20
```

**Available target classes:** Kinase, Ion channel, Membrane receptor, Nuclear hormone receptor, Transporter, Enzyme, Cytokine, etc.

### 4. target_dictionary - Target Information
Information about drug targets (proteins, receptors, etc.)

Key columns:
- `id` (integer) - Target ID (PRIMARY KEY)
- `name` (varchar) - Target name
- `target_class` (varchar) - Target class
- `tdl` (varchar) - Target Development Level (Tclin, Tchem, Tbio, Tdark)

### 5. approval - FDA Approval Data
FDA approval information.

Key columns:
- `struct_id` (integer) - Drug ID (→ structures.id)
- `approval` (date) - Approval date
- `type` (varchar) - Approval type (e.g., "US")
- `applicant` (varchar) - Company name
- `orphan` (boolean) - TRUE if orphan drug

**Find FDA approved drugs:**
```sql
SELECT s.name, a.approval, a.applicant, a.orphan
FROM structures s
JOIN approval a ON s.id = a.struct_id
WHERE a.type = 'US'
ORDER BY a.approval DESC
LIMIT 10
```

**Find orphan drugs:**
```sql
SELECT s.name, a.approval, a.applicant
FROM structures s
JOIN approval a ON s.id = a.struct_id
WHERE a.orphan = TRUE
ORDER BY a.approval DESC
LIMIT 10
```

## Common Query Patterns

### Pattern 1: Find drugs by name (any synonym)
```sql
SELECT DISTINCT s.id, s.name AS primary_name, syn.name AS synonym, s.cd_formula
FROM structures s
LEFT JOIN synonyms syn ON s.id = syn.id
WHERE s.name ILIKE '%DRUGNAME%' OR syn.name ILIKE '%DRUGNAME%'
LIMIT 10
```

### Pattern 2: Find drugs targeting specific protein/gene
```sql
SELECT s.name AS drug_name, atf.target_name, atf.gene, atf.target_class, atf.action_type, atf.act_value, atf.act_unit
FROM structures s
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE atf.target_name ILIKE '%PROTEIN%' OR atf.gene ILIKE '%GENE%'
LIMIT 10
```

### Pattern 3: Find drug targets for a specific drug
```sql
SELECT atf.target_name, atf.gene, atf.target_class, atf.action_type, atf.moa
FROM structures s
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE s.name ILIKE '%DRUGNAME%'
ORDER BY atf.moa DESC
LIMIT 10
```

### Pattern 4: Find FDA approved drugs by target class
```sql
SELECT DISTINCT s.name, a.approval, atf.target_class, atf.target_name
FROM structures s
JOIN approval a ON s.id = a.struct_id
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE atf.target_class = 'Kinase' AND a.type = 'US'
ORDER BY a.approval DESC
LIMIT 10
```

## Important Notes

- **Always use ILIKE** for case-insensitive searches (not LIKE)
- **Always include LIMIT** (queries auto-limited to 100 rows)
- **JOIN carefully** - structures.id = synonyms.id = act_table_full.struct_id = approval.struct_id
- **Gene symbols** may contain multiple genes separated by semicolons
- **Target class** values: Kinase, Ion channel, Membrane receptor, Nuclear hormone receptor, Transporter, Enzyme, etc.
- **Action types** include: INHIBITOR, AGONIST, ANTAGONIST, MODULATOR, BLOCKER, etc.
- **Boolean fields** use TRUE/FALSE (not 1/0)
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

Instructions:
- Return ONLY a valid PostgreSQL SELECT query
- Do not include explanations or markdown formatting
- Use proper PostgreSQL syntax
- Limit results to 100 rows with LIMIT clause
- Return the SQL query directly without any wrapper text

SQL Query:"""

    response = completion(
        model=settings.MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
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

        # Validate SQL is safe
        is_safe, error_msg = is_safe_sql_query(sql)
        if not is_safe:
            return f"Error: {error_msg}"

        # Execute query
        result = await execute_drugcentral_query(sql)

        # Format results
        if result["row_count"] == 0:
            return "No results found in DrugCentral database."

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
