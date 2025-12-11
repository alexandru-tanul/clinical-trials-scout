"""
Clinical Trial Scout Service

This module provides functionality to search and compare clinical trials
from ClinicalTrials.gov API v2.
"""
import aiohttp
from typing import Optional, Dict, List, Any


async def search_clinical_trials(
    query: Optional[str] = None,
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[List[str]] = None,
    phase: Optional[List[str]] = None,
    max_results: int = 10,
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
        max_results: Maximum number of results to return (default: 10, max: 1000)

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
    }

    # Build query.term filter
    query_parts = []
    if query:
        query_parts.append(query)
    if condition:
        query_parts.append(f"AREA[Condition]{condition}")
    if intervention:
        query_parts.append(f"AREA[Intervention]{intervention}")
    if location:
        query_parts.append(f"AREA[Location]{location}")

    if query_parts:
        params["query.term"] = " AND ".join(query_parts)

    # Add status filter
    if status:
        params["filter.overallStatus"] = ",".join(status)

    # Add phase filter
    if phase:
        params["filter.phase"] = ",".join(phase)

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

            # Extract relevant trial information
            trials = []
            for study in data.get("studies", []):
                protocol_section = study.get("protocolSection", {})
                identification_module = protocol_section.get("identificationModule", {})
                status_module = protocol_section.get("statusModule", {})
                description_module = protocol_section.get("descriptionModule", {})
                conditions_module = protocol_section.get("conditionsModule", {})
                design_module = protocol_section.get("designModule", {})
                eligibility_module = protocol_section.get("eligibilityModule", {})
                contacts_module = protocol_section.get("contactsModule", {})

                trial_info = {
                    "nct_id": identification_module.get("nctId"),
                    "title": identification_module.get("officialTitle") or identification_module.get("briefTitle"),
                    "status": status_module.get("overallStatus"),
                    "phase": design_module.get("phases", []),
                    "brief_summary": description_module.get("briefSummary"),
                    "conditions": conditions_module.get("conditions", []),
                    "interventions": [
                        {
                            "type": intervention.get("type"),
                            "name": intervention.get("name"),
                        }
                        for intervention in protocol_section.get("armsInterventionsModule", {}).get("interventions", [])
                    ],
                    "eligibility": {
                        "criteria": eligibility_module.get("eligibilityCriteria"),
                        "sex": eligibility_module.get("sex"),
                        "min_age": eligibility_module.get("minimumAge"),
                        "max_age": eligibility_module.get("maximumAge"),
                        "healthy_volunteers": eligibility_module.get("healthyVolunteers"),
                    },
                    "locations": [
                        {
                            "facility": location.get("facility"),
                            "city": location.get("city"),
                            "state": location.get("state"),
                            "country": location.get("country"),
                        }
                        for location in contacts_module.get("locations", [])
                    ],
                    "url": f"https://clinicaltrials.gov/study/{identification_module.get('nctId')}",
                    "start_date": status_module.get("startDateStruct", {}).get("date"),
                    "completion_date": status_module.get("completionDateStruct", {}).get("date"),
                }
                trials.append(trial_info)

            return {
                "success": True,
                "total_count": data.get("totalCount", 0),
                "trials": trials,
                "error": None,
            }

    except aiohttp.ClientError as e:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "error": str(e),
        }
    except Exception as e:
        return {
            "success": False,
            "total_count": 0,
            "trials": [],
            "error": f"Unexpected error: {str(e)}",
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
