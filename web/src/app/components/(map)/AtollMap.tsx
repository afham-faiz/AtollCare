// F-M4.3 Live map (react-leaflet, CARTO tiles matching theme): facilities by type, origin/destination, planned
// route polylines (dashed per leg, coloured by mode), live asset marker interpolated between polls, trail.
"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

import type { Facility, RouteOption, TrackResponse } from "@/lib/api";
import { MODE_COLOR, MODE_LABEL } from "@/lib/format";

export type MapCase = {
  id: string;
  label: string;
  originId: string;
  destinationId?: string | null;
  route?: RouteOption | null;
  track?: TrackResponse | null;
  highlight?: boolean;
};

const TYPE_STYLE: Record<string, { color: string; radius: number }> = {
  tertiary_hospital: { color: "#d92d20", radius: 8 },
  regional_hospital: { color: "#d92d20", radius: 6 },
  atoll_hospital: { color: "#d92d20", radius: 5 },
  health_centre: { color: "#0e7c86", radius: 5 },
  airport: { color: "#6b4fbb", radius: 4 },
};

function useDark() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const read = () => {
      const t = document.documentElement.dataset.theme;
      setDark(t ? t === "dark" : mq.matches);
    };
    read();
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    mq.addEventListener("change", read);
    return () => {
      obs.disconnect();
      mq.removeEventListener("change", read);
    };
  }, []);
  return dark;
}

const assetIcon = (color: string) =>
  L.divIcon({
    className: "",
    html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 0 0 2px ${color}"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });

/** Smoothly interpolates a marker between polled positions. */
function LiveMarker({ lat, lng, color, label }: { lat: number; lng: number; color: string; label: string }) {
  const [pos, setPos] = useState<[number, number]>([lat, lng]);
  const from = useRef<[number, number]>([lat, lng]);
  useEffect(() => {
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const step = (now: number) => {
      const f = Math.min(1, (now - start) / 1800);
      const next: [number, number] = [origin[0] + (lat - origin[0]) * f, origin[1] + (lng - origin[1]) * f];
      setPos(next);
      from.current = next;
      if (f < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [lat, lng]);
  const icon = useMemo(() => assetIcon(color), [color]);
  return (
    <Marker position={pos} icon={icon} zIndexOffset={1000}>
      <Tooltip direction="top" offset={[0, -10]}>
        {label}
      </Tooltip>
    </Marker>
  );
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join("|");
  useEffect(() => {
    if (points.length < 2) return;
    map.fitBounds(L.latLngBounds(points), { padding: [32, 32], maxZoom: 9 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

export default function ({
  facilities,
  cases = [],
  height = "24rem",
  fit = true,
}: {
  facilities: Facility[];
  cases?: MapCase[];
  height?: string;
  fit?: boolean;
}) {
  const dark = useDark();
  const byId = useMemo(() => Object.fromEntries(facilities.map((f) => [f.id, f])), [facilities]);
  // OSM standard tiles by default (CARTO basemaps now need a key); dark mode dims them with a CSS filter.
  const tiles = process.env.NEXT_PUBLIC_MAP_TILES ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  const fitPoints: [number, number][] = [];
  for (const c of cases) {
    const o = byId[c.originId];
    if (o) fitPoints.push([o.lat, o.lng]);
    const d = c.destinationId ? byId[c.destinationId] : undefined;
    if (d) fitPoints.push([d.lat, d.lng]);
    c.route?.legs.forEach((l) => fitPoints.push([l.to_point.lat, l.to_point.lng]));
  }

  return (
    <div style={{ height }} className={`w-full overflow-hidden rounded-[.75rem] border-[1px] border-border ${dark ? "atoll-map-dark" : ""}`}>
      <MapContainer center={[3.2, 73.2]} zoom={6} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          url={tiles}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {fit && <FitBounds points={fitPoints} />}
        {facilities.map((f) => {
          const s = TYPE_STYLE[f.type] ?? TYPE_STYLE.health_centre;
          return (
            <CircleMarker
              key={f.id}
              center={[f.lat, f.lng]}
              radius={s.radius}
              pathOptions={{ color: s.color, fillColor: s.color, fillOpacity: 0.85, weight: 1 }}
            >
              <Tooltip>{f.name}</Tooltip>
            </CircleMarker>
          );
        })}
        {cases.map((c) => {
          const o = byId[c.originId];
          const d = c.destinationId ? byId[c.destinationId] : undefined;
          const trail = c.track?.positions.map((p) => [p.lat, p.lng] as [number, number]) ?? [];
          const live = c.track?.transport.position;
          const legIdx = c.track?.transport.current_leg_index ?? 0;
          const liveMode = c.route?.legs[legIdx]?.mode;
          return (
            <Fragment key={c.id}>
              {c.route?.legs.map((leg, i) => (
                <Polyline
                  key={i}
                  positions={[
                    [leg.from_point.lat, leg.from_point.lng],
                    [leg.to_point.lat, leg.to_point.lng],
                  ]}
                  pathOptions={{ color: MODE_COLOR[leg.mode], weight: c.highlight ? 4 : 3, dashArray: "8 8", opacity: 0.9 }}
                >
                  <Tooltip sticky>{MODE_LABEL[leg.mode]}</Tooltip>
                </Polyline>
              ))}
              {trail.length > 1 && <Polyline positions={trail} pathOptions={{ color: "#0e7c86", weight: 3, opacity: 0.6 }} />}
              {o && (
                <CircleMarker center={[o.lat, o.lng]} radius={11} pathOptions={{ color: "#d92d20", weight: 3, fillOpacity: 0 }}>
                  <Tooltip permanent={c.highlight} direction="right">
                    {c.label} · origin
                  </Tooltip>
                </CircleMarker>
              )}
              {d && (
                <CircleMarker center={[d.lat, d.lng]} radius={12} pathOptions={{ color: "#0e7c86", weight: 3, fillOpacity: 0 }}>
                  <Tooltip>Destination: {d.name}</Tooltip>
                </CircleMarker>
              )}
              {live && c.track?.transport.status !== "none" && (
                <LiveMarker
                  lat={live.lat}
                  lng={live.lng}
                  color={liveMode ? MODE_COLOR[liveMode] : "#0e7c86"}
                  label={`${c.label} · ${liveMode ? MODE_LABEL[liveMode] : ""} · ${c.track?.transport.status}`}
                />
              )}
            </Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
}
