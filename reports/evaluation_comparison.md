# WikiRAG Retrieval Evaluation

- **Embedding model:** sentence-transformers/all-MiniLM-L6-v2
- **Corpus articles:** 200
- **Corpus chunks:** 8743
- **Evaluated K values:** 1, 3, 5, 10

## Aggregate results

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 0.7551 | 0.6333 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2889 | 0.1867 | 0.1067 | 24.76 | 65.84 |
| hybrid | 15 | 0.7583 | 0.6333 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2889 | 0.1867 | 0.1067 | 1490.53 | 1624.68 |

## Latency variability

One warm-up request per query and mode is excluded. Each query's measured requests are averaged before calculating the P50/P95 values in the aggregate results table above.

The table below instead summarizes all individual measured requests, including their sample standard deviation.

| Mode | Requests | Mean (ms) | Std dev (ms) | Raw P50 (ms) | Raw P95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| semantic | 75 | 35.65 | 33.65 | 23.22 | 90.54 |
| hybrid | 75 | 1508.31 | 109.69 | 1470.52 | 1749.25 |

## Constraint satisfaction comparison

Constraint satisfaction is measured per returned chunk hit against the
original question filters, using independently retrieved metadata.
Semantic retrieval does not apply these filters during retrieval;
hybrid retrieval enforces them in SQL.

| Mode | Queries checked | Returned hits | Compliant hits | Violations | Empty results | Compliance rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 450 | 420 | 30 | 0 | 0.9333 |
| hybrid | 15 | 450 | 450 | 0 | 0 | 1.0000 |

Empty result sets are counted separately and treated as compliant
by convention; they do not demonstrate successful retrieval.

| Query ID | Mode | Returned | Compliant | Violations | Rate |
| --- | --- | ---: | ---: | ---: | ---: |
| hyb_01 | semantic | 30 | 17 | 13 | 0.5667 |
| hyb_02 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_03 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_04 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_05 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_06 | semantic | 30 | 28 | 2 | 0.9333 |
| hyb_07 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_08 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_09 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_10 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_11 | semantic | 30 | 24 | 6 | 0.8000 |
| hyb_12 | semantic | 30 | 28 | 2 | 0.9333 |
| hyb_13 | semantic | 30 | 29 | 1 | 0.9667 |
| hyb_14 | semantic | 30 | 30 | 0 | 1.0000 |
| hyb_15 | semantic | 30 | 24 | 6 | 0.8000 |
| hyb_01 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_02 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_03 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_04 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_05 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_06 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_07 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_08 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_09 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_10 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_11 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_12 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_13 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_14 | hybrid | 30 | 30 | 0 | 1.0000 |
| hyb_15 | hybrid | 30 | 30 | 0 | 1.0000 |


## Per-query results

| Query ID | Mode | Reciprocal rank | Latency (ms) | Retrieved article IDs |
|---|---|---:|---:|---|
| hyb_01 | semantic | 1.0000 | 52.35 | 1711076, 25873, 4674, 13833, 4266, 24799509, 23968131, 3480761, 31274, 8640, 8377, 1010280, 7990, 37704882 |
| hyb_02 | semantic | 1.0000 | 20.70 | 26411268, 8377, 217356, 23968131, 60776, 37704882, 325521, 41054, 24799509, 25873 |
| hyb_03 | semantic | 1.0000 | 21.16 | 752991, 8377, 25873 |
| hyb_04 | semantic | 0.5000 | 24.76 | 19545, 24960699, 25873 |
| hyb_05 | semantic | 1.0000 | 41.64 | 29004, 25873, 8377, 24799509, 19545, 175285, 244884 |
| hyb_06 | semantic | 1.0000 | 18.70 | 100558, 25750, 45809, 97026, 125297, 230401, 97034 |
| hyb_07 | semantic | 1.0000 | 17.63 | 20039, 3268249, 201154, 25977485, 15205, 13995 |
| hyb_08 | semantic | 0.3333 | 23.29 | 4320, 4674, 2118, 4266, 26397, 18167 |
| hyb_09 | semantic | 0.2500 | 19.87 | 233488, 20926, 6836612, 76340, 173332, 65309, 233497, 1164, 1363880 |
| hyb_10 | semantic | 1.0000 | 20.71 | 40409788, 32472154, 1164, 21523, 233497 |
| hyb_11 | semantic | 0.1000 | 83.91 | 6021, 18016, 8218, 5739, 6734, 59868, 23939, 8095, 27404990, 29414838, 72038, 6759, 10939, 12590, 23862, 27471338, 10933, 2356196 |
| hyb_12 | semantic | 1.0000 | 39.28 | 10933, 18203, 2356196, 23862, 199701, 27471338, 24131, 18016, 27404990, 29414838, 3254510 |
| hyb_13 | semantic | 0.1429 | 41.41 | 15323, 15476, 22747, 31929, 25750, 24485, 30538, 4122592 |
| hyb_14 | semantic | 1.0000 | 58.10 | 526999, 20901, 7398 |
| hyb_15 | semantic | 1.0000 | 51.30 | 1260, 18934432, 187813, 29004, 1638777, 72038, 22747, 8339 |
| hyb_01 | hybrid | 1.0000 | 1812.29 | 1711076, 25873, 24799509, 23968131, 3480761, 8640, 8377, 7990, 37704882, 23824, 6870132 |
| hyb_02 | hybrid | 1.0000 | 1528.17 | 26411268, 8377, 217356, 23968131, 60776, 37704882, 325521, 41054, 24799509, 25873 |
| hyb_03 | hybrid | 1.0000 | 1532.95 | 752991, 8377, 25873 |
| hyb_04 | hybrid | 0.5000 | 1445.36 | 19545, 24960699, 25873 |
| hyb_05 | hybrid | 1.0000 | 1504.45 | 29004, 25873, 8377, 24799509, 19545, 175285, 244884 |
| hyb_06 | hybrid | 1.0000 | 1490.53 | 100558, 45809, 97026, 125297, 230401, 97034 |
| hyb_07 | hybrid | 1.0000 | 1459.80 | 20039, 3268249, 201154, 25977485, 15205, 13995 |
| hyb_08 | hybrid | 0.3333 | 1452.22 | 4320, 4674, 2118, 4266, 26397, 18167 |
| hyb_09 | hybrid | 0.2500 | 1457.19 | 233488, 20926, 6836612, 76340, 173332, 65309, 233497, 1164, 1363880 |
| hyb_10 | hybrid | 1.0000 | 1544.28 | 40409788, 32472154, 1164, 21523, 233497 |
| hyb_11 | hybrid | 0.1250 | 1495.07 | 6021, 18016, 5739, 6734, 59868, 23939, 27404990, 29414838, 72038, 23862, 27471338, 10933, 2356196 |
| hyb_12 | hybrid | 1.0000 | 1494.61 | 10933, 2356196, 23862, 199701, 27471338, 24131, 18016, 27404990, 29414838, 3254510 |
| hyb_13 | hybrid | 0.1667 | 1470.02 | 15323, 15476, 22747, 31929, 25750, 30538, 4122592 |
| hyb_14 | hybrid | 1.0000 | 1460.16 | 526999, 20901, 7398 |
| hyb_15 | hybrid | 1.0000 | 1477.60 | 1260, 18934432, 187813, 1638777 |
