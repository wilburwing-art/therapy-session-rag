import { StyleSheet, Text, View } from "react-native";

import type { ChatSource } from "@/types";

interface CitationCardProps {
  source: ChatSource;
}

export function CitationCard({ source }: CitationCardProps) {
  const timestamp =
    source.start_time != null ? formatTimestamp(source.start_time) : null;
  const relevance = `${Math.round(source.relevance_score * 100)}%`;
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.label}>
          {source.speaker ?? "Session"}
          {timestamp ? ` · ${timestamp}` : ""}
        </Text>
        <Text style={styles.relevance}>{relevance}</Text>
      </View>
      <Text style={styles.preview} numberOfLines={3}>
        {source.content_preview}
      </Text>
    </View>
  );
}

function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const mm = Math.floor(total / 60);
  const ss = total % 60;
  return `${mm}:${ss.toString().padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 10,
    padding: 10,
    backgroundColor: "#ffffff",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  label: {
    fontSize: 12,
    fontWeight: "600",
    color: "#475569",
  },
  relevance: {
    fontSize: 12,
    color: "#64748b",
  },
  preview: {
    fontSize: 13,
    color: "#334155",
    lineHeight: 18,
  },
});
