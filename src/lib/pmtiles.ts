import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";

let protocolAdded = false;

/**
 * Register the PMTiles protocol with MapLibre GL.
 * This must be called once before creating a Map instance.
 * After registration, sources can use "pmtiles://" URLs.
 */
export function addPMTilesProtocol(): void {
  if (protocolAdded) return;

  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tilev4);
  protocolAdded = true;
}
