# Report Methodology and Map Inference Notes

The map statistics and class interpretations below describe existing project
outputs from before the unpublished quality corrections now included in 0.1.0. They are historical examples,
not validation results for the current engine. Recompute affected products and
derive a new interpretation before using them in a final report. Class IDs and
their meanings need to be assessed for each fitted model.

Project: Unsupervised side-scan sonar acoustic facies classification  
Main project folder: `D:\a\SSS_processing\projects\MSc_Project_75m_AOI`  
Coordinate reference system used for SSS products: `EPSG:32632` / WGS 84 UTM Zone 32N  
Main analysis boundary: `D:\a\SSS_processing\projects\Boundary.shp`

## 1. How to Use This Document

This document is a report-writing guide for the final maps and processing products produced for the project. It summarizes:

- what each map is showing,
- what can reasonably be inferred from each map,
- the methodology that should be described in the technical report,
- limitations caused by the absence of sediment ground-truth samples,
- suggested wording for the results and discussion chapters.

The output should be described as an unsupervised acoustic facies classification, not a confirmed sediment classification. The acoustic classes are based on side-scan sonar intensity and texture behaviour. They may suggest changes in seabed character, but they do not prove sediment type without ground truth.

## 2. Final Products Used for Report Maps

The main report products are:

| Product | File / Layer | Use in report |
|---|---|---|
| Bathymetry map | SBES-derived depth surface or ArcGIS interpolation | Seabed depth and relief context |
| Combined standard corrected SSS mosaic | `mosaics\SSS_combined_standard_mosaic_AOI.tif` | Main acoustic image of the seabed |
| GLCM homogeneity | `textures\SSS_homogeneity.tif` | Smoothness / local uniformity |
| GLCM contrast | `textures\SSS_contrast.tif` | Local tonal difference / roughness indicator |
| Local intensity entropy | `textures\SSS_entropy.tif` | Local acoustic complexity / disorder |
| Acoustic facies classification | `classification\SSS_acoustic_facies_k5.tif` | Unsupervised class result |

If a cleaned classification raster is later produced, use the cleaned version for final cartographic display, but keep the original classification as the analytical result.

## 3. Data and Processing Summary

The side-scan sonar data were processed from Klein XTF files. The selected higher-resolution channel pair was processed through slant-range correction, beam-pattern/radiometric correction, georeferencing, and raster export. The georeferenced strips were then mosaicked to create channel and combined side-scan sonar products.

The final processing workflow used:

1. XTF input selection and channel processing.
2. Slant-range correction.
3. Beam-pattern estimation and correction.
4. Georeferencing using projected coordinates in `EPSG:32632`.
5. GMT blockmedian and nearneighbor gridding during georeferencing.
6. Strip quality control using valid-pixel percentage, standard deviation, and percentile range.
7. Robust P10-P50-P90 line balancing of accepted strips.
8. Feathered weighted mosaicking of overlapping corrected strips.
9. AOI masking using the boundary shapefile.
10. GLCM texture extraction from the standard corrected SSS mosaic.
11. Feature stacking.
12. Unsupervised clustering using KMeans.
13. Optional post-classification cleanup for map presentation.

The standard corrected side-scan sonar mosaic was not treated as absolute calibrated backscatter. It was used as a corrected relative acoustic-intensity product for texture extraction and unsupervised acoustic facies classification.

## 4. Key Numerical Summary

### 4.1 Side-Scan Sonar AOI Mosaic

The clipped combined standard corrected mosaic contains valid acoustic observations inside the AOI.

| Property | Value |
|---|---:|
| Valid SSS pixels | 3,982,368 |
| Relative intensity range | Recalculate from final standard mosaic |
| Mean relative intensity | Recalculate from final standard mosaic |
| Standard deviation | Recalculate from final standard mosaic |
| 2nd percentile | Recalculate from final standard mosaic |
| 98th percentile | Recalculate from final standard mosaic |

These are corrected relative intensity values, not physical backscatter units.

### 4.2 Bathymetry

The SBES point file used for bathymetry contains:

| Property | Value |
|---|---:|
| Number of valid SBES points | 119,927 |
| Source depth range in CSV | 17.39 m to 22.81 m |
| Mean source depth | 19.88 m |
| Standard deviation | 0.83 m |
| Displayed map range | approximately -23.83 m to -16.78 m |

The source CSV stores depth magnitude as positive `Depth_m`. The map may display depth as negative seabed elevation below datum. In the report, be consistent: either describe depth as positive "water depth" or as negative "seabed elevation below datum."

Suggested wording:

> Bathymetric values indicate a shallow marine seabed with depths generally around 18-23 m below the reference surface. The map shows a broad depth gradient across the study area, with shallower zones toward the northern part of the mapped area and relatively deeper zones toward the southern part.

### 4.3 Texture Feature Statistics

| Feature | Range | Mean | Interpretation |
|---|---:|---:|---|
| SSS acoustic intensity standard | Recalculate | Recalculate | Corrected relative acoustic intensity |
| SSS mean | Recalculate | Recalculate | Local average intensity |
| Standard deviation | 0-118.89 | 28.86 | Local variability |
| Entropy | 0-3.96 | 2.65 | Texture complexity |
| Contrast | 0-36.26 | 2.84 | Local tonal contrast |
| Homogeneity | 0.28-1.00 | 0.58 | Local smoothness / uniformity |
| Energy | 0.10-1.00 | 0.25 | Textural order / repeated pattern strength |

## 5. Map-by-Map Inference

### 5.1 Bathymetry Map

What the map shows:

- The map presents the depth distribution across the project area.
- The mapped seabed is shallow, with depths mainly around 17-24 m depending on whether the values are shown as positive depth or negative elevation.
- The map suggests a broad depth change across the AOI rather than abrupt large relief.
- The northern part of the displayed area appears relatively shallower, while parts of the southern area show deeper values.

What to infer:

- Bathymetry provides terrain context for acoustic interpretation.
- Areas of different acoustic facies should be compared against depth to check whether acoustic changes correspond to seabed relief or occur independently of depth.
- Where acoustic changes coincide with bathymetric changes, they may indicate geomorphic or sedimentary transitions.
- Where acoustic changes do not coincide with depth changes, they may be more strongly related to seabed texture, material, survey-line effects, or local seabed roughness.

Caution:

- The bathymetry should not be used alone to assign sediment type.
- Stripe-like or line-following depth patterns may reflect interpolation and survey-line geometry, so interpretation should focus on broader spatial trends.

Suggested report wording:

> The bathymetry map provides the geomorphic setting of the survey area. The seabed is generally shallow, with depths mostly within the range of approximately 17-24 m below the reference surface. The mapped surface indicates gradual depth variation rather than major relief. The bathymetry was therefore used as contextual information to support acoustic interpretation, while the unsupervised facies classification was mainly driven by side-scan sonar intensity and texture features.

### 5.2 Combined Standard Corrected Side-Scan Sonar Mosaic

What the map shows:

- This is the main acoustic image used for texture extraction and classification.
- Pixel values range from 0 to 255.
- Low values represent low relative acoustic intensity.
- High values represent high relative acoustic intensity.
- The mosaic shows a mixture of moderate intensity seabed, bright narrow linear features, darker linear bands, and high-contrast patches.
- Survey-line structure is still visible in some places, which is common in side-scan sonar mosaics even after line balancing and feathered mosaicking.

What to infer:

- Brighter zones may represent stronger acoustic returns, which can be caused by harder, rougher, coarser, or more reflective seabed material, but may also result from acquisition geometry or local artefacts.
- Darker zones may represent weaker acoustic returns, smoother seabed, finer sediment, acoustic shadow, or low grazing-angle effects.
- The right/eastern part of the mosaic shows several strong linear and high-contrast responses, suggesting localized roughness, possible objects, edges, or processing/overlap effects.
- The central part contains mixed but more continuous acoustic texture, indicating a broad acoustic domain rather than isolated objects only.

Caution:

- This map should not be labelled as sand, mud, gravel, or rock without ground-truth samples.
- It should be called a corrected relative acoustic intensity map or combined standard corrected side-scan sonar mosaic.

Suggested report wording:

> The combined standard corrected side-scan sonar mosaic shows clear spatial variation in relative acoustic intensity across the AOI. The mosaic contains both broad moderate-intensity zones and localized high-contrast linear features. These variations indicate changes in acoustic response and seabed texture, but because the data are line-balanced rather than absolutely calibrated, they are interpreted as relative acoustic patterns rather than absolute backscatter values.

### 5.3 GLCM Homogeneity Texture Map

What the map shows:

- Homogeneity ranges from about 0.27 to 1.00.
- Higher homogeneity means neighbouring pixels are more similar.
- Lower homogeneity means stronger local variation.
- The map highlights smoother and more uniform acoustic zones.

What to infer:

- High homogeneity areas likely represent smoother or more uniform acoustic textures.
- Low homogeneity areas correspond to more variable textures, edges, lineations, object-like responses, or transition zones.
- Homogeneity is useful for separating smooth acoustic areas from rough or mixed areas.

Caution:

- High homogeneity does not automatically mean mud or fine sediment.
- It only means the acoustic texture is locally uniform.

Suggested report wording:

> The GLCM homogeneity layer identifies areas where local side-scan intensity values are spatially uniform. Higher homogeneity values indicate smoother acoustic texture, while lower values occur around lineations, edges, and more irregular acoustic patterns. This layer helped the classifier distinguish uniform seabed responses from more complex seabed textures.

### 5.4 GLCM Contrast Texture Map

What the map shows:

- Contrast ranges from 0 to about 36.25.
- Most of the area has relatively low contrast.
- High contrast occurs as narrow linear and patchy features, especially around areas with strong tonal changes.
- The eastern/right side contains several high-contrast features.

What to infer:

- High contrast zones are acoustically rougher or more variable at the texture-window scale.
- These areas may correspond to rough seabed, hard objects, abrupt tonal changes, small relief, boundaries between acoustic domains, or residual processing artefacts.
- Low contrast zones are more acoustically uniform.

Caution:

- High contrast is a texture indicator, not direct proof of gravel, rock, or debris.

Suggested report wording:

> The GLCM contrast map emphasizes areas with sharp local changes in acoustic intensity. High contrast values are concentrated along narrow linear features and patchy zones, particularly toward the eastern part of the AOI. These locations represent acoustically variable seabed textures and are likely to influence the separation of rougher or more heterogeneous acoustic facies.

### 5.5 Local Intensity Entropy Texture Map

What the map shows:

- Entropy ranges from 0 to about 3.96.
- Higher entropy indicates more complex or less ordered texture.
- Lower entropy indicates simpler or more uniform texture.
- The map shows widespread moderate-to-high acoustic complexity, with stronger complexity around lineations and high-contrast areas.

What to infer:

- High entropy areas indicate heterogeneous or irregular seabed acoustic texture.
- Low entropy areas are more ordered or uniform.
- Entropy helps identify mixed acoustic zones that may not be obvious from intensity alone.

Caution:

- Entropy can respond to real seabed complexity and also to survey-line artefacts, seams, and unresolved striping.
- Interpret entropy together with the original SSS mosaic and classification map.

Suggested report wording:

> The Local intensity entropy map shows the spatial distribution of acoustic texture complexity. Higher entropy values occur where the sonar mosaic contains irregular, mixed, or highly variable tonal patterns. These areas are important because they represent acoustic heterogeneity that may correspond to changes in seabed character or to zones affected by lineation and survey artefacts.

## 6. Acoustic Facies Classification Result

The final unsupervised classification used `k=5`. The choice of five classes was supported by a balance between cluster metrics and visual interpretability. The evaluation showed that `k=5` reduced inertia relative to lower k values and had the lowest Davies-Bouldin score among the tested options, while avoiding an excessive number of very small classes.

Important metrics:

| k | Silhouette | Davies-Bouldin | Minimum class % | Maximum class % | Stability ARI |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.319 | 1.245 | 8.77 | 68.57 | 0.970 |
| 4 | 0.238 | 1.230 | 4.53 | 43.47 | 0.987 |
| 5 | 0.245 | 1.120 | 3.24 | 32.88 | 0.978 |
| 6 | 0.233 | 1.162 | 2.65 | 29.70 | 0.983 |

The classification produced five acoustic facies:

| Facies | Area % | Acoustic character based on cluster centres | Suggested interpretation |
|---:|---:|---|---|
| 1 | 30.64 | Lower relative intensity, moderate entropy, moderate variability | Low-to-moderate intensity mixed acoustic facies |
| 2 | 6.98 | Moderate intensity, highest standard deviation, highest entropy, highest contrast, low homogeneity | High-variability / rough-texture acoustic facies |
| 3 | 32.85 | Moderate intensity, lower contrast, higher homogeneity | Dominant moderate-intensity smoother acoustic facies |
| 4 | 26.30 | Higher relative intensity, moderate-to-high entropy and contrast | Higher-intensity mixed acoustic facies |
| 5 | 3.23 | Highest relative intensity, low entropy, high homogeneity, high energy | Bright but locally uniform acoustic facies |

Suggested interpretation:

- Facies 3 is the most extensive class and represents the dominant moderate acoustic background.
- Facies 1 and Facies 4 occupy large parts of the survey and represent lower and higher relative intensity domains respectively.
- Facies 2 is smaller but important because it captures the roughest and most texturally variable acoustic response.
- Facies 5 is minor in area but distinct because it has high relative intensity and high homogeneity. This may represent strongly reflective but smooth acoustic zones, or areas influenced by acquisition/processing effects.

Caution:

- These classes are acoustic facies, not verified sediment types.
- Class names should remain neutral unless sediment samples or independent validation data are available.
- Recommended labels are: Acoustic Facies 1, Acoustic Facies 2, Acoustic Facies 3, Acoustic Facies 4, and Acoustic Facies 5.

Suggested report wording:

> The unsupervised classification separated the study area into five acoustic facies based on standard corrected side-scan sonar intensity and GLCM texture features. The classes show differences in relative intensity, local variability, entropy, contrast, homogeneity, and energy. The dominant facies represent broad moderate-intensity acoustic backgrounds, while smaller classes capture rougher, higher-contrast, or more homogeneous high-intensity zones. Because no sediment samples were available, the classes are interpreted as acoustic seabed facies rather than confirmed sediment classes.

## 7. What the Final Maps Contribute to the Report

The final map set supports the following report points:

1. The bathymetry map establishes the seabed relief and depth setting.
2. The standard corrected SSS mosaic shows the primary acoustic evidence used for classification.
3. The homogeneity map explains where the seabed response is smoother or more uniform.
4. The contrast map identifies sharp tonal changes and rougher or more variable zones.
5. The entropy map identifies complex and heterogeneous acoustic textures.
6. The classification map integrates the acoustic intensity and texture variables into spatial acoustic facies.
7. The final interpretation should compare acoustic facies with bathymetric trends and visible SSS patterns.

## 8. Limitations to State Clearly

The report should clearly state the following limitations:

- No sediment samples were available.
- No ground-truth labels were available for supervised classification.
- Random Forest or other supervised classifiers were therefore not used as the main method.
- The side-scan sonar mosaic is line-balanced and should not be interpreted as absolute calibrated backscatter.
- Acoustic facies do not directly equal sediment classes.
- Survey-line artefacts, overlap seams, nadir effects, and residual radiometric differences may influence texture features and classification.
- The classification should be interpreted together with the original SSS mosaic, bathymetry, and expert visual assessment.

Suggested limitation wording:

> In the absence of sediment samples or independent ground-truth data, the classification results cannot be validated as sediment classes. The outputs are therefore interpreted as acoustic facies, representing zones with similar side-scan sonar intensity and texture characteristics. These acoustic facies provide a useful basis for seabed characterization, but sedimentological interpretation remains provisional.

## 9. Suggested Chapter 3 Methodology Text

The project adopted an unsupervised image-based seabed classification workflow using side-scan sonar and bathymetric data. The side-scan sonar data were processed from XTF files and georeferenced in WGS 84 UTM Zone 32N. After slant-range correction, beam-pattern correction, and gridding, the sonar strips were exported as GeoTIFF rasters. Each strip was inspected and statistically assessed before mosaicking. To reduce line-to-line brightness differences and trackline seam dominance, accepted strips were adjusted using a robust P10-P50-P90 percentile matching method and then mosaicked using feathered overlap averaging.

An AOI mask was generated from the project boundary and intersected with the valid sonar-data mask. This ensured that texture extraction and classification were limited to valid acoustic observations inside the study area. GLCM texture features were derived from the standard corrected side-scan sonar mosaic using a moving window, 16 grey-level quantization, and four directional offsets. The derived features included local mean, standard deviation, entropy, contrast, homogeneity, and energy.

The standard corrected sonar intensity and texture layers were stacked into a multi-band feature raster. Since no sediment samples or labelled ground-truth data were available, an unsupervised classification approach was used. KMeans clustering was applied to standardized feature values, and candidate class numbers were assessed using internal cluster validity metrics including inertia, silhouette score, Calinski-Harabasz index, Davies-Bouldin index, class balance, and clustering stability. A five-class solution was selected as a practical balance between statistical separation and cartographic interpretability.

The final classes were interpreted as acoustic facies rather than confirmed sediment classes. Bathymetry was used as supporting context for seabed relief and to assist interpretation of the acoustic facies, but the classification itself was based primarily on side-scan sonar intensity and texture.

## 10. Suggested Chapter 4 Results and Discussion Text

The bathymetric map indicates a generally shallow seabed within the study area, with mapped depths approximately within the range of 17-24 m below the reference surface. The bathymetry shows broad spatial variation rather than extreme relief, providing useful geomorphic context for interpreting the acoustic facies. Some elongated patterns may be influenced by survey-line geometry and interpolation, so interpretation was focused on broad spatial trends rather than isolated depth stripes.

The combined standard corrected side-scan sonar mosaic reveals clear variation in relative acoustic intensity and seabed texture. Moderate-intensity areas dominate much of the AOI, while localized bright and dark linear features indicate sharper acoustic transitions. The right/eastern side of the mosaic contains several high-contrast linear responses, which may reflect rougher seabed texture, object-like features, acoustic shadows, or residual acquisition effects. Since the mosaic was line-balanced for tonal consistency rather than calibrated to physical backscatter, its pixel values are interpreted as relative acoustic intensity.

The GLCM texture maps provide additional explanation of the acoustic patterns. Homogeneity highlights the smoother and more spatially uniform acoustic zones. Contrast identifies areas with strong local tonal differences, especially narrow linear and patchy features. Entropy identifies complex and heterogeneous textures. Together, these texture layers show that the AOI is not acoustically uniform; instead, it contains smoother background zones, high-contrast lineations, and mixed/irregular acoustic textures.

The unsupervised classification separated the AOI into five acoustic facies. The dominant classes represent broad low-to-moderate and moderate-intensity acoustic backgrounds, while smaller classes capture rougher, more heterogeneous, or strongly reflective zones. Facies 2, although limited in area, is important because it has the highest contrast, entropy, and local variability, suggesting a rough or highly mixed acoustic texture. Facies 5 is the smallest class but has high intensity and high homogeneity, suggesting a bright but locally uniform response. These interpretations remain acoustic rather than sedimentological because sediment samples were not available.

Overall, the map products show that the study area contains spatially variable seabed acoustic conditions. The combination of side-scan sonar intensity, GLCM texture measures, bathymetry, and unsupervised acoustic facies mapping provides a defensible workflow for seabed characterization where ground-truth sediment data are absent.

## 11. Recommended Captions

### Bathymetry Map

Bathymetric map of the study area showing seabed depth variation derived from SBES soundings. Depth is presented relative to the chosen reference surface and provides geomorphic context for acoustic facies interpretation.

### Combined Standard Corrected Side-Scan Sonar Mosaic

Combined standard corrected side-scan sonar mosaic of the AOI. Pixel values represent corrected relative acoustic intensity, where lower values indicate weaker relative acoustic return and higher values indicate stronger relative acoustic return.

### GLCM Homogeneity Texture

GLCM homogeneity texture map derived from the standard corrected side-scan sonar mosaic. Higher values indicate more spatially uniform acoustic texture, while lower values indicate greater local variation.

### GLCM Contrast Texture

GLCM contrast texture map derived from the standard corrected side-scan sonar mosaic. Higher values indicate stronger local tonal changes and more variable acoustic texture.

### Local Intensity Entropy Texture

Local intensity entropy texture map derived from the standard corrected side-scan sonar mosaic. Higher values indicate more complex or heterogeneous acoustic texture.

### Acoustic Facies Classification

Unsupervised acoustic facies classification derived from standard corrected side-scan sonar intensity and GLCM texture features. The classes represent acoustic facies and are not confirmed sediment classes due to the absence of sediment ground-truth samples.

## 12. Final Report Statement

The strongest final interpretation is:

> The study successfully produced an unsupervised acoustic seabed facies map from processed side-scan sonar data and derived texture features. The classification identifies zones of similar acoustic intensity and texture within the AOI. These zones provide useful seabed characterization information, but they should be interpreted as acoustic facies rather than confirmed sediment types because no sediment samples or independent ground-truth labels were available.
