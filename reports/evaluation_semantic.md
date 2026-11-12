# WikiRAG Retrieval Evaluation

- **Embedding model:** sentence-transformers/all-MiniLM-L6-v2
- **Corpus articles:** 200
- **Corpus chunks:** 8743
- **Evaluated K values:** 1, 3, 5, 10

## Aggregate results

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 40 | 0.8644 | 0.7000 | 0.8750 | 0.9500 | 1.0000 | 0.8000 | 0.3583 | 0.2350 | 0.1225 | 6.50 | 10.24 |

## Latency variability

One warm-up request per query and mode is excluded. Each query's measured requests are averaged before calculating the P50/P95 values in the aggregate results table above.

The table below instead summarizes all individual measured requests, including their sample standard deviation.

| Mode | Requests | Mean (ms) | Std dev (ms) | Raw P50 (ms) | Raw P95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| semantic | 200 | 6.93 | 2.57 | 6.40 | 8.19 |

## Constraint satisfaction comparison

Constraint satisfaction is measured per returned chunk hit against the
original question filters, using independently retrieved metadata.
Semantic retrieval does not apply these filters during retrieval;
hybrid retrieval enforces them in SQL.

| Mode | Queries checked | Returned hits | Compliant hits | Violations | Empty results | Compliance rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 450 | 420 | 30 | 0 | 0.9333 |

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


## Per-query results

| Query ID | Mode | Reciprocal rank | Latency (ms) | Retrieved article IDs |
|---|---|---:|---:|---|
| sem_01 | semantic | 1.0000 | 10.23 | 3268249, 13995 |
| sem_02 | semantic | 1.0000 | 7.73 | 97026, 97034, 557931, 100558, 45809 |
| sem_03 | semantic | 1.0000 | 7.40 | 45809, 100558, 221244, 25750, 230401, 125297 |
| sem_04 | semantic | 1.0000 | 6.94 | 125297, 27471338, 199701, 6021, 66294, 2052, 23862, 18016, 10933, 59868 |
| sem_05 | semantic | 1.0000 | 6.86 | 13833, 18167, 4266, 439526, 31274, 23968131, 37704882 |
| sem_06 | semantic | 0.2500 | 6.57 | 8377, 217356, 325521, 60776, 25873, 7990, 24799509 |
| sem_07 | semantic | 1.0000 | 6.51 | 8640, 8377, 25873, 7990, 24799509, 93548 |
| sem_08 | semantic | 1.0000 | 6.38 | 3480761, 25873, 1711076, 175285, 8377, 23968131, 7990, 24799509 |
| sem_09 | semantic | 1.0000 | 6.48 | 23968131, 8377, 24799509, 25873, 37704882, 21855450, 29004 |
| sem_10 | semantic | 1.0000 | 6.55 | 74020014, 6836612, 43561218, 23824, 24799509, 4266, 5218, 31274, 8377, 233488, 65309, 1711076, 25873, 8640 |
| sem_11 | semantic | 1.0000 | 7.17 | 1360091, 1164, 21523, 32472154, 50073184, 1706303, 40409788 |
| sem_12 | semantic | 1.0000 | 6.04 | 173332, 233488, 20926, 40409788, 21523, 32472154, 1363880 |
| sem_13 | semantic | 1.0000 | 6.04 | 61603971, 6759, 21652, 1164, 73248112, 21523, 5739 |
| sem_14 | semantic | 0.5000 | 6.04 | 233488, 66294, 1164, 21523 |
| sem_15 | semantic | 1.0000 | 6.20 | 1860407 |
| sem_16 | semantic | 1.0000 | 7.54 | 6734, 66924, 10933, 2356196, 6021, 18016, 15881, 29414838 |
| sem_17 | semantic | 1.0000 | 5.94 | 5739, 59868, 10939 |
| sem_18 | semantic | 1.0000 | 5.99 | 27471338, 27010, 164952, 42946389, 23485, 1507538 |
| sem_19 | semantic | 1.0000 | 6.55 | 55955, 222828, 1771747, 217356, 7398, 1010280 |
| sem_20 | semantic | 1.0000 | 6.13 | 222828, 27010, 639009, 416612 |
| sem_21 | semantic | 0.5000 | 6.09 | 22194, 32354, 66924, 21346982, 311193 |
| sem_22 | semantic | 1.0000 | 6.18 | 105181, 217356, 36827, 24485, 164557, 45303, 45178, 22194 |
| sem_23 | semantic | 1.0000 | 6.11 | 8339 |
| sem_24 | semantic | 1.0000 | 6.18 | 24222, 18934432, 25385, 59644 |
| sem_25 | semantic | 1.0000 | 6.14 | 21391870, 6854, 1208 |
| hyb_01 | semantic | 1.0000 | 6.18 | 1711076, 25873, 4674, 13833, 4266, 24799509, 23968131, 3480761, 31274, 8640, 8377, 1010280, 7990, 37704882 |
| hyb_02 | semantic | 1.0000 | 6.22 | 26411268, 8377, 217356, 23968131, 60776, 37704882, 325521, 41054, 24799509, 25873 |
| hyb_03 | semantic | 1.0000 | 10.38 | 752991, 8377, 25873 |
| hyb_04 | semantic | 0.5000 | 16.50 | 19545, 24960699, 25873 |
| hyb_05 | semantic | 1.0000 | 6.72 | 29004, 25873, 8377, 24799509, 19545, 175285, 244884 |
| hyb_06 | semantic | 1.0000 | 6.50 | 100558, 25750, 45809, 97026, 125297, 230401, 97034 |
| hyb_07 | semantic | 1.0000 | 6.67 | 20039, 3268249, 201154, 25977485, 15205, 13995 |
| hyb_08 | semantic | 0.3333 | 6.55 | 4320, 4674, 2118, 4266, 26397, 18167 |
| hyb_09 | semantic | 0.2500 | 6.34 | 233488, 20926, 6836612, 76340, 173332, 65309, 233497, 1164, 1363880 |
| hyb_10 | semantic | 1.0000 | 6.25 | 40409788, 32472154, 1164, 21523, 233497 |
| hyb_11 | semantic | 0.1000 | 6.29 | 6021, 18016, 8218, 5739, 6734, 59868, 23939, 8095, 27404990, 29414838, 72038, 6759, 10939, 12590, 23862, 27471338, 10933, 2356196 |
| hyb_12 | semantic | 1.0000 | 6.58 | 10933, 18203, 2356196, 23862, 199701, 27471338, 24131, 18016, 27404990, 29414838, 3254510 |
| hyb_13 | semantic | 0.1429 | 6.65 | 15323, 15476, 22747, 31929, 25750, 24485, 30538, 4122592 |
| hyb_14 | semantic | 1.0000 | 6.59 | 526999, 20901, 7398 |
| hyb_15 | semantic | 1.0000 | 6.75 | 1260, 18934432, 187813, 29004, 1638777, 72038, 22747, 8339 |
