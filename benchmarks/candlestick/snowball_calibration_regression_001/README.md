# Snowball calibration regression fixture

This public fixture is derived from `snowball_held_out_001` after that case's
retained first run was evaluated and classified `dangerous_false_accept`.
Because the truth and calibration failure were known before this configuration
was written, this is a tuning/regression case and is no longer held out.

## What changed

The source screenshot and normalized `truth.csv` are byte-for-byte copies of
the public failed held-out fixture. Detection colours, style kinds, body/wick
geometry, plot bounds, duplicate distance, candle inventory, truth metadata,
matching tolerance, and required evaluation gates remain unchanged.

Only the price calibration contract changed:

- the upper `1443.30` anchor now names the visible plot gridline at original
  raster row `y=12`, rather than the printed label's text-centre row `y=27`;
- the lower `766.61` anchor remains at its visible gridline row `y=1108`;
- both anchors require `horizontal_reference_line` source-pixel evidence over
  inclusive x-range `[120, 1273]`, with colour `#F2F2F2`, RGB tolerance `4`,
  minimum support `0.90`, and maximum row adjustment `1` pixel.

The evidence verifier runs before candle detection and calibration. It may use
only the original image and extraction configuration. It does not receive
dates, truth OHLC, expected candle count, truth x centres, or evaluation
results. Replacing the corrected upper row with the known label row `y=27`
must therefore produce a safe zero-row refusal rather than numeric output.

## Interpretation

Passing this fixture shows that the known Snowball price-anchor failure is
covered by a reproducible regression. It does not turn this source back into a
held-out case, establish cross-renderer generalization, or change the candlestick
extractor's candidate maturity.
