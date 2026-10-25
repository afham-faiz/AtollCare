// Home: the three places someone can be in a transfer, with what's live in each. Every screen's logo leads back here.
"use client";

import { ArrowUpRight, BarChart3, Building2, Ship, Smartphone } from "lucide-react";
import Link from "next/link";

import { useMeta, useTransfers } from "@/lib/swr";

import styles from "./Home.module.scss";

export default function () {
  const { data: meta } = useMeta();
  const { data: live } = useTransfers("preparing,pending,accepted");
  const moving = live?.length ?? 0;
  const waiting = live?.filter((t) => t.status === "pending").length ?? 0;
  const coming = live?.filter((t) => t.status !== "preparing").length ?? 0;
  const places = [
    {
      href: "/pre-arrival",
      icon: Smartphone,
      who: "With the patient",
      title: "Pre-arrival",
      text: "Film them and say what happened. Presage measures heart and breathing rate from the phone, before anyone moves.",
      foot: "Open it on a phone",
    },
    {
      href: "/crew",
      icon: Ship,
      who: "In the boat",
      title: "Crew",
      text: "Contactless vitals from the camera, notes by voice, and the handoff sent ahead.",
      foot: moving ? `${moving} in progress` : "No transfers in progress",
    },
    {
      href: "/hospital",
      icon: Building2,
      who: "At the hospital",
      title: "Hospital",
      text: "Who is coming, what was measured on the way, and when they'll arrive.",
      foot: waiting ? `${waiting} waiting for a response` : coming ? `${coming} on the way` : "Nothing on the way",
    },
  ];

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <h1 className={styles.title}>The patient&apos;s story arrives before the patient does</h1>
        <p className={styles.lede}>
          Contactless vitals, voice notes and a handoff the hospital reads before the boat lands
          {meta ? ` · ${meta.region.name}` : ""}
        </p>
      </header>

      <nav className={styles.places} aria-label="Where are you?">
        {places.map(({ href, icon: Icon, who, title, text, foot }) => (
          <Link key={href} href={href} className={`card ${styles.place}`}>
            <span className={styles.placeTop}>
              <span className={styles.placeIcon}>
                <Icon size={22} strokeWidth={1.75} />
              </span>
              <ArrowUpRight size={20} strokeWidth={1.75} className={styles.placeArrow} />
            </span>
            <span className={styles.placeWho}>{who}</span>
            <span className={styles.placeTitle}>{title}</span>
            <span className={styles.placeText}>{text}</span>
            <span className={styles.placeFoot}>{foot}</span>
          </Link>
        ))}
      </nav>

      <Link href="/insights" className={styles.insights}>
        <BarChart3 size={18} strokeWidth={1.75} /> Network insights
      </Link>
    </div>
  );
}
