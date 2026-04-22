import { Link, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { CrisisBanner } from "@/components/CrisisBanner";
import { Message } from "@/components/Message";
import { apiFetch, ApiError } from "@/lib/api";
import { clearSession, getSession } from "@/lib/auth";
import type {
  ChatMessageViewModel,
  ChatRequest,
  ChatResponse,
} from "@/types";

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessageViewModel[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const listRef = useRef<FlatList<ChatMessageViewModel>>(null);

  useEffect(() => {
    (async () => {
      const session = await getSession();
      if (!session) router.replace("/");
    })();
  }, []);

  const scrollToEnd = useCallback(() => {
    // Defer to after render so measurement is settled.
    requestAnimationFrame(() => {
      listRef.current?.scrollToEnd({ animated: true });
    });
  }, []);

  const send = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMessage: ChatMessageViewModel = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    const pendingAssistant: ChatMessageViewModel = {
      id: `local-pending-${Date.now()}`,
      role: "assistant",
      content: "…",
      pending: true,
    };
    setMessages((prev) => [...prev, userMessage, pendingAssistant]);
    setInput("");
    setSending(true);
    scrollToEnd();

    try {
      const body: ChatRequest = {
        message: trimmed,
        conversation_id: conversationId,
      };
      const response = await apiFetch<ChatResponse>("/api/v1/chat/patient", {
        method: "POST",
        json: body,
      });
      setConversationId(response.conversation_id);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingAssistant.id
            ? {
                id: response.conversation_id + "-" + prev.length,
                role: "assistant",
                content: response.response,
                sources: response.sources,
              }
            : m,
        ),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await clearSession();
        router.replace("/");
        return;
      }
      const errMessage =
        err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingAssistant.id
            ? {
                id: m.id,
                role: "assistant",
                content: errMessage,
                error: true,
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
      scrollToEnd();
    }
  }, [conversationId, input, scrollToEnd, sending]);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={Platform.OS === "ios" ? 88 : 0}
    >
      <CrisisBanner />
      <View style={styles.toolbar}>
        <Link href="/sessions" asChild>
          <Pressable accessibilityRole="link">
            <Text style={styles.toolbarLink}>Your sessions</Text>
          </Pressable>
        </Link>
        <Pressable
          accessibilityRole="button"
          onPress={async () => {
            await clearSession();
            router.replace("/");
          }}
        >
          <Text style={styles.toolbarLink}>Sign out</Text>
        </Pressable>
      </View>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <Message message={item} />}
        contentContainerStyle={styles.list}
        onContentSizeChange={scrollToEnd}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Ask about your sessions</Text>
            <Text style={styles.emptyBody}>
              Try: "What did we talk about last week?" or "Remind me of the
              breathing exercise we tried."
            </Text>
          </View>
        }
      />
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Type your question"
          placeholderTextColor="#94a3b8"
          multiline
          editable={!sending}
        />
        <Pressable
          accessibilityRole="button"
          onPress={send}
          disabled={sending || input.trim().length === 0}
          style={[
            styles.sendButton,
            (sending || input.trim().length === 0) && styles.sendButtonDisabled,
          ]}
        >
          {sending ? (
            <ActivityIndicator color="#ffffff" />
          ) : (
            <Text style={styles.sendText}>Send</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#ffffff",
  },
  toolbar: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#e2e8f0",
  },
  toolbarLink: {
    color: "#2563eb",
    fontSize: 14,
    fontWeight: "600",
  },
  list: {
    paddingVertical: 12,
    flexGrow: 1,
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
  inputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    padding: 12,
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#e2e8f0",
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#cbd5f5",
    borderRadius: 20,
    fontSize: 15,
    color: "#0f172a",
    backgroundColor: "#f8fafc",
  },
  sendButton: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    minWidth: 72,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: {
    backgroundColor: "#94a3b8",
  },
  sendText: {
    color: "#ffffff",
    fontWeight: "700",
  },
});
