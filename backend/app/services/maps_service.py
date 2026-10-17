import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"

# Geoapify pharmacy categories. The second key covers chemists/drugstores that
# are tagged under the commercial tree.
PHARMACY_CATEGORIES = "healthcare.pharmacy,commercial.health_and_beauty.pharmacy"

REQUEST_TIMEOUT_SECONDS = 8
MAX_RESULTS = 40


class MapsProviderError(Exception):
    """Provider request failed; intentionally carries no upstream details."""


class MapsProviderTimeoutError(MapsProviderError):
    """Provider request exceeded the configured timeout."""


class MapsService:
    def __init__(self):
        self.api_key = (settings.GEOAPIFY_API_KEY or "").strip()
        if not self.api_key:
            logger.warning("GEOAPIFY_API_KEY not set. Pharmacy search will not function.")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def get_nearby_pharmacies(self, lat: float, lon: float, radius: int = 5000) -> list:
        """
        Fetches nearby pharmacies using the Geoapify Places API.

        Results are limited to the requested circle and biased by proximity to
        the user so the closest pharmacies are returned first.
        """
        if not self.is_configured:
            logger.error("Geoapify client not initialized.")
            raise MapsProviderError()

        params = {
            "categories": PHARMACY_CATEGORIES,
            "filter": f"circle:{lon},{lat},{radius}",
            "bias": f"proximity:{lon},{lat}",
            "limit": MAX_RESULTS,
            "apiKey": self.api_key,
        }

        try:
            response = requests.get(
                GEOAPIFY_PLACES_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            # Timeouts are surfaced separately so the endpoint can respond 504.
            logger.error("Geoapify request timed out (%s).", type(exc).__name__)
            raise MapsProviderTimeoutError() from None
        except Exception as exc:
            # Provider errors can include request URLs or credential details.
            logger.error("Geoapify request failed (%s).", type(exc).__name__)
            raise MapsProviderError() from None

        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list):
            logger.error("Geoapify response did not include a features array.")
            raise MapsProviderError()

        pharmacies = []
        for feature in features:
            simplified = self._simplify_feature(feature)
            if simplified is not None:
                pharmacies.append(simplified)
        return pharmacies

    @staticmethod
    def _simplify_feature(feature) -> dict | None:
        """Map a Geoapify GeoJSON feature to the response shape the app expects."""
        if not isinstance(feature, dict):
            return None

        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []

        lat = properties.get("lat")
        lon = properties.get("lon")
        if (lat is None or lon is None) and isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            # GeoJSON positions are [longitude, latitude].
            lon, lat = coordinates[0], coordinates[1]

        if lat is None or lon is None:
            return None

        address = (
            properties.get("formatted")
            or properties.get("address_line1")
            or properties.get("address_line2")
        )

        # Geoapify place_id is a stable provider identifier; fall back to the
        # coordinates so the client always receives a usable key.
        place_id = properties.get("place_id") or f"geoapify:{lat},{lon}"

        return {
            "name": properties.get("name") or "Pharmacy",
            "vicinity": address,
            # Geoapify does not expose ratings, so we must not claim one.
            "rating": None,
            "user_ratings_total": None,
            "geometry": {
                "lat": lat,
                "lng": lon,
            },
            "place_id": str(place_id),
        }


maps_service = MapsService()
