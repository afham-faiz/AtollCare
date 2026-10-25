import { describe, expect, test } from "bun:test";

import { splitPlace } from "./format";

describe("splitPlace", () => {
  test("takes the atoll out of the brackets", () => {
    expect(splitPlace("Dhangethi Health Centre (Alif Dhaalu)")).toEqual({ name: "Dhangethi Health Centre", area: "Alif Dhaalu" });
  });

  test("leaves a plain name alone", () => {
    expect(splitPlace("IGMH")).toEqual({ name: "IGMH", area: null });
  });
});
