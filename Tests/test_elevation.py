import json
import unittest

from Core.Terrain.elevation import ElevationContract, UINT16_MAX


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.contract = ElevationContract(-200, 0, 600)

    def test_min_max_mapping(self):
        self.assertEqual(self.contract.encode(-200), 0)
        self.assertEqual(self.contract.encode(600), UINT16_MAX)
        self.assertEqual(self.contract.decode(0), -200)
        self.assertEqual(self.contract.decode(UINT16_MAX), 600)

    def test_sea_level_mapping_and_quantization(self):
        self.assertEqual(self.contract.encode(0), 16384)
        self.assertAlmostEqual(self.contract.decode(16384), 0.0030518043793392735)
        self.assertAlmostEqual(self.contract.quantization_step_m, 800 / 65535)

    def test_physical_round_trip_including_underwater_values(self):
        for value in (-200, -199.9, -100, -0.1, 0, 0.1, 125, 599.9, 600):
            with self.subTest(value=value):
                encoded = self.contract.encode(value)
                self.assertIsInstance(encoded, int)
                self.assertTrue(0 <= encoded <= UINT16_MAX)
                self.assertLessEqual(abs(self.contract.decode(encoded) - value),
                                     self.contract.quantization_step_m / 2 + 1e-12)

    def test_every_uint16_value_round_trips(self):
        for value in range(UINT16_MAX + 1):
            self.assertEqual(self.contract.encode(self.contract.decode(value)), value)

    def test_other_physical_ranges_and_sea_level_endpoints(self):
        for contract in (ElevationContract(-1000, 50, 3000),
                         ElevationContract(0, 0, 100), ElevationContract(-100, 0, 0)):
            with self.subTest(contract=contract):
                self.assertEqual(contract.encode(contract.min_elevation_m), 0)
                self.assertEqual(contract.encode(contract.max_elevation_m), 65535)
                self.assertLessEqual(abs(contract.decode(contract.encode(contract.sea_level_m))
                                         - contract.sea_level_m),
                                     contract.quantization_step_m / 2 + 1e-12)

    def test_invalid_contracts(self):
        for values in ((0, 0, 0), (600, 0, -200), (-200, 601, 600),
                       (-200, -201, 600), (float("nan"), 0, 600),
                       (-200, float("inf"), 600), (-200, 0, float("inf")),
                       (-1e308, 0, 1e308), (False, 0, 600), ("-200", 0, 600)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ElevationContract(*values)

    def test_invalid_physical_elevations_are_not_clipped(self):
        for value in (-200.001, 600.001, float("nan"), float("inf"),
                      -float("inf"), True, "0", 1j, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.contract.encode(value)

    def test_invalid_uint16_values_are_not_cast_or_wrapped(self):
        for value in (-1, 65536, 0.5, 16384.0, float("nan"),
                      float("inf"), True, "16384", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.contract.decode(value)

    def test_metadata_is_deterministic_and_independent(self):
        expected = self.contract.metadata_json()
        self.assertEqual(expected, ElevationContract(-200.0, 0.0, 600.0).metadata_json())
        metadata = json.loads(expected)
        self.assertEqual(metadata["sea_level_uint16"], 16384)
        restored = ElevationContract(**{key: metadata[key] for key in
                                      ("min_elevation_m", "sea_level_m", "max_elevation_m")})
        self.assertEqual(restored, self.contract)
        altered = self.contract.metadata()
        altered["sea_level_m"] = 999
        self.assertEqual(self.contract.metadata_json(), expected)


if __name__ == "__main__":
    unittest.main()
