// F-M4.2 Dispatch · F-M4.3 live map · F-M4.5 arrival · F-M4.8 crew brief
import TransportCaseClient from "./TransportCaseClient";

export const metadata = { title: "Dispatch" };

export default async function ({ params }: PageProps<"/transport/[caseId]">) {
  const { caseId } = await params;
  return <TransportCaseClient caseId={caseId} />;
}
