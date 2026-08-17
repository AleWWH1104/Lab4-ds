"""Evidence-driven Spanish report generation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


def _lake_name(value: str) -> str:
    return {"atitlan": "Atitlán", "amatitlan": "Amatitlán"}.get(value, value.title())


def _association(value: float) -> str:
    if pd.isna(value):
        return "no estimable"
    strength = "débil" if abs(value) < 0.3 else "moderada" if abs(value) < 0.7 else "fuerte"
    direction = "positiva" if value > 0 else "negativa"
    return f"{strength} {direction} (r={value:.2f})"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    separator = ["---"] * len(headers)
    return "\n".join("| " + " | ".join(row) + " |" for row in [headers, separator, *rows])


def _format_number(value: float, decimals: int = 1, signed: bool = False) -> str:
    if pd.isna(value):
        return "no estimable"
    sign = "+" if signed else ""
    return f"{value:{sign}.{decimals}f}"


def _temporal_section(summary: pd.DataFrame) -> tuple[str, str]:
    findings = []
    tables = []
    for lake, group in summary.groupby("lake"):
        group = group.sort_values("date")
        peak_extent = group.loc[group["high_value_percent"].idxmax()]
        peak_mean = group.loc[group["mean_chlorophyll_proxy"].idxmax()]
        findings.append(
            f"- **{_lake_name(lake)}:** la extensión alta fluctuó entre "
            f"{group['high_value_percent'].min():.1f}% y "
            f"{group['high_value_percent'].max():.1f}%. La fecha crítica por extensión fue "
            f"{peak_extent['date']} ({peak_extent['high_value_percent']:.1f}%); la mayor media "
            f"interpretable ocurrió el {peak_mean['date']} "
            f"({peak_mean['mean_chlorophyll_proxy']:.2f}). La cobertura del proxy interpretable "
            f"varió entre {group['chlorophyll_coverage_percent'].min():.1f}% y "
            f"{group['chlorophyll_coverage_percent'].max():.1f}% del agua válida."
        )
        if peak_mean["chlorophyll_coverage_percent"] < 50:
            findings.append(
                f"  La media máxima de {_lake_name(lake)} requiere cautela: solo "
                f"{peak_mean['chlorophyll_coverage_percent']:.1f}% del agua válida tuvo un proxy "
                "dentro del intervalo interpretable en esa fecha."
            )
        rows = [
            [
                str(row["date"]),
                f"{row['mean_chlorophyll_proxy']:.2f}",
                f"{row['high_value_percent']:.1f}",
                f"{row['surface_bloom_percent']:.2f}",
                f"{row['chlorophyll_coverage_percent']:.1f}",
                f"{row['negative_proxy_percent']:.1f}",
                f"{row['above_calibration_percent']:.1f}",
            ]
            for _, row in group.iterrows()
        ]
        tables.append(
            f"### {_lake_name(lake)}\n\n"
            + _table(
                [
                    "Fecha",
                    "Media proxy",
                    "Área alta (%)",
                    "FAI (%)",
                    "Proxy válido (%)",
                    "Negativo (%)",
                    ">=500 (%)",
                ],
                rows,
            )
        )
    return "\n".join(findings), "\n\n".join(tables)


def _spatial_section(zones: pd.DataFrame) -> tuple[str, str, str]:
    findings = []
    recommendations = []
    for lake, group in zones.groupby("lake"):
        concentration = group.loc[group["mean_chlorophyll_proxy"].idxmax()]
        persistence = group.loc[group["persistent_area_percent"].idxmax()]
        change = group.loc[group["change_first_last_pp"].abs().idxmax()]
        findings.append(
            f"- **{_lake_name(lake)}:** el cuadrante {concentration['zone']} tuvo la mayor media "
            f"ponderada del proxy ({concentration['mean_chlorophyll_proxy']:.2f}); el cuadrante "
            f"{persistence['zone']} presentó la mayor superficie persistente "
            f"({persistence['persistent_area_percent']:.1f}% de celdas evaluables). "
            "El mayor cambio "
            f"entre primera y última fecha ocurrió en {change['zone']} "
            f"({change['change_first_last_pp']:+.1f} puntos porcentuales)."
        )
        recommendations.append(
            f"- En {_lake_name(lake)}, priorizar verificación de campo en el cuadrante "
            f"{persistence['zone']} y contrastarla con el cuadrante de mayor media "
            f"({concentration['zone']}); las coordenadas exactas están en "
            "`spatial_zones.csv`."
        )
    rows = [
        [
            _lake_name(row["lake"]),
            row["zone"],
            _format_number(row["mean_chlorophyll_proxy"], 2),
            _format_number(row["mean_high_value_percent"]),
            _format_number(row["persistent_area_percent"]),
            _format_number(row["first_high_value_percent"]),
            _format_number(row["last_high_value_percent"]),
            _format_number(row["change_first_last_pp"], signed=True),
        ]
        for _, row in zones.sort_values(["lake", "zone"]).iterrows()
    ]
    table = _table(
        [
            "Lago",
            "Cuadrante",
            "Media proxy",
            "Área alta media (%)",
            "Persistente (%)",
            "Primera (%)",
            "Última (%)",
            "Cambio (pp)",
        ],
        rows,
    )
    return "\n".join(findings), table, "\n".join(recommendations)


def _correlation_section(correlations: pd.DataFrame) -> tuple[str, str]:
    overall = correlations[correlations["date"] == "all"].sort_values(["lake", "index"])
    findings = []
    for lake, group in overall.groupby("lake"):
        descriptions = [
            f"{row['index'].upper()}: {_association(row['pearson_r'])}, n={int(row['n'])}"
            for _, row in group.iterrows()
        ]
        findings.append(f"- **{_lake_name(lake)}:** " + "; ".join(descriptions) + ".")
    rows = [
        [
            _lake_name(row["lake"]),
            row["index"].upper(),
            str(int(row["n"])),
            f"{row['pearson_r']:.3f}",
            _association(row["pearson_r"]).split(" (")[0],
        ]
        for _, row in overall.iterrows()
    ]
    return "\n".join(findings), _table(
        ["Lago", "Índice", "Pares válidos", "Pearson r", "Lectura"], rows
    )


def _comparison_section(comparison: pd.DataFrame) -> str:
    rows = [
        [
            _lake_name(row["lake"]),
            str(int(row["observations"])),
            f"{row['mean_chlorophyll_proxy']:.2f}",
            f"{row['maximum_chlorophyll_proxy']:.2f}",
            f"{row['mean_high_value_percent']:.1f}",
            f"{row['maximum_high_value_percent']:.1f}",
            f"{row['bloom_date_frequency_percent']:.1f}",
        ]
        for _, row in comparison.sort_values("lake").iterrows()
    ]
    return _table(
        [
            "Lago",
            "Fechas",
            "Media temporal proxy",
            "Máxima media",
            "Área alta media (%)",
            "Área alta máxima (%)",
            "Fechas >=5% (%)",
        ],
        rows,
    )


def _exploratory_section(sensitivity: pd.DataFrame, seasonal: pd.DataFrame) -> tuple[str, str, str]:
    sensitivity_summary = (
        sensitivity.groupby(["lake", "threshold"], as_index=False)["high_value_percent"]
        .agg(["mean", "max"])
        .reset_index()
    )
    sensitivity_rows = [
        [
            _lake_name(row["lake"]),
            f"{row['threshold']:.0f}",
            f"{row['mean']:.1f}",
            f"{row['max']:.1f}",
        ]
        for _, row in sensitivity_summary.iterrows()
    ]
    season_lines = []
    season_rows = []
    for lake, group in seasonal.groupby("lake"):
        details = [
            f"{row['season']} (n={int(row['observations'])}, área alta media "
            f"{row['mean_high_percent']:.1f}%, proxy medio {row['mean_proxy']:.2f})"
            for _, row in group.iterrows()
        ]
        season_lines.append(f"- **{_lake_name(lake)}:** " + "; ".join(details) + ".")
        for _, row in group.iterrows():
            season_rows.append(
                [
                    _lake_name(lake),
                    row["season"],
                    str(int(row["observations"])),
                    f"{row['mean_proxy']:.2f}",
                    f"{row['mean_high_percent']:.1f}",
                ]
            )
    return (
        _table(["Lago", "Umbral", "Área media (%)", "Máxima (%)"], sensitivity_rows),
        "\n".join(season_lines),
        _table(["Lago", "Época", "n", "Proxy medio", "Área alta media (%)"], season_rows),
    )


def generate_report(
    config: dict[str, Any],
    template_path: Path = Path("report/plantilla.md"),
    output_path: Path = Path("report/informe.md"),
    table_root: Path = Path("outputs/tables"),
    build_pdf: bool = False,
) -> tuple[Path, Path | None]:
    template = template_path.read_text(encoding="utf-8")
    summary_path = table_root / "temporal_summary.csv"
    replacements = {
        "{{THRESHOLD}}": str(config["analysis"]["high_chlorophyll_threshold"]),
        "{{SENSITIVITY}}": ", ".join(map(str, config["analysis"]["sensitivity_thresholds"])),
    }
    if not summary_path.exists():
        pending = (
            "**Estado: adquisición en vivo pendiente.** Por integridad científica, este informe "
            "no presenta hallazgos hasta disponer de las tablas calculadas."
        )
        for marker in (
            "STATUS",
            "EXECUTIVE",
            "TEMPORAL",
            "TEMPORAL_TABLES",
            "SPATIAL",
            "SPATIAL_TABLE",
            "CORRELATIONS",
            "CORRELATION_TABLE",
            "COMPARISON_TABLE",
            "SENSITIVITY_TABLE",
            "SEASONALITY",
            "SEASONALITY_TABLE",
            "ZONE_RECOMMENDATIONS",
        ):
            replacements[f"{{{{{marker}}}}}"] = pending
    else:
        summary = pd.read_csv(summary_path)
        comparison = pd.read_csv(table_root / "lake_comparison.csv")
        correlations = pd.read_csv(table_root / "pixel_correlations.csv")
        sensitivity = pd.read_csv(table_root / "threshold_sensitivity.csv")
        seasonal = pd.read_csv(table_root / "exploratory_seasonality.csv")
        zones = pd.read_csv(table_root / "spatial_zones.csv")
        temporal, temporal_tables = _temporal_section(summary)
        spatial, spatial_table, zone_recommendations = _spatial_section(zones)
        correlation, correlation_table = _correlation_section(correlations)
        sensitivity_table, seasonality, seasonality_table = _exploratory_section(
            sensitivity, seasonal
        )
        most_extensive = comparison.loc[comparison["mean_high_value_percent"].idxmax()]
        replacements |= {
            "{{STATUS}}": (
                f"Se analizaron {len(summary)} de 22 escenas oficiales a partir de los GeoTIFF "
                "persistidos y validados, sin una nueva descarga."
            ),
            "{{EXECUTIVE}}": (
                f"En el período observado, {_lake_name(most_extensive['lake'])} presentó la mayor "
                f"extensión alta media ({most_extensive['mean_high_value_percent']:.1f}%) y "
                f"{most_extensive['bloom_date_frequency_percent']:.1f}% de fechas con al menos 5% "
                "de extensión alta. Estas señales ópticas orientan vigilancia; no demuestran "
                "toxicidad, especie ni causa."
            ),
            "{{TEMPORAL}}": temporal,
            "{{TEMPORAL_TABLES}}": temporal_tables,
            "{{SPATIAL}}": spatial,
            "{{SPATIAL_TABLE}}": spatial_table,
            "{{CORRELATIONS}}": correlation,
            "{{CORRELATION_TABLE}}": correlation_table,
            "{{COMPARISON_TABLE}}": _comparison_section(comparison),
            "{{SENSITIVITY_TABLE}}": sensitivity_table,
            "{{SEASONALITY}}": seasonality,
            "{{SEASONALITY_TABLE}}": seasonality_table,
            "{{ZONE_RECOMMENDATIONS}}": zone_recommendations,
        }
    content = template
    for marker, value in replacements.items():
        content = content.replace(marker, value)
    if not summary_path.exists():
        content = (
            "\n".join(line for line in content.splitlines() if not line.startswith("![")) + "\n"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    pdf_path = None
    if build_pdf:
        if not shutil.which("pandoc") or not shutil.which("xelatex"):
            raise RuntimeError("pandoc and xelatex are required to build the PDF")
        pdf_path = output_path.with_suffix(".pdf")
        subprocess.run(
            ["pandoc", output_path.name, "--pdf-engine=xelatex", "-o", pdf_path.name],
            cwd=output_path.parent,
            check=True,
        )
    return output_path, pdf_path
