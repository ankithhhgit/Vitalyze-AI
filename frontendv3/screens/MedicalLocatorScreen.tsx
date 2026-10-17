import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { Picker } from '@react-native-picker/picker';
import api from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

interface Store {
  place_id: string;
  name: string;
  vicinity: string;
  rating?: number;
  user_ratings_total?: number;
  geometry: { lat: number; lng: number };
  distanceVal?: string;
}

interface LocationCoords {
  lat: number;
  lng: number;
}

export default function MedicalLocatorScreen() {
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState<LocationCoords | null>(null);
  const [radius, setRadius] = useState(5000);

  const calculateDistance = (lat1: number, lon1: number, lat2: number, lon2: number): string => {
    const R = 6371;
    const dLat = deg2rad(lat2 - lat1);
    const dLon = deg2rad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return (R * c).toFixed(1);
  };

  const deg2rad = (deg: number): number => {
    return deg * (Math.PI / 180);
  };

  const fetchStores = async (lat: number, lng: number, searchRadius: number) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/maps/pharmacies', {
        params: { lat, lng, radius: searchRadius },
      });

      const resultsWithDistance = response.data.map((store: Store) => ({
        ...store,
        distanceVal: calculateDistance(lat, lng, store.geometry.lat, store.geometry.lng),
      }));

      resultsWithDistance.sort((a: Store, b: Store) => 
        parseFloat(a.distanceVal || '0') - parseFloat(b.distanceVal || '0')
      );

      setStores(resultsWithDistance);
    } catch (err: any) {
      if (err.response?.status === 503) {
        setError('Pharmacy search is not configured. The backend needs a pharmacy search API key.');
      } else if (err.response?.status === 502) {
        setError('The pharmacy provider is temporarily unavailable. Please try again later.');
      } else if (err.response?.status === 504) {
        setError('The pharmacy provider timed out. Please try again.');
      } else if (err.response?.status === 401) {
        setError('Your session expired. Sign in again to continue.');
      } else {
        setError('Could not load pharmacies. Check your connection and try again.');
      }
      setStores([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const getLocation = async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== 'granted') {
          setError('Location permission denied. Please allow location access in settings.');
          setLoading(false);
          return;
        }

        const locationResult = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });

        const { latitude, longitude } = locationResult.coords;
        setLocation({ lat: latitude, lng: longitude });
      } catch (err) {
        console.error('Location Error:', err);
        setError('Could not get your location. Please check your location settings.');
        setLoading(false);
      }
    };

    if (!location) {
      getLocation();
    }
  }, []);

  useEffect(() => {
    if (location) {
      fetchStores(location.lat, location.lng, radius);
    }
  }, [location, radius]);

  const handleViewMap = (store: Store) => {
    // Geoapify place IDs are not Google place IDs, so link by coordinates.
    const { lat, lng } = store.geometry;
    const url = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
    Linking.openURL(url).catch(() => setError('Could not open Google Maps on this device.'));
  };

  const openNearbyPharmaciesInMaps = () => {
    const query = encodeURIComponent(
      location ? `pharmacies near ${location.lat},${location.lng}` : 'pharmacies near me'
    );
    Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${query}`)
      .catch(() => setError('Could not open Google Maps on this device.'));
  };

  const renderStoreCard = ({ item }: { item: Store }) => (
    <View style={styles.storeCard}>
      <View style={styles.storeHeader}>
        <Text style={styles.storeName} numberOfLines={1}>{item.name}</Text>
        <View style={styles.distanceBadge}>
          <Text style={styles.distanceText}>{item.distanceVal} km</Text>
        </View>
      </View>

      <View style={styles.storeInfo}>
        <View style={styles.infoRow}>
          <Ionicons name="location-outline" size={16} color={COLORS.textSecondary} />
          <Text style={styles.infoText} numberOfLines={2}>{item.vicinity || 'Address not available'}</Text>
        </View>

        <View style={styles.infoRow}>
          <Ionicons name="star" size={16} color={COLORS.warning} />
          <Text style={styles.infoText}>
            {item.rating ? `${item.rating} (${item.user_ratings_total || 0} reviews)` : 'No ratings yet'}
          </Text>
        </View>
      </View>

      <TouchableOpacity style={styles.mapButton} onPress={() => handleViewMap(item)}>
        <Text style={styles.mapButtonText}>View on Map</Text>
        <Ionicons name="open-outline" size={16} color={COLORS.primary} />
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <View style={styles.header}>
        <Text style={styles.title}>Medical Locator</Text>
        <Text style={styles.subtitle}>Find Trusted Pharmacies Near You</Text>
      </View>

      {error && (
        <View style={styles.errorCard}>
          <Ionicons name="alert-circle" size={24} color={COLORS.error} />
          <Text style={styles.errorText}>{error}</Text>
          <Text style={styles.errorText}>This opens a separate Google Maps search; Vitalyze has not retrieved pharmacy results.</Text>
          <TouchableOpacity style={styles.mapButton} onPress={openNearbyPharmaciesInMaps}>
            <Text style={styles.mapButtonText}>Open nearby search in Google Maps</Text>
          </TouchableOpacity>
        </View>
      )}

      {location && (
        <View style={styles.controls}>
          <View style={styles.locationInfo}>
            <Ionicons name="navigate" size={16} color={COLORS.primary} />
            <Text style={styles.locationText}>
              {location.lat.toFixed(4)}, {location.lng.toFixed(4)}
            </Text>
          </View>

          <View style={styles.pickerContainer}>
            <Picker
              selectedValue={radius}
              onValueChange={(value) => setRadius(value)}
              style={styles.picker}
              dropdownIconColor={COLORS.text}
              enabled={!loading}
            >
              <Picker.Item label="Within 1 km" value={1000} />
              <Picker.Item label="Within 3 km" value={3000} />
              <Picker.Item label="Within 5 km" value={5000} />
              <Picker.Item label="Within 10 km" value={10000} />
            </Picker>
          </View>
          <Text style={styles.radiusHint}>
            {loading
              ? 'Radius selection is paused while search is loading.'
              : error
                ? 'Radius changes apply when the pharmacy search provider is available.'
                : 'Choose how far to search for pharmacies.'}
          </Text>
        </View>
      )}

      {loading && (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.loadingText}>Locating Pharmacies...</Text>
        </View>
      )}

      {!loading && !error && stores.length === 0 && location && (
        <View style={styles.emptyContainer}>
          <Ionicons name="medical-outline" size={48} color={COLORS.textMuted} />
          <Text style={styles.emptyText}>No pharmacies found within {radius / 1000} km.</Text>
        </View>
      )}

      {!loading && !error && stores.length > 0 && (
        <View style={styles.resultsContainer}>
          <Text style={styles.resultsCount}>{stores.length} Results Found</Text>
          <FlatList
            data={stores}
            keyExtractor={(item) => item.place_id}
            renderItem={renderStoreCard}
            contentContainerStyle={styles.listContent}
            showsVerticalScrollIndicator={false}
          />
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  header: {
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingTop: moderateScale(8),
    paddingBottom: moderateScale(16),
  },
  title: {
    fontSize: moderateScale(SIZES.h2),
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginTop: moderateScale(4),
  },
  errorCard: {
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 10,
    backgroundColor: 'rgba(255, 123, 114, 0.1)',
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(14),
    marginHorizontal: moderateScale(SIZES.padding),
    marginBottom: moderateScale(16),
  },
  errorText: {
    flex: 1,
    color: COLORS.error,
    fontSize: moderateScale(SIZES.small),
  },
  controls: {
    paddingHorizontal: moderateScale(SIZES.padding),
    marginBottom: moderateScale(16),
  },
  locationInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: moderateScale(12),
  },
  locationText: {
    fontSize: moderateScale(SIZES.caption),
    color: COLORS.textSecondary,
  },
  pickerContainer: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    overflow: 'hidden',
  },
  picker: {
    color: COLORS.text,
    height: 50,
  },
  radiusHint: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(SIZES.caption),
    marginTop: moderateScale(6),
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: moderateScale(16),
  },
  loadingText: {
    fontSize: moderateScale(SIZES.body),
    color: COLORS.textSecondary,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: moderateScale(12),
    paddingHorizontal: moderateScale(SIZES.padding * 2),
  },
  emptyText: {
    fontSize: moderateScale(SIZES.body),
    color: COLORS.textSecondary,
    textAlign: 'center',
  },
  resultsContainer: {
    flex: 1,
    paddingHorizontal: moderateScale(SIZES.padding),
  },
  resultsCount: {
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: moderateScale(12),
  },
  listContent: {
    paddingBottom: moderateScale(20),
  },
  storeCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    marginBottom: moderateScale(12),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  storeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: moderateScale(12),
  },
  storeName: {
    flex: 1,
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
    marginRight: moderateScale(10),
  },
  distanceBadge: {
    backgroundColor: 'rgba(0, 188, 212, 0.15)',
    paddingHorizontal: moderateScale(10),
    paddingVertical: moderateScale(4),
    borderRadius: moderateScale(12),
  },
  distanceText: {
    fontSize: moderateScale(SIZES.caption),
    fontWeight: '600',
    color: COLORS.primary,
  },
  storeInfo: {
    gap: moderateScale(8),
    marginBottom: moderateScale(12),
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  infoText: {
    flex: 1,
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
  },
  mapButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: moderateScale(10),
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    marginTop: moderateScale(4),
  },
  mapButtonText: {
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
    color: COLORS.primary,
  },
});
