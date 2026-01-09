"""
Clinical Trial Scout Service

This module provides functionality to search and compare clinical trials
from ClinicalTrials.gov API v2.
"""
import asyncio
import aiohttp
from typing import Optional, Dict, List, Any


async def search_clinical_trials(
    query: Optional[str] = None,
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[List[str]] = None,
    phase: Optional[List[str]] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Search for clinical trials using ClinicalTrials.gov API v2.

    Args:
        query: General search query string
        condition: Medical condition or disease
        intervention: Intervention/treatment type
        location: Geographic location
        status: List of recruitment statuses (e.g., ['RECRUITING', 'NOT_YET_RECRUITING'])
        phase: List of trial phases (e.g., ['PHASE1', 'PHASE2', 'PHASE3', 'PHASE4'])
        max_results: Maximum number of results to return (default: 5, max: 1000)

    Returns:
        Dictionary containing:
            - success (bool): Whether the request was successful
            - total_count (int): Total number of matching trials
            - trials (list): List of trial data
            - error (str): Error message if request failed
    """
    base_url = "https://clinicaltrials.gov/api/v2/studies"

    # Build query parameters
    params = {
        "format": "json",
        "pageSize": min(max_results, 1000),  # API max is 1000
        "countTotal": "true",  # Required to get totalCount in response
        "sort": "@relevance",  # Sort by relevance for best matches first
    }

    # Use dedicated query parameters for better search accuracy
    # (These are more accurate than AREA syntax in query.term)
    if query:
        params["query.term"] = query  # General free-text search
    if condition:
        params["query.cond"] = condition  # Dedicated condition search
    if intervention:
        params["query.intr"] = intervention  # Dedicated intervention search
    if location:
        params["query.locn"] = location  # Dedicated location search

    # Add status filter
    if status:
        params["filter.overallStatus"] = ",".join(status)

    # Add phase filter
    if phase:
        params["filter.phase"] = ",".join(phase)

    try:
        timeout = aiohttp.ClientTimeout(total=60)  # Increased to 60s for complex queries
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

            # Extract relevant trial information
            trials = []
            for study in data.get("studies", []):
                protocol_section = study.get("protocolSection", {})
                results_section = study.get("resultsSection", {})

                # Protocol Section Modules
                identification_module = protocol_section.get("identificationModule", {})
                status_module = protocol_section.get("statusModule", {})
                description_module = protocol_section.get("descriptionModule", {})
                conditions_module = protocol_section.get("conditionsModule", {})
                design_module = protocol_section.get("designModule", {})
                eligibility_module = protocol_section.get("eligibilityModule", {})
                contacts_module = protocol_section.get("contactsLocationsModule", {})
                sponsor_module = protocol_section.get("sponsorCollaboratorsModule", {})
                outcomes_module = protocol_section.get("outcomesModule", {})
                arms_interventions_module = protocol_section.get("armsInterventionsModule", {})

                # Results Section Modules (when available)
                outcome_measures_module = results_section.get("outcomeMeasuresModule", {})
                adverse_events_module = results_section.get("adverseEventsModule", {})
                participant_flow_module = results_section.get("participantFlowModule", {})
                baseline_module = results_section.get("baselineCharacteristicsModule", {})

                # Build trial info dictionary
                trial_info = {
                    "nct_id": identification_module.get("nctId"),
                    "title": identification_module.get("officialTitle") or identification_module.get("briefTitle"),
                    "status": status_module.get("overallStatus"),
                    "phase": design_module.get("phases", []),
                    "brief_summary": description_module.get("briefSummary"),
                    # Skip detailed_description to save tokens (brief_summary is sufficient)
                    "conditions": conditions_module.get("conditions", []),
                    "keywords": conditions_module.get("keywords", []),
                    "interventions": [
                        {
                            "type": intervention.get("type"),
                            "name": intervention.get("name"),
                            # Skip description to save tokens (name + type is sufficient)
                        }
                        for intervention in arms_interventions_module.get("interventions", [])
                    ],
                    "eligibility": {
                        "criteria": eligibility_module.get("eligibilityCriteria"),
                        "sex": eligibility_module.get("sex"),
                        "min_age": eligibility_module.get("minimumAge"),
                        "max_age": eligibility_module.get("maximumAge"),
                        "healthy_volunteers": eligibility_module.get("healthyVolunteers"),
                    },
                    # Limit locations to first 5 to save tokens
                    "locations": [
                        {
                            "facility": location.get("facility"),
                            "city": location.get("city"),
                            "state": location.get("state"),
                            "country": location.get("country"),
                        }
                        for location in contacts_module.get("locations", [])[:5]
                    ],
                    "url": f"https://clinicaltrials.gov/study/{identification_module.get('nctId')}",
                    "start_date": status_module.get("startDateStruct", {}).get("date"),
                    "completion_date": status_module.get("completionDateStruct", {}).get("date"),

                    # NEW: Sponsor information
                    "sponsor": {
                        "lead_sponsor": sponsor_module.get("leadSponsor", {}).get("name"),
                        "collaborators": [c.get("name") for c in sponsor_module.get("collaborators", [])],
                    },

                    # NEW: Study design details
                    "design": {
                        "study_type": design_module.get("studyType"),
                        "enrollment": design_module.get("enrollmentInfo", {}).get("count"),
                        "allocation": design_module.get("designInfo", {}).get("allocation"),
                        "intervention_model": design_module.get("designInfo", {}).get("interventionModel"),
                        "primary_purpose": design_module.get("designInfo", {}).get("primaryPurpose"),
                        "masking": design_module.get("designInfo", {}).get("maskingInfo", {}).get("masking"),
                    },

                    # NEW: Outcome measures (from protocol)
                    "outcome_measures": {
                        "primary": [
                            {
                                "measure": om.get("measure"),
                                "description": om.get("description"),
                                "time_frame": om.get("timeFrame"),
                            }
                            for om in outcomes_module.get("primaryOutcomes", [])
                        ],
                        "secondary": [
                            {
                                "measure": om.get("measure"),
                                "description": om.get("description"),
                                "time_frame": om.get("timeFrame"),
                            }
                            for om in outcomes_module.get("secondaryOutcomes", [])
                        ],
                    },

                    # NEW: Results data (when available)
                    "has_results": bool(results_section),
                    "results": None,
                }

                # Extract results if available (simplified to reduce token usage)
                if results_section:
                    # Extract enrollment summary from participant flow
                    enrollment_summary = None
                    if participant_flow_module:
                        groups = participant_flow_module.get("groups", [])
                        periods = participant_flow_module.get("periods", [])

                        # Get enrollment numbers from first milestone (STARTED)
                        enrollment_data = {}
                        if periods and len(periods) > 0:
                            first_period = periods[0]
                            milestones = first_period.get("milestones", [])
                            for milestone in milestones:
                                if milestone.get("type") == "STARTED":
                                    for achievement in milestone.get("achievements", []):
                                        group_id = achievement.get("groupId")
                                        num_subjects = achievement.get("numSubjects")
                                        # Find group title
                                        group_title = next((g.get("title") for g in groups if g.get("id") == group_id), group_id)
                                        enrollment_data[group_title] = num_subjects

                        enrollment_summary = {
                            "recruitment_details": participant_flow_module.get("recruitmentDetails"),
                            "enrollment_by_group": enrollment_data
                        }

                    # Extract key baseline demographics only
                    baseline_summary = None
                    if baseline_module:
                        measures = baseline_module.get("measures", [])
                        demographics = {}

                        # Extract only age, sex, race, ethnicity (first 4 measures typically)
                        for measure in measures[:4]:
                            title = measure.get("title", "")
                            if any(keyword in title.lower() for keyword in ["age", "sex", "gender", "race", "ethnicity"]):
                                demographics[title] = {
                                    "param_type": measure.get("paramType"),
                                    "unit": measure.get("unitOfMeasure")
                                }

                        baseline_summary = {
                            "population_description": baseline_module.get("populationDescription"),
                            "key_demographics": list(demographics.keys())
                        }

                    # Simplified outcome measures - just key results
                    outcomes_summary = []
                    for om in outcome_measures_module.get("outcomeMeasures", [])[:10]:  # Limit to first 10
                        outcome = {
                            "type": om.get("type"),
                            "title": om.get("title"),
                            "time_frame": om.get("timeFrame"),
                            "param_type": om.get("paramType"),
                            "unit": om.get("unitOfMeasure"),
                        }

                        # Extract first statistical analysis if available
                        analyses = om.get("analyses", [])
                        if analyses:
                            first_analysis = analyses[0]
                            outcome["analysis"] = {
                                "p_value": first_analysis.get("pValue"),
                                "statistical_method": first_analysis.get("statisticalMethod"),
                                "param_value": first_analysis.get("paramValue"),
                                "ci_lower": first_analysis.get("ciLowerLimit"),
                                "ci_upper": first_analysis.get("ciUpperLimit"),
                            }

                        outcomes_summary.append(outcome)

                    # Simplified adverse events - counts and top events
                    adverse_events_summary = None
                    if adverse_events_module:
                        groups = adverse_events_module.get("eventGroups", [])
                        serious_events = adverse_events_module.get("seriousEvents", [])
                        other_events = adverse_events_module.get("otherEvents", [])

                        # Summary counts
                        group_summaries = []
                        for g in groups:
                            group_summaries.append({
                                "group": g.get("title"),
                                "deaths": g.get("deathsNumAffected"),
                                "serious_events": g.get("seriousNumAffected"),
                                "other_events": g.get("otherNumAffected"),
                            })

                        # Top 5 serious events only
                        top_serious = []
                        for se in serious_events[:5]:
                            event = {
                                "term": se.get("term"),
                                "organ_system": se.get("organSystem"),
                            }
                            # Get total affected across all groups
                            stats = se.get("stats", [])
                            if stats:
                                total_affected = sum(s.get("numAffected", 0) for s in stats)
                                event["total_affected"] = total_affected
                            top_serious.append(event)

                        adverse_events_summary = {
                            "time_frame": adverse_events_module.get("timeFrame"),
                            "group_summaries": group_summaries,
                            "top_serious_events": top_serious,
                            "total_serious_events": len(serious_events),
                            "total_other_events": len(other_events),
                        }

                    trial_info["results"] = {
                        "enrollment": enrollment_summary,
                        "baseline": baseline_summary,
                        "outcome_measures": outcomes_summary,
                        "adverse_events": adverse_events_summary,
                    }

                trials.append(trial_info)

            return {
                "success": True,
                "total_count": data.get("totalCount", 0),
                "trials": trials,
                "error": None,
            }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "error": "ClinicalTrials.gov API request timed out after 60 seconds. The service may be slow or unavailable. Please try again.",
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "error": f"ClinicalTrials.gov API error: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "error": f"Unexpected error: {str(e)}",
        }


def _generate_search_variations(term: str) -> List[str]:
    """
    Generate common variations of a search term.

    Handles drug naming conventions:
    - ABC1234 -> ABC-1234, ABC 1234
    - ABC-1234 -> ABC1234, ABC 1234
    - etc.
    """
    import re

    variations = {term}  # Use set to avoid duplicates

    # Pattern: letters followed by numbers (e.g., LNS8801)
    letter_number = re.match(r'^([A-Za-z]+)(\d+)$', term)
    if letter_number:
        prefix, numbers = letter_number.groups()
        variations.add(f"{prefix}-{numbers}")  # LNS-8801
        variations.add(f"{prefix} {numbers}")  # LNS 8801

    # Pattern: letters-numbers (e.g., LNS-8801)
    hyphen_split = re.match(r'^([A-Za-z]+)-(\d+)$', term)
    if hyphen_split:
        prefix, numbers = hyphen_split.groups()
        variations.add(f"{prefix}{numbers}")   # LNS8801
        variations.add(f"{prefix} {numbers}")  # LNS 8801

    # Pattern: letters space numbers (e.g., LNS 8801)
    space_split = re.match(r'^([A-Za-z]+)\s+(\d+)$', term)
    if space_split:
        prefix, numbers = space_split.groups()
        variations.add(f"{prefix}{numbers}")   # LNS8801
        variations.add(f"{prefix}-{numbers}")  # LNS-8801

    return list(variations)


async def smart_search_clinical_trials(
    search_term: str,
    location: Optional[str] = None,
    status: Optional[List[str]] = None,
    phase: Optional[List[str]] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Smart multi-strategy search for clinical trials.

    Instead of relying on the LLM to choose the right field (query, condition, intervention),
    this function tries multiple search strategies in PARALLEL and returns the best results.

    Strategies (run concurrently):
    1. Free-text query (searches all fields)
    2. Intervention field (for drug names)
    3. Condition field (for disease names)
    4. Query variations (with/without hyphens, spaces)

    Args:
        search_term: The main search term (drug name, condition, target, etc.)
        location: Optional geographic location filter
        status: Optional list of recruitment statuses
        phase: Optional list of trial phases
        max_results: Maximum results to return (default: 5)

    Returns:
        Dictionary containing:
            - success (bool): Whether any strategy found results
            - total_count (int): Total trials found by best strategy
            - trials (list): List of trial data
            - strategy_used (str): Which search strategy worked best
            - all_strategies (dict): Results count from each strategy tried
            - error (str): Error message if all strategies failed
    """

    # Generate search term variations
    variations = _generate_search_variations(search_term)

    # Build list of search tasks (strategies to try in parallel)
    search_tasks = []
    strategy_names = []

    # Strategy 1: Free-text query (primary - most flexible)
    search_tasks.append(
        search_clinical_trials(
            query=search_term,
            location=location,
            status=status,
            phase=phase,
            max_results=max_results
        )
    )
    strategy_names.append(f"query:{search_term}")

    # Strategy 2: Intervention field (for drug names)
    search_tasks.append(
        search_clinical_trials(
            intervention=search_term,
            location=location,
            status=status,
            phase=phase,
            max_results=max_results
        )
    )
    strategy_names.append(f"intervention:{search_term}")

    # Strategy 3: Condition field (for disease names)
    search_tasks.append(
        search_clinical_trials(
            condition=search_term,
            location=location,
            status=status,
            phase=phase,
            max_results=max_results
        )
    )
    strategy_names.append(f"condition:{search_term}")

    # Strategy 4+: Try variations (hyphenated, spaced, etc.)
    for variation in variations:
        if variation != search_term:  # Don't duplicate the original
            search_tasks.append(
                search_clinical_trials(
                    query=variation,
                    location=location,
                    status=status,
                    phase=phase,
                    max_results=max_results
                )
            )
            strategy_names.append(f"query:{variation}")

    # Execute all searches in parallel
    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Collect all successful results with their strategies
    all_strategies = {}
    successful_results = []  # List of (priority_index, strategy, result)

    for i, result in enumerate(results):
        strategy = strategy_names[i]

        # Handle exceptions from gather
        if isinstance(result, Exception):
            all_strategies[strategy] = {"count": 0, "error": str(result)}
            continue

        # Handle failed searches
        if not result.get("success"):
            all_strategies[strategy] = {"count": 0, "error": result.get("error")}
            continue

        count = result.get("total_count", 0)
        all_strategies[strategy] = {"count": count}

        if count > 0:
            successful_results.append((i, strategy, result))

    # Selection logic: prioritize RELEVANCE over quantity
    # Priority order: exact query > intervention > condition > variations
    # Only fall back to variations if primary strategies find nothing
    best_result = None
    best_strategy = None

    if successful_results:
        # Sort by priority index (lower = higher priority)
        successful_results.sort(key=lambda x: x[0])

        # Primary strategies are indices 0, 1, 2 (query, intervention, condition)
        primary_results = [r for r in successful_results if r[0] < 3]

        if primary_results:
            # Use first successful primary strategy (by priority)
            _, best_strategy, best_result = primary_results[0]
        else:
            # Fall back to variations only if no primary strategy worked
            _, best_strategy, best_result = successful_results[0]

    # Return best result with metadata
    if best_result:
        return {
            "success": True,
            "total_count": best_result["total_count"],
            "trials": best_result["trials"],
            "strategy_used": best_strategy,
            "all_strategies": all_strategies,
            "error": None
        }
    else:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "strategy_used": None,
            "all_strategies": all_strategies,
            "error": f"No trials found for '{search_term}' using any search strategy"
        }


def compare_eligibility(patient_data: Dict[str, Any], trial_eligibility: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare patient data against trial eligibility criteria.

    Args:
        patient_data: Dictionary containing patient information
            - age (int): Patient age
            - sex (str): Patient sex ('MALE', 'FEMALE', 'ALL')
            - conditions (list): List of patient conditions
        trial_eligibility: Trial eligibility dictionary from search results

    Returns:
        Dictionary containing:
            - eligible (bool): Whether patient meets basic criteria
            - matches (list): List of matching criteria
            - mismatches (list): List of non-matching criteria
    """
    matches = []
    mismatches = []

    # Check age eligibility
    patient_age = patient_data.get("age")
    min_age = trial_eligibility.get("min_age")
    max_age = trial_eligibility.get("max_age")

    if patient_age and min_age:
        try:
            # Parse age strings (e.g., "18 Years", "N/A")
            if min_age != "N/A":
                min_age_num = int(min_age.split()[0])
                if patient_age >= min_age_num:
                    matches.append(f"Age meets minimum requirement ({min_age})")
                else:
                    mismatches.append(f"Age below minimum requirement ({min_age})")
        except (ValueError, IndexError):
            pass

    if patient_age and max_age:
        try:
            if max_age != "N/A":
                max_age_num = int(max_age.split()[0])
                if patient_age <= max_age_num:
                    matches.append(f"Age meets maximum requirement ({max_age})")
                else:
                    mismatches.append(f"Age exceeds maximum requirement ({max_age})")
        except (ValueError, IndexError):
            pass

    # Check sex eligibility
    patient_sex = patient_data.get("sex", "").upper()
    trial_sex = trial_eligibility.get("sex", "ALL").upper()

    if trial_sex == "ALL" or patient_sex == trial_sex:
        matches.append(f"Sex matches eligibility criteria ({trial_sex})")
    else:
        mismatches.append(f"Sex does not match ({trial_sex} required)")

    # Check healthy volunteers
    is_healthy = patient_data.get("is_healthy", False)
    accepts_healthy = trial_eligibility.get("healthy_volunteers", "No") == "Yes"

    if not is_healthy or accepts_healthy:
        matches.append("Patient status matches trial requirements")
    else:
        mismatches.append("Trial does not accept healthy volunteers")

    # Determine overall eligibility (no mismatches = eligible)
    eligible = len(mismatches) == 0

    return {
        "eligible": eligible,
        "matches": matches,
        "mismatches": mismatches,
    }
