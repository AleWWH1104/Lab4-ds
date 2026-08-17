---
title: "Monitoreo exploratorio de cianobacterias en los lagos Atitlán y Amatitlán"
subtitle: "Laboratorio 4: análisis de datos geoespaciales"
lang: es-GT
geometry: margin=2.0cm
fontsize: 10pt
colorlinks: true
---

# Resumen ejecutivo

Se analizaron 22 de 22 escenas oficiales a partir de los GeoTIFF persistidos y validados, sin una nueva descarga.

En el período observado, Amatitlán presentó la mayor extensión alta media (26.5%) y 81.8% de fechas con al menos 5% de extensión alta. Estas señales ópticas orientan vigilancia; no demuestran toxicidad, especie ni causa.

Este estudio utiliza observaciones Sentinel-2 para describir señales ópticas compatibles con
clorofila-a y floraciones superficiales. Es un diagnóstico exploratorio para priorizar observación y
muestreo: no sustituye análisis de agua, identificación taxonómica ni mediciones de toxinas.

# Datos, alcance y validez del método

El análisis incluye las 11 fechas oficiales de cada lago. La adquisición conservó las bandas
necesarias para CyanoLakes, NDVI y NDWI, además de la clasificación SCL y la máscara de datos. Se
excluyeron nubes, cirros, sombras, nieve, píxeles defectuosos y zonas sin datos. Como el repositorio
no contiene los GeoJSON mencionados en la guía, se emplearon sus cajas geográficas y la detección
espectral de agua del script. Por tanto, “porcentaje del lago” significa porcentaje del agua válida
detectada dentro de cada caja, no de un límite catastral.

El método conserva dos señales que no deben confundirse:

- **Proxy continuo:** el polinomio NDCI de CyanoLakes, calculado en agua válida sin floración
  superficial. Es una estimación óptica basada en datos simulados, no una concentración medida.
- **Floración superficial FAI:** clasificación independiente cuando FAI es mayor que 0.08. Se
  incluye en la extensión alta, pero no se le asigna artificialmente una concentración.

## Tratamiento de validez

El polinomio original puede producir números negativos cuando se evalúa fuera de una respuesta
físicamente posible y valores iguales o superiores al límite de 500 usado al entrenar el modelo. Esos valores
se preservan en el producto raster para auditoría, pero **no se recortan a cero ni se presentan como
concentración**. Las medias, percentiles, correlaciones y boxplots usan `0 <= proxy < 500`.
Las tablas informan por fecha el porcentaje interpretable, negativo e igual o superior a 500.

La extensión alta mantiene como denominador toda el agua válida detectada. Así, excluir una
estimación de la media no aumenta artificialmente el porcentaje de área alta. El umbral principal
es 20.0 unidades del proxy y la sensibilidad se evalúa con 10.0, 20.0, 50.0. Ninguno es un
límite sanitario.

\newpage

# Ejercicio 4. Evolución temporal

- **Amatitlán:** la extensión alta fluctuó entre 0.0% y 93.3%. La fecha crítica por extensión fue 2026-06-19 (93.3%); la mayor media interpretable ocurrió el 2026-06-19 (67.10). La cobertura del proxy interpretable varió entre 98.7% y 100.0% del agua válida.
- **Atitlán:** la extensión alta fluctuó entre 0.0% y 13.9%. La fecha crítica por extensión fue 2025-01-18 (13.9%); la mayor media interpretable ocurrió el 2025-01-18 (39.13). La cobertura del proxy interpretable varió entre 9.0% y 96.0% del agua válida.
  La media máxima de Atitlán requiere cautela: solo 9.0% del agua válida tuvo un proxy dentro del intervalo interpretable en esa fecha.

La fecha crítica se define reproduciblemente como la de mayor porcentaje de agua válida con proxy
igual o superior al umbral o con floración FAI. Una media alta describe intensidad entre los píxeles
interpretables; una extensión alta describe cuánta superficie fue clasificada. Ambas medidas deben
leerse juntas.

![Evolución temporal de la media interpretable y la extensión alta](../outputs/figures/temporal_evolution.png)

## Evidencia por fecha

### Amatitlán

| Fecha | Media proxy | Área alta (%) | FAI (%) | Proxy válido (%) | Negativo (%) | >=500 (%) |
| --- | --- | --- | --- | --- | --- | --- |
| 2025-01-28 | 14.91 | 19.6 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2025-04-15 | 10.44 | 12.3 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2025-04-28 | 13.60 | 23.4 | 0.06 | 99.9 | 0.1 | 0.0 |
| 2025-11-24 | 13.13 | 15.1 | 0.20 | 99.8 | 0.0 | 0.0 |
| 2026-01-08 | 23.13 | 40.2 | 0.26 | 99.7 | 0.0 | 0.0 |
| 2026-02-02 | 6.68 | 0.0 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2026-02-07 | 8.12 | 1.4 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2026-03-29 | 17.21 | 22.7 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2026-04-13 | 16.57 | 20.8 | 0.00 | 100.0 | 0.0 | 0.0 |
| 2026-04-28 | 24.05 | 42.3 | 1.29 | 98.7 | 0.0 | 0.0 |
| 2026-06-19 | 67.10 | 93.3 | 0.27 | 99.7 | 0.0 | 0.0 |

### Atitlán

| Fecha | Media proxy | Área alta (%) | FAI (%) | Proxy válido (%) | Negativo (%) | >=500 (%) |
| --- | --- | --- | --- | --- | --- | --- |
| 2025-01-18 | 39.13 | 13.9 | 0.00 | 9.0 | 31.6 | 10.5 |
| 2025-04-13 | 3.23 | 0.0 | 0.00 | 94.7 | 5.3 | 0.0 |
| 2025-05-13 | 3.62 | 0.0 | 0.00 | 93.5 | 6.5 | 0.0 |
| 2025-07-17 | 4.24 | 0.2 | 0.00 | 95.6 | 4.4 | 0.0 |
| 2025-11-21 | 6.05 | 2.3 | 0.00 | 69.4 | 30.1 | 0.1 |
| 2025-12-29 | 4.11 | 0.4 | 0.00 | 66.8 | 32.9 | 0.0 |
| 2026-02-12 | 4.50 | 0.7 | 0.00 | 70.0 | 21.9 | 0.2 |
| 2026-03-24 | 3.67 | 0.0 | 0.00 | 96.0 | 4.0 | 0.0 |
| 2026-04-13 | 3.55 | 0.0 | 0.00 | 87.7 | 12.3 | 0.0 |
| 2026-04-28 | 3.13 | 0.0 | 0.00 | 91.5 | 8.5 | 0.0 |
| 2026-07-22 | 3.98 | 0.2 | 0.02 | 95.5 | 4.5 | 0.0 |

No se interpreta la unión entre puntos como cambio continuo: las fechas son irregulares y no
observan lo ocurrido entre adquisiciones.

\newpage

# Ejercicio 5. Distribución espacial, persistencia y cambio

Para evitar afirmaciones basadas en inspección visual, cada cuadrícula se dividió por sus
coordenadas centrales en cuatro zonas reproducibles: noroeste, noreste, suroeste y sureste. Sus
límites geográficos están en `outputs/tables/spatial_zones.csv`. Son cuadrantes de análisis, no
unidades ecológicas ni cuencas de aporte.

- **Amatitlán:** el cuadrante noreste tuvo la mayor media ponderada del proxy (28.32); el cuadrante noreste presentó la mayor superficie persistente (57.7% de celdas evaluables). El mayor cambio entre primera y última fecha ocurrió en sureste (+83.3 puntos porcentuales).
- **Atitlán:** el cuadrante sureste tuvo la mayor media ponderada del proxy (5.26); el cuadrante suroeste presentó la mayor superficie persistente (0.8% de celdas evaluables). El mayor cambio entre primera y última fecha ocurrió en noreste (-17.4 puntos porcentuales).

| Lago | Cuadrante | Media proxy | Área alta media (%) | Persistente (%) | Primera (%) | Última (%) | Cambio (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Amatitlán | noreste | 28.32 | 39.8 | 57.7 | 66.6 | 96.5 | +29.9 |
| Amatitlán | noroeste | 27.72 | 31.2 | 39.4 | 24.0 | 94.0 | +70.0 |
| Amatitlán | sureste | 18.51 | 19.8 | 6.4 | 8.1 | 91.4 | +83.3 |
| Amatitlán | suroeste | 4.87 | 4.8 | 1.2 | 37.5 | no estimable | no estimable |
| Atitlán | noreste | 4.52 | 1.8 | 0.0 | 17.4 | 0.0 | -17.4 |
| Atitlán | noroeste | 4.56 | 1.5 | 0.0 | 12.5 | 0.0 | -12.4 |
| Atitlán | sureste | 5.26 | 1.7 | 0.6 | 9.7 | 1.8 | -7.9 |
| Atitlán | suroeste | 3.73 | 1.0 | 0.8 | 2.6 | 1.1 | -1.5 |

“Persistente” significa que una celda fue alta en al menos la fracción configurada de sus
observaciones y tuvo por lo menos dos observaciones válidas. No identifica por sí sola una fuente
de nutrientes ni una trayectoria de transporte.

## Mapas de todas las fechas

El color representa el proxy interpretable desde 0 hasta menos de 500; el rojo superpuesto representa FAI. Las
áreas transparentes no deben leerse como concentración cero: pueden ser tierra, nube, dato no
válido, floración FAI o estimación fuera del intervalo interpretable.

![Distribución espacial en Atitlán](../outputs/figures/spatial_atitlan.png)

![Distribución espacial en Amatitlán](../outputs/figures/spatial_amatitlan.png)

## Frecuencia y cambio

![Frecuencia de valores altos en Atitlán](../outputs/figures/hotspots_atitlan.png)

![Frecuencia de valores altos en Amatitlán](../outputs/figures/hotspots_amatitlan.png)

Los mapas siguientes comparan únicamente la primera y la última fecha oficial: azul indica que la
clasificación alta desapareció, blanco que no cambió y rojo que apareció. No resumen las fechas
intermedias.

![Cambio entre primera y última fecha de Atitlán](../outputs/figures/difference_atitlan.png)

![Cambio entre primera y última fecha de Amatitlán](../outputs/figures/difference_amatitlan.png)

\newpage

# Ejercicio 6. Relación con NDVI y NDWI

- **Amatitlán:** NDVI: moderada positiva (r=0.50), n=257381; NDWI: débil negativa (r=-0.28), n=257381.
- **Atitlán:** NDVI: moderada positiva (r=0.33), n=1797665; NDWI: débil positiva (r=0.12), n=1797665.

| Lago | Índice | Pares válidos | Pearson r | Lectura |
| --- | --- | --- | --- | --- |
| Amatitlán | NDVI | 257381 | 0.499 | moderada positiva |
| Amatitlán | NDWI | 257381 | -0.279 | débil negativa |
| Atitlán | NDVI | 1797665 | 0.333 | moderada positiva |
| Atitlán | NDWI | 1797665 | 0.116 | débil positiva |

Una asociación positiva indica que ambas señales tienden a aumentar juntas; una negativa, que una
tiende a disminuir cuando la otra aumenta; una relación débil tiene poca utilidad predictiva lineal
por sí sola. Ambientalmente, NDVI puede responder a vegetación o materia flotante y NDWI al
contraste espectral agua-tierra. Sin embargo, ambos comparten bandas o condiciones ópticas con
NDCI y también responden a turbidez, mezcla de orilla y corrección atmosférica. Por ello estas
correlaciones describen covariación espectral, no causalidad ni identidad de organismos.

# Ejercicio 7. Comparación entre lagos

| Lago | Fechas | Media temporal proxy | Máxima media | Área alta media (%) | Área alta máxima (%) | Fechas >=5% (%) |
| --- | --- | --- | --- | --- | --- | --- |
| Amatitlán | 11 | 19.54 | 67.10 | 26.5 | 93.3 | 81.8 |
| Atitlán | 11 | 7.20 | 39.13 | 1.6 | 13.9 | 9.1 |

La intensidad se resume con la media temporal del proxy interpretable y su máxima media por fecha.
La frecuencia se define como el porcentaje de fechas con al menos 5% de extensión alta. La
extensión media y máxima cuantifica superficie y no concentración. Esta separación evita concluir
que un evento localizado pero intenso equivale a uno extendido.

## Hipótesis causales que requieren medición

Los raster no midieron nutrientes, uso del suelo, descargas, presión urbana, profundidad,
circulación, temperatura ni precipitación. Por tanto, las siguientes son **hipótesis de trabajo**, no
resultados del estudio:

- **Presión urbana y uso del suelo:** si las zonas con mayor recurrencia reciben más aportes de
  aguas residuales o escorrentía agrícola, deberían coincidir con concentraciones de nutrientes y
  trazadores medidos en campo.
- **Geografía y circulación:** si la forma, profundidad o circulación retienen material flotante,
  la persistencia debería repetirse bajo condiciones comparables de viento y nivel del lago.
- **Temperatura y clima:** si temperatura, radiación o lluvia modulan la proliferación, una serie
  más larga debería mostrar asociaciones consistentes después de controlar nubosidad y cobertura.

Estas hipótesis pueden explicar diferencias potenciales entre lagos, pero no se aceptan ni se
rechazan con los índices disponibles.

\newpage

# Ejercicio 8. Análisis exploratorio adicional

## Extensión y sensibilidad al umbral

| Lago | Umbral | Área media (%) | Máxima (%) |
| --- | --- | --- | --- |
| Amatitlán | 10 | 51.3 | 98.3 |
| Amatitlán | 20 | 26.5 | 93.3 |
| Amatitlán | 50 | 10.2 | 67.1 |
| Atitlán | 10 | 2.2 | 14.3 |
| Atitlán | 20 | 1.6 | 13.9 |
| Atitlán | 50 | 1.3 | 12.6 |

La variación entre umbrales muestra cuánto depende la extensión de la convención analítica. FAI se
conserva como alta en todos los umbrales porque el script la trata como una rama independiente.

## Distribuciones y diferencias

Los boxplots comparan solo el proxy interpretable desde 0 hasta menos de 500. La línea central es la mediana, la
caja resume el rango intercuartílico y se ocultan valores atípicos para legibilidad, no para el
cálculo de estadísticas.

![Distribuciones interpretables por fecha](../outputs/figures/distributions.png)

Los mapas de frecuencia y diferencia del Ejercicio 5 complementan los boxplots: los primeros
localizan recurrencia y los segundos muestran dónde apareció o desapareció la clasificación alta.

## Estacionalidad exploratoria

- **Amatitlán:** lluviosa (n=1, área alta media 93.3%, proxy medio 67.10); seca (n=10, área alta media 19.8%, proxy medio 14.79).
- **Atitlán:** lluviosa (n=3, área alta media 0.1%, proxy medio 3.95); seca (n=8, área alta media 2.2%, proxy medio 8.42).

| Lago | Época | n | Proxy medio | Área alta media (%) |
| --- | --- | --- | --- | --- |
| Amatitlán | lluviosa | 1 | 67.10 | 93.3 |
| Amatitlán | seca | 10 | 14.79 | 19.8 |
| Atitlán | lluviosa | 3 | 3.95 | 0.1 |
| Atitlán | seca | 8 | 8.42 | 2.2 |

La época seca se definió como noviembre-abril y la lluviosa como mayo-octubre. Con 11 fechas
irregulares por lago, grupos muy desbalanceados y poco más de un ciclo anual, estas diferencias no
demuestran estacionalidad. Sirven para diseñar una serie mensual que incluya varios años.

# Limitaciones

- El modelo fue entrenado con datos simulados bajo restricciones ópticas y aquí se aplicó a L2A
  para disponer de SCL; los valores no son intercambiables automáticamente con medición de campo.
- No existe una geometría oficial del contorno en el repositorio; el agua detectada puede incluir
  bordes, cuerpos vecinos o píxeles mixtos dentro de la caja.
- Nubes, bruma, turbidez, fondo visible, vegetación flotante y efectos de adyacencia pueden alterar
  las señales. La máscara reduce estos problemas, pero no los elimina.
- Una escena es una instantánea. Once observaciones irregulares por lago no caracterizan duración,
  inicio o fin de una floración ni permiten inferir tendencias de largo plazo.
- La correlación por píxel tiene tamaños muestrales grandes por resolución espacial, pero existe
  autocorrelación espacial; `n` no equivale a igual número de muestras independientes.
- Sentinel-2 no confirma especie, toxina ni riesgo sanitario. No debe emitirse una alerta pública
  solo con estos resultados.

# Recomendaciones de monitoreo

- En Amatitlán, priorizar verificación de campo en el cuadrante noreste y contrastarla con el cuadrante de mayor media (noreste); las coordenadas exactas están en `spatial_zones.csv`.
- En Atitlán, priorizar verificación de campo en el cuadrante suroeste y contrastarla con el cuadrante de mayor media (sureste); las coordenadas exactas están en `spatial_zones.csv`.

- Muestrear clorofila-a, ficocianina, composición taxonómica y toxinas en fechas críticas y en una
  zona de contraste; registrar coordenada, hora, profundidad y condiciones meteorológicas.
- Mantener observación mensual y aumentar frecuencia después de una señal extensa; conservar
  también fechas sin evento para estimar falsos positivos y negativos.
- Incorporar contornos oficiales y calcular área física en hectáreas con una proyección adecuada.
- Integrar precipitación, viento, temperatura del agua, nutrientes, uso del suelo y descargas antes
  de evaluar las hipótesis causales.
- Calibrar y validar el proxy localmente con muestras coincidentes con el paso satelital antes de
  usarlo para decisiones operativas.

# Proveniencia y reproducibilidad

Contiene datos Copernicus Sentinel modificados, procesados mediante Sentinel Hub. El polinomio,
FAI y la lógica de agua reproducen el script *Cyanobacteria Chlorophyll-a NDCI L1C* de CyanoLakes,
atribuido a Kravitz y Matthews (2020) en el repositorio oficial de scripts de Sentinel Hub. Las
restricciones de entrenamiento y la referencia metodológica se documentan en esa misma fuente.

Todas las cifras del informe se regeneran desde los 22 GeoTIFF persistidos. Las tablas CSV y los
GeoTIFF de frecuencia permiten auditar fechas, denominadores, cuadrantes, correlaciones y umbrales.
