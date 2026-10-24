// Light map with English labels (Esri World Light Gray + reference layer): origin, destination, route, vehicle.
"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

import type { Region, Transfer } from "@/lib/api";
import { place } from "@/lib/format";

const BASE = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";

function Fit({ t }: { t: Transfer }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(
      L.latLngBounds([
        [t.origin_point.lat, t.origin_point.lng],
        [t.destination_point.lat, t.destination_point.lng],
      ]),
      { padding: [36, 36], maxZoom: 10 },
    );
  }, [map, t.id, t.origin_point, t.destination_point]);
  return null;
}

export default function ({ t, region, height = "16rem" }: { t: Transfer; region?: Region; height?: string }) {
  const vehicle = useMemo(
    () =>
      L.divIcon({
        className: "",
        html: '<div style="width:16px;height:16px;border-radius:50%;background:#0f9286;border:3px solid #fff;box-shadow:0 0 0 2px #0f9286"></div>',
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      }),
    [],
  );
  const o: [number, number] = [t.origin_point.lat, t.origin_point.lng];
  const d: [number, number] = [t.destination_point.lat, t.destination_point.lng];
  const p: [number, number] = [t.position.lat, t.position.lng];
  return (
    <div style={{ height }} className="w-full overflow-hidden rounded-[1.25rem] border-[1px] border-line">
      <MapContainer center={o} zoom={8} scrollWheelZoom={false} zoomControl={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer url={BASE} attribution="Tiles &copy; Esri — Esri, HERE, Garmin, &copy; OpenStreetMap contributors" maxZoom={16} />
        <TileLayer url={LABELS} maxZoom={16} />
        <Fit t={t} />
        <Polyline positions={[o, d]} pathOptions={{ color: "#8a9aaa", weight: 2, dashArray: "6 6" }} />
        <Polyline positions={[o, p]} pathOptions={{ color: "#0f9286", weight: 3 }} />
        <CircleMarker center={o} radius={6} pathOptions={{ color: "#4f6377", fillColor: "#fff", fillOpacity: 1, weight: 2 }}>
          <Tooltip>{place(region, t.origin_id)}</Tooltip>
        </CircleMarker>
        <CircleMarker center={d} radius={7} pathOptions={{ color: "#0b766c", fillColor: "#0f9286", fillOpacity: 1, weight: 2 }}>
          <Tooltip permanent direction="top" offset={[0, -6]}>
            {place(region, t.destination_id)}
          </Tooltip>
        </CircleMarker>
        {t.status !== "arrived" && t.status !== "closed" && <Marker position={p} icon={vehicle} />}
      </MapContainer>
    </div>
  );
}
