"""`child_view()`: the only projection of a Problem that may reach the child (AD-5).

It drops `answer`, `hint` and `solution` from every Part. For `spot_difference` this
also drops the answer regions; the child keeps only `count`.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from hoctap.content.schema import (
    ANSWER_FIELDS,
    CompareView,
    ConnectDotsView,
    CountImageView,
    DotDrawView,
    ExpressionInputView,
    FallbackView,
    GridFillView,
    ImageSelectView,
    MatchView,
    MultipleChoiceView,
    NumberInputView,
    NumberTreeView,
    OrderView,
    ProblemDoc,
    ProblemHeader,
    SpotDifferenceView,
)

ChildPart = Annotated[
    NumberInputView
    | ExpressionInputView
    | CompareView
    | MultipleChoiceView
    | ImageSelectView
    | OrderView
    | NumberTreeView
    | GridFillView
    | MatchView
    | CountImageView
    | DotDrawView
    | ConnectDotsView
    | SpotDifferenceView
    | FallbackView,
    Field(discriminator="type"),
]


class ChildProblemView(ProblemHeader):
    """A ProblemDoc without Answer Keys, Hints or Solutions."""

    parts: list[ChildPart] = Field(min_length=1)

    @model_validator(mode="after")
    def _cross_refs(self) -> ChildProblemView:
        self._check_header(list(self.parts))
        return self


def child_view(doc: ProblemDoc) -> ChildProblemView:
    data = doc.model_dump(mode="json")
    for part in data["parts"]:
        for field in ANSWER_FIELDS:
            part.pop(field, None)
    return ChildProblemView.model_validate(data)
