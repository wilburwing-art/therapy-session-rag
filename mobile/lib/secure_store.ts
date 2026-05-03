// Tiny typed wrapper over expo-secure-store so the rest of the app
// doesn't have to deal with string serialization or null-vs-missing.

import * as SecureStore from "expo-secure-store";

import type { StoredSession } from "@/types";

const SESSION_KEY = "therapyrag_patient_session";

export async function getItem(key: string): Promise<string | null> {
  return SecureStore.getItemAsync(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value);
}

export async function deleteItem(key: string): Promise<void> {
  await SecureStore.deleteItemAsync(key);
}

export async function getStoredSession(): Promise<StoredSession | null> {
  const raw = await getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    // Corrupt payload — clear so the user re-authenticates cleanly.
    await deleteItem(SESSION_KEY);
    return null;
  }
}

export async function setStoredSession(session: StoredSession): Promise<void> {
  await setItem(SESSION_KEY, JSON.stringify(session));
}

export async function clearStoredSession(): Promise<void> {
  await deleteItem(SESSION_KEY);
}

export { SESSION_KEY };
