import CrewClient from "./CrewClient";

export const metadata = { title: "Crew monitor" };

export default async function ({ params }: PageProps<"/crew/[transferId]">) {
  const { transferId } = await params;
  return <CrewClient transferId={transferId} />;
}
