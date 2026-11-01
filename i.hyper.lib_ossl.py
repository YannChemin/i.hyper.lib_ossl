#!/usr/bin/env python
##############################################################################
# MODULE:    i.hyper.lib_ossl
# AUTHOR(S): Spectral Feature Extraction and Interpretation Engine
# PURPOSE:   Harvest the Open Soil Spectral Library (OSSL,
#            soilspectroscopy.org) into the same shared, source-tagged,
#            partitioned local spectral database used by i.hyper.lib_ecosis,
#            i.hyper.lib_usgs, i.hyper.lib_relab and i.hyper.lib_gsti
#            (GeoParquet by default, SQLite fallback), usable by any
#            i.hyper.* module. Two routes: the experimental OSSL REST API
#            (filterable by nation/state/bbox/depth/texture, MIR + VisNIR
#            only) and the Google Cloud Storage v1.3 per-dataset bulk files
#            (complete, the only route carrying the NIR/Neospectra scans).
# SPDX-License-Identifier: Unlicense
##############################################################################

# %module
# % description: Harvest the Open Soil Spectral Library (OSSL) soil spectra and paired soil properties into the shared local spectral database used by i.hyper.* modules
# % keyword: imagery
# % keyword: hyperspectral
# % keyword: spectral library
# % keyword: OSSL
# % keyword: soil spectroscopy
# % keyword: soil properties
# %end

# %option
# % key: source
# % type: string
# % required: no
# % options: api,gcs
# % answer: gcs
# % description: Harvest route. gcs streams the complete v1.3 per-dataset bulk files from Google Cloud Storage (20 datasets, the only route carrying the NIR/Neospectra scans); api uses the experimental OSSL REST API, which is filterable by nation/state/bbox/depth/texture but serves only 10 datasets and only MIR and VisNIR
# % guisection: Input
# %end

# %option
# % key: output
# % type: string
# % required: no
# % description: Shared spectral library root directory (default: $HOME/grassdata/hyperspeclib -- the same fixed location used by i.hyper.lib_ecosis, i.hyper.lib_usgs, i.hyper.lib_relab and i.hyper.lib_gsti)
# % guisection: Output
# %end

# %option
# % key: format
# % type: string
# % required: no
# % options: parquet,sqlite
# % answer: parquet
# % description: Storage backend. parquet (GeoParquet, since OSSL records carry lat/lon) supports fast partitioned/parallel columnar access; sqlite is a zero-extra-dependency fallback
# % guisection: Output
# %end

# %option
# % key: datasets
# % type: string
# % required: no
# % multiple: yes
# % description: Restrict ingestion to specific OSSL dataset codes (gcs: e.g. KSSL,LUCAS,Neospectra; api: e.g. KSSL.SSL,LUCAS.SSL). Use the -l flag to list the codes available on the chosen source. Default: all
# % guisection: Input
# %end

# %option
# % key: scans
# % type: string
# % required: no
# % multiple: yes
# % options: mir,visnir,nir
# % answer: mir,visnir,nir
# % description: Spectral domains to ingest. mir = mid-infrared absorbance (600-4000 1/cm), visnir = visible/near-infrared reflectance (350-2500 nm), nir = Neospectra-class near-infrared reflectance (1100-2550 nm, source=gcs only)
# % guisection: Input
# %end

# %option
# % key: mir_axis
# % type: string
# % required: no
# % options: nm,wavenumber
# % answer: nm
# % description: Spectral axis stored for MIR scans. nm converts the native wavenumbers to wavelengths (nm = 1e7 / 1/cm, re-sorted ascending) so MIR rows are directly comparable with the nm-based rows of the other i.hyper.lib_* sources and with i.hyper.speclookup's min/max wavelength filters; wavenumber keeps the native 1/cm axis
# % guisection: Input
# %end

# %option
# % key: nation
# % type: string
# % required: no
# % description: Subset by nation name as spelled by the OSSL API, e.g. France (source=api only; see -n to list)
# % guisection: Filter
# %end

# %option
# % key: state
# % type: string
# % required: no
# % description: Subset by state/region name within nation (source=api only)
# % guisection: Filter
# %end

# %option
# % key: bbox
# % type: string
# % required: no
# % description: Subset by bounding box as a WKT geometry in WGS84 lon/lat, e.g. "POLYGON((-5 42,9 42,9 51,-5 51,-5 42))". With source=gcs the box is applied locally to the site coordinates; with source=api it is passed to the server
# % guisection: Filter
# %end

# %option
# % key: soil_texture
# % type: string
# % required: no
# % description: Subset by USDA soil texture class as spelled by the OSSL API, e.g. Loam (source=api only)
# % guisection: Filter
# %end

# %option
# % key: depth_min
# % type: double
# % required: no
# % description: Keep only layers whose upper depth is at or below this value [cm]
# % guisection: Filter
# %end

# %option
# % key: depth_max
# % type: double
# % required: no
# % description: Keep only layers whose lower depth is at or above this value [cm]
# % guisection: Filter
# %end

# %option
# % key: var
# % type: string
# % required: no
# % description: Soil property column to filter on, e.g. oc_usda.c729_w.pct (organic carbon). With var_min/var_max, only layers whose value for this property falls in the range are kept
# % guisection: Filter
# %end

# %option
# % key: var_min
# % type: double
# % required: no
# % description: Lower bound for var [var units]
# % guisection: Filter
# %end

# %option
# % key: var_max
# % type: double
# % required: no
# % description: Upper bound for var [var units]
# % guisection: Filter
# %end

# %option
# % key: cache_dir
# % type: string
# % required: no
# % description: Directory in which to keep the downloaded OSSL source files, so a re-run or a second scan domain does not download them again (default: stream straight from the network without saving, which uses no disk but re-downloads)
# % guisection: Input
# %end

# %option
# % key: station_chunk
# % type: integer
# % required: no
# % answer: 200
# % description: Number of station IDs requested per OSSL API /data call (source=api only). The API has no limit/offset parameter, so a large dataset has to be paged by station; smaller chunks are slower but more robust to server timeouts
# % guisection: Input
# %end

# %option
# % key: stream_batch_size
# % type: integer
# % required: no
# % answer: 2000
# % description: Number of records buffered in memory per incremental write batch (bounds peak memory regardless of dataset size)
# % guisection: Input
# %end

# %option
# % key: timeout
# % type: integer
# % required: no
# % answer: 600
# % description: Network timeout per HTTP request [seconds]
# % guisection: Input
# %end

# %option
# % key: retries
# % type: integer
# % required: no
# % answer: 3
# % description: Number of retries per failed HTTP request (exponential backoff)
# % guisection: Input
# %end

# %flag
# % key: l
# % description: List the dataset codes available on the chosen source with their record counts, then exit without ingesting
# % guisection: Input
# %end

# %flag
# % key: n
# % description: List the nation, state and soil texture filter vocabularies accepted by the OSSL API, then exit without ingesting
# % guisection: Filter
# %end

# %flag
# % key: f
# % description: Force re-ingestion of datasets already present in the library (default: skip datasets whose source record count hasn't grown since last ingestion)
# % guisection: Input
# %end

# %flag
# % key: k
# % description: Keep going on a per-record parse error or a failed server request instead of aborting the whole run
# %end

# %rules
# % collective: var_min,var
# % collective: var_max,var
# % requires: state,nation
# %end

from __future__ import annotations

import csv
import datetime
import gzip
import io
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Iterator, Optional

import grass.script as gs

SOURCE_DATABASE = "ossl"
DEFAULT_LIBRARY_ROOT = os.path.join(
    os.path.expanduser("~"), "grassdata", "hyperspeclib"
)
MANIFEST_NAME = "_manifest.json"

API_BASE = "https://api.soilspectroscopy.org"
GCS_BASE = "https://storage.googleapis.com/soilspec4gg-public/datasets"
GCS_URL_LIST = (
    "https://docs.soilspectroscopy.org/tabular/ossl_individual_datasets_urls_v1.3.csv"
)
OSSL_VERSION = "v1.3"

# Dataset codes shipped as v1.3 bulk files on Google Cloud Storage. Kept as a
# fallback for when the published URL list is unreachable; the list itself is
# authoritative and is fetched first.
GCS_DATASETS_FALLBACK = [
    "AFSIS1",
    "AFSIS2",
    "AUT",
    "BESB",
    "CAF",
    "GEMAS",
    "Geocradle",
    "GPKOR",
    "HLF_CAN",
    "HSDOS",
    "ICRAF_ISRIC",
    "KSSL",
    "LF_BRA",
    "LUCAS",
    "MTQ",
    "NEON",
    "Neospectra",
    "PF_NZL",
    "SRB",
    "WS_SWIND",
]

# Per-domain physical meaning of the scan columns. The OSSL encodes the MIR
# axis in wavenumbers (1/cm, absorbance) and both NIR axes in nanometres
# (reflectance); see the column-name conventions scan_mir.<wavenumber>_abs,
# scan_visnir.<nm>_ref and scan_nir.<nm>_ref.
SCAN_DOMAINS = {
    "mir": {
        "prefix": "scan_mir.",
        "suffix": "_abs",
        "measurement_type": "absorbance",
        "native_unit": "1/cm",
        "label": "MIR",
    },
    "visnir": {
        "prefix": "scan_visnir.",
        "suffix": "_ref",
        "measurement_type": "reflectance",
        "native_unit": "nm",
        "label": "VisNIR",
    },
    "nir": {
        "prefix": "scan_nir.",
        "suffix": "_ref",
        "measurement_type": "reflectance",
        "native_unit": "nm",
        "label": "NIR",
    },
}

# Site columns promoted to first-class row fields; everything else in the
# site and soil-lab tables is carried verbatim in extra_metadata.
_SITE_LON_KEYS = ("longitude.point_wgs84_dd", "longitude.county_wgs84_dd")
_SITE_LAT_KEYS = ("latitude.point_wgs84_dd", "latitude.county_wgs84_dd")
_SITE_UPPER_DEPTH = "layer.upper.depth_usda_cm"
_SITE_LOWER_DEPTH = "layer.lower.depth_usda_cm"
_LAYER_LOCAL_ID = "id.layer_local_c"
_LAYER_UUID = "id.layer_uuid_txt"
_DATASET_CODE = "dataset.code_ascii_txt"

# Identifier columns that the soil-lab table repeats from the join. They are
# not soil properties and are kept out of the soil_properties namespace.
_JOIN_KEY_COLUMNS = frozenset({_LAYER_LOCAL_ID, _LAYER_UUID, _DATASET_CODE})


def _record_id(layer_id: str, scan_local: Optional[str]) -> str:
    """Compose a record id that is unique within one dataset and scan domain.

    A dataset can hold several scans of the same layer (KSSL has one per
    optics setup), so the scan's own id is appended to keep the rows
    distinct. Where the two ids are the same, as in several datasets that
    scanned each layer once, nothing is appended."""
    if scan_local and scan_local != layer_id:
        return "{}::{}".format(layer_id, scan_local)
    return layer_id


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _sanitize_id(name: Optional[str]) -> str:
    if not name:
        return "Unclassified"
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return sanitized or "Unclassified"


def _clean(v: Optional[str]) -> Optional[str]:
    """Normalize a CSV cell. The OSSL tables use several spellings of
    'missing' across their constituent datasets."""
    if v is None:
        return None
    v = v.strip()
    if v in ("", "NA", "N/A", "na", "NaN", "nan", "NULL", "null", "-", "."):
        return None
    return v


def _to_float(v) -> Optional[float]:
    if isinstance(v, float):
        return None if math.isnan(v) else v
    if isinstance(v, int):
        return float(v)
    v = _clean(v)
    if v is None:
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _wavenumber_to_nm(wavenumber_cm: float) -> float:
    """1/cm -> nm. 1 cm = 1e7 nm, so nm = 1e7 / wavenumber."""
    return 1.0e7 / wavenumber_cm


def _parse_bbox(wkt: Optional[str]) -> Optional[tuple]:
    """Extract an axis-aligned (min_lon, min_lat, max_lon, max_lat) envelope
    from a WKT geometry, for local filtering of the bulk files. Only the
    envelope is used, which is what the OSSL API does with bbox too."""
    if not wkt:
        return None
    coords = re.findall(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", wkt)
    if not coords:
        gs.fatal(
            "Could not read any coordinate pair out of bbox=<{}>. Expected a "
            "WKT geometry in WGS84 lon/lat, e.g. "
            '"POLYGON((-5 42,9 42,9 51,-5 51,-5 42))".'.format(wkt)
        )
    lons = [float(x) for x, _ in coords]
    lats = [float(y) for _, y in coords]
    return min(lons), min(lats), max(lons), max(lats)


def _in_bbox(lon: Optional[float], lat: Optional[float], bbox: Optional[tuple]) -> bool:
    if bbox is None:
        return True
    if lon is None or lat is None:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _http_open(url: str, timeout: int, retries: int, quiet_404: bool = False):
    """Open a URL with retries and exponential backoff, returning the live
    response object so large bodies can be streamed rather than buffered.

    The OSSL API answers an empty result set with HTTP 500 rather than an
    empty payload, so a 500 is reported to the caller as None instead of
    being treated as a hard failure."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "i.hyper.lib_ossl (GRASS GIS addon)"}
            )
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            # 404 and 500 are deterministic answers, not transient faults.
            if exc.code == 404 and quiet_404:
                return None
            if exc.code in (404, 500):
                return None
            last_exc = exc
        except Exception as exc:
            last_exc = exc
        if attempt < retries:
            backoff = 2.0**attempt
            gs.verbose(
                "Request failed ({}); retrying in {:.0f} s [{}/{}]".format(
                    last_exc, backoff, attempt + 1, retries
                )
            )
            time.sleep(backoff)
    gs.warning("Giving up on {} after {} retr(ies): {}".format(url, retries, last_exc))
    return None


def _api_get_json(path: str, params: dict, timeout: int, retries: int):
    query = urllib.parse.urlencode(
        [(k, v) for k, v in params.items() if v not in (None, "")]
    )
    url = "{}/{}{}".format(API_BASE, path, "?" + query if query else "")
    response = _http_open(url, timeout, retries)
    if response is None:
        return None
    with response:
        try:
            return json.loads(response.read().decode("utf-8", "replace"))
        except ValueError as exc:
            gs.warning("Malformed JSON from {}: {}".format(url, exc))
            return None


class _CountingReader(io.RawIOBase):
    """Wraps a stream and reports how many bytes have been consumed, so a
    gzip download of unknown row count can still drive a real progress
    percentage off Content-Length.

    Progress is forwarded to the user through gs.percent(), which the
    MetaMonitor GRASS shim picks up automatically
    (https://github.com/YannChemin/MetaMonitor)."""

    def __init__(self, stream, total: Optional[int], label: str):
        self._stream = stream
        self._total = total or 0
        self._label = label
        self._read = 0
        self._last_pct = -1

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        chunk = self._stream.read(len(buffer))
        if not chunk:
            return 0
        buffer[: len(chunk)] = chunk
        self._read += len(chunk)
        if self._total:
            pct = int(100 * self._read / self._total)
            if pct != self._last_pct:
                self._last_pct = pct
                gs.percent(min(self._read, self._total), self._total, 2)
        return len(chunk)


def _open_csv_gz(
    url: str, cache_dir: Optional[str], timeout: int, retries: int, label: str
):
    """Return a text-mode reader over a remote gzipped CSV.

    With cache_dir set the compressed file is downloaded once and reused, so
    a second scan domain or a re-run costs nothing; without it the gzip
    stream is decoded straight off the socket and never touches disk."""
    if cache_dir:
        local = os.path.join(
            cache_dir, url.rsplit("/", 2)[-2] + "_" + url.rsplit("/", 1)[-1]
        )
        if not os.path.isfile(local) or os.path.getsize(local) == 0:
            response = _http_open(url, timeout, retries, quiet_404=True)
            if response is None:
                return None
            total = response.headers.get("Content-Length")
            gs.message("Downloading {}…".format(label))
            tmp = local + ".part"
            try:
                with response, open(tmp, "wb") as out:
                    reader = _CountingReader(
                        response, int(total) if total else None, label
                    )
                    while True:
                        chunk = reader.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                os.replace(tmp, local)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        return io.TextIOWrapper(
            gzip.open(local, "rb"), encoding="utf-8", errors="replace", newline=""
        )

    response = _http_open(url, timeout, retries, quiet_404=True)
    if response is None:
        return None
    total = response.headers.get("Content-Length")
    gs.message("Streaming {}…".format(label))
    counted = io.BufferedReader(
        _CountingReader(response, int(total) if total else None, label),
        buffer_size=1 << 20,
    )
    return io.TextIOWrapper(
        gzip.GzipFile(fileobj=counted), encoding="utf-8", errors="replace", newline=""
    )


# ---------------------------------------------------------------------------
# Scan-column parsing
#
# Every OSSL dataset ships its own column layout: the identifier columns
# differ (KSSL's scan tables lead with id.scan_local_c / id.sample_local_c,
# most others with id.layer_local_c alone), the spectral range differs
# (LUCAS MIR starts at 628 1/cm, MTQ NIR at 1100 nm, Neospectra NIR at
# 1350 nm) and KSSL's VisNIR table stores its odd wavelengths under bare
# integer column names ('351') interleaved with the regular
# scan_visnir.352_ref spelling. So the spectral columns are discovered from
# the header rather than assumed.
# ---------------------------------------------------------------------------


def parse_scan_header(header: list, scan: str) -> tuple:
    """Split a scan table header into (spectral_columns, metadata_columns).

    spectral_columns is a list of (column_index, axis_value) sorted by axis
    value; metadata_columns is a list of (column_index, column_name)."""
    spec = SCAN_DOMAINS[scan]
    prefix, suffix = spec["prefix"], spec["suffix"]
    spectral, metadata = [], []

    for index, raw_name in enumerate(header):
        name = raw_name.strip()
        axis = None
        if name.startswith(prefix):
            token = name[len(prefix) :]
            if token.endswith(suffix):
                token = token[: -len(suffix)]
            axis = _to_float(token)
        elif name.isdigit():
            # KSSL VisNIR: odd wavelengths carry a bare integer as their
            # column name. Accepted only where a prefixed sibling proves
            # this really is a spectral table.
            axis = float(name)
        if axis is not None and axis > 0:
            spectral.append((index, axis, name.startswith(prefix)))
        else:
            metadata.append((index, name))

    if not any(is_prefixed for _, _, is_prefixed in spectral):
        # No properly named spectral column: the bare integers, if any, are
        # not wavelengths. Treat them as metadata.
        metadata.extend((index, header[index].strip()) for index, _, _ in spectral)
        metadata.sort()
        return [], metadata

    spectral = [(index, axis) for index, axis, _ in spectral]
    spectral.sort(key=lambda item: item[1])
    return spectral, metadata


def extract_spectrum(row: list, spectral: list, scan: str, mir_axis: str) -> tuple:
    """Pull one record's spectrum out of a scan-table row, dropping bands
    with no value, and return (axis_values, measurements, unit)."""
    axes, values = [], []
    n_columns = len(row)
    for index, axis in spectral:
        if index >= n_columns:
            continue
        value = _to_float(row[index])
        if value is None:
            continue
        axes.append(axis)
        values.append(value)

    unit = SCAN_DOMAINS[scan]["native_unit"]
    if scan == "mir" and mir_axis == "nm" and axes:
        # Wavenumber -> wavelength inverts the ordering, so re-sort to keep
        # the stored axis ascending like every other i.hyper.lib_* source.
        converted = [(_wavenumber_to_nm(a), v) for a, v in zip(axes, values)]
        converted.sort(key=lambda item: item[0])
        axes = [a for a, _ in converted]
        values = [v for _, v in converted]
        unit = "nm"
    return axes, values, unit


# ---------------------------------------------------------------------------
# Record -> unified i.hyper.lib_* row schema
# ---------------------------------------------------------------------------


def build_row(
    dataset_id: str,
    dataset_title: str,
    scan: str,
    record_id: str,
    site: dict,
    soillab: dict,
    scan_meta: dict,
    axes: list,
    values: list,
    unit: str,
) -> Optional[dict]:
    if not record_id or not axes:
        return None

    longitude = latitude = None
    for key in _SITE_LON_KEYS:
        longitude = _to_float(site.get(key))
        if longitude is not None:
            break
    for key in _SITE_LAT_KEYS:
        latitude = _to_float(site.get(key))
        if latitude is not None:
            break

    # The soil properties paired with each spectrum are what distinguishes
    # the OSSL from the other sources in this library, so they are kept in
    # their own namespace inside extra_metadata rather than flattened in
    # among the site and scan metadata.
    soil_properties = {
        k: v
        for k, v in soillab.items()
        if _clean(v) is not None and k not in _JOIN_KEY_COLUMNS
    }
    extra = {
        "ossl_version": OSSL_VERSION,
        "scan_domain": scan,
        "layer_local_id": record_id,
        "soil_properties": soil_properties,
        "site": {k: v for k, v in site.items() if _clean(v) is not None},
    }
    if scan_meta:
        extra["scan_metadata"] = {
            k: v for k, v in scan_meta.items() if _clean(v) is not None
        }
    if site.get(_LAYER_UUID):
        extra["layer_uuid"] = _clean(site.get(_LAYER_UUID))

    return {
        "source_database": SOURCE_DATABASE,
        "dataset_id": dataset_id,
        "dataset_title": dataset_title,
        "record_id": record_id,
        "organization": _clean(site.get("dataset.owner_utf8_txt"))
        or _clean(site.get("surveyor.title_utf8_txt")),
        "source_url": "https://soilspectroscopy.org/",
        "source_api_url": _clean(site.get("dataset.doi_idf_url"))
        or "https://doi.org/10.1371/journal.pone.0296545",
        "longitude": longitude,
        "latitude": latitude,
        "measurement_type": SCAN_DOMAINS[scan]["measurement_type"],
        "wavelength_unit": unit,
        "n_bands": len(axes),
        "wavelengths": axes,
        "values": values,
        "extra_metadata": json.dumps(extra, default=str),
        "ingest_date": datetime.datetime.now().isoformat(),
    }


class RowFilter:
    """Depth, bounding-box and soil-property filtering applied locally.

    The OSSL API understands most of these server-side, but the bulk files
    do not, and the API's own filtering is applied to stations rather than
    to layers, so the same tests are re-applied here for both routes. That
    makes a filtered harvest give the same answer whichever source is
    chosen."""

    def __init__(self, bbox, depth_min, depth_max, var, var_min, var_max):
        self.bbox = bbox
        self.depth_min = depth_min
        self.depth_max = depth_max
        self.var = var
        self.var_min = var_min
        self.var_max = var_max

    @property
    def active(self) -> bool:
        return any(
            x is not None for x in (self.bbox, self.depth_min, self.depth_max, self.var)
        )

    def keeps(self, site: dict, soillab: dict) -> bool:
        if self.bbox is not None:
            longitude = latitude = None
            for key in _SITE_LON_KEYS:
                longitude = _to_float(site.get(key))
                if longitude is not None:
                    break
            for key in _SITE_LAT_KEYS:
                latitude = _to_float(site.get(key))
                if latitude is not None:
                    break
            if not _in_bbox(longitude, latitude, self.bbox):
                return False

        if self.depth_min is not None:
            upper = _to_float(site.get(_SITE_UPPER_DEPTH))
            if upper is None or upper < self.depth_min:
                return False
        if self.depth_max is not None:
            lower = _to_float(site.get(_SITE_LOWER_DEPTH))
            if lower is None or lower > self.depth_max:
                return False

        if self.var is not None:
            value = _to_float(soillab.get(self.var))
            if value is None:
                return False
            if self.var_min is not None and value < self.var_min:
                return False
            if self.var_max is not None and value > self.var_max:
                return False
        return True


def iter_row_batches(rows: Iterator[dict], batch_size: int) -> Iterator[list]:
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Source: Google Cloud Storage v1.3 bulk files
# ---------------------------------------------------------------------------


def gcs_available_files(timeout: int, retries: int) -> dict:
    """Fetch the published v1.3 URL list and return
    {dataset_code: {ossl_file: public_url}}."""
    response = _http_open(GCS_URL_LIST, timeout, retries)
    if response is None:
        gs.warning(
            "Could not fetch the published v1.3 file list ({}); falling back "
            "to the built-in dataset list and probing each URL.".format(GCS_URL_LIST)
        )
        return {
            code: {
                "ossl_{}_{}.csv.gz".format(
                    table, OSSL_VERSION
                ): "{}/{}/ossl_{}_{}.csv.gz".format(GCS_BASE, code, table, OSSL_VERSION)
                for table in ("soilsite", "soillab", "mir", "visnir", "nir")
            }
            for code in GCS_DATASETS_FALLBACK
        }

    with response:
        text = response.read().decode("utf-8", "replace")
    available: dict = {}
    for record in csv.DictReader(io.StringIO(text)):
        code = (record.get("dataset_code") or "").strip()
        name = (record.get("ossl_file") or "").strip()
        url = (record.get("public_url") or "").strip()
        if code and name and url:
            available.setdefault(code, {})[name] = url
    return available


def _read_keyed_table(reader, label: str) -> tuple:
    """Load a small side table (soilsite / soillab) into
    {id.layer_local_c: {column: value}}. These tables carry one row per
    layer and are at most a few MB, so they are held in memory while the
    large scan table is streamed against them."""
    if reader is None:
        return {}, []
    with reader as handle:
        rows = csv.reader(handle)
        try:
            header = [c.strip() for c in next(rows)]
        except StopIteration:
            gs.warning("{} is empty.".format(label))
            return {}, []
        if _LAYER_LOCAL_ID not in header:
            gs.warning(
                "{} has no {} column; its contents cannot be joined to the "
                "spectra and are skipped.".format(label, _LAYER_LOCAL_ID)
            )
            return {}, header
        key_index = header.index(_LAYER_LOCAL_ID)
        table = {}
        for row in rows:
            if key_index >= len(row):
                continue
            key = _clean(row[key_index])
            if key is None:
                continue
            table[key] = {name: row[i] for i, name in enumerate(header) if i < len(row)}
        return table, header


def gcs_iter_rows(
    code: str,
    scan: str,
    files: dict,
    dataset_id: str,
    dataset_title: str,
    row_filter: RowFilter,
    mir_axis: str,
    cache_dir: Optional[str],
    timeout: int,
    retries: int,
    keep_going: bool,
    counters: dict,
) -> Iterator[dict]:
    """Stream one (dataset, scan domain) pair out of the v1.3 bulk files,
    joining each spectrum to its site and soil-lab record on
    id.layer_local_c -- the only key the v1.3 scan tables carry."""
    scan_file = "ossl_{}_{}.csv.gz".format(scan, OSSL_VERSION)
    scan_url = files.get(scan_file)
    if not scan_url:
        return

    site_table, _ = _read_keyed_table(
        _open_csv_gz(
            files.get("ossl_soilsite_{}.csv.gz".format(OSSL_VERSION), ""),
            cache_dir,
            timeout,
            retries,
            "{} site table".format(code),
        ),
        "{} soilsite".format(code),
    )
    soillab_table, _ = _read_keyed_table(
        _open_csv_gz(
            files.get("ossl_soillab_{}.csv.gz".format(OSSL_VERSION), ""),
            cache_dir,
            timeout,
            retries,
            "{} soil-lab table".format(code),
        ),
        "{} soillab".format(code),
    )

    reader = _open_csv_gz(
        scan_url,
        cache_dir,
        timeout,
        retries,
        "{} {} spectra".format(code, SCAN_DOMAINS[scan]["label"]),
    )
    if reader is None:
        gs.warning("Could not read {} for dataset {}; skipped.".format(scan_file, code))
        return

    with reader as handle:
        rows = csv.reader(handle)
        try:
            header = [c.strip() for c in next(rows)]
        except StopIteration:
            gs.warning("{} {} table is empty.".format(code, scan))
            return
        spectral, metadata = parse_scan_header(header, scan)
        if not spectral:
            gs.warning(
                "No {} spectral columns found in {} for dataset {}; skipped.".format(
                    SCAN_DOMAINS[scan]["label"], scan_file, code
                )
            )
            return
        if _LAYER_LOCAL_ID not in header:
            gs.warning(
                "{} for dataset {} has no {} column, so its spectra cannot be "
                "joined to site or soil data; skipped.".format(
                    scan_file, code, _LAYER_LOCAL_ID
                )
            )
            return
        key_index = header.index(_LAYER_LOCAL_ID)
        meta_names = {index: name for index, name in metadata}

        for row in rows:
            counters["seen"] += 1
            try:
                if key_index >= len(row):
                    continue
                layer_id = _clean(row[key_index])
                if layer_id is None:
                    continue
                site = dict(site_table.get(layer_id, {}))
                site.setdefault(_DATASET_CODE, code)
                soillab = soillab_table.get(layer_id, {})

                if row_filter.active and not row_filter.keeps(site, soillab):
                    counters["filtered"] += 1
                    continue

                axes, values, unit = extract_spectrum(row, spectral, scan, mir_axis)
                if not axes:
                    counters["empty"] += 1
                    continue

                scan_meta = {
                    name: row[index]
                    for index, name in meta_names.items()
                    if index < len(row) and name != _LAYER_LOCAL_ID
                }
                record_id = _record_id(
                    layer_id, _clean(scan_meta.get("id.scan_local_c"))
                )

                built = build_row(
                    dataset_id,
                    dataset_title,
                    scan,
                    record_id,
                    site,
                    soillab,
                    scan_meta,
                    axes,
                    values,
                    unit,
                )
            except Exception as exc:
                message = "Could not build a {} record for dataset {}: {}".format(
                    scan, code, exc
                )
                if keep_going:
                    gs.warning(message)
                    continue
                gs.fatal(message)
                return
            if built is not None:
                yield built


# ---------------------------------------------------------------------------
# Source: experimental OSSL REST API
# ---------------------------------------------------------------------------


def api_datasets(timeout: int, retries: int) -> list:
    codes = _api_get_json("dataset", {}, timeout, retries)
    if not isinstance(codes, list):
        gs.fatal(
            "Could not list datasets from the OSSL API at {}/dataset. The API "
            "is experimental and is sometimes down; consider source=gcs, which "
            "reads the published bulk files instead.".format(API_BASE)
        )
    return [c for c in codes if isinstance(c, str)]


def api_stations(
    code: Optional[str], options: dict, timeout: int, retries: int
) -> list:
    """Resolve the station IDs matching the server-side filters.

    The /data endpoint has no limit/offset parameter, so a dataset has to be
    paged by station ID. Resolving the stations first also yields the exact
    record count, which gives the ingest a real progress percentage."""
    params = {
        "dataset": code,
        "nation": options.get("nation"),
        "state": options.get("state"),
        "bbox": options.get("bbox"),
        "soil_texture": options.get("soil_texture"),
        "depth_min": options.get("depth_min"),
        "depth_max": options.get("depth_max"),
    }
    stations = _api_get_json("station", params, timeout, retries)
    if stations is None:
        return []
    if not isinstance(stations, list):
        gs.warning("Unexpected /station response for dataset {}.".format(code))
        return []
    return [str(s) for s in stations if s not in (None, "")]


def _api_fetch_chunk(
    stations: list, options: dict, timeout: int, retries: int
) -> Optional[dict]:
    """Fetch one station chunk from /data and return the member CSVs as
    {table_name: parsed_rows}. /data answers with a ZIP holding
    soilsite.data.csv, soillab.data.csv, mir.data.csv and visnir.data.csv."""
    params = [("station", s) for s in stations]
    for key in ("var", "var_min", "var_max"):
        if options.get(key):
            params.append((key, options[key]))
    url = "{}/data?{}".format(API_BASE, urllib.parse.urlencode(params))
    response = _http_open(url, timeout, retries)
    if response is None:
        # The API answers an empty match with HTTP 500, so this is reported
        # but is not necessarily an error.
        return None
    with response:
        payload = response.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        gs.warning(
            "The OSSL API returned {} bytes that are not a ZIP archive for a "
            "chunk of {} station(s); skipped.".format(len(payload), len(stations))
        )
        return None

    tables = {}
    for member in archive.namelist():
        name = os.path.basename(member)
        if not name.endswith(".csv"):
            continue
        with archive.open(member) as handle:
            text = io.TextIOWrapper(
                handle, encoding="utf-8", errors="replace", newline=""
            )
            rows = list(csv.reader(text))
        tables[
            name[: -len(".data.csv")]
            if name.endswith(".data.csv")
            else name[: -len(".csv")]
        ] = rows
    return tables


def _index_api_table(rows: list) -> tuple:
    """Index one of the API's CSV tables by id.layer_uuid_txt, falling back
    to id.layer_local_c. Unlike the v1.3 bulk files, the API's tables do
    carry the OSSL UUID, which is the documented join key."""
    if not rows:
        return {}, []
    header = [c.strip() for c in rows[0]]
    key_index = None
    for key in (_LAYER_UUID, _LAYER_LOCAL_ID):
        if key in header:
            key_index = header.index(key)
            break
    if key_index is None:
        return {}, header
    table = {}
    for row in rows[1:]:
        if key_index >= len(row):
            continue
        key = _clean(row[key_index])
        if key is None:
            continue
        table.setdefault(key, []).append(row)
    return table, header


def api_iter_rows(
    code: str,
    scan: str,
    stations: list,
    options: dict,
    dataset_id: str,
    dataset_title: str,
    row_filter: RowFilter,
    mir_axis: str,
    chunk_size: int,
    timeout: int,
    retries: int,
    keep_going: bool,
    counters: dict,
) -> Iterator[dict]:
    """Stream one (dataset, scan domain) pair out of the REST API, paging by
    station chunk."""
    n_chunks = max(1, (len(stations) + chunk_size - 1) // chunk_size)
    for chunk_index in range(n_chunks):
        chunk = stations[chunk_index * chunk_size : (chunk_index + 1) * chunk_size]
        if not chunk:
            continue
        gs.percent(chunk_index, n_chunks, 1)
        tables = _api_fetch_chunk(chunk, options, timeout, retries)
        if tables is None:
            counters["failed_chunks"] += 1
            if not keep_going:
                gs.warning(
                    "No data returned for station chunk {}/{} of dataset {}. "
                    "The OSSL API answers an empty match with HTTP 500, so "
                    "this may simply mean no record in this chunk carries "
                    "{} data.".format(
                        chunk_index + 1,
                        n_chunks,
                        code,
                        SCAN_DOMAINS[scan]["label"],
                    )
                )
            continue

        scan_rows = tables.get(scan, [])
        if len(scan_rows) < 2:
            continue
        site_table, site_header = _index_api_table(tables.get("soilsite", []))
        soillab_table, soillab_header = _index_api_table(tables.get("soillab", []))

        header = [c.strip() for c in scan_rows[0]]
        spectral, metadata = parse_scan_header(header, scan)
        if not spectral:
            continue
        meta_names = {index: name for index, name in metadata}
        key_index = None
        for key in (_LAYER_UUID, _LAYER_LOCAL_ID):
            if key in header:
                key_index = header.index(key)
                break
        if key_index is None:
            gs.warning(
                "The API's {} table carries neither {} nor {}; its rows cannot "
                "be joined to site or soil data and are skipped.".format(
                    scan, _LAYER_UUID, _LAYER_LOCAL_ID
                )
            )
            continue
        local_index = (
            header.index(_LAYER_LOCAL_ID) if _LAYER_LOCAL_ID in header else None
        )

        for row in scan_rows[1:]:
            counters["seen"] += 1
            try:
                if key_index >= len(row):
                    continue
                key = _clean(row[key_index])
                if key is None:
                    continue
                site_rows = site_table.get(key, [])
                site = (
                    {
                        n: site_rows[0][i]
                        for i, n in enumerate(site_header)
                        if i < len(site_rows[0])
                    }
                    if site_rows
                    else {}
                )
                site.setdefault(_DATASET_CODE, code)
                soillab_rows = soillab_table.get(key, [])
                soillab = (
                    {
                        n: soillab_rows[0][i]
                        for i, n in enumerate(soillab_header)
                        if i < len(soillab_rows[0])
                    }
                    if soillab_rows
                    else {}
                )

                if row_filter.active and not row_filter.keeps(site, soillab):
                    counters["filtered"] += 1
                    continue

                axes, values, unit = extract_spectrum(row, spectral, scan, mir_axis)
                if not axes:
                    counters["empty"] += 1
                    continue

                scan_meta = {
                    name: row[index]
                    for index, name in meta_names.items()
                    if index < len(row)
                }
                layer_id = (
                    _clean(row[local_index])
                    if local_index is not None and local_index < len(row)
                    else None
                ) or key
                record_id = _record_id(
                    layer_id, _clean(scan_meta.get("id.scan_local_c"))
                )

                built = build_row(
                    dataset_id,
                    dataset_title,
                    scan,
                    record_id,
                    site,
                    soillab,
                    scan_meta,
                    axes,
                    values,
                    unit,
                )
            except Exception as exc:
                message = "Could not build a {} record for dataset {}: {}".format(
                    scan, code, exc
                )
                if keep_going:
                    gs.warning(message)
                    continue
                gs.fatal(message)
                return
            if built is not None:
                yield built
    gs.percent(n_chunks, n_chunks, 1)


# ---------------------------------------------------------------------------
# Manifest (per-dataset ingest bookkeeping, for incremental/skip-if-complete)
# ---------------------------------------------------------------------------


def load_manifest(root: str) -> dict:
    path = os.path.join(root, MANIFEST_NAME)
    if os.path.isfile(path):
        try:
            with open(path) as handle:
                return json.load(handle)
        except (ValueError, OSError) as exc:
            gs.warning(
                "Could not read {} ({}); starting a fresh one.".format(path, exc)
            )
    return {}


def save_manifest(root: str, manifest: dict) -> None:
    path = os.path.join(root, MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(manifest, handle, indent=2)
    os.replace(tmp, path)


def manifest_key(dataset_id: str) -> str:
    return "{}:{}".format(SOURCE_DATABASE, dataset_id)


# ---------------------------------------------------------------------------
# Parquet (GeoParquet -- OSSL records carry real lat/lon) backend. Identical
# schema and writer strategy to i.hyper.lib_ecosis / i.hyper.lib_usgs /
# i.hyper.lib_relab / i.hyper.lib_gsti, so all five sources land in the same
# partitioned tree and are queryable together.
# ---------------------------------------------------------------------------

_PARQUET_SCHEMA_FIELDS = [
    ("source_database", "string"),
    ("dataset_id", "string"),
    ("dataset_title", "string"),
    ("record_id", "string"),
    ("organization", "string"),
    ("source_url", "string"),
    ("source_api_url", "string"),
    ("longitude", "double"),
    ("latitude", "double"),
    ("measurement_type", "string"),
    ("wavelength_unit", "string"),
    ("n_bands", "int32"),
    ("wavelengths", "list<double>"),
    ("values", "list<double>"),
    ("extra_metadata", "string"),
    ("ingest_date", "string"),
]


def _require_pyarrow():
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        gs.fatal(
            "format=parquet requires the 'pyarrow' package "
            "(pip install pyarrow). Use format=sqlite for a "
            "zero-extra-dependency alternative."
        )


def _has_shapely() -> bool:
    try:
        import shapely  # noqa: F401

        return True
    except ImportError:
        return False


def _geoparquet_metadata() -> bytes:
    return json.dumps(
        {
            "version": "1.1.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                    "crs": None,  # OGC:CRS84 (lon/lat WGS84), GeoParquet default
                }
            },
        }
    ).encode()


def _rows_to_arrow_table(rows: list, include_geometry: bool):
    """One batch of rows -> a pyarrow Table with a fixed schema (whether or
    not this particular batch has any geolocated rows -- include_geometry is
    decided once per run, not per batch, so every batch written to the same
    incremental ParquetWriter has an identical schema)."""
    import pyarrow as pa

    columns = {name: [] for name, _ in _PARQUET_SCHEMA_FIELDS}
    for row in rows:
        for name, _ in _PARQUET_SCHEMA_FIELDS:
            columns[name].append(row.get(name))

    arrays = {
        "source_database": pa.array(columns["source_database"], type=pa.string()),
        "dataset_id": pa.array(columns["dataset_id"], type=pa.string()),
        "dataset_title": pa.array(columns["dataset_title"], type=pa.string()),
        "record_id": pa.array(columns["record_id"], type=pa.string()),
        "organization": pa.array(columns["organization"], type=pa.string()),
        "source_url": pa.array(columns["source_url"], type=pa.string()),
        "source_api_url": pa.array(columns["source_api_url"], type=pa.string()),
        "longitude": pa.array(columns["longitude"], type=pa.float64()),
        "latitude": pa.array(columns["latitude"], type=pa.float64()),
        "measurement_type": pa.array(columns["measurement_type"], type=pa.string()),
        "wavelength_unit": pa.array(columns["wavelength_unit"], type=pa.string()),
        "n_bands": pa.array(columns["n_bands"], type=pa.int32()),
        "wavelengths": pa.array(columns["wavelengths"], type=pa.list_(pa.float64())),
        "values": pa.array(columns["values"], type=pa.list_(pa.float64())),
        "extra_metadata": pa.array(columns["extra_metadata"], type=pa.string()),
        "ingest_date": pa.array(columns["ingest_date"], type=pa.string()),
    }

    if include_geometry:
        from shapely.geometry import Point

        wkb = [
            Point(lon, lat).wkb if lon is not None and lat is not None else None
            for lon, lat in zip(columns["longitude"], columns["latitude"])
        ]
        arrays["geometry"] = pa.array(wkb, type=pa.binary())

    return pa.table(arrays)


def write_parquet_dataset_streaming(
    root: str, dataset_id: str, batch_iter, include_geometry: bool
) -> tuple:
    """One Parquet file per (OSSL dataset, scan domain), under a Hive-style
    source_database=ossl/ partition -- readable together with
    i.hyper.lib_ecosis's source_database=ecosis/, i.hyper.lib_usgs's
    source_database=usgs_splib07/, i.hyper.lib_relab's
    source_database=relab/ and i.hyper.lib_gsti's source_database=gsti/
    partitions by any consumer walking the shared library root."""
    import pyarrow.parquet as pq

    part_dir = os.path.join(root, "source_database={}".format(SOURCE_DATABASE))
    os.makedirs(part_dir, exist_ok=True)
    out_path = os.path.join(part_dir, "dataset_{}.parquet".format(dataset_id))

    writer = None
    n_total = 0
    try:
        for batch_rows in batch_iter:
            if not batch_rows:
                continue
            table = _rows_to_arrow_table(batch_rows, include_geometry)
            if writer is None:
                schema = table.schema
                if include_geometry:
                    schema = schema.with_metadata(
                        {**(schema.metadata or {}), b"geo": _geoparquet_metadata()}
                    )
                writer = pq.ParquetWriter(out_path, schema, compression="zstd")
            writer.write_table(table)
            n_total += len(batch_rows)
    finally:
        if writer is not None:
            writer.close()

    if n_total == 0:
        # Nothing was written, so do not leave a zero-row file behind.
        if os.path.exists(out_path):
            os.remove(out_path)
        return None, 0
    return out_path, n_total


# ---------------------------------------------------------------------------
# SQLite backend (zero extra dependency) -- same table as the other
# i.hyper.lib_* harvesters
# ---------------------------------------------------------------------------

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS spectra (
    source_database TEXT NOT NULL,
    dataset_id      TEXT NOT NULL,
    dataset_title   TEXT,
    record_id       TEXT NOT NULL,
    organization    TEXT,
    source_url      TEXT,
    source_api_url  TEXT,
    longitude       REAL,
    latitude        REAL,
    measurement_type TEXT,
    wavelength_unit TEXT,
    n_bands         INTEGER,
    wavelengths     TEXT,
    values_json     TEXT,
    extra_metadata  TEXT,
    ingest_date     TEXT,
    PRIMARY KEY (source_database, dataset_id, record_id)
);
CREATE INDEX IF NOT EXISTS idx_spectra_dataset ON spectra (source_database, dataset_id);
CREATE INDEX IF NOT EXISTS idx_spectra_geo ON spectra (longitude, latitude);
"""

_SQLITE_INSERT = (
    "INSERT OR REPLACE INTO spectra VALUES "
    "(:source_database,:dataset_id,:dataset_title,:record_id,:organization,"
    ":source_url,:source_api_url,:longitude,:latitude,:measurement_type,"
    ":wavelength_unit,:n_bands,:wavelengths,:values_json,:extra_metadata,:ingest_date)"
)


def write_sqlite_dataset_streaming(root: str, batch_iter) -> tuple:
    db_path = os.path.join(root, "hyperspeclib.sqlite")
    con = sqlite3.connect(db_path)
    n_total = 0
    try:
        con.executescript(_SQLITE_DDL)
        for batch_rows in batch_iter:
            if not batch_rows:
                continue
            con.executemany(
                _SQLITE_INSERT,
                [
                    {
                        **r,
                        "wavelengths": json.dumps(r["wavelengths"]),
                        "values_json": json.dumps(r["values"]),
                    }
                    for r in batch_rows
                ],
            )
            con.commit()
            n_total += len(batch_rows)
    finally:
        con.close()

    if n_total == 0:
        return None, 0
    return db_path, n_total


# ---------------------------------------------------------------------------
# Listings (-l and -n)
# ---------------------------------------------------------------------------


def list_datasets(source: str, timeout: int, retries: int) -> None:
    if source == "api":
        codes = api_datasets(timeout, retries)
        gs.message(
            "OSSL API datasets at {} ({} code(s)); MIR and VisNIR only:".format(
                API_BASE, len(codes)
            )
        )
        for code in codes:
            stations = api_stations(code, {}, timeout, retries)
            print("{}\t{} station(s)".format(code, len(stations)))
        return

    available = gcs_available_files(timeout, retries)
    gs.message(
        "OSSL {} bulk datasets on Google Cloud Storage ({} code(s)):".format(
            OSSL_VERSION, len(available)
        )
    )
    for code in sorted(available):
        scans = [
            scan
            for scan in ("mir", "visnir", "nir")
            if "ossl_{}_{}.csv.gz".format(scan, OSSL_VERSION) in available[code]
        ]
        print("{}\t{}".format(code, ",".join(scans) if scans else "(no spectra)"))


def list_vocabularies(timeout: int, retries: int) -> None:
    for path, label in (("nation", "Nations"), ("var", "Target variables / textures")):
        values = _api_get_json(path, {}, timeout, retries)
        if isinstance(values, list):
            gs.message("{} accepted by the OSSL API ({}):".format(label, len(values)))
            for value in sorted({str(v) for v in values}):
                print(value)
        else:
            gs.warning("Could not list /{} from the OSSL API.".format(path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(options, flags):
    source = options.get("source") or "gcs"
    output_root = options.get("output") or DEFAULT_LIBRARY_ROOT
    fmt = options.get("format") or "parquet"
    mir_axis = options.get("mir_axis") or "nm"
    timeout = int(options.get("timeout") or 600)
    retries = int(options.get("retries") or 3)
    chunk_size = max(1, int(options.get("station_chunk") or 200))
    stream_batch_size = max(1, int(options.get("stream_batch_size") or 2000))
    force = flags["f"]
    keep_going = flags["k"]

    if flags["n"]:
        list_vocabularies(timeout, retries)
        return 0
    if flags["l"]:
        list_datasets(source, timeout, retries)
        return 0

    wanted_scans = [s for s in (options.get("scans") or "").split(",") if s]
    if not wanted_scans:
        wanted_scans = ["mir", "visnir", "nir"]
    if source == "api" and "nir" in wanted_scans:
        gs.warning(
            "The OSSL API serves only MIR and VisNIR; the NIR (Neospectra) "
            "scans exist only in the {} bulk files. Use source=gcs to "
            "harvest them.".format(OSSL_VERSION)
        )
        wanted_scans = [s for s in wanted_scans if s != "nir"]
        if not wanted_scans:
            gs.fatal("No scan domain left to harvest from the OSSL API.")

    wanted_datasets = [
        d.strip() for d in (options.get("datasets") or "").split(",") if d.strip()
    ]

    for key in ("nation", "state", "soil_texture"):
        if source == "gcs" and options.get(key):
            gs.warning(
                "{}= is a server-side OSSL API filter and is ignored with "
                "source=gcs. Use bbox=, depth_min=/depth_max= or var=, which "
                "are applied locally to the bulk files, or switch to "
                "source=api.".format(key)
            )

    row_filter = RowFilter(
        _parse_bbox(options.get("bbox")) if source == "gcs" else None,
        _to_float(options.get("depth_min")),
        _to_float(options.get("depth_max")),
        _clean(options.get("var")),
        _to_float(options.get("var_min")),
        _to_float(options.get("var_max")),
    )

    if fmt == "parquet":
        _require_pyarrow()
    include_geometry = fmt == "parquet" and _has_shapely()
    if fmt == "parquet" and not include_geometry:
        gs.verbose(
            "shapely is not installed, so the Parquet output carries the "
            "longitude/latitude columns but no GeoParquet geometry column."
        )

    cache_dir = options.get("cache_dir") or None
    if cache_dir:
        cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)

    os.makedirs(output_root, exist_ok=True)
    manifest = load_manifest(output_root)

    # Build the work list of (dataset code, scan domain) pairs.
    if source == "gcs":
        available = gcs_available_files(timeout, retries)
        codes = wanted_datasets or sorted(available)
        unknown = [c for c in codes if c not in available]
        if unknown:
            gs.fatal(
                "Unknown OSSL {} dataset code(s): {}. Run with the -l flag to "
                "list the codes available on this source.".format(
                    OSSL_VERSION, ", ".join(unknown)
                )
            )
        work = [
            (code, scan)
            for code in codes
            for scan in wanted_scans
            if "ossl_{}_{}.csv.gz".format(scan, OSSL_VERSION) in available[code]
        ]
    else:
        available = {}
        api_codes = api_datasets(timeout, retries)
        codes = wanted_datasets or api_codes
        unknown = [c for c in codes if c not in api_codes]
        if unknown:
            gs.fatal(
                "Unknown OSSL API dataset code(s): {}. Run with the -l flag to "
                "list the codes the API serves (they differ from the {} bulk "
                "file codes).".format(", ".join(unknown), OSSL_VERSION)
            )
        work = [(code, scan) for code in codes for scan in wanted_scans]

    if not work:
        gs.fatal(
            "Nothing to harvest: no dataset on source={} carries any of the "
            "requested scan domain(s) {}.".format(source, ",".join(wanted_scans))
        )

    gs.message(
        "Harvesting OSSL {} from source={}: {} dataset/scan pair(s).".format(
            OSSL_VERSION, source, len(work)
        )
    )

    n_written = 0
    n_records = 0
    n_skipped = 0
    station_cache: dict = {}

    for index, (code, scan) in enumerate(work):
        gs.percent(index, len(work), 1)
        label = SCAN_DOMAINS[scan]["label"]
        dataset_id = "{}_{}".format(_sanitize_id(code), scan)
        dataset_title = "OSSL {} ({} {} scans)".format(code, OSSL_VERSION, label)
        key = manifest_key(dataset_id)
        previous = manifest.get(key, {})

        counters = {"seen": 0, "filtered": 0, "empty": 0, "failed_chunks": 0}

        if source == "gcs":
            expected = None  # Row count is unknown until the file is streamed.
            if not force and previous.get("n_records") and not row_filter.active:
                gs.verbose(
                    "Skipping '{}': already ingested ({} records). Use the -f "
                    "flag to force re-ingestion.".format(
                        dataset_id, previous["n_records"]
                    )
                )
                n_skipped += 1
                continue
            rows = gcs_iter_rows(
                code,
                scan,
                available[code],
                dataset_id,
                dataset_title,
                row_filter,
                mir_axis,
                cache_dir,
                timeout,
                retries,
                keep_going,
                counters,
            )
        else:
            if code not in station_cache:
                station_cache[code] = api_stations(code, options, timeout, retries)
            stations = station_cache[code]
            if not stations:
                gs.verbose(
                    "No station in dataset {} matches the requested filters.".format(
                        code
                    )
                )
                continue
            expected = len(stations)
            previous_expected = previous.get("expected_total") or 0
            if not force and previous_expected and previous_expected >= expected:
                gs.verbose(
                    "Skipping '{}': already ingested ({} of {} stations). Use "
                    "the -f flag to force re-ingestion.".format(
                        dataset_id, previous.get("n_records", 0), previous_expected
                    )
                )
                n_skipped += 1
                continue
            gs.message(
                "Dataset {} {}: paging {} station(s) in chunks of {}…".format(
                    code, label, expected, chunk_size
                )
            )
            rows = api_iter_rows(
                code,
                scan,
                stations,
                options,
                dataset_id,
                dataset_title,
                row_filter,
                mir_axis,
                chunk_size,
                timeout,
                retries,
                keep_going,
                counters,
            )

        batches = iter_row_batches(rows, stream_batch_size)
        if fmt == "parquet":
            out_path, n_rows = write_parquet_dataset_streaming(
                output_root, dataset_id, batches, include_geometry
            )
        else:
            out_path, n_rows = write_sqlite_dataset_streaming(output_root, batches)

        if counters["failed_chunks"]:
            gs.warning(
                "{} of the station chunks for dataset {} {} returned no data "
                "(the OSSL API answers an empty match with HTTP 500).".format(
                    counters["failed_chunks"], code, label
                )
            )

        if n_rows == 0:
            gs.verbose(
                "Dataset '{}' yielded no usable record ({} source row(s) read, "
                "{} filtered out, {} with no usable band); nothing "
                "written.".format(
                    dataset_id,
                    counters["seen"],
                    counters["filtered"],
                    counters["empty"],
                )
            )
            continue

        manifest[key] = {
            "dataset_title": dataset_title,
            "dataset_code": code,
            "scan_domain": scan,
            "ossl_version": OSSL_VERSION,
            "harvest_source": source,
            "n_records": n_rows,
            "n_source_rows": counters["seen"],
            "n_filtered_out": counters["filtered"],
            "expected_total": expected,
            "filtered": row_filter.active,
            "mir_axis": mir_axis if scan == "mir" else None,
            "last_updated": datetime.datetime.now().isoformat(),
            "path": out_path,
        }
        save_manifest(output_root, manifest)
        n_written += 1
        n_records += n_rows
        gs.verbose(
            "Wrote {} record(s) for '{}' -> {}".format(n_rows, dataset_id, out_path)
        )

    gs.percent(len(work), len(work), 1)
    gs.message(
        "Done: {} dataset/scan pair(s) ingested ({} records), {} already up to "
        "date, library at {} (format={}).".format(
            n_written, n_records, n_skipped, output_root, fmt
        )
    )
    return 0


if __name__ == "__main__":
    options, flags = gs.parser()
    sys.exit(main(options, flags))
