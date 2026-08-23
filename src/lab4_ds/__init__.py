"""Sentinel-2 cyanobacteria laboratory pipeline."""

import os
import sys

__version__ = "0.1.0"


def _drop_foreign_geo_data_dirs() -> None:
    """Remove PROJ/GDAL data dirs that belong to another install.

    The PostgreSQL/PostGIS Windows installer sets PROJ_LIB and GDAL_DATA
    machine-wide, pointing at a PROJ database too old for rasterio/pyproj
    ("DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected").
    Those wheels bundle their own data, so clearing any value that lives
    outside this environment restores the bundled lookups. Must run before
    the first CRS access, hence at package import.
    """
    prefix = os.path.normcase(sys.prefix)
    for name in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
        value = os.environ.get(name)
        if value and not os.path.normcase(value).startswith(prefix):
            del os.environ[name]


_drop_foreign_geo_data_dirs()
