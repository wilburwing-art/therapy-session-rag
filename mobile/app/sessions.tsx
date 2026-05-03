import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { apiFetch, ApiError } from "@/lib/api";
import { clearSession, getSession } from "@/lib/auth";
import type { Session } from "@/types";

export default function SessionsScreen() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    const session = await getSession();
    if (!session) {
      router.replace("/");
      return;
    }
    try {
      const list = await apiFetch<Session[]>(
        `/api/v1/sessions/patient/${session.patient_id}`,
      );
      setSessions(list);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await clearSession();
        router.replace("/");
        return;
      }
      setError(
        err instanceof Error ? err.message : "Could not load your sessions.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  if (sessions === null && error === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorTitle}>Could not load sessions</Text>
        <Text style={styles.errorBody}>{error}</Text>
        <Pressable style={styles.retry} onPress={() => void load()}>
          <Text style={styles.retryText}>Try again</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <FlatList
      data={sessions ?? []}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.list}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No sessions yet</Text>
          <Text style={styles.emptyBody}>
            Recordings your therapist uploads will appear here once they're
            processed.
          </Text>
        </View>
      }
      renderItem={({ item }) => <SessionRow session={item} />}
    />
  );
}

function SessionRow({ session }: { session: Session }) {
  const date = new Date(session.session_date);
  const dateLabel = Number.isNaN(date.getTime())
    ? session.session_date
    : date.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      });
  const duration =
    session.recording_duration_seconds != null
      ? formatDuration(session.recording_duration_seconds)
      : null;

  return (
    <View style={styles.row}>
      <View style={styles.rowTop}>
        <Text style={styles.rowDate}>{dateLabel}</Text>
        <StatusPill status={session.status} />
      </View>
      <View style={styles.rowMeta}>
        <Text style={styles.rowMetaText}>
          {session.session_type === "video_call" ? "Video call" : "Upload"}
        </Text>
        {duration ? (
          <Text style={styles.rowMetaText}>· {duration}</Text>
        ) : null}
      </View>
    </View>
  );
}

function StatusPill({ status }: { status: Session["status"] }) {
  const tone = STATUS_TONE[status];
  return (
    <View style={[styles.pill, { backgroundColor: tone.bg }]}>
      <Text style={[styles.pillText, { color: tone.fg }]}>{status}</Text>
    </View>
  );
}

const STATUS_TONE: Record<Session["status"], { bg: string; fg: string }> = {
  pending: { bg: "#fef3c7", fg: "#78350f" },
  uploaded: { bg: "#e0e7ff", fg: "#3730a3" },
  transcribing: { bg: "#e0e7ff", fg: "#3730a3" },
  embedding: { bg: "#e0e7ff", fg: "#3730a3" },
  ready: { bg: "#dcfce7", fg: "#166534" },
  failed: { bg: "#fee2e2", fg: "#991b1b" },
};

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hh = Math.floor(total / 3600);
  const mm = Math.floor((total % 3600) / 60);
  if (hh > 0) return `${hh}h ${mm}m`;
  return `${mm}m`;
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 8,
    backgroundColor: "#ffffff",
  },
  errorTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "#991b1b",
  },
  errorBody: {
    fontSize: 14,
    color: "#475569",
    textAlign: "center",
  },
  retry: {
    marginTop: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: "#2563eb",
  },
  retryText: {
    color: "#ffffff",
    fontWeight: "700",
  },
  list: {
    padding: 16,
    gap: 10,
    flexGrow: 1,
    backgroundColor: "#ffffff",
  },
  empty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
    gap: 8,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: "#0f172a",
  },
  emptyBody: {
    fontSize: 14,
    color: "#475569",
    textAlign: "center",
    lineHeight: 20,
  },
  row: {
    padding: 14,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 10,
    backgroundColor: "#ffffff",
  },
  rowTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  rowDate: {
    fontSize: 15,
    fontWeight: "600",
    color: "#0f172a",
  },
  rowMeta: {
    flexDirection: "row",
    gap: 6,
    marginTop: 4,
  },
  rowMetaText: {
    fontSize: 13,
    color: "#64748b",
  },
  pill: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
  },
  pillText: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
});
