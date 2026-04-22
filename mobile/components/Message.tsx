import { StyleSheet, Text, View } from "react-native";

import { CitationCard } from "@/components/CitationCard";
import type { ChatMessageViewModel } from "@/types";

interface MessageProps {
  message: ChatMessageViewModel;
}

export function Message({ message }: MessageProps) {
  const isUser = message.role === "user";
  return (
    <View
      style={[
        styles.row,
        isUser ? styles.rowUser : styles.rowAssistant,
      ]}
    >
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAssistant,
          message.error ? styles.bubbleError : null,
        ]}
      >
        <Text
          style={[
            styles.text,
            isUser ? styles.textUser : styles.textAssistant,
          ]}
        >
          {message.content}
        </Text>
        {message.pending ? (
          <Text style={styles.pending}>Sending…</Text>
        ) : null}
      </View>

      {!isUser && message.sources && message.sources.length > 0 ? (
        <View style={styles.citations}>
          {message.sources.map((source) => (
            <CitationCard key={source.chunk_id} source={source} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  rowUser: {
    alignItems: "flex-end",
  },
  rowAssistant: {
    alignItems: "flex-start",
  },
  bubble: {
    maxWidth: "85%",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
  },
  bubbleUser: {
    backgroundColor: "#2563eb",
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: "#f1f5f9",
    borderBottomLeftRadius: 4,
  },
  bubbleError: {
    backgroundColor: "#fee2e2",
  },
  text: {
    fontSize: 16,
    lineHeight: 22,
  },
  textUser: {
    color: "#ffffff",
  },
  textAssistant: {
    color: "#0f172a",
  },
  pending: {
    fontSize: 12,
    color: "#cbd5f5",
    marginTop: 4,
  },
  citations: {
    marginTop: 6,
    width: "85%",
    gap: 4,
  },
});
