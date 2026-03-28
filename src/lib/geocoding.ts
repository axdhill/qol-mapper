export interface GeocodingResult {
  name: string;
  displayName: string;
  lng: number;
  lat: number;
  type: string;
}

const PHOTON_API = "https://photon.komoot.io/api/";
const NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse";

/**
 * Forward geocode a query string to geographic coordinates.
 * Uses Photon (Komoot) for fast, free autocomplete.
 * Bounded to continental US.
 */
export async function geocode(query: string): Promise<GeocodingResult[]> {
  if (!query.trim()) return [];

  const params = new URLSearchParams({
    q: query,
    limit: "5",
    bbox: "-125,24,-66,50", // CONUS bounding box
    lang: "en",
  });

  const res = await fetch(`${PHOTON_API}?${params}`);
  if (!res.ok) return [];

  const data = await res.json();

  return (data.features ?? []).map(
    (f: {
      geometry: { coordinates: number[] };
      properties: {
        name?: string;
        city?: string;
        state?: string;
        postcode?: string;
        type?: string;
      };
    }) => {
      const props = f.properties;
      const parts = [props.name, props.city, props.state, props.postcode].filter(
        Boolean
      );
      return {
        name: props.name || props.city || "Unknown",
        displayName: parts.join(", "),
        lng: f.geometry.coordinates[0],
        lat: f.geometry.coordinates[1],
        type: props.type || "place",
      };
    }
  );
}

/**
 * Reverse geocode coordinates to a place name.
 * Uses Nominatim (rate limited, 1 req/sec).
 */
export async function reverseGeocode(
  lng: number,
  lat: number
): Promise<string> {
  const params = new URLSearchParams({
    format: "json",
    lat: lat.toString(),
    lon: lng.toString(),
    zoom: "10",
  });

  const res = await fetch(`${NOMINATIM_REVERSE}?${params}`, {
    headers: { "User-Agent": "QoLMapper/1.0" },
  });

  if (!res.ok) return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

  const data = await res.json();
  return data.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
}
