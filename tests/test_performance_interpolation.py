from __future__ import annotations

import json
import math
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from itertools import product
from pathlib import Path

from sr22_course_simulator.performance import (
    DerivedPerformanceGrid,
    InvalidCoordinateError,
    OutOfDomainError,
    PerformanceAxis,
    PerformanceTableLoadError,
    QueryDimensionError,
    RectilinearPerformanceTable,
    TableDefinitionError,
    derive_grid,
    load_performance_table,
    multilinear_interpolate,
    performance_table_from_mapping,
)
from sr22_course_simulator.provenance import (
    Applicability,
    ApplicabilityField,
    Coverage,
    EvidenceKind,
    GapKind,
    ModelGap,
    SourceCitation,
    SupportStatus,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "performance"
    / "synthetic_surface.json"
)


def multi_affine(x: float, y: float, z: float) -> float:
    """Function exactly reproducible by multilinear interpolation."""

    return (
        7.0
        + 2.0 * x
        - 3.0 * y
        + 0.5 * z
        + 0.25 * x * y
        - 0.1 * x * z
        + 0.05 * y * z
        + 0.01 * x * y * z
    )


def synthetic_citation() -> SourceCitation:
    return SourceCitation(
        document_title="Synthetic test source",
        revision="1",
        table="unit-test",
        extraction_method="programmatic fixture",
    )


def synthetic_applicability() -> Applicability:
    return Applicability(
        aircraft_model="synthetic-test-only",
        configuration=(ApplicabilityField("fixture", "unit-test"),),
    )


class ProvenanceTests(unittest.TestCase):
    def test_evidence_kind_contains_project_semantic_labels(self) -> None:
        required = {
            "procedure_target",
            "procedure_limit",
            "procedure_nominal",
            "procedure_initial_setting",
            "advisory_reference",
            "poh_table_value",
            "poh_interpolated",
            "physics_derived",
            "calibrated",
            "assumed",
            "unsupported",
        }
        self.assertTrue(required <= {item.value for item in EvidenceKind})

    def test_provenance_collections_are_normalized_and_immutable(self) -> None:
        citation = SourceCitation(
            document_title="Synthetic source",
            transformations=["axis order normalized"],  # type: ignore[arg-type]
            notes=["test only"],  # type: ignore[arg-type]
        )
        applicability = Applicability(
            aircraft_model="Synthetic",
            configuration=[ApplicabilityField("flap", "UP")],  # type: ignore[arg-type]
            conditions=["No operational use"],  # type: ignore[arg-type]
        )
        self.assertEqual(citation.transformations, ("axis order normalized",))
        self.assertEqual(applicability.conditions, ("No operational use",))
        with self.assertRaises(FrozenInstanceError):
            citation.document_title = "changed"  # type: ignore[misc]

    def test_coverage_combines_conservatively_and_retains_metadata(self) -> None:
        gap = ModelGap(
            kind=GapKind.SOURCE_NOT_STATED,
            description="Pitch response is not stated by the source",
            quantity="vertical_speed",
        )
        supported = Coverage(
            SupportStatus.SUPPORTED,
            evidence=(EvidenceKind.POH_TABLE_VALUE,),
        )
        assumed = Coverage(
            SupportStatus.ASSUMPTION_DEPENDENT,
            evidence=(EvidenceKind.POH_TABLE_VALUE, EvidenceKind.ASSUMED),
            gaps=(gap,),
        )
        unsupported = Coverage(
            SupportStatus.UNSUPPORTED,
            evidence=(EvidenceKind.UNSUPPORTED,),
            gaps=(gap,),
        )

        combined = Coverage.combine(supported, assumed, unsupported)

        self.assertIs(combined.status, SupportStatus.UNSUPPORTED)
        self.assertEqual(
            combined.evidence,
            (
                EvidenceKind.POH_TABLE_VALUE,
                EvidenceKind.ASSUMED,
                EvidenceKind.UNSUPPORTED,
            ),
        )
        self.assertEqual(combined.gaps, (gap,))

        out_of_domain = Coverage(SupportStatus.OUT_OF_DOMAIN)
        self.assertIs(
            Coverage.combine(supported, out_of_domain).status,
            SupportStatus.OUT_OF_DOMAIN,
        )

    def test_coverage_rejects_empty_combine_and_raw_string_enums(self) -> None:
        with self.assertRaises(ValueError):
            Coverage.combine()
        with self.assertRaises(ValueError):
            Coverage("supported")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ModelGap("not_implemented", "missing")  # type: ignore[arg-type]


class CanonicalTableTests(unittest.TestCase):
    def test_loaded_table_shape_and_row_major_indexing(self) -> None:
        table = load_performance_table(FIXTURE)

        self.assertEqual(table.shape, (3, 2, 2))
        self.assertEqual(table.value_at((0, 0, 0)), 14.5)
        self.assertEqual(table.value_at((1, 0, 1)), 20.4)
        self.assertEqual(table.value_at((2, 1, 1)), 22.0)
        self.assertIs(table.evidence, EvidenceKind.POH_TABLE_VALUE)
        self.assertIs(table.coverage.status, SupportStatus.SUPPORTED)

    def test_table_and_axis_inputs_are_normalized_to_immutable_tuples(self) -> None:
        axis_values = [0, 1]
        output_values = [10, 20]
        axis = PerformanceAxis("x", "m", axis_values)  # type: ignore[arg-type]
        table = RectilinearPerformanceTable(
            table_id="immutability",
            axes=[axis],  # type: ignore[arg-type]
            output_name="result",
            output_unit="s",
            values=output_values,  # type: ignore[arg-type]
            citation=synthetic_citation(),
            applicability=synthetic_applicability(),
        )
        axis_values[0] = 99
        output_values[0] = 99

        self.assertEqual(axis.values, (0.0, 1.0))
        self.assertEqual(table.values, (10.0, 20.0))
        with self.assertRaises(FrozenInstanceError):
            table.output_name = "changed"  # type: ignore[misc]

    def test_invalid_axes_are_rejected(self) -> None:
        cases = (
            (),
            (0.0, 0.0),
            (1.0, 0.0),
            (0.0, math.nan),
            (0.0, math.inf),
            (False, 1.0),
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(TableDefinitionError):
                    PerformanceAxis("x", "m", values)

    def test_invalid_table_shape_values_and_axis_names_are_rejected(self) -> None:
        x = PerformanceAxis("x", "m", (0.0, 1.0))
        duplicate_x = PerformanceAxis("x", "s", (0.0, 1.0))
        common = {
            "table_id": "invalid",
            "output_name": "result",
            "output_unit": "unit",
            "citation": synthetic_citation(),
            "applicability": synthetic_applicability(),
        }
        with self.assertRaises(TableDefinitionError):
            RectilinearPerformanceTable(axes=(), values=(), **common)
        with self.assertRaises(TableDefinitionError):
            RectilinearPerformanceTable(axes=(x,), values=(1.0,), **common)
        with self.assertRaises(TableDefinitionError):
            RectilinearPerformanceTable(
                axes=(x,), values=(1.0, math.nan), **common
            )
        with self.assertRaises(TableDefinitionError):
            RectilinearPerformanceTable(
                axes=(x, duplicate_x), values=(1.0, 2.0, 3.0, 4.0), **common
            )

    def test_value_at_rejects_wrong_dimension_or_python_negative_index(self) -> None:
        table = load_performance_table(FIXTURE)
        for indices in ((0, 0), (-1, 0, 0), (3, 0, 0), (True, 0, 0)):
            with self.subTest(indices=indices):
                with self.assertRaises(IndexError):
                    table.value_at(indices)


class InterpolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_performance_table(FIXTURE)

    def test_every_source_node_is_returned_exactly_with_source_evidence(self) -> None:
        for indices in product(*(range(size) for size in self.table.shape)):
            point = {
                axis.name: axis.values[index]
                for axis, index in zip(self.table.axes, indices, strict=True)
            }
            with self.subTest(indices=indices, point=point):
                result = multilinear_interpolate(self.table, point)
                self.assertEqual(result.value, self.table.value_at(indices))
                self.assertIs(result.evidence, EvidenceKind.POH_TABLE_VALUE)
                self.assertTrue(result.is_source_node)
                self.assertIs(result.coverage.status, SupportStatus.SUPPORTED)
                self.assertEqual(
                    result.coverage.evidence, (EvidenceKind.POH_TABLE_VALUE,)
                )
                self.assertIs(result.citation, self.table.citation)
                self.assertIs(result.applicability, self.table.applicability)

    def test_nonuniform_three_dimensional_multi_affine_interior(self) -> None:
        point = {"x": 1.0, "y": 1.5, "z": 22.0}

        result = multilinear_interpolate(self.table, point)

        self.assertAlmostEqual(result.value, multi_affine(**point), places=12)
        self.assertIs(result.evidence, EvidenceKind.POH_INTERPOLATED)
        self.assertFalse(result.is_source_node)
        self.assertEqual(result.unit, "output-unit")
        self.assertEqual(result.quantity, "synthetic_output")

    def test_query_mapping_order_does_not_change_axis_order_or_result(self) -> None:
        result = multilinear_interpolate(
            self.table,
            {"z": 30.0, "y": 1.5, "x": 2.0},
        )

        self.assertAlmostEqual(result.value, multi_affine(2.0, 1.5, 30.0))
        self.assertEqual(result.query, (("x", 2.0), ("y", 1.5), ("z", 30.0)))
        self.assertIs(result.evidence, EvidenceKind.POH_INTERPOLATED)

    def test_exact_in_some_dimensions_is_still_interpolated(self) -> None:
        result = multilinear_interpolate(
            self.table,
            {"x": 2.0, "y": 1.5, "z": 30.0},
        )

        self.assertAlmostEqual(result.value, multi_affine(2.0, 1.5, 30.0))
        self.assertIs(result.evidence, EvidenceKind.POH_INTERPOLATED)

    def test_near_node_is_not_tolerance_snapped(self) -> None:
        near_x = math.nextafter(2.0, 5.0)

        result = multilinear_interpolate(
            self.table,
            {"x": near_x, "y": -1.0, "z": 10.0},
        )

        self.assertIs(result.evidence, EvidenceKind.POH_INTERPOLATED)
        self.assertEqual(result.query[0], ("x", near_x))

    def test_one_dimensional_interpolation(self) -> None:
        table = RectilinearPerformanceTable(
            table_id="one-dimensional",
            axes=(PerformanceAxis("x", "m", (-2.0, 1.0, 5.0)),),
            output_name="y",
            output_unit="s",
            values=(-3.0, 3.0, 11.0),
            citation=synthetic_citation(),
            applicability=synthetic_applicability(),
        )

        result = multilinear_interpolate(table, {"x": 3.0})

        self.assertEqual(result.value, 7.0)
        self.assertIs(result.evidence, EvidenceKind.POH_INTERPOLATED)

    def test_singleton_axis_has_no_implied_constant_domain(self) -> None:
        table = RectilinearPerformanceTable(
            table_id="singleton",
            axes=(PerformanceAxis("fixed_weight", "lb", (3400.0,)),),
            output_name="value",
            output_unit="unit",
            values=(99.0,),
            citation=synthetic_citation(),
            applicability=synthetic_applicability(),
        )
        self.assertEqual(
            multilinear_interpolate(table, {"fixed_weight": 3400.0}).value,
            99.0,
        )
        with self.assertRaises(OutOfDomainError):
            multilinear_interpolate(table, {"fixed_weight": 3400.0001})

    def test_below_and_above_domain_raise_structured_error(self) -> None:
        for requested in (-1.0001, 4.0001):
            with self.subTest(requested=requested):
                with self.assertRaises(OutOfDomainError) as caught:
                    multilinear_interpolate(
                        self.table,
                        {"x": 2.0, "y": requested, "z": 10.0},
                    )
                error = caught.exception
                self.assertEqual(error.table_id, self.table.table_id)
                self.assertEqual(error.axis_name, "y")
                self.assertEqual(error.requested, requested)
                self.assertEqual((error.lower, error.upper), (-1.0, 4.0))
                self.assertEqual(error.unit, "y-unit")
                self.assertIs(error.evidence, EvidenceKind.OUT_OF_DOMAIN)
                self.assertIs(error.coverage.status, SupportStatus.OUT_OF_DOMAIN)
                self.assertIs(error.coverage.gaps[0].kind, GapKind.OUT_OF_DOMAIN)
                self.assertIn("outside source domain", str(error))

    def test_missing_and_unknown_coordinates_are_rejected_together(self) -> None:
        with self.assertRaises(QueryDimensionError) as caught:
            multilinear_interpolate(
                self.table,
                {"x": 1.0, "z": 20.0, "temperature": 15.0},
            )
        self.assertEqual(caught.exception.missing, ("y",))
        self.assertEqual(caught.exception.unexpected, ("temperature",))

    def test_nonfinite_nonreal_and_boolean_coordinates_are_rejected(self) -> None:
        for bad_value in (math.nan, math.inf, -math.inf, "1", True, None):
            with self.subTest(bad_value=bad_value):
                with self.assertRaises(InvalidCoordinateError):
                    multilinear_interpolate(
                        self.table,
                        {"x": bad_value, "y": 1.0, "z": 20.0},  # type: ignore[dict-item]
                    )


class DerivedGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_performance_table(FIXTURE)

    def test_derived_grid_is_distinct_reproducible_and_provenance_aware(self) -> None:
        axes = (
            PerformanceAxis("x", "x-unit", (0.0, 1.0, 2.0, 5.0)),
            PerformanceAxis("y", "y-unit", (-1.0, 1.5, 4.0)),
            PerformanceAxis("z", "z-unit", (10.0, 20.0, 30.0)),
        )
        original_values = self.table.values

        first = derive_grid(self.table, axes)
        second = derive_grid(self.table, axes)

        self.assertIsInstance(first, DerivedPerformanceGrid)
        self.assertNotIsInstance(first, RectilinearPerformanceTable)
        self.assertEqual(first, second)
        self.assertEqual(first.shape, (4, 3, 3))
        self.assertEqual(self.table.values, original_values)
        self.assertEqual(first.value_at((0, 0, 0)), multi_affine(0.0, -1.0, 10.0))
        self.assertAlmostEqual(
            first.value_at((1, 1, 1)), multi_affine(1.0, 1.5, 20.0), places=12
        )
        self.assertIs(first.evidence_at((0, 0, 0)), EvidenceKind.POH_TABLE_VALUE)
        self.assertIs(first.evidence_at((1, 1, 1)), EvidenceKind.POH_INTERPOLATED)
        self.assertEqual(
            first.coverage_at((1, 1, 1)).evidence,
            (EvidenceKind.POH_INTERPOLATED,),
        )
        self.assertIs(first.citation, self.table.citation)
        self.assertIs(first.applicability, self.table.applicability)

    def test_derived_grid_rejects_out_of_domain_axis(self) -> None:
        axes = (
            PerformanceAxis("x", "x-unit", (-0.1, 1.0)),
            self.table.axes[1],
            self.table.axes[2],
        )
        with self.assertRaises(OutOfDomainError):
            derive_grid(self.table, axes)

    def test_derived_grid_rejects_axis_count_name_and_unit_mismatch(self) -> None:
        cases = (
            self.table.axes[:2],
            (
                PerformanceAxis("wrong", "x-unit", (0.0,)),
                self.table.axes[1],
                self.table.axes[2],
            ),
            (
                PerformanceAxis("x", "wrong-unit", (0.0,)),
                self.table.axes[1],
                self.table.axes[2],
            ),
        )
        for axes in cases:
            with self.subTest(axes=axes):
                with self.assertRaises(TableDefinitionError):
                    derive_grid(self.table, axes)


class StrictLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_valid_fixture_preserves_source_and_applicability(self) -> None:
        table = load_performance_table(FIXTURE)

        self.assertEqual(table.citation.document_title, self.document["citation"]["document_title"])
        self.assertEqual(table.citation.page, "1")
        self.assertEqual(table.applicability.aircraft_model, "synthetic-test-only")
        self.assertEqual(table.applicability.configuration[0].name, "fixture_kind")

    def test_schema_version_and_unknown_keys_are_rejected(self) -> None:
        bad_version = dict(self.document)
        bad_version["schema_version"] = 2
        with self.assertRaises(PerformanceTableLoadError):
            performance_table_from_mapping(bad_version)

        unknown_root = dict(self.document)
        unknown_root["surprise"] = True
        with self.assertRaises(PerformanceTableLoadError):
            performance_table_from_mapping(unknown_root)

        unknown_axis = json.loads(json.dumps(self.document))
        unknown_axis["axes"][0]["surprise"] = True
        with self.assertRaises(PerformanceTableLoadError):
            performance_table_from_mapping(unknown_axis)

    def test_shape_and_sparse_values_are_rejected_by_file_loader(self) -> None:
        self.document["values"] = self.document["values"][:-1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text(json.dumps(self.document), encoding="utf-8")
            with self.assertRaises(PerformanceTableLoadError) as caught:
                load_performance_table(path)
        self.assertIn("requires 12 values, got 11", str(caught.exception))

    def test_duplicate_json_keys_and_nonstandard_constants_are_rejected(self) -> None:
        documents = (
            '{"schema_version": 1, "schema_version": 1}',
            '{"schema_version": NaN}',
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, document in enumerate(documents):
                with self.subTest(document=document):
                    path = Path(temporary_directory) / f"invalid-{index}.json"
                    path.write_text(document, encoding="utf-8")
                    with self.assertRaises(PerformanceTableLoadError):
                        load_performance_table(path)

    def test_arrays_are_required_for_axes_values_and_metadata_lists(self) -> None:
        cases = []
        bad_axes = dict(self.document)
        bad_axes["axes"] = "not-an-array"
        cases.append(bad_axes)

        bad_values = dict(self.document)
        bad_values["values"] = {"not": "an-array"}
        cases.append(bad_values)

        bad_notes = json.loads(json.dumps(self.document))
        bad_notes["citation"]["notes"] = "not-an-array"
        cases.append(bad_notes)

        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(PerformanceTableLoadError):
                    performance_table_from_mapping(document)


if __name__ == "__main__":
    unittest.main()
