"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export interface MapViewportProps {
  routesGeoJSON: any;
  customers: Array<{ id: string; lat: number; lng: number; demand?: number }>;
  depot: { id: string; lat: number; lng: number };
  activeLocation?: string;
}

const CITY_PRESETS: Record<string, { center: [number, number]; zoom: number }> = {
  "salt-lake": {
    center: [88.4330, 22.5800],
    zoom: 13.5,
  },
  "manhattan": {
    center: [-73.9712, 40.7831],
    zoom: 13.0,
  },
};

export default function MapViewport({ routesGeoJSON, customers, depot, activeLocation = "Salt Lake" }: MapViewportProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const apiKey = process.env.NEXT_PUBLIC_STADIA_API_KEY || "";
  const isManhattan = activeLocation.toLowerCase().includes("manhattan");
  const targetCity = isManhattan ? CITY_PRESETS["manhattan"] : CITY_PRESETS["salt-lake"];

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    // Bulletproof Raster Fallback: Immune to WebGL Vector parsing crashes
    const STADIA_RASTER_STYLE: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        "stadia-dark": {
          type: "raster",
          tiles: [
            `https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png?api_key=${apiKey}`
          ],
          tileSize: 256,
          attribution: "&copy; Stadia Maps &copy; OpenMapTiles &copy; OpenStreetMap contributors",
        }
      },
      layers: [
        {
          id: "stadia-dark-layer",
          type: "raster",
          source: "stadia-dark",
          minzoom: 0,
          maxzoom: 20,
        }
      ]
    };

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: STADIA_RASTER_STYLE,
      center: targetCity.center,
      zoom: targetCity.zoom,
      // CRITICAL FIX: minZoom and maxBounds are completely removed to prevent Camera Lock
      attributionControl: false,
    });

    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

    map.on("load", () => {
      map.resize();

      map.addSource("routes", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "routes-glow",
        type: "line",
        source: "routes",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 7,
          "line-opacity": 0.35,
          "line-blur": 2,
        },
      });

      map.addLayer({
        id: "routes-line",
        type: "line",
        source: "routes",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": 3,
          "line-opacity": 0.95,
        },
      });
    });

    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(mapContainer.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, [apiKey]); // Added Dependency

  // Handle city switching dynamically without bounding box lockups
  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({
      center: targetCity.center,
      zoom: targetCity.zoom,
      duration: 1200,
    });
  }, [activeLocation, targetCity]);

  // Update dynamic route line features
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    const setRoutes = () => {
      const source = map.getSource("routes") as maplibregl.GeoJSONSource;
      if (source && routesGeoJSON) {
        source.setData(routesGeoJSON);
      }
    };

    if (map.isStyleLoaded()) {
      setRoutes();
    } else {
      map.once("styledata", setRoutes);
    }
  }, [routesGeoJSON]);

  // Render Depot and Customer Node Markers
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    document.querySelectorAll(".vrp-marker").forEach((el) => el.remove());

    if (depot.lat !== 0 && depot.lng !== 0) {
      const depotEl = document.createElement("div");
      depotEl.className = "vrp-marker w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-lg shadow-red-500/50 z-20";
      new maplibregl.Marker({ element: depotEl }).setLngLat([depot.lng, depot.lat]).addTo(map);
    }

    customers.forEach((c) => {
      const el = document.createElement("div");
      el.className = "vrp-marker w-3 h-3 bg-blue-400 rounded-full border border-white shadow-sm z-10";
      new maplibregl.Marker({ element: el }).setLngLat([c.lng, c.lat]).addTo(map);
    });

    if (customers.length > 0 && depot.lat !== 0) {
      const allLngs = [depot.lng, ...customers.map((c) => c.lng)];
      const allLats = [depot.lat, ...customers.map((c) => c.lat)];
      map.fitBounds(
        [
          [Math.min(...allLngs) - 0.005, Math.min(...allLats) - 0.005],
          [Math.max(...allLngs) + 0.005, Math.max(...allLats) + 0.005],
        ],
        { padding: 80, duration: 1000 }
      );
    }
  }, [customers, depot]);

  return (
    <div className="absolute inset-0 w-full h-full bg-[#18191a]">
      <div ref={mapContainer} className="absolute inset-0 w-full h-full outline-none" />
    </div>
  );
}