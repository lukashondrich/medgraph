"""Build patient context strings for agent prompt injection.

The `build_patient_summary()` function creates a formatted string that gets
appended to every agent's system prompt when a patient is loaded, making
all agents patient-aware with zero per-agent code changes.
"""

from __future__ import annotations

from .schemas import PatientProfile


def build_patient_summary(profile: PatientProfile) -> str:
    """Format a PatientProfile into a context block for agent prompts.

    Returns a multi-line string suitable for appending to a system prompt.
    Includes demographics, conditions, medications, allergies, and key labs.
    """
    lines = [
        "--- PATIENT CONTEXT ---",
        f"Name: {profile.name} | Age: {profile.age}{profile.sex}",
        "",
    ]

    # Conditions
    if profile.conditions:
        lines.append("Active conditions:")
        for c in profile.conditions:
            onset = f" (since {c.onset_date})" if c.onset_date else ""
            lines.append(f"  - {c.abbreviation} ({c.patient_friendly_name}){onset}")
    else:
        lines.append("Active conditions: None recorded")
    lines.append("")

    # Medications
    if profile.medications:
        lines.append("Current medications:")
        for m in profile.medications:
            freq = f" {m.frequency}" if m.frequency else ""
            reason = f" [for {m.reason_display}]" if m.reason_display else ""
            lines.append(f"  - {m.short_name}{freq}{reason}")
    else:
        lines.append("Current medications: None recorded")
    lines.append("")

    # Allergies
    if profile.allergies:
        lines.append("Allergies:")
        for a in profile.allergies:
            crit = f" (criticality: {a.criticality})" if a.criticality else ""
            lines.append(f"  - {a.display}{crit}")
        lines.append("")

    # Key labs (show up to 10 most relevant)
    if profile.recent_labs:
        lines.append("Recent lab values:")
        for lab in profile.recent_labs[:10]:
            lines.append(f"  - {lab.short_name}: {lab.value} {lab.unit} ({lab.observed_date})")
        lines.append("")

    lines.append("--- END PATIENT CONTEXT ---")
    return "\n".join(lines)
