import numpy as np

from lab4_ds.indices import (
    calculate_layers,
    chlorophyll_from_ndci,
    clear_data_mask,
    fai,
    ndci,
    ndvi,
    ndwi,
    water_body_mask,
)


def test_normalized_indices_and_zero_denominator() -> None:
    red = np.array([0.2, 0.0], dtype=np.float32)
    nir = np.array([0.6, 0.0], dtype=np.float32)
    green = np.array([0.4, 0.0], dtype=np.float32)
    np.testing.assert_allclose(ndvi(red, nir)[0], 0.5, rtol=1e-6)
    np.testing.assert_allclose(ndwi(green, nir)[0], -0.2, rtol=1e-6)
    assert np.isnan(ndvi(red, nir)[1])


def test_official_ndci_polynomial_and_fai() -> None:
    red = np.array([0.1], dtype=np.float32)
    red_edge = np.array([0.2], dtype=np.float32)
    value = ndci(red, red_edge)
    expected = 826.57 * (1 / 3) ** 3 - 176.43 * (1 / 3) ** 2 + 19 * (1 / 3) + 4.071
    np.testing.assert_allclose(chlorophyll_from_ndci(value), expected, rtol=1e-5)
    np.testing.assert_allclose(
        fai(red, red_edge, np.array([0.3], dtype=np.float32)), -0.018, rtol=1e-6
    )


def test_masks_exclude_cloud_and_detect_water() -> None:
    shape = (1, 2)
    valid = clear_data_mask(np.ones(shape), np.array([[6, 9]], dtype=np.float32))
    np.testing.assert_array_equal(valid, [[True, False]])
    water = water_body_mask(
        np.full(shape, 0.05),
        np.full(shape, 0.10),
        np.full(shape, 0.05),
        np.full(shape, 0.02),
        np.full(shape, 0.01),
        np.full(shape, 0.005),
    )
    assert water.all()


def test_surface_bloom_is_retained_as_classification() -> None:
    shape = (1, 1)
    bands = {
        "B02": np.full(shape, 0.05),
        "B03": np.full(shape, 0.10),
        "B04": np.full(shape, 0.02),
        "B05": np.full(shape, 0.06),
        "B07": np.full(shape, 0.20),
        "B08": np.full(shape, 0.02),
        "B8A": np.full(shape, 0.02),
        "B11": np.full(shape, 0.01),
        "B12": np.full(shape, 0.005),
        "SCL": np.full(shape, 6),
        "dataMask": np.ones(shape),
    }
    result = calculate_layers(bands)
    assert result["surface_bloom"][0, 0] == 1
    assert np.isnan(result["chlorophyll_proxy"][0, 0])
    assert result["water"][0, 0] == 1
