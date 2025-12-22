"""
DrugCentral database integration.

Provides text-to-SQL capability for querying pharmaceutical data.
"""
import re
from tortoise import Tortoise
from litellm import completion
from app.config import settings
from typing import Optional


# Schema documentation for LLM context
DRUGCENTRAL_SCHEMA = """
# DrugCentral Database - Query Guide

## Simplified Views (Use These!)

The database has pre-built views that make querying much easier. Always use these views instead of raw tables.

## Rule #1: Finding Drugs by Name

**Use `drug_search_all` for ALL drug name searches.**

This view has ONLY these columns:
- `drug_id` - Unique identifier
- `primary_name` - Chemical name (e.g., "acetylsalicylic acid")
- `all_synonyms` - All other names (e.g., contains "aspirin")
- `chemical_formula` - Chemical formula
- `is_fda_approved` - TRUE if FDA approved
- `formulation_count` - Number of formulations

**IMPORTANT:** This view does NOT have molecular_weight or other detailed properties.
For those, JOIN with drug_info using drug_id.

**Search pattern:**
```sql
SELECT drug_id, primary_name, chemical_formula
FROM drug_search_all
WHERE primary_name ILIKE '%DRUGNAME%' OR all_synonyms ILIKE '%DRUGNAME%'
```

**Examples:**
```sql
-- Find aspirin
SELECT * FROM drug_search_all
WHERE primary_name ILIKE '%aspirin%' OR all_synonyms ILIKE '%aspirin%'

-- Find Tylenol
SELECT * FROM drug_search_all
WHERE primary_name ILIKE '%tylenol%' OR all_synonyms ILIKE '%tylenol%'
```

## Rule #2: Getting Drug Details

**Use `drug_info` for complete drug information.**

This view has ONLY these columns:
- `drug_id` - Unique identifier
- `drug_name` - Chemical name only (NOT brand names, NOT synonyms)
- `cas_reg_no` - CAS number
- `chemical_formula` - Chemical formula
- `molecular_weight` - Molecular weight
- `smiles`, `inchikey` - Chemical identifiers
- `primary_approval_authority` - First approval authority (e.g., "FDA")
- `primary_approval_date` - First approval date
- `is_fda_approved` - TRUE if FDA approved
- `formulation_count`, `product_count`, `target_count` - Counts

**IMPORTANT:** This view does NOT have `primary_name` or `all_synonyms`.
For brand name searches, JOIN with drug_search_all using drug_id.

**Simple search (if you know the chemical name):**
```sql
SELECT drug_name, molecular_weight, chemical_formula
FROM drug_info
WHERE drug_name ILIKE '%ibuprofen%'
```

**Search by any name (brand or chemical):**
```sql
SELECT di.drug_name, di.molecular_weight, di.chemical_formula
FROM drug_info di
JOIN drug_search_all dsa ON di.drug_id = dsa.drug_id
WHERE dsa.primary_name ILIKE '%aspirin%' OR dsa.all_synonyms ILIKE '%aspirin%'
```

## Rule #3: Finding FDA Approved Drugs

**Use `fda_approved_drugs` for FDA-specific queries.**

This view has:
- `drug_id` - Unique identifier
- `drug_name` - Chemical name
- `chemical_formula` - Chemical formula
- `fda_approval_date` - FDA approval date
- `applicant_company` - Company name
- `is_orphan_drug` - TRUE if orphan drug
- `formulation_count` - Number of formulations

**Examples:**
```sql
-- 10 most recent FDA approvals
SELECT drug_name, fda_approval_date, applicant_company
FROM fda_approved_drugs
ORDER BY fda_approval_date DESC
LIMIT 10

-- FDA approvals in 2020
SELECT drug_name, fda_approval_date
FROM fda_approved_drugs
WHERE fda_approval_date BETWEEN '2020-01-01' AND '2020-12-31'

-- Orphan drugs
SELECT drug_name, fda_approval_date
FROM fda_approved_drugs
WHERE is_orphan_drug = TRUE
ORDER BY fda_approval_date DESC
LIMIT 10
```

## Rule #4: Finding Drug Products

**Use `drug_products` for product formulations.**

This view has:
- `drug_id` - Unique identifier
- `drug_name` - Chemical name only (NOT brand names)
- `ndc_product_code` - Product code
- `product_name` - Product brand name
- `generic_name` - Generic name
- `dosage_form` - Form (TABLET, CAPSULE, INJECTION, etc.)
- `administration_route` - Route (ORAL, INTRAVENOUS, TOPICAL, etc.)
- `marketing_status` - Marketing status
- `ingredient_quantity`, `ingredient_unit` - Dosage

**Search by chemical name:**
```sql
SELECT product_name, dosage_form, administration_route
FROM drug_products
WHERE drug_name ILIKE '%ibuprofen%' AND dosage_form = 'TABLET'
```

**Search by any name (brand or chemical):**
```sql
SELECT dp.product_name, dp.dosage_form, dp.administration_route
FROM drug_products dp
JOIN drug_search_all dsa ON dp.drug_id = dsa.drug_id
WHERE (dsa.primary_name ILIKE '%aspirin%' OR dsa.all_synonyms ILIKE '%aspirin%')
AND dp.dosage_form = 'TABLET'
```

## Rule #5: Finding Drug Targets

**Use `drug_targets` for mechanism of action.**

This view has:
- `drug_id` - Unique identifier
- `drug_name` - Chemical name only (NOT brand names)
- `target_id` - Target identifier
- `target_name` - Protein/enzyme name
- `target_class` - Class (GPCR, Kinase, Enzyme, Ion channel, etc.)
- `gene` - Gene symbol (e.g., "ABL1", "SRC") - IMPORTANT for Pharos enrichment!
- `uniprot` - UniProt accession ID
- `target_organism` - Species (Homo sapiens, etc.)
- `action_type` - Action (INHIBITOR, AGONIST, ANTAGONIST, etc.)
- `activity_value`, `activity_unit` - Potency (IC50, Ki, etc.)
- `is_primary_mechanism` - TRUE if primary MOA

**IMPORTANT:** Always include `gene` column in SELECT to enable Pharos IDG enrichment!

**Search by chemical name:**
```sql
SELECT target_name, target_class, gene, action_type, activity_value
FROM drug_targets
WHERE drug_name ILIKE '%atorvastatin%'
```

**Search by any name:**
```sql
SELECT dt.target_name, dt.target_class, dt.gene, dt.action_type
FROM drug_targets dt
JOIN drug_search_all dsa ON dt.drug_id = dsa.drug_id
WHERE dsa.primary_name ILIKE '%lipitor%' OR dsa.all_synonyms ILIKE '%lipitor%'
```

**Filter by target type:**
```sql
SELECT drug_name, target_name, gene, action_type
FROM drug_targets
WHERE target_class = 'Kinase' AND action_type = 'INHIBITOR'
```

**Find drugs targeting specific protein:**
```sql
SELECT drug_name, target_name, gene, action_type, activity_value
FROM drug_targets
WHERE target_name ILIKE '%tyrosine kinase%'
LIMIT 10
```

## Rule #6: Finding Drug Classes

**Use `drug_classes` for therapeutic classification.**

This view has:
- `drug_id` - Unique identifier
- `drug_name` - Chemical name
- `atc_code` - ATC code
- `anatomical_group` - Broadest (e.g., "NERVOUS SYSTEM")
- `therapeutic_group` - Therapeutic (e.g., "ANALGESICS")
- `pharmacological_group` - Pharmacological
- `chemical_group` - Most specific (e.g., "OPIOID ANALGESICS")

**Examples:**
```sql
-- All analgesics
SELECT drug_name, chemical_group
FROM drug_classes
WHERE chemical_group ILIKE '%analgesic%'

-- All cardiovascular drugs
SELECT drug_name, therapeutic_group, chemical_group
FROM drug_classes
WHERE anatomical_group ILIKE '%cardiovascular%'
```

## Important Notes

- Always use ILIKE for case-insensitive searches
- Always include LIMIT (queries auto-limited to 100 rows)
- Boolean fields use TRUE/FALSE (not 1/0)
- When user mentions a drug name, ALWAYS search using drug_search_all first
- Column names are exact: use `drug_name` in drug_info, `primary_name` in drug_search_all

## Searching for Targets with Multiple Names

Many proteins have multiple names/aliases. When searching for a target, use OR conditions to search variations:

**Common protein name variations:**
- GPER = GPR30 = G protein-coupled estrogen receptor
- GLP1R = GLP-1R = Glucagon-like peptide-1 receptor
- EGFR = HER1 = Epidermal growth factor receptor
- ESR1 = ER-alpha = Estrogen receptor alpha

**Example: Search for drugs targeting tyrosine kinase:**
```sql
SELECT drug_name, target_name, action_type
FROM drug_targets
WHERE target_name ILIKE '%tyrosine%kinase%'
   OR target_name ILIKE '%tyrosine-protein%kinase%'
LIMIT 10
```

**CRITICAL: When searching returns 0 results:**
1. Try broader search terms (e.g., "kinase" instead of "ABL1 kinase")
2. Try common abbreviations and full names
3. Search in both target_name AND action_type columns

## Core Tables (Advanced - Only if Views Don't Work)

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
- `type` (varchar) - Approval authority. **IMPORTANT:** Use 'FDA' for US approvals, NOT 'US'!
  Valid values: 'FDA', 'EMA', 'Health Canada', 'PMDA', 'CDSCO (INDIA)', etc.
- `applicant` (varchar) - Company name
- `orphan` (boolean) - TRUE if orphan drug

**Find FDA approved drugs:**
```sql
SELECT s.name, a.approval, a.applicant, a.orphan
FROM structures s
JOIN approval a ON s.id = a.struct_id
WHERE a.type = 'FDA'
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
WHERE atf.target_class = 'Kinase' AND a.type = 'FDA'
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

## Searching for Targets with Multiple Names

Many proteins have multiple names/aliases. When searching for a target, use OR conditions to search ALL known names:

**Common protein name variations:**
- GPER = GPR30 = G protein-coupled estrogen receptor
- GLP1R = GLP-1R = Glucagon-like peptide-1 receptor
- EGFR = HER1 = Epidermal growth factor receptor
- ESR1 = ER-alpha = Estrogen receptor alpha
- TNFR = TNF receptor

**Example: Search for GPER (which may be listed as GPR30):**
```sql
SELECT s.name AS drug_name, atf.target_name, atf.gene, atf.action_type
FROM structures s
JOIN act_table_full atf ON s.id = atf.struct_id
WHERE atf.target_name ILIKE '%GPER%'
   OR atf.target_name ILIKE '%GPR30%'
   OR atf.target_name ILIKE '%G protein-coupled estrogen%'
   OR atf.gene ILIKE '%GPER%'
   OR atf.gene ILIKE '%GPR30%'
LIMIT 10
```

**CRITICAL: When a user asks for a specific target and you get 0 results, try these strategies:**
1. Search with common abbreviations (GLP1R → GLP-1R, GLP 1R)
2. Search with full protein name if abbreviation given
3. Search with gene symbols and alternate names
4. Use broader terms (e.g., "estrogen receptor" instead of just "ESR1")
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
