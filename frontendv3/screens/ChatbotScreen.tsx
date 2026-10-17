import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Markdown from 'react-native-markdown-display';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { formatApiError } from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

interface Message {
  id: string;
  from: 'bot' | 'user';
  text: string;
}

export default function ChatbotScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      from: 'bot',
    text: '**AI responses require backend provider configuration.** No offline or mock medical answers are generated.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    if (flatListRef.current && messages.length > 0) {
      flatListRef.current.scrollToEnd({ animated: true });
    }
  }, [messages, loading]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      from: 'user',
      text: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await api.post('/chat/', { message: trimmed });
      const botReply = response.data.response;
      if (typeof botReply !== 'string' || !botReply.trim()) {
        throw new Error('The assistant returned an invalid response.');
      }

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        from: 'bot',
        text: botReply,
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      const status = (err as any)?.response?.status;
      const message = status === 503
        ? 'AI responses require backend provider configuration. No medical response was generated.'
        : status === 502
          ? 'The AI provider is temporarily unavailable. Please try again later.'
          : status === 401
            ? 'Your session expired. Sign in again to continue.'
            : formatApiError(err, 'Could not reach the healthcare assistant. Check your connection and try again.');
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        from: 'bot',
        text: message,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isBot = item.from === 'bot';

    return (
      <View style={[styles.messageContainer, isBot ? styles.botMessage : styles.userMessage]}>
        {isBot && (
          <View style={styles.botIcon}>
            <Ionicons name="medical" size={16} color={COLORS.primary} />
          </View>
        )}
        <View style={[styles.messageBubble, isBot ? styles.botBubble : styles.userBubble]}>
          <Markdown
            style={{
              body: {
                color: isBot ? COLORS.text : COLORS.white,
                fontSize: moderateScale(SIZES.small),
                lineHeight: moderateScale(20),
              },
              strong: {
                fontWeight: '700',
                color: isBot ? COLORS.text : COLORS.white,
              },
              paragraph: {
                marginVertical: 0,
              },
              list_item: {
                marginVertical: 2,
              },
            }}
          >
            {item.text}
          </Markdown>
        </View>
      </View>
    );
  };

  const renderTypingIndicator = () => {
    if (!loading) return null;

    return (
      <View style={[styles.messageContainer, styles.botMessage]}>
        <View style={styles.botIcon}>
          <Ionicons name="medical" size={16} color={COLORS.primary} />
        </View>
        <View style={[styles.messageBubble, styles.botBubble, styles.typingBubble]}>
          <View style={styles.typingDots}>
            <View style={[styles.dot, styles.dot1]} />
            <View style={[styles.dot, styles.dot2]} />
            <View style={[styles.dot, styles.dot3]} />
          </View>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Vitalyze AI Assistant</Text>
          <Text style={styles.headerSubtitle}>Powered by Gemini Medical AI</Text>
        </View>

        {/* Messages */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messagesList}
          showsVerticalScrollIndicator={false}
          ListFooterComponent={renderTypingIndicator}
        />

        {/* Input Area */}
        <View style={styles.inputArea}>
          <TextInput
            style={styles.input}
            placeholder="Ask a medical question..."
            placeholderTextColor={COLORS.textMuted}
            value={input}
            onChangeText={setInput}
            multiline
            maxLength={1000}
            editable={!loading}
          />
          <TouchableOpacity
            style={[styles.sendButton, (!input.trim() || loading) && styles.sendButtonDisabled]}
            onPress={handleSend}
            disabled={!input.trim() || loading}
          >
            {loading ? (
              <ActivityIndicator size="small" color={COLORS.white} />
            ) : (
              <Ionicons name="send" size={20} color={COLORS.white} />
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingVertical: moderateScale(12),
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  headerTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
  },
  headerSubtitle: {
    fontSize: moderateScale(SIZES.caption),
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  messagesList: {
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingVertical: moderateScale(16),
  },
  messageContainer: {
    flexDirection: 'row',
    marginBottom: moderateScale(12),
    alignItems: 'flex-end',
  },
  botMessage: {
    justifyContent: 'flex-start',
  },
  userMessage: {
    justifyContent: 'flex-end',
  },
  botIcon: {
    width: moderateScale(28),
    height: moderateScale(28),
    borderRadius: moderateScale(14),
    backgroundColor: 'rgba(0, 188, 212, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: moderateScale(8),
  },
  messageBubble: {
    maxWidth: '80%',
    padding: moderateScale(12),
    borderRadius: SIZES.radius,
  },
  botBubble: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderBottomLeftRadius: 4,
  },
  userBubble: {
    backgroundColor: COLORS.primary,
    borderBottomRightRadius: 4,
    marginLeft: 'auto',
  },
  typingBubble: {
    paddingVertical: moderateScale(16),
  },
  typingDots: {
    flexDirection: 'row',
    gap: 4,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.primary,
    opacity: 0.6,
  },
  dot1: {
    opacity: 1,
  },
  dot2: {
    opacity: 0.7,
  },
  dot3: {
    opacity: 0.4,
  },
  inputArea: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingVertical: moderateScale(12),
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    backgroundColor: COLORS.surface,
    gap: moderateScale(10),
  },
  input: {
    flex: 1,
    backgroundColor: COLORS.surfaceLight,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius,
    paddingHorizontal: moderateScale(14),
    paddingVertical: moderateScale(12),
    fontSize: moderateScale(SIZES.body),
    color: COLORS.text,
    maxHeight: 100,
  },
  sendButton: {
    width: moderateScale(48),
    height: moderateScale(48),
    borderRadius: moderateScale(24),
    backgroundColor: COLORS.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
});
