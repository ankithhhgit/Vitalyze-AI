import logging

import pytest
import requests

from app.services import maps_service as maps_service_module


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"synthetic status {self.status_code}")

    def json(self):
        return self._payload


def make_feature(name, lat, lon, **properties):
    props = {"name": name, "lat": lat, "lon": lon}
    props.update(properties)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(maps_service_module.maps_service, "api_key", "synthetic-key")
    return maps_service_module.maps_service


def test_successful_search_maps_geoapify_fields(configured, monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "type": "FeatureCollection",
                "features": [
                    make_feature(
                        "Synthetic Pharmacy",
                        12.34,
                        56.78,
                        address_line1="1 Synthetic Street",
                        formatted="1 Synthetic Street, Synthetic City",
                        place_id="geoapify-place-1",
                    ),
                    make_feature(
                        "Second Pharmacy",
                        12.35,
                        56.79,
                        formatted="2 Synthetic Street, Synthetic City",
                        place_id="geoapify-place-2",
                    ),
                ],
            }
        )

    monkeypatch.setattr(maps_service_module.requests, "get", fake_get)

    results = configured.get_nearby_pharmacies(12.34, 56.78, 3000)

    assert captured["url"] == maps_service_module.GEOAPIFY_PLACES_URL
    assert captured["params"]["categories"] == maps_service_module.PHARMACY_CATEGORIES
    assert captured["params"]["filter"] == "circle:56.78,12.34,3000"
    assert captured["params"]["apiKey"] == "synthetic-key"
    assert captured["timeout"] == maps_service_module.REQUEST_TIMEOUT_SECONDS

    assert len(results) == 2
    first = results[0]
    assert first["name"] == "Synthetic Pharmacy"
    assert first["vicinity"] == "1 Synthetic Street, Synthetic City"
    assert first["geometry"] == {"lat": 12.34, "lng": 56.78}
    assert first["place_id"] == "geoapify-place-1"
    # Geoapify does not provide ratings, so nothing may be claimed.
    assert first["rating"] is None
    assert first["user_ratings_total"] is None


def test_feature_falls_back_to_geometry_coordinates(configured, monkeypatch):
    feature = {
        "type": "Feature",
        "properties": {"name": "Geometry Only", "place_id": "geoapify-place-3"},
        "geometry": {"type": "Point", "coordinates": [10.5, -20.25]},
    }
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"features": [feature]}),
    )

    results = configured.get_nearby_pharmacies(0, 0, 1000)

    assert results == [
        {
            "name": "Geometry Only",
            "vicinity": None,
            "rating": None,
            "user_ratings_total": None,
            "geometry": {"lat": -20.25, "lng": 10.5},
            "place_id": "geoapify-place-3",
        }
    ]


def test_place_id_falls_back_to_coordinates_when_absent(configured, monkeypatch):
    feature = {
        "type": "Feature",
        "properties": {"name": "No Id"},
        "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
    }
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"features": [feature]}),
    )

    results = configured.get_nearby_pharmacies(0, 0, 1000)

    assert results[0]["place_id"] == "geoapify:2.0,1.0"


def test_empty_results_return_empty_list(configured, monkeypatch):
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"type": "FeatureCollection", "features": []}),
    )

    assert configured.get_nearby_pharmacies(1.0, 2.0, 5000) == []


def test_feature_without_coordinates_is_skipped(configured, monkeypatch):
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"features": [{"properties": {"name": "No Coords"}}]}),
    )

    assert configured.get_nearby_pharmacies(1.0, 2.0, 5000) == []


def test_missing_key_raises_provider_error(monkeypatch):
    monkeypatch.setattr(maps_service_module.maps_service, "api_key", "")

    with pytest.raises(maps_service_module.MapsProviderError):
        maps_service_module.maps_service.get_nearby_pharmacies(1.0, 2.0, 5000)


def test_http_error_raises_provider_error(configured, monkeypatch, caplog):
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"error": "synthetic"}, status_code=500),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(maps_service_module.MapsProviderError):
            configured.get_nearby_pharmacies(1.0, 2.0, 5000)

    assert "synthetic" not in caplog.text


def test_connection_error_is_generic_and_does_not_leak(configured, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("https://api.geoapify.com?apiKey=synthetic-secret")

    monkeypatch.setattr(maps_service_module.requests, "get", boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(maps_service_module.MapsProviderError):
            configured.get_nearby_pharmacies(1.0, 2.0, 5000)

    assert "synthetic-secret" not in caplog.text
    assert "api.geoapify.com" not in caplog.text


def test_timeout_raises_timeout_error(configured, monkeypatch):
    def boom(*args, **kwargs):
        raise requests.Timeout("synthetic timeout")

    monkeypatch.setattr(maps_service_module.requests, "get", boom)

    with pytest.raises(maps_service_module.MapsProviderTimeoutError):
        configured.get_nearby_pharmacies(1.0, 2.0, 5000)


def test_malformed_payload_raises_provider_error(configured, monkeypatch):
    monkeypatch.setattr(
        maps_service_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"type": "FeatureCollection"}),
    )

    with pytest.raises(maps_service_module.MapsProviderError):
        configured.get_nearby_pharmacies(1.0, 2.0, 5000)
