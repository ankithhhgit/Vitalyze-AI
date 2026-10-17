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
import { Picker } from '@react-native-picker/picker';
import { useAuth } from '../context/AuthContext';
import { formatApiError, isE164PhoneNumber, normalizePhoneNumber } from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

export default function RegisterScreen() {
  const navigation = useNavigation<any>();
  const { register } = useAuth();

  const [formData, setFormData] = useState({
    name: '',
    age: '',
    gender: 'male',
    password: '',
  });
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (name: string, value: string) => {
    setFormData({ ...formData, [name]: value });
  };

  const handleSubmit = async () => {
    if (loading) return;
    setError('');

    if (!phone.trim() || !formData.password || !formData.name.trim()) {
      setError('Please fill in all required fields.');
      return;
    }

    const normalizedPhone = normalizePhoneNumber(phone);
    if (!isE164PhoneNumber(normalizedPhone)) {
      setError('Enter your phone in international format, for example +91 98765 43210.');
      return;
    }

    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    const age = formData.age.trim() ? Number(formData.age) : null;
    if (age !== null && (!Number.isInteger(age) || age <= 0)) {
      setError('Age must be a positive whole number.');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        name: formData.name.trim(),
        phone_number: normalizedPhone,
        password: formData.password,
        age,
        gender: formData.gender,
      };

      await register(payload);
      Alert.alert('Success', 'Registration Successful! Please Sign In.', [
        { text: 'OK', onPress: () => navigation.navigate('SignIn') },
      ]);
    } catch (err: any) {
      setError(formatApiError(err, 'Registration failed. Check your details and try again.'));
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
          <Text style={styles.title}>Create an Account</Text>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Full Name *</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter your full name"
              placeholderTextColor={COLORS.textMuted}
              value={formData.name}
              onChangeText={(value) => handleChange('name', value)}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Phone Number *</Text>
            <TextInput
              style={styles.input}
              placeholder="+91 98765 43210"
              placeholderTextColor={COLORS.textMuted}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Password (Min 8 chars) *</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter your password"
              placeholderTextColor={COLORS.textMuted}
              value={formData.password}
              onChangeText={(value) => handleChange('password', value)}
              secureTextEntry
            />
          </View>

          <View style={styles.row}>
            <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
              <Text style={styles.label}>Age</Text>
              <TextInput
                style={styles.input}
                placeholder="Age"
                placeholderTextColor={COLORS.textMuted}
                value={formData.age}
                onChangeText={(value) => handleChange('age', value)}
                keyboardType="numeric"
              />
            </View>

            <View style={[styles.inputGroup, { flex: 1, marginLeft: 8 }]}>
              <Text style={styles.label}>Gender</Text>
              <View style={styles.pickerContainer}>
                <Picker
                  selectedValue={formData.gender}
                  onValueChange={(value) => handleChange('gender', value)}
                  style={styles.picker}
                  dropdownIconColor={COLORS.text}
                >
                  <Picker.Item label="Male" value="male" />
                  <Picker.Item label="Female" value="female" />
                  <Picker.Item label="Other" value="other" />
                </Picker>
              </View>
            </View>
          </View>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSubmit}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <Text style={styles.buttonText}>Register</Text>
            )}
          </TouchableOpacity>

          <View style={styles.linkContainer}>
            <Text style={styles.linkText}>Already have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('SignIn')}>
              <Text style={styles.link}>Sign In</Text>
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
  row: {
    flexDirection: 'row',
  },
  pickerContainer: {
    backgroundColor: COLORS.surfaceLight,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    overflow: 'hidden',
  },
  picker: {
    color: COLORS.text,
    height: 50,
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
