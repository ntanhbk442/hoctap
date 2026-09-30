"""Story 1.4: the ProblemDoc v1 contract, `child_view()` and the exported JSON Schema.

One test per row of the I/O matrix, plus one parametrised round-trip and leak test per
Problem Type fixture (`tests/fixtures/problemdocs/<type>.json`). No model calls.
"""

from __future__ import annotations

import copy
import json
import unicodedata
from pathlib import Path
from typing import Any

import anthropic
import pytest
from pydantic import ValidationError

from hoctap.cli import DEFAULT_SCHEMA_OUT
from hoctap.cli import main as cli_main
from hoctap.content import PROBLEM_TYPES, ChildProblemView, ProblemDoc, child_view
from hoctap.content.schema import answer_map, problemdoc_json_schema

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"


def load(problem_type: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{problem_type}.json").read_text(encoding="utf-8"))


def walk(node: Any):
    """Yield every (key, value) pair of every dict in a JSON tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in strings(v)]
    return []


# --------------------------------------------------------------------------- per type


def test_one_fixture_per_problem_type() -> None:
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(PROBLEM_TYPES)
    assert len(PROBLEM_TYPES) == 14
    for problem_type in PROBLEM_TYPES:
        assert problem_type in {part["type"] for part in load(problem_type)["parts"]}


@pytest.mark.parametrize("problem_type", PROBLEM_TYPES)
def test_fixture_parses_and_round_trips(problem_type: str) -> None:
    raw = load(problem_type)
    doc = ProblemDoc.model_validate(raw)
    # Lossless: dumping gives back exactly the fixture, and JSON re-parses to an equal model.
    assert doc.model_dump(mode="json", exclude_unset=True) == raw
    again = ProblemDoc.model_validate_json(doc.model_dump_json())
    assert again == doc
    assert again.model_dump_json() == doc.model_dump_json()


@pytest.mark.parametrize("problem_type", PROBLEM_TYPES)
def test_child_view_leaks_no_answer(problem_type: str) -> None:
    raw = load(problem_type)
    doc = ProblemDoc.model_validate(raw)
    view = child_view(doc)
    assert isinstance(view, ChildProblemView)
    data = view.model_dump(mode="json")
    text = view.model_dump_json()

    secret_fields = {"answer", "hint", "solution"}
    # No answer-bearing field anywhere, at any depth, nor on any Part.
    assert not secret_fields & {key for key, _ in walk(data)}
    for part_raw, full, part_view in zip(raw["parts"], doc.parts, data["parts"], strict=True):
        assert not secret_fields & set(part_view)
        # An exact projection: nothing else is dropped, added or changed.
        assert part_view == full.model_dump(mode="json", exclude=secret_fields)
        # Hint and Solution text never appear.
        solution = part_raw["solution"]
        for secret in [part_raw["hint"], *solution["steps"], solution["final"]]:
            assert secret not in text
        if part_raw["type"] == "spot_difference":
            # This Part's answer regions (keys and boxes) are gone; only `count` stays.
            view_values = [v for _, v in walk(part_view)]
            for region in part_raw["answer"]["regions"]:
                assert region["region_key"] not in strings(part_view)
                assert region["bbox"] not in view_values
            assert part_view["count"] == len(part_raw["answer"]["regions"])


def test_child_view_keeps_given_values_but_not_slot_values() -> None:
    view = child_view(ProblemDoc.model_validate(load("number_tree")))
    nodes = {n.node_key: n.given for n in view.parts[0].nodes}
    assert nodes == {"top": "5", "l": "2", "r": None}


# --------------------------------------------------------------------------- matrix rows


def test_unknown_type_names_the_discriminator() -> None:
    raw = load("number_input")
    raw["parts"][0]["type"] = "essay"
    with pytest.raises(ValidationError) as exc:
        ProblemDoc.model_validate(raw)
    message = str(exc.value)
    assert "'type'" in message and "essay" in message


@pytest.mark.parametrize(
    ("problem_type", "mutate"),
    [
        ("number_input", lambda p: p["answer"].pop(0)),
        ("number_input", lambda p: p["answer"].append({"key": "s9", "value": "1"})),
        ("number_input", lambda p: p["answer"].append({"key": "s1", "value": "5"})),  # dup
        ("compare", lambda p: p["answer"].pop(1)),
        ("compare", lambda p: p["answer"].append({"key": "r1", "value": "<"})),  # dup
        ("number_tree", lambda p: p["answer"].append({"key": "l", "value": "2"})),
        ("grid_fill", lambda p: p["answer"].pop(2)),
        ("count_image", lambda p: p["answer"].append({"key": "meo", "value": "1"})),
        ("dot_draw", lambda p: p["answer"].pop(1)),
        ("order", lambda p: p["answer"]["order"].pop()),
        ("match", lambda p: p["answer"]["pairs"].pop()),
        ("match", lambda p: p["answer"]["pairs"].append(["l9", "r4"])),
        ("multiple_choice", lambda p: p["answer"].update({"selected": ["z"]})),
        ("multiple_choice", lambda p: p["answer"].update({"selected": ["a", "b"]})),
        ("image_select", lambda p: p["answer"].update({"selected": []})),
        ("connect_dots", lambda p: p["answer"].update({"sequence": [1, 2, 3, 4, 5, 5]})),
        ("connect_dots", lambda p: p["answer"]["sequence"].append(7)),
        ("spot_difference", lambda p: p["answer"]["regions"].pop()),
    ],
)
def test_answer_slot_mismatch_names_the_part(problem_type: str, mutate) -> None:
    raw = load(problem_type)
    part = raw["parts"][0]
    mutate(part)
    with pytest.raises(ValidationError) as exc:
        ProblemDoc.model_validate(raw)
    assert f"part {part['part_key']!r}" in str(exc.value)


@pytest.mark.parametrize(
    ("problem_type", "mutate", "key"),
    [
        ("number_input", lambda p: p["image_keys"].append("ghost"), "ghost"),
        ("count_image", lambda p: p.update({"image_key": "ghost"}), "ghost"),
        ("fallback", lambda p: p.update({"image_key": "ghost"}), "ghost"),
        ("spot_difference", lambda p: p.update({"image_right": "ghost"}), "ghost"),
        ("multiple_choice", lambda p: p["options"][1].update({"image_key": "ghost"}), "ghost"),
    ],
)
def test_dangling_image_ref_names_the_key(problem_type: str, mutate, key: str) -> None:
    raw = load(problem_type)
    mutate(raw["parts"][0])
    with pytest.raises(ValidationError) as exc:
        ProblemDoc.model_validate(raw)
    assert repr(key) in str(exc.value)


def test_dangling_structural_refs_are_rejected() -> None:
    raw = load("number_tree")
    raw["parts"][0]["nodes"][1]["parent_key"] = "ghost"
    with pytest.raises(ValidationError, match="'ghost'"):
        ProblemDoc.model_validate(raw)
    raw = load("number_input")
    raw["parts"][0]["template"] = "3 + 2 = [[s2]]"
    with pytest.raises(ValidationError, match="template markers"):
        ProblemDoc.model_validate(raw)


@pytest.mark.parametrize(
    ("problem_type", "mutate"),
    [
        ("number_input", lambda d: d["parts"][1].update({"part_key": "a"})),
        ("compare", lambda d: d["parts"][0]["rows"][1].update({"slot_key": "r1"})),
        ("multiple_choice", lambda d: d["parts"][0]["options"][1].update({"option_key": "a"})),
        ("order", lambda d: d["parts"][0]["items"][1].update({"item_key": "n6"})),
        ("number_tree", lambda d: d["parts"][0]["nodes"][1].update({"node_key": "top"})),
        ("image_select", lambda d: d["parts"][0]["regions"][1].update({"region_key": "t1"})),
        ("multiple_choice", lambda d: d["images"][1].update({"image_key": "hinh-a"})),
    ],
)
def test_duplicate_key_is_rejected(problem_type: str, mutate) -> None:
    raw = load(problem_type)
    mutate(raw)
    with pytest.raises(ValidationError, match="duplicate"):
        ProblemDoc.model_validate(raw)


@pytest.mark.parametrize("bad_key", ["A", "-a", "a.b", "a" * 17, ""])
def test_key_pattern_is_enforced(bad_key: str) -> None:
    raw = load("compare")
    raw["parts"][0]["part_key"] = bad_key
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


@pytest.mark.parametrize(
    "bbox",
    [
        [0.5, 0.1, 0.5, 0.3],  # x0 == x1
        [0.6, 0.1, 0.5, 0.3],  # x0 > x1
        [0.1, 0.4, 0.5, 0.3],  # y0 > y1
        [0.1, 0.1, 1.2, 0.3],  # > 1
        [-0.1, 0.1, 0.5, 0.3],  # < 0
        [0.1, 0.1, 0.5],  # not 4 numbers
    ],
)
def test_bad_bbox_is_rejected(bbox: list[float]) -> None:
    for where in ("source_pages", "images"):
        raw = load("count_image")
        raw[where][0]["bbox"] = bbox
        with pytest.raises(ValidationError):
            ProblemDoc.model_validate(raw)
    raw = load("image_select")
    raw["parts"][0]["regions"][0]["bbox"] = bbox
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


@pytest.mark.parametrize(
    "problem_id",
    [
        "toan1-2020-q1.tuan-5.tiet-2.bai-2",
        "toan1-2020-q2.tuan-5.tiet-2.bai-1",
        "tuan-5.tiet-2.bai-1",
        "toan1-2020-q1/tuan-5/tiet-2/bai-1",
    ],
)
def test_wrong_problem_id_is_rejected(problem_id: str) -> None:
    raw = load("number_input")
    raw["problem_id"] = problem_id
    with pytest.raises(ValidationError, match="problem_id"):
        ProblemDoc.model_validate(raw)


def test_nfd_text_is_stored_as_nfc() -> None:
    raw = load("number_input")
    nfd = unicodedata.normalize("NFD", "Tính nhẩm rồi điền số:")
    assert nfd != unicodedata.normalize("NFC", nfd)
    raw["instruction"] = nfd
    raw["parts"][0]["hint"] = unicodedata.normalize("NFD", raw["parts"][0]["hint"])
    raw["parts"][0]["solution"]["steps"] = [
        unicodedata.normalize("NFD", s) for s in raw["parts"][0]["solution"]["steps"]
    ]
    doc = ProblemDoc.model_validate(raw)
    assert doc.instruction == "Tính nhẩm rồi điền số:"
    assert unicodedata.is_normalized("NFC", doc.parts[0].hint)
    assert all(unicodedata.is_normalized("NFC", s) for s in doc.parts[0].solution.steps)
    assert unicodedata.is_normalized("NFC", doc.model_dump_json())


def test_answer_bearing_fields_are_required_and_non_empty() -> None:
    for mutate in (
        lambda p: p.pop("hint"),
        lambda p: p.update({"hint": "  "}),
        lambda p: p.update({"solution": {"steps": [], "final": "5"}}),
        lambda p: p.pop("answer"),
        lambda p: p["answer"][0].update({"value": "năm"}),  # not a numeric string
        lambda p: p["answer"][0].update({"extra": "x"}),  # entries forbid extra fields
        lambda p: p.update({"answer": {"s1": "5"}}),  # the old dict shape
    ):
        raw = load("number_input")
        mutate(raw["parts"][0])
        with pytest.raises(ValidationError):
            ProblemDoc.model_validate(raw)


def test_unknown_fields_and_empty_parts_are_rejected() -> None:
    raw = load("compare")
    raw["parts"][0]["answer_key"] = "x"
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)
    raw = load("compare")
    raw["parts"] = []
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


def test_compare_values_are_limited() -> None:
    raw = load("compare")
    raw["parts"][0]["answer"][0]["value"] = "≤"
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


@pytest.mark.parametrize(
    ("problem_type", "expected"),
    [
        ("number_input", {"s1": "5"}),
        ("compare", {"r1": "<", "r2": ">", "r3": "="}),
        ("number_tree", {"r": "3"}),
        ("grid_fill", {"r0c1": "2", "r0c3": "4", "r1c2": "7"}),
        ("count_image", {"ga": "7", "vit": "3"}),
        ("dot_draw", {"b1": "4", "b2": "6"}),
    ],
)
def test_answer_map(problem_type: str, expected: dict[str, str]) -> None:
    doc = ProblemDoc.model_validate(load(problem_type))
    assert answer_map(doc.parts[0]) == expected


def test_answer_map_rejects_unkeyed_answers() -> None:
    doc = ProblemDoc.model_validate(load("order"))
    with pytest.raises(TypeError):
        answer_map(doc.parts[0])


def test_fallback_answer_is_null() -> None:
    raw = load("fallback")
    raw["parts"][0]["answer"] = {"x": "1"}
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


def test_fixtures_do_not_share_mutable_state() -> None:
    raw = load("match")
    doc = ProblemDoc.model_validate(copy.deepcopy(raw))
    child_view(doc)
    assert doc.model_dump(mode="json", exclude_unset=True) == raw


# --------------------------------------------------------------------------- schema


def _count(schema: Any) -> tuple[int, int]:
    """(optional properties, anyOf unions) over the whole schema, each $def counted once."""
    optional = unions = 0
    if isinstance(schema, dict):
        if isinstance(schema.get("properties"), dict):
            optional += len(set(schema["properties"]) - set(schema.get("required", [])))
        if "anyOf" in schema:
            unions += 1
        for value in schema.values():
            o, u = _count(value)
            optional, unions = optional + o, unions + u
    elif isinstance(schema, list):
        for value in schema:
            o, u = _count(value)
            optional, unions = optional + o, unions + u
    return optional, unions


def test_transform_schema_accepts_problemdoc() -> None:
    schema = anthropic.transform_schema(ProblemDoc)
    defs = schema["$defs"]
    # The discriminator survives as an enum (transform_schema drops `const`).
    tags = {
        tuple(d["properties"]["type"].get("enum", ()))
        for d in defs.values()
        if "type" in d.get("properties", {})
    }
    assert tags == {(t,) for t in PROBLEM_TYPES}
    assert schema["properties"]["schema_version"]["enum"] == ["v1"]
    # Pinned so a change is noticed against the structured-output limits (24 optional,
    # 16 unions): 10 optional = 7 `?` fields + FallbackPart.answer + DotBox.given + expression mode;
    # 8 unions = the 7 nullable `?` fields + the Part union. Recorded in the spec.
    assert _count(schema) == (10, 8)


def _collapsed(node: Any, defs: dict[str, Any]) -> bool:
    """True if a transformed schema node can only hold an empty object (or has no items)."""
    if "$ref" in node:
        return _collapsed(defs[node["$ref"].split("/")[-1]], defs)
    if "anyOf" in node:
        return any(_collapsed(v, defs) for v in node["anyOf"] if v.get("type") != "null")
    if node.get("type") == "object":
        props = node.get("properties") or {}
        return not props or any(_collapsed(v, defs) for v in props.values())
    if node.get("type") == "array":
        return "items" not in node or _collapsed(node["items"], defs)
    return False


def test_transform_schema_keeps_every_answer_shape() -> None:
    schema = anthropic.transform_schema(ProblemDoc)
    defs = schema["$defs"]
    part_defs = [d for d in defs.values() if "enum" in d.get("properties", {}).get("type", {})]
    assert len(part_defs) == len(PROBLEM_TYPES)
    for part in part_defs:
        tag = part["properties"]["type"]["enum"][0]
        answer = part["properties"]["answer"]
        if tag == "fallback":
            assert answer["type"] == "null"
        else:
            assert not _collapsed(answer, defs), tag


def test_export_schema_writes_the_committed_file(tmp_path: Path) -> None:
    out = tmp_path / "problemdoc.schema.json"
    assert cli_main(["export-schema", "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == problemdoc_json_schema()
    # The committed copy must be regenerated whenever the model changes.
    committed = json.loads(DEFAULT_SCHEMA_OUT.read_text(encoding="utf-8"))
    assert committed == written


# --------------------------------------------------------------------------- review rules


def rejects(raw: dict[str, Any], match: str | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        ProblemDoc.model_validate(raw)


def test_number_tree_with_every_node_given_is_rejected() -> None:
    raw = load("number_tree")
    part = raw["parts"][0]
    part["nodes"][2]["given"] = "3"
    part["answer"] = []
    rejects(raw, "Answer Slot")


def test_grid_fill_with_every_cell_given_is_rejected() -> None:
    raw = load("grid_fill")
    part = raw["parts"][0]
    for row in part["cells"]:
        for cell in row:
            cell["given"] = "1"
    part["answer"] = []
    rejects(raw, "at least one cell must be empty")


def test_duplicate_slot_marker_is_rejected() -> None:
    raw = load("number_input")
    raw["parts"][0]["template"] = "[[s1]] + 2 = [[s1]]"
    rejects(raw, "duplicate")


@pytest.mark.parametrize(
    ("pairs", "match"),
    [
        ([["l1", "r5"], ["l1", "r4"], ["l2", "r4"], ["l3", "r5"]], "duplicate"),
        ([["l1", "r5"], ["l2", "r9"], ["l3", "r5"]], "unknown right"),
    ],
)
def test_bad_match_pairs_are_rejected(pairs: list[list[str]], match: str) -> None:
    raw = load("match")
    raw["parts"][0]["answer"]["pairs"] = pairs
    rejects(raw, match)


def test_parent_key_cycle_is_rejected() -> None:
    raw = load("number_tree")
    raw["parts"][0]["nodes"][0]["parent_key"] = "l"
    rejects(raw, "cycle")


def test_grid_rows_must_match_cells() -> None:
    raw = load("grid_fill")
    raw["parts"][0]["rows"] = 3
    rejects(raw, "rows")


def test_option_needs_text_or_image() -> None:
    raw = load("multiple_choice")
    del raw["parts"][0]["options"][0]["text"]
    rejects(raw, "needs text or image_key")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("concept_ids", ["x.bad"]),
        ("concept_ids", ["g1.so-sanh-so", "g1.so-sanh-so"]),
        ("concept_proposals", ["Đếm", "Đếm"]),
    ],
)
def test_bad_concepts_are_rejected(field: str, value: list[str]) -> None:
    raw = load("number_input")
    raw[field] = value
    rejects(raw)


def test_concepts_may_both_be_empty() -> None:
    raw = load("fallback")
    assert raw["concept_ids"] == [] and raw["concept_proposals"] == []
    ProblemDoc.model_validate(raw)


@pytest.mark.parametrize(
    ("problem_type", "mutate"),
    [
        ("connect_dots", lambda p: p["dots"][1].update({"n": 1})),
        ("count_image", lambda p: p["slots"][1].update({"slot_key": "ga"})),
        ("dot_draw", lambda p: p["boxes"][1].update({"slot_key": "b1"})),
        ("match", lambda p: p["left"][1].update({"item_key": "l1"})),
        ("match", lambda p: p["right"][1].update({"item_key": "r4"})),
        ("spot_difference", lambda p: p["answer"]["regions"][1].update({"region_key": "d1"})),
        ("number_input", lambda p: p.update({"image_keys": ["x", "x"]})),
    ],
)
def test_more_duplicate_keys_are_rejected(problem_type: str, mutate) -> None:
    raw = load(problem_type)
    if problem_type == "number_input":
        raw["images"] = [{"image_key": "x", "page": 12, "bbox": [0.1, 0.1, 0.2, 0.2]}]
    mutate(raw["parts"][0])
    rejects(raw, "duplicate")


def test_single_select_with_two_selected_is_rejected() -> None:
    raw = load("image_select")
    raw["parts"][0]["multi"] = False
    rejects(raw, "exactly one")


@pytest.mark.parametrize("value", ["1.000", "05", "-0", "-0,0", "1,", ",5", "1.5", "+3", " 3"])
def test_non_canonical_numbers_are_rejected(value: str) -> None:
    raw = load("number_input")
    raw["parts"][0]["answer"][0]["value"] = value
    rejects(raw)


@pytest.mark.parametrize("value", ["0", "12", "-3", "1,5", "-0,5", "1000"])
def test_canonical_numbers_are_accepted(value: str) -> None:
    raw = load("number_input")
    raw["parts"][0]["answer"][0]["value"] = value
    ProblemDoc.model_validate(raw)


@pytest.mark.parametrize("problem_type", ["count_image", "dot_draw"])
@pytest.mark.parametrize("value", ["-1", "2,5", "07"])
def test_counts_are_non_negative_integers(problem_type: str, value: str) -> None:
    raw = load(problem_type)
    raw["parts"][0]["answer"][0]["value"] = value
    rejects(raw)


def test_dot_draw_answer_below_given_is_rejected() -> None:
    raw = load("dot_draw")
    raw["parts"][0]["boxes"][0]["given"] = 5  # answer is 4
    rejects(raw, "already given")


def test_dot_draw_given_defaults_to_zero_and_is_non_negative() -> None:
    raw = load("dot_draw")
    del raw["parts"][0]["boxes"][0]["given"]
    assert ProblemDoc.model_validate(raw).parts[0].boxes[0].given == 0
    raw["parts"][0]["boxes"][0]["given"] = -1
    rejects(raw)


def test_dot_draw_label_must_not_be_empty() -> None:
    raw = load("dot_draw")
    raw["parts"][0]["boxes"][0]["label"] = " "
    rejects(raw)


def test_non_contiguous_dots_are_rejected() -> None:
    raw = load("connect_dots")
    raw["parts"][0]["dots"][5]["n"] = 7
    raw["parts"][0]["answer"]["sequence"] = [1, 2, 3, 4, 5, 7]
    rejects(raw, "exactly 1..6")


def test_connect_dots_sequence_must_be_ascending() -> None:
    raw = load("connect_dots")
    raw["parts"][0]["answer"]["sequence"] = [2, 1, 3, 4, 5, 6]
    rejects(raw, "in order")


@pytest.mark.parametrize("where", ["dot", "sequence"])
def test_bool_is_not_a_dot_number(where: str) -> None:
    raw = load("connect_dots")
    part = raw["parts"][0]
    if where == "dot":
        part["dots"][0]["n"] = True
    else:
        part["answer"]["sequence"][0] = True
    rejects(raw)


def test_forest_tree_is_rejected() -> None:
    raw = load("number_tree")
    raw["parts"][0]["nodes"][2]["parent_key"] = None
    rejects(raw, "exactly one root")


def test_numeric_order_must_follow_direction() -> None:
    raw = load("order")
    raw["parts"][0]["answer"]["order"] = ["n9", "n6", "n4", "n2"]
    rejects(raw, "not asc")
    raw["parts"][0]["direction"] = "desc"
    ProblemDoc.model_validate(raw)
    raw["parts"][0]["direction"] = "custom"
    raw["parts"][0]["answer"]["order"] = ["n6", "n2", "n9", "n4"]
    ProblemDoc.model_validate(raw)


def test_image_page_must_be_a_source_page() -> None:
    raw = load("count_image")
    raw["images"][0]["page"] = 6
    rejects(raw, "not in source_pages")


def test_spot_difference_needs_two_images() -> None:
    raw = load("spot_difference")
    raw["parts"][0]["image_right"] = "tranh-trai"
    rejects(raw, "must differ")


def test_expression_input_child_view_has_mode_but_no_answer() -> None:
    view = child_view(ProblemDoc.model_validate(load("expression_input")))
    assert [p.mode for p in view.parts] == ["value", "exact"]
    assert "36" not in view.model_dump_json().replace("12 × 3", "")


@pytest.mark.parametrize("value", ["", "3+", "abc", "x" * 101])
def test_expression_input_answer_must_be_an_expression(value: str) -> None:
    raw = load("expression_input")
    raw["parts"][0]["answer"][0]["value"] = value
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)


def test_expression_input_answer_must_cover_slots_and_mode_is_closed() -> None:
    raw = load("expression_input")
    raw["parts"][0]["answer"][0]["key"] = "zz"
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)
    raw = load("expression_input")
    raw["parts"][0]["mode"] = "fuzzy"
    with pytest.raises(ValidationError):
        ProblemDoc.model_validate(raw)
    raw = load("expression_input")
    del raw["parts"][0]["mode"]
    assert ProblemDoc.model_validate(raw).parts[0].mode == "value"
