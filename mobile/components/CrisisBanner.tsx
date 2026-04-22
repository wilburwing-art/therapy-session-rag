import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

/**
 * Fixed-position banner shown above the chat. Required by our safety
 * UX: a patient should always have one tap to a human crisis line,
 * regardless of what the RAG said.
 */
export function CrisisBanner() {
  return (
    <View style={styles.container} accessibilityRole="alert">
      <Text style={styles.title}>In crisis?</Text>
      <Text style={styles.body}>
        This chat is not a substitute for emergency care. Call or text 988 to
        reach the Suicide & Crisis Lifeline.
      </Text>
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          style={styles.action}
          onPress={() => {
            void Linking.openURL("tel:988");
          }}
        >
          <Text style={styles.actionText}>Call 988</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          style={styles.action}
          onPress={() => {
            void Linking.openURL("sms:988");
          }}
        >
          <Text style={styles.actionText}>Text 988</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#fef3c7",
    borderBottomWidth: 1,
    borderBottomColor: "#fbbf24",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  title: {
    fontSize: 13,
    fontWeight: "700",
    color: "#78350f",
  },
  body: {
    fontSize: 12,
    color: "#78350f",
    marginTop: 2,
    lineHeight: 16,
  },
  actions: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8,
  },
  action: {
    backgroundColor: "#b45309",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionText: {
    color: "#ffffff",
    fontSize: 12,
    fontWeight: "600",
  },
});
