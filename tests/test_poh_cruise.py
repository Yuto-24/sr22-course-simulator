from __future__ import annotations

import math
import unittest
from dataclasses import replace
from itertools import product

from sr22_course_simulator.performance import (
    CruiseConfiguration,
    CruiseTableCompatibilityError,
    OutOfDomainError,
    PerformanceAxis,
    PohCruiseQuery,
    SourcedKtasCorrection,
    load_bundled_cruise_query,
)
from sr22_course_simulator.provenance import (
    Applicability,
    ApplicabilityField,
    EvidenceKind,
)


class BundledCruiseQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.query = load_bundled_cruise_query()

    def test_every_source_power_node_reproduces_common_source_nodes_exactly(self) -> None:
        map_axis, isa_axis = self.query.power_table.axes
        for map_index, isa_index in product(
            range(len(map_axis.values)), range(len(isa_axis.values))
        ):
            requested_power = self.query.power_table.value_at(
                (map_index, isa_index)
            )
            isa_deviation = isa_axis.values[isa_index]
            with self.subTest(
                map_index=map_index,
                isa_index=isa_index,
                requested_power=requested_power,
            ):
                result = self.query.query_canonical(
                    power_percent=requested_power,
                    isa_deviation_deg_c=isa_deviation,
                )
                self.assertEqual(
                    result.manifold_pressure_inhg,
                    map_axis.values[map_index],
                )
                self.assertEqual(result.power.value, requested_power)
                self.assertEqual(
                    result.canonical_ktas,
                    self.query.ktas_table.value_at((map_index, isa_index)),
                )
                self.assertEqual(
                    result.fuel_flow_gph,
                    self.query.fuel_flow_table.value_at((map_index, isa_index)),
                )
                self.assertIs(result.power.evidence, EvidenceKind.POH_TABLE_VALUE)
                self.assertIs(
                    result.true_airspeed.canonical.evidence,
                    EvidenceKind.POH_TABLE_VALUE,
                )
                self.assertIs(
                    result.fuel_flow.evidence,
                    EvidenceKind.POH_TABLE_VALUE,
                )
                self.assertIs(
                    result.manifold_pressure.evidence,
                    EvidenceKind.POH_TABLE_VALUE,
                )

    def test_exact_bundled_node_has_expected_values_and_provenance(self) -> None:
        result = self.query.query_canonical(
            power_percent=76.0,
            isa_deviation_deg_c=0.0,
        )

        self.assertIs(
            result.configuration,
            CruiseConfiguration.POH_CANONICAL_BASELINE,
        )
        self.assertEqual(result.manifold_pressure_inhg, 24.4)
        self.assertEqual(result.canonical_ktas, 170.0)
        self.assertEqual(result.effective_ktas, 170.0)
        self.assertEqual(result.fuel_flow_gph, 18.0)
        self.assertFalse(result.true_airspeed.is_corrected)
        self.assertIsNone(result.true_airspeed.correction)
        for source_result in (
            result.power,
            result.true_airspeed.canonical,
            result.fuel_flow,
        ):
            self.assertEqual(
                source_result.citation.document_title,
                "SR22 G6 型式証明飛行規程 全章",
            )
            self.assertEqual(source_result.citation.page, "5-32 (PDF page 192)")
            self.assertEqual(
                source_result.applicability.aircraft_model,
                "Cirrus SR22 G6",
            )

    def test_piecewise_inverse_and_source_surfaces_interpolate_together(self) -> None:
        result = self.query.query_canonical(
            power_percent=77.0,
            isa_deviation_deg_c=15.0,
        )

        self.assertAlmostEqual(result.manifold_pressure_inhg, 25.15, places=12)
        self.assertAlmostEqual(result.power.value, 77.0, places=12)
        self.assertAlmostEqual(result.canonical_ktas, 169.75, places=12)
        self.assertAlmostEqual(result.fuel_flow_gph, 19.0375, places=12)
        self.assertIs(
            result.manifold_pressure.evidence,
            EvidenceKind.POH_INTERPOLATED,
        )
        self.assertIs(result.power.evidence, EvidenceKind.POH_INTERPOLATED)
        self.assertIs(
            result.true_airspeed.canonical.evidence,
            EvidenceKind.POH_INTERPOLATED,
        )
        self.assertIs(result.fuel_flow.evidence, EvidenceKind.POH_INTERPOLATED)
        self.assertEqual(
            result.power.query,
            result.true_airspeed.canonical.query,
        )
        self.assertEqual(result.power.query, result.fuel_flow.query)
        self.assertEqual(result.manifold_pressure.lower_map_inhg, 24.4)
        self.assertEqual(result.manifold_pressure.upper_map_inhg, 25.4)
        self.assertIs(
            result.manifold_pressure.lower_power.evidence,
            EvidenceKind.POH_INTERPOLATED,
        )
        self.assertIs(
            result.manifold_pressure.upper_power.evidence,
            EvidenceKind.POH_INTERPOLATED,
        )

    def test_map_only_interior_interpolation_matches_linear_source_slice(self) -> None:
        result = self.query.query_canonical(
            power_percent=78.0,
            isa_deviation_deg_c=0.0,
        )

        self.assertAlmostEqual(result.manifold_pressure_inhg, 24.9, places=12)
        self.assertAlmostEqual(result.canonical_ktas, 171.5, places=12)
        self.assertAlmostEqual(result.fuel_flow_gph, 18.5, places=12)
        self.assertEqual(result.manifold_pressure.lower_power.value, 76.0)
        self.assertEqual(result.manifold_pressure.upper_power.value, 80.0)
        self.assertIs(
            result.manifold_pressure.lower_power.evidence,
            EvidenceKind.POH_TABLE_VALUE,
        )
        self.assertIs(
            result.manifold_pressure.upper_power.evidence,
            EvidenceKind.POH_TABLE_VALUE,
        )

    def test_spiral_entry_power_is_explicitly_outside_cruise_source_domain(self) -> None:
        with self.assertRaises(OutOfDomainError) as caught:
            self.query.query_target_configuration(
                power_percent=10.0,
                isa_deviation_deg_c=0.0,
            )

        error = caught.exception
        self.assertEqual(error.axis_name, "power")
        self.assertEqual(error.unit, "percent")
        self.assertEqual(error.requested, 10.0)
        self.assertEqual((error.lower, error.upper), (72.0, 88.0))
        self.assertIs(error.evidence, EvidenceKind.OUT_OF_DOMAIN)

    def test_isa_deviation_and_upper_power_are_not_extrapolated(self) -> None:
        with self.assertRaises(OutOfDomainError) as isa_error:
            self.query.query_canonical(
                power_percent=76.0,
                isa_deviation_deg_c=30.0001,
            )
        self.assertEqual(isa_error.exception.axis_name, "isa_deviation_deg_c")

        with self.assertRaises(OutOfDomainError) as power_error:
            self.query.query_canonical(
                power_percent=88.0001,
                isa_deviation_deg_c=0.0,
            )
        self.assertEqual(power_error.exception.axis_name, "power")

    def test_invalid_numeric_inputs_are_rejected_before_query(self) -> None:
        cases = (
            {"power_percent": True, "isa_deviation_deg_c": 0.0},
            {"power_percent": math.nan, "isa_deviation_deg_c": 0.0},
            {"power_percent": 76.0, "isa_deviation_deg_c": math.inf},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.query.query_canonical(**arguments)

    def test_target_correction_is_explicit_typed_and_does_not_mutate_canonical_data(self) -> None:
        original_values = self.query.ktas_table.values
        canonical = self.query.query_canonical(
            power_percent=76.0,
            isa_deviation_deg_c=0.0,
        )
        target = self.query.query_target_configuration(
            power_percent=76.0,
            isa_deviation_deg_c=0.0,
        )

        self.assertIs(
            target.configuration,
            CruiseConfiguration.TARGET_NOSE_WHEEL_PANT_REMOVED,
        )
        self.assertEqual(target.canonical_ktas, canonical.canonical_ktas)
        self.assertEqual(target.effective_ktas, canonical.canonical_ktas - 10.0)
        self.assertEqual(target.true_airspeed.canonical, canonical.true_airspeed.canonical)
        self.assertTrue(target.true_airspeed.is_corrected)
        correction = target.true_airspeed.correction
        self.assertIsInstance(correction, SourcedKtasCorrection)
        assert correction is not None
        self.assertEqual(correction.delta_ktas, -10.0)
        self.assertIs(correction.evidence, EvidenceKind.POH_TABLE_VALUE)
        self.assertEqual(
            correction.baseline_configuration,
            ApplicabilityField("canonical_wheel_fairing_baseline", "installed"),
        )
        self.assertEqual(
            correction.target_configuration,
            ApplicabilityField("nose_wheel_pant_fairing", "removed"),
        )
        self.assertIn("subtract 10 KTAS", correction.source_note)
        self.assertIs(correction.citation, self.query.ktas_table.citation)
        self.assertEqual(self.query.ktas_table.values, original_values)

    def test_fuel_flow_remains_volumetric_without_hidden_density_conversion(self) -> None:
        result = self.query.query_canonical(
            power_percent=76.0,
            isa_deviation_deg_c=0.0,
        )

        self.assertEqual(result.fuel_flow.unit, "US gal/h")
        self.assertEqual(result.fuel_flow_gph, 18.0)
        self.assertFalse(hasattr(result, "fuel_flow_kg_s"))


class CruiseTableCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bundled = load_bundled_cruise_query()
        cls.power = bundled.power_table
        cls.ktas = bundled.ktas_table
        cls.fuel = bundled.fuel_flow_table

    def test_axis_nodes_must_match_exactly(self) -> None:
        map_axis, isa_axis = self.ktas.axes
        changed_map = PerformanceAxis(
            map_axis.name,
            map_axis.unit,
            map_axis.values[:-1] + (27.5,),
        )
        changed_ktas = replace(self.ktas, axes=(changed_map, isa_axis))

        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(self.power, changed_ktas, self.fuel)

    def test_citation_revision_must_match(self) -> None:
        changed_ktas = replace(
            self.ktas,
            citation=replace(self.ktas.citation, revision="incompatible revision"),
        )

        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(self.power, changed_ktas, self.fuel)

    def test_core_applicability_must_match(self) -> None:
        changed_configuration = tuple(
            ApplicabilityField(item.name, 3300.0, item.unit)
            if item.name == "weight"
            else item
            for item in self.power.applicability.configuration
        )
        changed_power = replace(
            self.power,
            applicability=Applicability(
                aircraft_model=self.power.applicability.aircraft_model,
                configuration=changed_configuration,
                conditions=self.power.applicability.conditions,
            ),
        )

        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(changed_power, self.ktas, self.fuel)

    def test_query_is_restricted_to_the_named_altitude_and_rpm_slice(self) -> None:
        def change_altitude(table):
            configuration = tuple(
                ApplicabilityField(item.name, 4000.0, item.unit)
                if item.name == "pressure_altitude"
                else item
                for item in table.applicability.configuration
            )
            return replace(
                table,
                applicability=Applicability(
                    aircraft_model=table.applicability.aircraft_model,
                    configuration=configuration,
                    conditions=table.applicability.conditions,
                ),
            )

        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(
                change_altitude(self.power),
                change_altitude(self.ktas),
                change_altitude(self.fuel),
            )

    def test_ktas_correction_note_and_baseline_are_required(self) -> None:
        missing_note = replace(
            self.ktas,
            citation=replace(self.ktas.citation, notes=("canonical only",)),
        )
        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(self.power, missing_note, self.fuel)

        changed_configuration = tuple(
            ApplicabilityField(item.name, "removed", item.unit)
            if item.name == "canonical_wheel_fairing_baseline"
            else item
            for item in self.ktas.applicability.configuration
        )
        wrong_baseline = replace(
            self.ktas,
            applicability=Applicability(
                aircraft_model=self.ktas.applicability.aircraft_model,
                configuration=changed_configuration,
                conditions=self.ktas.applicability.conditions,
            ),
        )
        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(self.power, wrong_baseline, self.fuel)

    def test_power_must_be_strictly_monotonic_at_every_isa_node(self) -> None:
        values = list(self.power.values)
        values[3] = 75.0  # MAP index 1 / ISA index 0, below preceding 76%.
        nonmonotonic_power = replace(self.power, values=tuple(values))

        with self.assertRaises(CruiseTableCompatibilityError):
            PohCruiseQuery(nonmonotonic_power, self.ktas, self.fuel)


if __name__ == "__main__":
    unittest.main()
