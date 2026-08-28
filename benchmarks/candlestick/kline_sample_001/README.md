# kline_sample_001

This is a user-consented real-raster tuning and regression benchmark. It is not a held-out case and does not establish general candlestick support.

- `original.png` is retained at its original 1505 x 874 resolution.
- `truth.csv` contains the 11 date/OHLC rows mapped from `股票数据汇总.xlsx` and independently annotated original-pixel candle centers.
- Dates identify benchmark rows; they are not treated as image-extracted values.
- Truth data is available only to the evaluator after extraction. The extractor receives only `manifest.json/extraction_config` and the locked image contract.
- Volume, turnover, percentage changes, amplitude, moving averages, annotations, and hidden source records are outside this benchmark.
