import { router } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { getSession } from "@/lib/auth";

/**
 * Landing route.
 *
 * If a valid session cookie is already persisted, jump straight to
 * /chat. Otherwise show the "waiting for your link" state — the user
 * is expected to arrive via a `therapyrag://chat?t=…` deep link from
 * the email their therapist sent.
 */
export default function Landing() {
  const [status, setStatus] = useState<"checking" | "waiting">("checking");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const session = await getSession();
      if (cancelled) return;
      if (session) {
        router.replace("/chat");
        return;
      }
      setStatus("waiting");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "checking") {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Waiting for your sign-in link</Text>
      <Text style={styles.body}>
        Your therapist will email you a one-tap link. Open it on this device
        to start chatting with your session history.
      </Text>
      <Text style={styles.subtle}>
        Links expire after 15 minutes and can only be used once.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
    backgroundColor: "#ffffff",
    gap: 12,
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    color: "#0f172a",
    textAlign: "center",
  },
  body: {
    fontSize: 15,
    color: "#334155",
    textAlign: "center",
    lineHeight: 22,
  },
  subtle: {
    fontSize: 13,
    color: "#64748b",
    textAlign: "center",
    marginTop: 8,
  },
});
