import PreArrivalStartClient from "./PreArrivalStartClient";

export const metadata = { title: "Before you arrive" };

// ?centre=<facility id>: a QR code at the health centre opens the page already pointed at it
export default async function ({ searchParams }: { searchParams: Promise<{ centre?: string }> }) {
  const { centre } = await searchParams;
  return <PreArrivalStartClient centre={centre} />;
}
