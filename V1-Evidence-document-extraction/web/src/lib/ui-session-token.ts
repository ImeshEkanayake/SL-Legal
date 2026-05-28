import { createHmac, timingSafeEqual } from "node:crypto";

export type UiSessionPayload = {
  version: 1;
  userId: string;
  issuedAt: number;
  expiresAt: number;
};

const MAX_CLOCK_SKEW_SECONDS = 120;
const USER_ID_PATTERN = /^[A-Za-z0-9_.:@-]{1,128}$/;

export function createUiSessionToken({
  userId,
  secret,
  nowSeconds = Math.floor(Date.now() / 1000),
  ttlSeconds = 8 * 60 * 60,
}: {
  userId: string;
  secret: string;
  nowSeconds?: number;
  ttlSeconds?: number;
}): string {
  assertUsableSecret(secret);
  assertUsableUserId(userId);
  if (!Number.isInteger(ttlSeconds) || ttlSeconds < 60) {
    throw new Error("UI session ttlSeconds must be at least 60 seconds.");
  }
  const payload: UiSessionPayload = {
    version: 1,
    userId,
    issuedAt: nowSeconds,
    expiresAt: nowSeconds + ttlSeconds,
  };
  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  return `${encodedPayload}.${signPayload(encodedPayload, secret)}`;
}

export function verifyUiSessionToken({
  token,
  secret,
  nowSeconds = Math.floor(Date.now() / 1000),
}: {
  token: string;
  secret: string;
  nowSeconds?: number;
}): UiSessionPayload {
  assertUsableSecret(secret);
  const [encodedPayload, signature, ...extra] = token.split(".");
  if (!encodedPayload || !signature || extra.length > 0) {
    throw new Error("Invalid UI session token format.");
  }
  const expectedSignature = signPayload(encodedPayload, secret);
  if (!safeEqual(signature, expectedSignature)) {
    throw new Error("Invalid UI session signature.");
  }
  const parsed = JSON.parse(base64UrlDecode(encodedPayload)) as Partial<UiSessionPayload>;
  if (parsed.version !== 1) {
    throw new Error("Unsupported UI session version.");
  }
  if (typeof parsed.userId !== "string" || !USER_ID_PATTERN.test(parsed.userId)) {
    throw new Error("Invalid UI session user.");
  }
  if (
    typeof parsed.issuedAt !== "number" ||
    typeof parsed.expiresAt !== "number" ||
    !Number.isInteger(parsed.issuedAt) ||
    !Number.isInteger(parsed.expiresAt)
  ) {
    throw new Error("Invalid UI session timestamps.");
  }
  const issuedAt = parsed.issuedAt;
  const expiresAt = parsed.expiresAt;
  if (issuedAt > nowSeconds + MAX_CLOCK_SKEW_SECONDS) {
    throw new Error("UI session was issued in the future.");
  }
  if (expiresAt <= nowSeconds) {
    throw new Error("UI session has expired.");
  }
  return { version: 1, userId: parsed.userId, issuedAt, expiresAt };
}

function signPayload(encodedPayload: string, secret: string): string {
  return createHmac("sha256", secret).update(encodedPayload).digest("base64url");
}

function base64UrlEncode(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

function base64UrlDecode(value: string): string {
  return Buffer.from(value, "base64url").toString("utf8");
}

function assertUsableSecret(secret: string): void {
  if (secret.length < 32) {
    throw new Error("UI session secret must be at least 32 characters.");
  }
}

function assertUsableUserId(userId: string): void {
  if (!USER_ID_PATTERN.test(userId)) {
    throw new Error("UI session user id contains unsupported characters.");
  }
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return timingSafeEqual(leftBuffer, rightBuffer);
}
