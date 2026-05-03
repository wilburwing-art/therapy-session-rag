import * as Linking from "expo-linking";
import { router, Stack } from "expo-router";
import { useEffect, useRef } from "react";
import { Alert } from "react-native";

import { redeemMagicLink } from "@/lib/auth";

/**
 * Root stack + deep-link handler.
 *
 * Inbound URLs look like `therapyrag://chat?t=<token>` (also works
 * from a browser-initiated redirect from the email). The token is
 * POSTed to /api/v1/auth/patient/session; on success the session
 * cookie is persisted and we push the user to the chat screen.
 */
export default function RootLayout() {
  // useRef so a hot reload doesn't cause us to redeem the same token
  // twice — magic links are single-use on the server.
  const redeemingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const handleUrl = async (url: string | null) => {
      if (!url) return;
      const parsed = Linking.parse(url);
      const token = typeof parsed.queryParams?.t === "string"
        ? parsed.queryParams.t
        : null;
      if (!token) return;

      if (redeemingRef.current.has(token)) return;
      redeemingRef.current.add(token);

      try {
        await redeemMagicLink(token);
        router.replace("/chat");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Could not sign you in.";
        Alert.alert("Sign-in failed", message);
        router.replace("/");
      }
    };

    // Cold start: the URL that launched the app.
    Linking.getInitialURL().then((url) => {
      void handleUrl(url);
    });

    // Warm start: app already running when the link is tapped.
    const sub = Linking.addEventListener("url", (event) => {
      void handleUrl(event.url);
    });

    return () => {
      sub.remove();
    };
  }, []);

  return (
    <Stack
      screenOptions={{
        headerShown: true,
        headerTitle: "TherapyRAG",
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="chat" options={{ title: "Chat" }} />
      <Stack.Screen name="sessions" options={{ title: "Your sessions" }} />
    </Stack>
  );
}
