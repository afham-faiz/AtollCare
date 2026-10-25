// The browser → bridge frame format. If this drifts from presage-bridge/src/index.js the SDK silently gets nothing.
import { expect, test } from "bun:test";

import { encodeFrame, encodeJpegFrame } from "./presage";

test("frame header matches what the bridge decodes", () => {
  const width = 4;
  const height = 2;
  const pixels = new Uint8ClampedArray(width * height * 4).map((_, i) => i);
  const buf = encodeFrame(pixels, width, height, 1234.5);
  const view = new DataView(buf);

  expect(String.fromCharCode(...new Uint8Array(buf, 0, 4))).toBe("ACPF"); // magic 0x41435046, big-endian
  expect(view.getUint16(4)).toBe(width);
  expect(view.getUint16(6)).toBe(height);
  expect(view.getFloat64(8)).toBe(1234.5);
  // the bridge drops any frame whose payload isn't exactly width × height × 4
  expect(buf.byteLength - 16).toBe(width * height * 4);
  expect([...new Uint8Array(buf, 16, 3)]).toEqual([0, 1, 2]);
});

test("JPEG frames carry the same header with their own magic", () => {
  const jpeg = new Uint8Array([0xff, 0xd8, 1, 2, 3, 0xff, 0xd9]).buffer;
  const buf = encodeJpegFrame(jpeg, 360, 640, 99.25);
  const view = new DataView(buf);
  expect(String.fromCharCode(...new Uint8Array(buf, 0, 4))).toBe("ACPJ"); // magic 0x4143504a, big-endian
  expect(view.getUint16(4)).toBe(360);
  expect(view.getUint16(6)).toBe(640);
  expect(view.getFloat64(8)).toBe(99.25);
  expect([...new Uint8Array(buf, 16)]).toEqual([0xff, 0xd8, 1, 2, 3, 0xff, 0xd9]);
});
