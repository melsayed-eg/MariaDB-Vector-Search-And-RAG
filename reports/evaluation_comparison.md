# WikiRAG Retrieval Evaluation

- **Embedding model:** sentence-transformers/all-MiniLM-L6-v2
- **Corpus articles:** 200
- **Corpus chunks:** 8743
- **Evaluated K values:** 1, 3, 5, 10

## Aggregate results

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 0.7551 | 0.6667 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2667 | 0.1733 | 0.1000 | 6.11 | 6.64 |
| hybrid | 15 | 0.7583 | 0.6667 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2667 | 0.1733 | 0.1000 | 571.55 | 579.64 |

## Latency variability

One warm-up request per query and mode is excluded. Each query's measured requests are averaged before calculating the P50/P95 values in the aggregate results table above.

The table below instead summarizes all individual measured requests, including their sample standard deviation.

| Mode | Requests | Mean (ms) | Std dev (ms) | Raw P50 (ms) | Raw P95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| semantic | 75 | 6.21 | 0.29 | 6.14 | 6.78 |
| hybrid | 75 | 570.79 | 11.65 | 568.07 | 597.89 |

## Hybrid filter compliance

- **Queries checked:** 15
- **Returned chunk hits:** 450
- **Compliant hits:** 450
- **Violating hits:** 0
- **Empty result sets:** 0
- **Overall compliance rate:** 1.0000

Compliance is measured per returned chunk hit against independently retrieved article metadata and chunk distances. Empty result sets count as vacuously compliant but are reported separately.

| Query ID | Returned | Compliant | Violations | Rate |
|---|---:|---:|---:|---:|
| hyb_01 | 30 | 30 | 0 | 1.0000 |
| hyb_02 | 30 | 30 | 0 | 1.0000 |
| hyb_03 | 30 | 30 | 0 | 1.0000 |
| hyb_04 | 30 | 30 | 0 | 1.0000 |
| hyb_05 | 30 | 30 | 0 | 1.0000 |
| hyb_06 | 30 | 30 | 0 | 1.0000 |
| hyb_07 | 30 | 30 | 0 | 1.0000 |
| hyb_08 | 30 | 30 | 0 | 1.0000 |
| hyb_09 | 30 | 30 | 0 | 1.0000 |
| hyb_10 | 30 | 30 | 0 | 1.0000 |
| hyb_11 | 30 | 30 | 0 | 1.0000 |
| hyb_12 | 30 | 30 | 0 | 1.0000 |
| hyb_13 | 30 | 30 | 0 | 1.0000 |
| hyb_14 | 30 | 30 | 0 | 1.0000 |
| hyb_15 | 30 | 30 | 0 | 1.0000 |


## Per-query results

| Query ID | Mode | Reciprocal rank | Latency (ms) | Retrieved article IDs |
|---|---|---:|---:|---|
| hyb_01 | semantic | 1.0000 | 6.94 | 1711076, 25873, 4674, 13833, 4266, 24799509, 23968131, 3480761, 31274, 8640, 8377, 1010280, 7990, 37704882 |
| hyb_02 | semantic | 1.0000 | 6.34 | 26411268, 8377, 217356, 23968131, 60776, 37704882, 325521, 41054, 24799509, 25873 |
| hyb_03 | semantic | 1.0000 | 6.42 | 752991, 8377, 25873 |
| hyb_04 | semantic | 0.5000 | 6.22 | 19545, 24960699, 25873 |
| hyb_05 | semantic | 1.0000 | 5.98 | 29004, 25873, 8377, 24799509, 19545, 175285, 244884 |
| hyb_06 | semantic | 1.0000 | 6.10 | 100558, 25750, 45809, 97026, 125297, 230401, 97034 |
| hyb_07 | semantic | 1.0000 | 6.51 | 20039, 3268249, 201154, 25977485, 15205, 13995 |
| hyb_08 | semantic | 0.3333 | 6.21 | 4320, 4674, 2118, 4266, 26397, 18167 |
| hyb_09 | semantic | 0.2500 | 5.84 | 233488, 20926, 6836612, 76340, 173332, 65309, 233497, 1164, 1363880 |
| hyb_10 | semantic | 1.0000 | 6.06 | 40409788, 32472154, 1164, 21523, 233497 |
| hyb_11 | semantic | 0.1000 | 6.11 | 6021, 18016, 8218, 5739, 6734, 59868, 23939, 8095, 27404990, 29414838, 72038, 6759, 10939, 12590, 23862, 27471338, 10933, 2356196 |
| hyb_12 | semantic | 1.0000 | 6.04 | 10933, 18203, 2356196, 23862, 199701, 27471338, 24131, 18016, 27404990, 29414838, 3254510 |
| hyb_13 | semantic | 0.1429 | 6.09 | 15323, 15476, 22747, 31929, 25750, 24485, 30538, 4122592 |
| hyb_14 | semantic | 1.0000 | 6.13 | 526999, 20901, 7398 |
| hyb_15 | semantic | 1.0000 | 6.11 | 1260, 18934432, 187813, 29004, 1638777, 72038, 22747, 8339 |
| hyb_01 | hybrid | 1.0000 | 562.42 | 1711076, 25873, 24799509, 23968131, 3480761, 8640, 8377, 7990, 37704882, 23824, 6870132 |
| hyb_02 | hybrid | 1.0000 | 585.95 | 26411268, 8377, 217356, 23968131, 60776, 37704882, 325521, 41054, 24799509, 25873 |
| hyb_03 | hybrid | 1.0000 | 569.04 | 752991, 8377, 25873 |
| hyb_04 | hybrid | 0.5000 | 571.72 | 19545, 24960699, 25873 |
| hyb_05 | hybrid | 1.0000 | 557.31 | 29004, 25873, 8377, 24799509, 19545, 175285, 244884 |
| hyb_06 | hybrid | 1.0000 | 563.60 | 100558, 45809, 97026, 125297, 230401, 97034 |
| hyb_07 | hybrid | 1.0000 | 573.68 | 20039, 3268249, 201154, 25977485, 15205, 13995 |
| hyb_08 | hybrid | 0.3333 | 570.16 | 4320, 4674, 2118, 4266, 26397, 18167 |
| hyb_09 | hybrid | 0.2500 | 565.58 | 233488, 20926, 6836612, 76340, 173332, 65309, 233497, 1164, 1363880 |
| hyb_10 | hybrid | 1.0000 | 574.55 | 40409788, 32472154, 1164, 21523, 233497 |
| hyb_11 | hybrid | 0.1250 | 574.66 | 6021, 18016, 5739, 6734, 59868, 23939, 27404990, 29414838, 72038, 23862, 27471338, 10933, 2356196 |
| hyb_12 | hybrid | 1.0000 | 576.31 | 10933, 2356196, 23862, 199701, 27471338, 24131, 18016, 27404990, 29414838, 3254510 |
| hyb_13 | hybrid | 0.1667 | 576.94 | 15323, 15476, 22747, 31929, 25750, 30538, 4122592 |
| hyb_14 | hybrid | 1.0000 | 571.55 | 526999, 20901, 7398 |
| hyb_15 | hybrid | 1.0000 | 568.33 | 1260, 18934432, 187813, 1638777 |
