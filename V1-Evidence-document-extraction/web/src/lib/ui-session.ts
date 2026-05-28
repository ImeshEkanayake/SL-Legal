import "server-only";

import { cookies } from "next/headers";
import { verifyUiSessionToken } from "./ui-session-token";

export type UiSession = {
  userId: string;
  source: "signed_cookie" | "development_env";
};

const DEFAULT_SESSION_COOKIE_NAME = "sl_legal_session";

export async function resolveUiSession(): Promise<UiSession> {
  const cookieName = process.env.SL_LEGAL_UI_SESSION_COOKIE_NAME?.trim() || DEFAULT_SESSION_COOKIE_NAME;
  const secret = uiSessionSecret();
  const cookieStore = await cookies();
  const token = cookieStore.get(cookieName)?.value;
  if (token) {
    const payload = verifyUiSessionToken({ token, secret });
    return { userId: payload.userId, source: "signed_cookie" };
  }

  const devUserId = process.env.SL_LEGAL_UI_USER_ID?.trim();
  if (process.env.NODE_ENV !== "production" && devUserId) {
    return { userId: devUserId, source: "development_env" };
  }

  throw new Error(
    `No signed UI session was found. Set the ${cookieName} cookie with a signed session token before loading the legal workspace.`,
  );
}

function uiSessionSecret(): string {
  const secret = process.env.SL_LEGAL_UI_SESSION_SECRET?.trim() || process.env.SL_LEGAL_AUTH_HMAC_SECRET?.trim();
  if (!secret || secret.length < 32) {
    throw new Error("SL_LEGAL_UI_SESSION_SECRET or SL_LEGAL_AUTH_HMAC_SECRET must be at least 32 characters.");
  }
  return secret;
}
