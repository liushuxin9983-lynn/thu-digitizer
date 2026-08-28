#!/usr/bin/env node
/** Render one deterministic Lightweight Charts case and record renderer coordinates. */

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';


function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error('usage: node render_lwc_case.mjs --spec SPEC --output-dir DIR');
    }
    values[key.slice(2)] = value;
  }
  if (!values.spec || !values['output-dir']) {
    throw new Error('both --spec and --output-dir are required');
  }
  return values;
}


async function readPackageVersion(packagePath) {
  return JSON.parse(await fs.readFile(packagePath, 'utf8')).version;
}


async function main() {
  const args = parseArgs(process.argv.slice(2));
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const outputDir = path.resolve(args['output-dir']);
  await fs.mkdir(outputDir, { recursive: true });
  const spec = JSON.parse(await fs.readFile(path.resolve(args.spec), 'utf8'));
  const libraryScript = path.join(
    scriptDir,
    'node_modules',
    'lightweight-charts',
    'dist',
    'lightweight-charts.standalone.production.js',
  );

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: spec.width, height: spec.height },
      deviceScaleFactor: 1,
      locale: 'en-US',
      timezoneId: 'UTC',
    });
    const page = await context.newPage();
    await page.setContent(
      '<!doctype html><html><head><meta charset="utf-8"></head>' +
      `<body style="margin:0;overflow:hidden;background:${spec.theme.background}">` +
      `<div id="chart" style="width:${spec.width}px;height:${spec.height}px"></div></body></html>`,
    );
    await page.addScriptTag({ path: libraryScript });
    const rendered = await page.evaluate(async (input) => {
      const L = globalThis.LightweightCharts;
      const chart = L.createChart(document.getElementById('chart'), {
        width: input.width,
        height: input.height,
        layout: {
          background: { type: L.ColorType.Solid, color: input.theme.background },
          textColor: input.theme.text,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: input.theme.grid },
          horzLines: { color: input.theme.grid },
        },
        crosshair: { mode: L.CrosshairMode.Hidden },
        handleScroll: false,
        handleScale: false,
        rightPriceScale: {
          visible: true,
          borderVisible: true,
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          borderVisible: true,
          fixLeftEdge: true,
          fixRightEdge: true,
          rightOffset: 0,
          timeVisible: false,
          secondsVisible: false,
        },
      });
      const candleSeries = chart.addSeries(L.CandlestickSeries, input.candlestick);
      candleSeries.setData(input.candles);
      for (const overlay of input.overlays ?? []) {
        const line = chart.addSeries(L.LineSeries, {
          color: overlay.color,
          lineWidth: overlay.width,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        line.setData(overlay.data);
      }
      chart.timeScale().fitContent();
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

      const timeScale = chart.timeScale();
      const paneWidth = timeScale.width();
      const paneHeight = input.height - timeScale.height();
      const candleXCenters = input.candles.map((row) => timeScale.timeToCoordinate(row.time));
      const anchorPixels = [
        Math.max(1, Math.round(paneHeight * 0.15)),
        Math.max(2, Math.round(paneHeight * 0.85)),
      ];
      const priceAnchors = anchorPixels.map((pixel) => ({
        pixel,
        value: candleSeries.coordinateToPrice(pixel),
      }));
      const canvas = chart.takeScreenshot();
      return {
        pngBase64: canvas.toDataURL('image/png').split(',')[1],
        paneWidth,
        paneHeight,
        candleXCenters,
        priceAnchors,
      };
    }, spec);

    const allCoordinates = [
      ...rendered.candleXCenters,
      ...rendered.priceAnchors.flatMap((anchor) => [anchor.pixel, anchor.value]),
    ];
    if (rendered.candleXCenters.length !== spec.candles.length ||
        allCoordinates.some((value) => !Number.isFinite(value))) {
      throw new Error('renderer returned missing or non-finite coordinates');
    }

    await fs.writeFile(path.join(outputDir, 'original.png'), Buffer.from(rendered.pngBase64, 'base64'));
    const metadata = {
      schema_version: 1,
      case_id: spec.case_id,
      coordinate_space: 'original_raster_pixels',
      width: spec.width,
      height: spec.height,
      plot_bounds: [0, 0, Math.floor(rendered.paneWidth) - 1, Math.floor(rendered.paneHeight) - 1],
      candle_x_centers: rendered.candleXCenters.map((value) => Number(value.toFixed(6))),
      price_anchors: rendered.priceAnchors.map((anchor) => ({
        pixel: anchor.pixel,
        value: Number(anchor.value.toFixed(8)),
      })),
      renderer: {
        name: 'lightweight-charts',
        version: await readPackageVersion(path.join(scriptDir, 'node_modules', 'lightweight-charts', 'package.json')),
        playwright_version: await readPackageVersion(path.join(scriptDir, 'node_modules', 'playwright', 'package.json')),
        browser: await browser.version(),
        device_scale_factor: 1,
      },
    };
    await fs.writeFile(
      path.join(outputDir, 'render-metadata.json'),
      `${JSON.stringify(metadata, null, 2)}\n`,
      'utf8',
    );
    await context.close();
  } finally {
    await browser.close();
  }
}


main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.exitCode = 1;
});
