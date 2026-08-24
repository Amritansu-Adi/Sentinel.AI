"""
SentinelAI — python-detection service (Task 3.3: synthetic company knowledge base)

Scope boundary (per project.md Task 3.3): this is fake seed data only, used
to give `vector_detector.py` something realistic to index and query against.
None of this describes a real company, project, or person. Field names
mirror project.md §4's `company_knowledge` Mongo schema
(doc_id/title/classification/content) so this data could later be loaded
into that collection unchanged if Amritansu wants persistence beyond the
FAISS index — that wiring is NOT part of this task (retrieval only).
"""

from typing import TypedDict


class CompanyDoc(TypedDict):
    doc_id: str
    title: str
    classification: str  # CONFIDENTIAL | INTERNAL | PUBLIC (per project.md §4)
    content: str


# 10 synthetic docs (8 original + 2 added in Task 7.4) — deliberately
# varied classification levels so `search_company_context` callers
# (categorizer + two-tier action policy) can distinguish CONFIDENTIAL
# hits (strict-block tier) from INTERNAL ones (flag-and-allow tier).
# Content is short (1-3 sentences) since embedding quality for this task
# only needs to be "good enough to retrieve the right doc for an
# obviously-related query", not production-grade semantic search.
COMPANY_DOCS: list[CompanyDoc] = [
    {
        "doc_id": "proj-aurora",
        "title": "Project Aurora — Q3 Roadmap",
        "classification": "CONFIDENTIAL",
        "content": (
            "Project Aurora is the codename for our unreleased next-generation "
            "battery management firmware, targeting a 22% efficiency gain over "
            "the current production line. Launch is planned for Q3, pending "
            "certification from the regulatory compliance team."
        ),
    },
    {
        "doc_id": "proj-nightingale",
        "title": "Project Nightingale — Acquisition Target Brief",
        "classification": "CONFIDENTIAL",
        "content": (
            "Project Nightingale refers to the confidential due-diligence "
            "review of a potential acquisition target in the healthcare "
            "analytics space. Deal terms and valuation figures are restricted "
            "to the executive team and legal counsel until signing."
        ),
    },
    {
        "doc_id": "infra-topology",
        "title": "Internal Network Topology Overview",
        "classification": "CONFIDENTIAL",
        "content": (
            "This document maps the internal production network topology, "
            "including VPC subnet ranges, the bastion host addressing scheme, "
            "and the internal DNS zone used by the platform team. Distribution "
            "outside engineering is prohibited."
        ),
    },
    {
        "doc_id": "hr-comp-bands",
        "title": "2026 Compensation Band Structure",
        "classification": "CONFIDENTIAL",
        "content": (
            "This document defines the internal compensation bands by level "
            "and region for the current fiscal year, including base salary "
            "ranges, equity grant guidelines, and bonus targets. Restricted to "
            "HR and people managers."
        ),
    },
    {
        "doc_id": "eng-onboarding",
        "title": "Engineering Onboarding Guide",
        "classification": "INTERNAL",
        "content": (
            "This guide walks new engineering hires through repository access "
            "requests, local development environment setup, and the standard "
            "code review process. It links to the team's style guide and CI "
            "pipeline documentation."
        ),
    },
    {
        "doc_id": "brand-voice",
        "title": "Brand Voice & Tone Guidelines",
        "classification": "INTERNAL",
        "content": (
            "This guide describes the company's preferred tone across "
            "marketing copy, support responses, and product UI text — "
            "friendly, direct, and free of jargon. Used by the content and "
            "marketing teams."
        ),
    },
    {
        "doc_id": "product-faq",
        "title": "Public Product FAQ",
        "classification": "PUBLIC",
        "content": (
            "Frequently asked questions covering account setup, billing "
            "cycles, and how to contact customer support. This content is "
            "already published on the company's public help center."
        ),
    },
    {
        "doc_id": "press-kit",
        "title": "Company Press Kit Summary",
        "classification": "PUBLIC",
        "content": (
            "A summary of the company's public press kit, including founding "
            "year, mission statement, and logo usage guidelines for media "
            "outlets. No restricted information is contained here."
        ),
    },
    {
        # Task 7.4: added per project.md §4 — the seeded set previously had
        # no doc covering "who's on this project / who are we selling to"
        # detail, so a prompt asking about internal team/client structure
        # had nothing CONFIDENTIAL to match against and could slip past
        # Tier 1 of the two-tier action policy undetected.
        "doc_id": "team-roster",
        "title": "Internal Team & Client Roster",
        "classification": "CONFIDENTIAL",
        "content": (
            "This roster lists internal reporting lines across engineering, "
            "sales, and operations, along with named client and partner "
            "accounts currently under contract. Team assignments, account "
            "ownership, and client contact details here are restricted to "
            "internal use and must never be shared outside the company."
        ),
    },
    {
        # Task 7.4: added per project.md §4 — a realistic INTERNAL-tier
        # example distinct from the CONFIDENTIAL docs above, matching
        # Tier 2b (flag-and-allow) of the two-tier action policy rather
        # than Tier 1 (strict block).
        "doc_id": "ai-usage-policy",
        "title": "AI Tool Usage & Data Handling Policy",
        "classification": "INTERNAL",
        "content": (
            "This policy defines what employees may and may not paste into "
            "external AI tools such as ChatGPT, Claude, or Gemini, including "
            "guidance on customer data, credentials, and unreleased product "
            "details. It also explains how SentinelAI's gateway enforces "
            "these rules automatically for company-managed AI access."
        ),
    },
]