import { describe, expect, it } from "vitest";
import { createUiSessionToken, verifyUiSessionToken } from "./ui-session-token";

const secret = "test-ui-session-secret-with-32-characters";

describe("ui session tokens", () => {
  it("verifies a signed session token", () => {
    const token = createUiSessionToken({
      userId: "user_1",
      secret,
      nowSeconds: 1_800_000_000,
      ttlSeconds: 600,
    });

    expect(
      verifyUiSessionToken({
        token,
        secret,
        nowSeconds: 1_800_000_100,
      }),
    ).toMatchObject({
      version: 1,
      userId: "user_1",
      issuedAt: 1_800_000_000,
      expiresAt: 1_800_000_600,
    });
  });

  it("rejects expired tokens", () => {
    const token = createUiSessionToken({
      userId: "user_1",
      secret,
      nowSeconds: 1_800_000_000,
      ttlSeconds: 600,
    });

    expect(() =>
      verifyUiSessionToken({
        token,
        secret,
        nowSeconds: 1_800_000_601,
      }),
    ).toThrow("expired");
  });

  it("rejects tampered payloads", () => {
    const token = createUiSessionToken({
      userId: "user_1",
      secret,
      nowSeconds: 1_800_000_000,
      ttlSeconds: 600,
    });
    const [payload, signature] = token.split(".");
    const tamperedToken = `${payload.slice(0, -1)}x.${signature}`;

    expect(() =>
      verifyUiSessionToken({
        token: tamperedToken,
        secret,
        nowSeconds: 1_800_000_100,
      }),
    ).toThrow("signature");
  });
});
