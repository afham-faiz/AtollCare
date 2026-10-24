// F-M1.8 Read-only shared case view (family link)
import SharedCaseClient from "./SharedCaseClient";

export const metadata = { title: "Case status" };

export default async function ({ params }: PageProps<"/case/[caseId]">) {
  const { caseId } = await params;
  return <SharedCaseClient caseId={caseId} />;
}
