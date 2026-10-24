// F-M4.1 Dispatch board · F-M4.3 live map · F-M4.6 asset roster · F-M4.7 weather banner
import TransportClient from "./TransportClient";

export const metadata = { title: "Transport" };

export default async function () {
  return <TransportClient />;
}
