# ruff: noqa: E501
"""Build the offline, executable Laboratory 4 Part 2 notebook."""

from pathlib import Path

import nbformat as nbf


def markdown(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


cells = [
    markdown(
        """
# Laboratorio 4, Parte 2: clasificación geoespacial de cianobacteria

**CC3084 – Data Science**  
**Integrantes:** Iris Ayala, Anggie Quezada y Jonathan Diaz

Esta entrega parcial reproduce, sin red ni credenciales, los ejercicios 1–7 y la validación temporal a partir de los 22 GeoTIFF locales de Sentinel-2. Únicamente los ejercicios 8–10 quedan identificados al final como trabajo **no implementado**.

> **Alcance científico.** La respuesta representa una categoría construida a partir de un **proxy satelital** de clorofila-a y la detección espectral FAI; no es una medición sanitaria, una identificación taxonómica de cianobacterias ni una medición de toxinas. Los resultados sirven para priorizar observación y muestreo de campo, no para emitir alertas de salud pública.
"""
    ),
    markdown(
        """
## Plan de esfuerzo de la entrega parcial

Los ejercicios 1–3 son correcciones completas y no se contabilizan como trabajo nuevo. Para el esfuerzo restante se estimaron **unidades completas**, evitando dejar incisos parcialmente implementados.

| Unidad restante | Estado | Esfuerzo relativo |
|---|---:|---:|
| Ejercicio 4: tres modelos, split común y ajuste | Implementado | 10 % |
| Ejercicio 5: métricas, matrices e interpretación | Implementado | 12 % |
| Ejercicio 6: bloques UTM, mapa y GroupKFold | Implementado | 18 % |
| Validación temporal cronológica y comparación | Implementado | 10 % |
| Ejercicio 7: transferencia entre lagos | Implementado | 15 % |
| Ejercicio 8: importancia y SHAP | TODO | 12 % |
| Ejercicio 9: mapas predictivos y errores | TODO | 13 % |
| Ejercicio 10: conclusiones integrales | TODO | 10 % |
| **Total implementado nuevo** |  | **65 %** |
| **Total pendiente (ejercicios 8–10)** |  | **35 %** |
"""
    ),
    markdown(
        """
## Método reproducible y controles contra fuga

- Se leen únicamente `data/raw/<lago>/*.tif` y su producto alineado en `data/processed`; no se realiza adquisición.
- La población elegible exige agua, máscara válida, `dataMask=1`, exclusión SCL de NoData/defectos/sombra/nube/cirrus/nieve y valores espectrales finitos.
- La respuesta es estrictamente `0/1`: `1` si el proxy es ≥20 o el detector FAI marca floración superficial; `0` en caso contrario. El umbral de 20 µg/L-equivalente es un corte operacional coherente con el análisis de Parte 1 y con un estado eutrófico aproximado en la escala trófica de Carlson. **No se interpreta como límite sanitario.**
- La transformación NDCI–clorofila sigue el modelo del script CyanoLakes descrito por Kravitz y Matthews (2020). La incertidumbre de transferencia óptica y la falta de validación in situ obligan a hablar de proxy.
- Se excluyen de los predictores el target, proxy, NDCI, FAI/floración, B04, B05, B07 y B8A. También se excluye NDVI porque usa B04. NDVI y NDWI se conservan en el dataset por la rúbrica, pero no entrenan los modelos. Coordenadas, fecha y lago se conservan para validación y trazabilidad, pero tampoco se usan como predictores para impedir memorización espacial/temporal o de identidad del lago.
- Predictores defendibles: B02, B03, B08, B11 y B12. No forman NDCI ni FAI. Aunque algunas participan en la máscara de agua, no construyen directamente la respuesta.
- Para limitar costo, se toma una muestra determinista (`seed=42`) de hasta 500 observaciones por lago–fecha–clase. Antes del muestreo se guardan conteos completos de población. Así nunca se materializan los 16.5 millones de píxeles, inválidos en su mayoría.

**Referencias.** Carlson, R. E. (1977), *A trophic state index for lakes*, Limnology and Oceanography 22(2), 361–369, https://doi.org/10.4319/lo.1977.22.2.0361. Kravitz, J. y Matthews, M. (2020), *Chlorophyll-a for cyanobacteria blooms from Sentinel-2*, Remote Sensing of Environment 247, 111906, https://doi.org/10.1016/j.rse.2020.111906. WHO (2021), *Guidelines on recreational water quality, Volume 1*; la evaluación sanitaria requiere evidencia adicional, no solo color oceánico.
"""
    ),
    code(
        """
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from IPython.display import Image, display

from lab4_ds.ml import (
    PREDICTORS,
    TARGET_THRESHOLD,
    add_spatial_blocks,
    build_ml_dataset,
    chronological_split_indices,
    evaluate_cross_lake,
    evaluate_models,
    evaluate_spatial_cv,
    evaluate_temporal_holdout,
    random_split_indices,
    tune_models,
)

RANDOM_STATE = 42
EVIDENCE_DIR = Path("outputs/tables")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
pd.set_option("display.max_columns", 30)
pd.set_option("display.precision", 4)
sns.set_theme(style="whitegrid", context="notebook")


def display_figure(figure):
    # Render explicitly because the execution environment uses the non-interactive Agg backend.
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
    display(Image(data=buffer.getvalue()))
    plt.close(figure)
"""
    ),
    markdown(
        """
## Ejercicio 1 — Preparación, limpieza y EDA

La función reutilizable recorre cada escena una sola vez, calcula estadísticas sobre todos los píxeles y materializa únicamente la muestra estratificada válida. Las coordenadas corresponden al centro de cada píxel según el `Affine` del GeoTIFF.
"""
    ),
    code(
        """
bundle = build_ml_dataset(maximum_per_scene_class=500, random_state=RANDOM_STATE)
data = bundle.sample
population = bundle.population

population.to_csv(EVIDENCE_DIR / "ml_population_by_scene.csv", index=False)

global_population = population[["raster_pixels", "valid_water_pixels", "eligible_pixels", "class_0", "class_1", "sampled_pixels"]].sum().to_frame("count")
by_lake = population.groupby("lake")[["raster_pixels", "valid_water_pixels", "eligible_pixels", "class_0", "class_1", "sampled_pixels"]].sum()

print(f"Observaciones elegibles en la población: {population['eligible_pixels'].sum():,}")
print(f"Observaciones en la muestra reproducible: {len(data):,}")
print(f"Escenas locales: {len(population)}")
display(global_population)
display(by_lake)
display(population)
"""
    ),
    code(
        """
schema = pd.DataFrame({
    "variable": data.columns,
    "dtype": data.dtypes.astype(str).values,
    "missing_n": data.isna().sum().values,
    "missing_percent": (data.isna().mean().mul(100)).values,
})
display(schema)
display(data.describe(include="all").T)
"""
    ),
    code(
        """
fig, axes = plt.subplots(2, 3, figsize=(14, 8))
for variable, axis in zip(PREDICTORS, axes.flat, strict=False):
    sns.histplot(data=data, x=variable, hue="target", bins=35, stat="density", common_norm=False, element="step", ax=axis)
    axis.set_title(f"Distribución de {variable} por clase")
axes.flat[-1].axis("off")
fig.suptitle("EDA de predictores sobre la muestra estratificada", y=1.02)
plt.tight_layout()
display_figure(fig)

display(data.groupby(["lake", "target"])[list(PREDICTORS)].agg(["mean", "std"]).round(4))
"""
    ),
    markdown(
        """
**Interpretación del ejercicio 1.** Los conteos de población, y no la muestra balanceada por estratos, son la referencia para describir cobertura y prevalencia. La muestra solo reduce el costo de entrenamiento. No hay imputación: una observación con predictor no finito queda excluida. La unidad observacional sigue siendo el píxel-fecha; por ello existe dependencia entre píxeles vecinos y entre observaciones repetidas de una zona, problema que se trata explícitamente en las validaciones espacial y temporal.
"""
    ),
    markdown(
        """
## Ejercicio 2 — Respuesta binaria, distribución y desbalance

La clase positiva combina dos ramas del algoritmo de origen: proxy NDCI ≥20 y FAI de floración superficial. Este diseño evita convertir la ausencia de una estimación de clorofila en un negativo cuando FAI detecta una capa superficial. El corte es útil como regla de análisis ambiental, pero **no demuestra presencia de una especie, toxicidad ni riesgo sanitario**.
"""
    ),
    code(
        """
population_distribution = population[["class_0", "class_1"]].sum()
population_prevalence = population_distribution["class_1"] / population_distribution.sum()
distribution_by_lake = population.groupby("lake")[["class_0", "class_1"]].sum()
distribution_by_lake["positive_percent"] = 100 * distribution_by_lake["class_1"] / distribution_by_lake[["class_0", "class_1"]].sum(axis=1)
distribution_by_date = population[["lake", "date", "class_0", "class_1"]].copy()
distribution_by_date["positive_percent"] = 100 * distribution_by_date["class_1"] / distribution_by_date[["class_0", "class_1"]].sum(axis=1)

print(f"Prevalencia positiva real: {population_prevalence:.2%}")
print(f"Razón mayoría/minoría: {population_distribution.max() / population_distribution.min():.2f}:1")
display(population_distribution.to_frame("count"))
display(distribution_by_lake)
display(distribution_by_date)

fig, ax = plt.subplots(figsize=(12, 4))
sns.barplot(data=distribution_by_date, x="date", y="positive_percent", hue="lake", ax=ax)
ax.tick_params(axis="x", rotation=70)
ax.set_ylabel("Clase positiva (%)")
ax.set_title("Distribución poblacional de la respuesta por lago y fecha")
plt.tight_layout()
display_figure(fig)
"""
    ),
    markdown(
        """
**Consecuencia del desbalance.** Accuracy puede parecer alta si un modelo favorece la clase mayoritaria. Por eso se reportan precision, recall, F1 y ROC-AUC, se usan pesos balanceados y se ajustan hiperparámetros con F2, que pondera recall más que precision. Ambientalmente, un falso negativo puede omitir una zona que merece inspección; un falso positivo consume recursos de verificación. Se prioriza reducir falsos negativos sin afirmar que toda señal positiva sea una floración tóxica.

Como el test proviene de la muestra estratificada, precision, accuracy y matrices describen ese diseño de evaluación y no una prevalencia operativa de campo. Para estimar valores predictivos en despliegue sería necesario validar sobre una muestra representativa o recalibrar con la prevalencia poblacional.

**Fuga identificada.** `target`, `cyanobacteria_proxy`, `ndci`, `surface_bloom`, B04/B05 (NDCI), B04/B07/B8A (FAI) y cualquier clase derivada están prohibidos. NDVI también queda fuera porque usa B04. NDWI se conserva, pero se excluye del modelo para mantener un conjunto espectral simple y evitar incorporar un índice ya empleado en la selección de agua.
"""
    ),
    markdown("## Ejercicio 3 — Selección y justificación de variables"),
    code(
        """
variable_catalog = pd.DataFrame([
    ("B02", "Azul", "Banda espectral", "Sí", "Respuesta óptica independiente de NDCI/FAI; puede capturar dispersión y turbidez."),
    ("B03", "Verde", "Banda espectral", "Sí", "Aporta contraste del agua y material suspendido sin formar el target."),
    ("B04", "Rojo", "Banda espectral", "No", "Fuga: participa en NDCI y FAI."),
    ("B05", "Borde rojo 1", "Banda espectral", "No", "Fuga: participa directamente en NDCI."),
    ("B07", "Borde rojo 3", "Banda espectral", "No", "Fuga: participa directamente en FAI."),
    ("B08", "Infrarrojo cercano", "Banda espectral", "Sí", "Describe respuesta del agua/partículas y no forma NDCI ni FAI."),
    ("B8A", "NIR estrecho", "Banda espectral", "No", "Fuga: participa directamente en FAI."),
    ("B11", "SWIR 1", "Banda espectral", "Sí", "Puede capturar humedad y contraste agua-tierra; independiente del target."),
    ("B12", "SWIR 2", "Banda espectral", "Sí", "Complementa discriminación espectral del agua sin formar el target."),
    ("NDVI", "Vegetación", "Índice", "No", "Se conserva por rúbrica, pero usa B04, banda del target."),
    ("NDWI", "Agua", "Índice", "No", "Se conserva para EDA; ya interviene conceptualmente en selección de agua."),
    ("NDCI/proxy/FAI", "Señal objetivo", "Índice/derivada", "No", "Construyen directa o indirectamente la respuesta."),
    ("Longitud/latitud", "Posición", "Espacial", "No", "Se usan para bloques; entrenar con ellas memorizaría zonas."),
    ("Fecha", "Adquisición", "Temporal", "No", "Se usa para corte cronológico; no se codifica para evitar memorizar campañas."),
    ("Lago", "Identidad", "Categórica", "No", "Se conserva para estratos y reporte; podría inflar generalización interna."),
], columns=["variable", "meaning", "class", "used_as_predictor", "justification"])
display(variable_catalog)
print("Predictores finales:", ", ".join(PREDICTORS))
"""
    ),
    markdown(
        """
No se agrega ingeniería de características: cocientes o índices nuevos podrían reconstruir parcialmente la señal objetivo, y con solo 22 fechas aumentarían complejidad sin evidencia independiente. Esta decisión favorece auditabilidad sobre una mejora aparente.
"""
    ),
    markdown("## Ejercicios 4 y 5 — Modelos, ajuste y evaluación aleatoria común"),
    code(
        """
random_train, random_test = random_split_indices(data, random_state=RANDOM_STATE)
models, tuning = tune_models(data, random_train, random_state=RANDOM_STATE)
random_metrics = evaluate_models(models, data, random_test, strategy="random_70_30")

tuning.to_csv(EVIDENCE_DIR / "ml_tuning.csv", index=False)
random_metrics.to_csv(EVIDENCE_DIR / "ml_random_metrics.csv", index=False)

print(f"Train: {len(random_train):,} ({len(random_train)/len(data):.1%}); test común: {len(random_test):,} ({len(random_test)/len(data):.1%})")
display(tuning)
display(random_metrics)
"""
    ),
    markdown(
        """
Los tres modelos usan exactamente el mismo test estratificado 30 %. El ajuste ocurre solo dentro del 70 % de training mediante validación estratificada de tres folds. Se exploran rejillas pequeñas para controlar costo: `C` en logística; profundidad y mínimo por hoja en Random Forest; tasa de aprendizaje en Gradient Boosting. El criterio F2 prioriza sensibilidad sin ignorar precision. Los pesos de clase se calculan únicamente sobre cada training.
"""
    ),
    code(
        """
fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
for axis, row in zip(axes, random_metrics.itertuples(), strict=True):
    matrix = np.array([[row.tn, row.fp], [row.fn, row.tp]])
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar=False, ax=axis)
    axis.set_title(row.model)
    axis.set_xlabel("Predicción")
    axis.set_ylabel("Real")
    axis.set_xticklabels([0, 1])
    axis.set_yticklabels([0, 1], rotation=0)
plt.suptitle("Matrices de confusión — test aleatorio común")
plt.tight_layout()
display_figure(fig)

best_random = random_metrics.sort_values(["recall", "f1"], ascending=False).iloc[0]
print(f"Mayor recall aleatorio: {best_random['model']} ({best_random['recall']:.3f}); falsos negativos: {best_random['fn']}.")
print("La selección ambiental se apoya primero en recall y después en F1; ROC-AUC describe ordenamiento, no el costo operativo del umbral 0.5.")
"""
    ),
    markdown("## Ejercicio 6 — Validación espacial con bloques de 1 km"),
    code(
        """
spatial_data = add_spatial_blocks(data, block_size_m=1_000)
block_counts = spatial_data.groupby(["lake", "spatial_block"], as_index=False).agg(observations=("target", "size"), positives=("target", "sum"), dates=("date", "nunique"))
block_summary = block_counts.groupby("lake").agg(blocks=("spatial_block", "nunique"), min_observations=("observations", "min"), median_observations=("observations", "median"), max_observations=("observations", "max"), total_observations=("observations", "sum"))

block_counts.to_csv(EVIDENCE_DIR / "ml_spatial_block_counts.csv", index=False)
display(block_summary)
display(block_counts)
"""
    ),
    code(
        """
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for axis, (lake, lake_data) in zip(axes, spatial_data.groupby("lake"), strict=True):
    block_codes = pd.Categorical(lake_data["spatial_block"]).codes
    scatter = axis.scatter(lake_data["x_utm"], lake_data["y_utm"], c=block_codes, s=4, cmap="tab20", alpha=0.65)
    axis.set_title(f"{lake.title()}: {lake_data['spatial_block'].nunique()} bloques")
    axis.set_xlabel("Este UTM 15N (m)")
    axis.set_ylabel("Norte UTM 15N (m)")
    axis.set_aspect("equal")
plt.suptitle("Muestra válida asignada a bloques regulares de 1 km — EPSG:32615")
plt.tight_layout()
display_figure(fig)
"""
    ),
    markdown(
        """
El tamaño solicitado produce varios grupos con observaciones en ambos lagos y permite cinco folds externos. El identificador incluye lago y celda, por lo que una celda nunca se comparte entre training y validación. La evaluación es **anidada**: para cada test espacial externo se realiza un tuning nuevo dentro del training externo mediante GroupKFold interno de tres folds. Tanto los folds externos como los internos mantienen bloques íntegros; ninguna etiqueta del test externo participa en la selección de hiperparámetros. Si un test fold contiene una sola clase, ROC-AUC se deja como `NaN`; no se inventa un valor.
"""
    ),
    code(
        """
spatial_folds, spatial_tuning = evaluate_spatial_cv(
    spatial_data, n_splits=5, inner_splits=3, random_state=RANDOM_STATE
)
spatial_folds.to_csv(EVIDENCE_DIR / "ml_spatial_fold_metrics.csv", index=False)
spatial_tuning.to_csv(EVIDENCE_DIR / "ml_spatial_tuning.csv", index=False)
spatial_summary = spatial_folds[spatial_folds["status"] == "ok"].groupby("model", as_index=False)[["accuracy", "precision", "recall", "f1", "roc_auc"]].mean()
display(spatial_folds)
display(spatial_tuning)
display(spatial_summary)
assert spatial_tuning["outer_test_tuning_overlap"].eq(0).all()
assert spatial_tuning["maximum_inner_group_overlap"].eq(0).all()
"""
    ),
    markdown("## Validación temporal — entrenamiento en pasado, evaluación en futuro"),
    code(
        """
temporal_train, temporal_test, temporal_cutoff = chronological_split_indices(data, train_fraction=0.70)
temporal_metrics, temporal_tuning = evaluate_temporal_holdout(
    data,
    temporal_train,
    temporal_test,
    inner_splits=3,
    random_state=RANDOM_STATE,
)
temporal_metrics.to_csv(EVIDENCE_DIR / "ml_temporal_metrics.csv", index=False)
temporal_tuning.to_csv(EVIDENCE_DIR / "ml_temporal_tuning.csv", index=False)

print(f"Última fecha de training: {pd.Timestamp(data.iloc[temporal_train]['date'].max()).date()}")
print(f"Primera fecha de test: {pd.Timestamp(data.iloc[temporal_test]['date'].min()).date()}")
print(f"Training temporal: {len(temporal_train):,}; test futuro: {len(temporal_test):,}")
print("Fechas de test:", ", ".join(str(pd.Timestamp(value).date()) for value in sorted(data.iloc[temporal_test]['date'].unique())))
display(temporal_metrics)
display(temporal_tuning)
assert temporal_tuning["future_test_tuning_overlap"].eq(0).all()
assert (temporal_tuning["latest_tuning_date"] < temporal_tuning["earliest_future_test_date"]).all()
"""
    ),
    markdown(
        """
El corte se calcula sobre fechas globalmente ordenadas: 70 % de fechas tempranas para training y 30 % posteriores para test. Por construcción, `max(train_date) < min(test_date)`. El tuning temporal también es independiente: usa tres divisiones internas de ventana expansiva dentro del período pasado, y en cada una las fechas de entrenamiento preceden estrictamente a las fechas de validación. Luego se reajusta la mejor configuración sobre todo el pasado y se evalúa una sola vez sobre el futuro. Ni etiquetas ni filas futuras intervienen en la selección.
"""
    ),
    code(
        """
random_comparison = random_metrics[["model", "accuracy", "precision", "recall", "f1", "roc_auc"]].assign(strategy="random_70_30")
spatial_comparison = spatial_summary.assign(strategy="spatial_groupkfold")
temporal_comparison = temporal_metrics[["model", "accuracy", "precision", "recall", "f1", "roc_auc"]].assign(strategy="temporal_future")
comparison = pd.concat([random_comparison, spatial_comparison, temporal_comparison], ignore_index=True)
comparison.to_csv(EVIDENCE_DIR / "ml_validation_comparison.csv", index=False)
display(comparison.sort_values(["model", "strategy"]))

recall_pivot = comparison.pivot(index="model", columns="strategy", values="recall")
recall_pivot["spatial_minus_random"] = recall_pivot["spatial_groupkfold"] - recall_pivot["random_70_30"]
recall_pivot["temporal_minus_random"] = recall_pivot["temporal_future"] - recall_pivot["random_70_30"]
display(recall_pivot)

fig, ax = plt.subplots(figsize=(10, 4.5))
sns.barplot(data=comparison, x="model", y="recall", hue="strategy", ax=ax)
ax.set_ylim(0, 1)
ax.set_title("Recall por estrategia de validación")
plt.xticks(rotation=15)
plt.tight_layout()
display_figure(fig)
"""
    ),
    markdown(
        """
### Interpretación conjunta

La división aleatoria mezcla píxeles vecinos y fechas de una misma escena entre train y test, de modo que puede beneficiarse de autocorrelación y producir una estimación optimista. GroupKFold pregunta si el modelo se desplaza a bloques no vistos, mientras que el corte temporal pregunta si se mantiene en adquisiciones futuras. Las diferencias de recall mostradas arriba cuantifican esa pérdida o ganancia para cada modelo. Con solo 22 escenas, estas métricas tienen incertidumbre y no sustituyen una campaña externa.

El resultado más realista depende del uso: para visitar una nueva zona del mismo sistema, validación espacial; para pronosticar una campaña posterior, validación temporal. La transferencia entre lagos se evalúa separadamente a continuación.
"""
    ),
    markdown(
        """
## Ejercicio 7 — Generalización entre lagos

Se ejecutan los dos sentidos exigidos con los tres modelos. En cada experimento, el lago externo queda completamente aislado: preprocesamiento, pesos, selección F2 e hiperparámetros se ajustan únicamente con el lago de entrenamiento. El CV interno usa tres folds `GroupKFold` sobre bloques de 1 km del lago de entrenamiento; luego el modelo seleccionado se reajusta con todo ese lago y se evalúa una sola vez sobre el otro.
"""
    ),
    code(
        """
cross_lake_metrics, cross_lake_tuning = evaluate_cross_lake(
    spatial_data,
    inner_splits=3,
    random_state=RANDOM_STATE,
)
cross_lake_metrics.to_csv(EVIDENCE_DIR / "ml_cross_lake_metrics.csv", index=False)
cross_lake_tuning.to_csv(EVIDENCE_DIR / "ml_cross_lake_tuning.csv", index=False)

assert cross_lake_tuning["evaluation_tuning_overlap"].eq(0).all()
assert cross_lake_tuning["maximum_inner_group_overlap"].eq(0).all()
display(cross_lake_metrics)
display(cross_lake_tuning)

baseline = random_metrics[["model", "accuracy", "precision", "recall", "f1", "roc_auc"]].rename(
    columns={metric: f"mixed_random_{metric}" for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]}
)
cross_lake_comparison = cross_lake_metrics.merge(baseline, on="model", how="left")
for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
    cross_lake_comparison[f"delta_{metric}"] = cross_lake_comparison[metric] - cross_lake_comparison[f"mixed_random_{metric}"]
cross_lake_comparison.to_csv(EVIDENCE_DIR / "ml_cross_lake_comparison.csv", index=False)
display(cross_lake_comparison)
"""
    ),
    code(
        """
population_context = population.groupby("lake", as_index=False).agg(
    scenes=("date", "nunique"),
    first_date=("date", "min"),
    last_date=("date", "max"),
    eligible_population=("eligible_pixels", "sum"),
    population_positive=("class_1", "sum"),
)
population_context["population_positive_percent"] = 100 * population_context["population_positive"] / population_context["eligible_population"]

sample_context = data.groupby("lake", as_index=False).agg(
    sample_n=("target", "size"),
    sample_positive_percent=("target", lambda values: 100 * values.mean()),
)
spectral_context = data.groupby("lake")[list(PREDICTORS)].agg(["mean", "median", "std"])
spectral_context.columns = [f"{band}_{statistic}" for band, statistic in spectral_context.columns]
spectral_context = spectral_context.reset_index()
cross_lake_context = population_context.merge(sample_context, on="lake").merge(spectral_context, on="lake")
cross_lake_context.to_csv(EVIDENCE_DIR / "ml_cross_lake_distributions.csv", index=False)
display(cross_lake_context)

for experiment, results in cross_lake_metrics.groupby("experiment"):
    best = results.sort_values(["recall", "f1"], ascending=False).iloc[0]
    baseline_recall = random_metrics.set_index("model").loc[best["model"], "recall"]
    print(
        f"{experiment}: mayor recall = {best['model']} {best['recall']:.3f}; "
        f"F1={best['f1']:.3f}; ROC-AUC={best['roc_auc']:.3f}; "
        f"Δ recall frente a mixed random={best['recall'] - baseline_recall:+.3f}."
    )

atitlan_to_amatitlan = cross_lake_metrics.query("experiment == 'atitlan_to_amatitlan'").sort_values(["recall", "f1"], ascending=False).iloc[0]
amatitlan_to_atitlan = cross_lake_metrics.query("experiment == 'amatitlan_to_atitlan'").sort_values(["recall", "f1"], ascending=False).iloc[0]
first_specificity = atitlan_to_amatitlan["tn"] / (atitlan_to_amatitlan["tn"] + atitlan_to_amatitlan["fp"])
print(
    "Conclusión explícita: NO se observa generalización adecuada y equilibrada entre lagos. "
    f"Atitlán→Amatitlán alcanza recall={atitlan_to_amatitlan['recall']:.3f}, pero "
    f"precision={atitlan_to_amatitlan['precision']:.3f}, especificidad={first_specificity:.3f} "
    f"y FP={int(atitlan_to_amatitlan['fp'])}. "
    f"Amatitlán→Atitlán alcanza como máximo recall={amatitlan_to_atitlan['recall']:.3f} "
    f"y omite FN={int(amatitlan_to_atitlan['fn'])} positivos del test estratificado."
)
"""
    ),
    code(
        """
cross_plot = cross_lake_metrics[["experiment", "model", "recall", "f1"]].copy()
mixed_plot = random_metrics[["model", "recall", "f1"]].assign(experiment="mixed_random_70_30")
cross_plot = pd.concat([cross_plot, mixed_plot], ignore_index=True)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
for metric, axis in zip(["recall", "f1"], axes, strict=True):
    sns.barplot(data=cross_plot, x="model", y=metric, hue="experiment", ax=axis)
    axis.set_ylim(0, 1)
    axis.set_title(f"{metric.upper()}: transferencia frente a mezcla")
    axis.tick_params(axis="x", rotation=15)
axes[0].legend(title="Experimento", fontsize=8)
axes[1].get_legend().remove()
plt.suptitle("Generalización entre lagos con test externo intacto")
plt.tight_layout()
display_figure(fig)
"""
    ),
    markdown(
        """
### Respuestas 7.4–7.6 e interpretación

La comparación anterior usa como referencia el test aleatorio común con ambos lagos. Esa referencia mezcla espacio, fechas e identidades de lago y, además, tanto ella como los tests externos provienen de la muestra estratificada por lago–fecha–clase. Por ello sus precision, accuracy y matrices son condicionales al diseño de muestreo: no estiman directamente valores predictivos bajo la prevalencia poblacional.

**Respuesta explícita:** los resultados no respaldan una generalización adecuada y equilibrada en ninguno de los dos sentidos. Atitlán→Amatitlán favorece casi indiscriminadamente la clase positiva y Amatitlán→Atitlán conserva precision alta a costa de omitir la mayoría de positivos. Una caída frente a `mixed_random_70_30` indica cambio de dominio: el patrón aprendido en un lago no conserva el mismo desempeño en el otro. Incluso si una métrica aislada mejora, dos lagos y 22 fechas no prueban generalización a otros cuerpos de agua ni a campañas futuras.

Las diferencias observables están en la tabla de contexto: prevalencia poblacional del proxy, intervalos de fechas, cobertura elegible y medias/medianas/dispersión de B02, B03, B08, B11 y B12. Esas diferencias espectrales pueden reflejar combinaciones de material suspendido, color del agua, geometría de adquisición, atmósfera residual o condiciones limnológicas. Diferencias geográficas como morfometría, altitud y presión de cuenca son hipótesis plausibles, pero no están medidas por este dataset y **no se interpretan causalmente**. Para atribución ambiental harían falta muestreos in situ, variables meteorológicas/hidrológicas y validación multisitio representativa.
"""
    ),
    markdown(
        """
## TODO explícito — trabajo no implementado

Los siguientes ejercicios **no están implementados** en esta entrega parcial:

- **Ejercicio 8 (8.1–8.4), interpretación:** falta seleccionar el mejor modelo con el conjunto completo de experimentos, producir importancia global y SHAP Summary Plot, e interpretar dirección y contexto ambiental. SHAP no se agregó como dependencia.
- **Ejercicio 9 (9.1–9.7), mapas predictivos:** falta inferir probabilidades sobre las grillas válidas completas, reconstruir y exportar mapas para ambos lagos, comparar con Parte 1 y mapear falsos positivos/negativos y regiones difíciles.
- **Ejercicio 10 (10.1–10.3), análisis y conclusiones finales:** falta integrar los experimentos 7–9, decidir con evidencia si el sistema puede apoyar monitoreo, consolidar limitaciones y proponer datos adicionales.

No se presenta una conclusión final del laboratorio porque hacerlo antes de completar explicabilidad y mapas sería científicamente engañoso. Con el ejercicio 7 terminado, queda aproximadamente 35 % del esfuerzo nuevo estimado, correspondiente exclusivamente a los ejercicios 8–10.
"""
    ),
]

notebook = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    },
)
nbf.write(notebook, Path("Lab4.ipynb"))
