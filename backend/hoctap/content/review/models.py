"""`content_review_*` tables. Only `hoctap.content.review.service` writes them (AD-2).

- `content_review_concept_proposals`: one row per proposed Concept name per Grade, keyed
  by `proposal_key` (the name NFC-normalised, trimmed, whitespace-collapsed and
  case-folded). `text` is the name as first seen; `problem_count` counts the linked
  Problems. Status starts `proposed`; accepting sets `accepted` and merging `merged`,
  with the target `concept_id` (Story 1.8).
- `content_review_problem_proposals`: which Problem proposes which key.
- `content_review_overrides`: field-level edits over the extracted ProblemDoc, unique on
  (`problem_id`, `part_key` or '' for the top level, `field`). `value_json` is the new
  value, `base_hash` the sha256 of the canonical JSON of the extracted value at save time.
- `content_review_status`: one row per reviewed Problem (`approved_hash`, `hidden`).
- `content_review_error_reports`: parent or child Error Reports, open or resolved.
- `content_review_concepts` / `content_review_problem_concepts`: the curated Concepts
  and their links to Problems (built from accepted or merged proposals).
- `content_review_guide_overrides` / `content_review_guide_status`: Anh's field edits of a
  Concept Guide (unique on `concept_id, field`, with the `base_hash` of the generated field)
  and its approval (`approved_hash`), like Problems (Story 5.1).
- `content_review_spot_check_samples` / `content_review_spot_checks`: each drawn
  spot-check sample (seed, size) and its Problems with the verdict (null | correct |
  wrong), the effective hash the verdict was given for, when it was first judged wrong,
  and a note. Only the latest
  sample counts; older ones are kept for history.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

content_review_concept_proposals = Table(
    "content_review_concept_proposals",
    metadata,
    Column("proposal_key", Text, nullable=False),
    Column("grade", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("problem_count", Integer, nullable=False),
    Column("first_seen", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="proposed"),  # proposed|accepted|merged
    Column("target_concept_id", Text, nullable=True),  # set when accepted or merged
    PrimaryKeyConstraint("proposal_key", "grade", name="pk_content_review_concept_proposals"),
)

content_review_problem_proposals = Table(
    "content_review_problem_proposals",
    metadata,
    Column("problem_id", Text, nullable=False),
    Column("proposal_key", Text, nullable=False),
    Column("grade", Integer, nullable=False),
    PrimaryKeyConstraint(
        "problem_id", "proposal_key", "grade", name="pk_content_review_problem_proposals"
    ),
    Index("ix_content_review_problem_proposals_key", "proposal_key", "grade"),
)

content_review_overrides = Table(
    "content_review_overrides",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("problem_id", Text, nullable=False),
    Column("part_key", Text, nullable=False, server_default=""),  # '' for the top level
    Column("field", Text, nullable=False),
    Column("value_json", Text, nullable=False),
    Column("base_hash", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("problem_id", "part_key", "field", name="uq_content_review_overrides"),
)

content_review_status = Table(
    "content_review_status",
    metadata,
    Column("problem_id", Text, primary_key=True),
    Column("approved_hash", Text, nullable=True),
    Column("hidden", Integer, nullable=False, server_default="0"),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("hidden IN (0, 1)", name="ck_content_review_status_hidden"),
)

content_review_error_reports = Table(
    "content_review_error_reports",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("problem_id", Text, nullable=False),
    Column("kind", Text, nullable=False),  # parent | child
    Column("note", Text, nullable=False, server_default=""),
    Column("status", Text, nullable=False, server_default="open"),  # open | resolved
    Column("created_at", Text, nullable=False),
    Column("resolved_at", Text, nullable=True),
    CheckConstraint("kind IN ('parent', 'child')", name="ck_content_review_error_reports_kind"),
    CheckConstraint(
        "status IN ('open', 'resolved')", name="ck_content_review_error_reports_status"
    ),
    Index("ix_content_review_error_reports_problem", "problem_id", "status"),
)

content_review_concepts = Table(
    "content_review_concepts",
    metadata,
    Column("concept_id", Text, primary_key=True),  # g{grade}.{slug}; never changes
    Column("grade", Integer, nullable=False),
    Column("name_vi", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("grade BETWEEN 1 AND 5", name="ck_content_review_concepts_grade"),
)

content_review_problem_concepts = Table(
    "content_review_problem_concepts",
    metadata,
    Column("problem_id", Text, nullable=False),
    Column("concept_id", Text, nullable=False),
    PrimaryKeyConstraint("problem_id", "concept_id", name="pk_content_review_problem_concepts"),
    Index("ix_content_review_problem_concepts_concept", "concept_id"),
)

content_review_spot_check_samples = Table(
    "content_review_spot_check_samples",
    metadata,
    Column("sample_id", Text, primary_key=True),  # UUIDv7
    Column("seed", Integer, nullable=False),
    Column("size", Integer, nullable=False),
    Column("scope_hash", Text, nullable=False),  # the pilot scope it was drawn from
    Column("created_at", Text, nullable=False),
)

content_review_spot_checks = Table(
    "content_review_spot_checks",
    metadata,
    Column(
        "sample_id",
        Text,
        ForeignKey("content_review_spot_check_samples.sample_id"),
        nullable=False,
    ),
    Column("problem_id", Text, nullable=False),
    Column("position", Integer, nullable=False),  # 1-based order on screen
    Column("verdict", Text, nullable=True),  # null | correct | wrong (the latest)
    Column("verdict_hash", Text, nullable=True),  # the effective hash when judged
    # Set by the first `wrong` verdict and never cleared: the item counts as wrong for
    # good (the gate measures extraction accuracy).
    Column("first_wrong_at", Text, nullable=True),
    Column("note", Text, nullable=False, server_default=""),
    Column("checked_at", Text, nullable=True),
    PrimaryKeyConstraint("sample_id", "problem_id", name="pk_content_review_spot_checks"),
    CheckConstraint(
        "verdict IS NULL OR verdict IN ('correct', 'wrong')",
        name="ck_content_review_spot_checks_verdict",
    ),
)

content_review_guide_overrides = Table(
    "content_review_guide_overrides",
    metadata,
    Column("id", Text, primary_key=True),  # UUIDv7
    Column("concept_id", Text, nullable=False),
    Column("field", Text, nullable=False),  # explanation | example
    Column("value_json", Text, nullable=False),
    Column("base_hash", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("concept_id", "field", name="uq_content_review_guide_overrides"),
)

content_review_guide_status = Table(
    "content_review_guide_status",
    metadata,
    Column("concept_id", Text, primary_key=True),
    Column("approved_hash", Text, nullable=True),
    Column("updated_at", Text, nullable=False),
)
