import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { formatApiError, isE164PhoneNumber, normalizePhoneNumber } from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

export default function SignInScreen() {
  const navigation = useNavigation<any>();
  const { login } = useAuth();

  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setError('');
    setLoading(true);

    const normalizedPhone = normalizePhoneNumber(phone);
    if (!normalizedPhone || !password) {
      setError('Please enter both phone number and password.');
      setLoading(false);
      return;
    }
    if (!isE164PhoneNumber(normalizedPhone)) {
      setError('Enter your phone in international format, for example +91 98765 43210.');
      setLoading(false);
      return;
    }

    try {
      await login(normalizedPhone, password);
    } catch (err: any) {
      setError(formatApiError(err, 'Sign in failed. Check your phone number and password.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.formContainer}>
          <Text style={styles.title}>Sign In to Vitalyze</Text>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Phone Number</Text>
            <TextInput
              style={styles.input}
              placeholder="+91 98765 43210"
              placeholderTextColor={COLORS.textMuted}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              autoCapitalize="none"
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter your password"
              placeholderTextColor={COLORS.textMuted}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
          </View>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <Text style={styles.buttonText}>Sign In</Text>
            )}
          </TouchableOpacity>

          <View style={styles.linkContainer}>
            <Text style={styles.linkText}>New User? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Register')}>
              <Text style={styles.link}>Create an Account</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: moderateScale(SIZES.padding * 1.5),
  },
  formContainer: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding * 1.5),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  title: {
    fontSize: moderateScale(SIZES.h2),
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: moderateScale(24),
  },
  errorText: {
    color: COLORS.error,
    fontSize: moderateScale(SIZES.small),
    textAlign: 'center',
    marginBottom: moderateScale(16),
    padding: moderateScale(10),
    backgroundColor: 'rgba(255, 123, 114, 0.1)',
    borderRadius: SIZES.radius / 2,
  },
  inputGroup: {
    marginBottom: moderateScale(16),
  },
  label: {
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
    color: COLORS.text,
    marginBottom: moderateScale(8),
  },
  input: {
    backgroundColor: COLORS.surfaceLight,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(14),
    fontSize: moderateScale(SIZES.body),
    color: COLORS.text,
  },
  button: {
    backgroundColor: COLORS.primary,
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(16),
    alignItems: 'center',
    marginTop: moderateScale(8),
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: COLORS.white,
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
  },
  linkContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: moderateScale(24),
  },
  linkText: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(SIZES.small),
  },
  link: {
    color: COLORS.primary,
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
  },
});
