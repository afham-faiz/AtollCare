import HospitalClient from "../HospitalClient";

export const metadata = { title: "Incoming transfer" };

export default async function ({ params }: PageProps<"/hospital/[transferId]">) {
  const { transferId } = await params;
  return <HospitalClient transferId={transferId} />;
}
